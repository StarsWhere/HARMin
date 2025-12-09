from __future__ import annotations

import logging
from typing import List

from .comparator import ResponseComparator
from .config import Config
from .filtering import RequestFilter
from .har_loader import HarLoader
from .http_client import HttpClient
from .minimizer import RequestMinimizer, count_body_fields, resolve_body_kind
from .models import MinimizationResult, ProcessedRequest, ReportEntry, RequestData, ResponseSnapshot
from .reporting import HarExporter, ReportWriter

logger = logging.getLogger(__name__)


class MinimizationOrchestrator:
    def __init__(self, config: Config):
        self.config = config
        self.loader = HarLoader(config.input_har)
        self.client = HttpClient(config.client)
        self.comparator = ResponseComparator(config.comparator)
        self.request_filter = RequestFilter(config.filters, config.scope)
        self.minimizer = RequestMinimizer(config, self.client, self.comparator)

    def run(self) -> List[ReportEntry]:
        entries = self.loader.load()
        filtered = self.request_filter.apply(entries)
        logger.info("共载入 %s 个请求，筛选后剩余 %s 个", len(entries), len(filtered))
        processed: List[ProcessedRequest] = []
        report_entries: List[ReportEntry] = []
        for entry in filtered:
            baseline, result = self.minimizer.minimize(entry.request)
            processed.append(ProcessedRequest(request=entry.request, baseline=baseline, result=result))
            report_entries.append(self._build_report_entry(entry.request, baseline, result))
        ReportWriter(self.config.report_path).write(report_entries)
        logger.info("最小化报告已写入 %s", self.config.report_path)
        if self.config.output_har:
            exporter = HarExporter(self.loader.get_raw())
            exporter.apply(processed, include_metadata=self.config.update_har_metadata)
            exporter.write(self.config.output_har)
            logger.info("更新后的 HAR 已写入 %s", self.config.output_har)
        return report_entries

    def _build_report_entry(
        self,
        request: RequestData,
        baseline: ResponseSnapshot,
        result: MinimizationResult,
    ) -> ReportEntry:
        body_kind = resolve_body_kind(request, self.config.minimization.body.body_type)
        original_body_fields = count_body_fields(body_kind, request.body_text)
        final_body_fields = count_body_fields(body_kind, result.body_text)
        error_message = None
        if not baseline.ok():
            error_message = baseline.error
        elif result.response and result.response.error:
            error_message = result.response.error
        return ReportEntry(
            index=request.index,
            method=request.method,
            url=request.url,
            path=request.path,
            query=request.query,
            baseline_status=baseline.status_code,
            baseline_length=baseline.length,
            final_status=result.response.status_code if result.response else None,
            final_length=result.response.length if result.response else 0,
            matched=result.matched,
            header_counts={
                "original": len(request.headers),
                "candidates": result.header_candidates,
                "final": len(result.headers),
            },
            body_counts={
                "original": original_body_fields,
                "candidates": result.body_candidates,
                "final": final_body_fields,
            },
            minimized_headers=result.headers,
            minimized_body=result.body_text,
            error=error_message,
        )
