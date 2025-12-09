from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Dict, Iterable, List

from .models import MinimizationResult, ProcessedRequest, ReportEntry


class ReportWriter:
    def __init__(self, path: str):
        self.path = Path(path)

    def write(self, entries: Iterable[ReportEntry]) -> None:
        data = [self._to_dict(entry) for entry in entries]
        if self.path.parent and not self.path.parent.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _to_dict(self, entry: ReportEntry) -> Dict:
        return {
            "index": entry.index,
            "method": entry.method,
            "url": entry.url,
            "path": entry.path,
            "query": entry.query,
            "baseline": {
                "status": entry.baseline_status,
                "length": entry.baseline_length,
            },
            "final": {
                "status": entry.final_status,
                "length": entry.final_length,
            },
            "matched_baseline": entry.matched,
            "headers": entry.header_counts,
            "body": entry.body_counts,
            "minimized_headers": entry.minimized_headers,
            "minimized_body": entry.minimized_body,
            "error": entry.error,
        }


class HarExporter:
    def __init__(self, raw_har: Dict):
        self.raw = deepcopy(raw_har)

    def apply(self, processed: Iterable[ProcessedRequest], include_metadata: bool = True) -> None:
        entries = self.raw.get("log", {}).get("entries", [])
        for item in processed:
            if not item.result.matched:
                continue
            index = item.request.index
            if index >= len(entries):
                continue
            entry = entries[index]
            request_block = entry.setdefault("request", {})
            request_block["headers"] = deepcopy(item.result.headers)
            if item.result.body_text is not None:
                post_data = request_block.setdefault("postData", {})
                post_data["text"] = item.result.body_text
                if item.request.mime_type:
                    post_data.setdefault("mimeType", item.request.mime_type)
            elif request_block.get("postData") and "text" in request_block["postData"]:
                request_block["postData"]["text"] = item.request.body_text or ""
            if include_metadata:
                meta = entry.setdefault("_minimized", {})
                meta.update(
                    {
                        "original_header_count": len(item.request.headers),
                        "final_header_count": len(item.result.headers),
                        "header_candidates": item.result.header_candidates,
                        "body_candidates": item.result.body_candidates,
                        "matched": item.result.matched,
                    }
                )

    def write(self, path: str) -> None:
        target = Path(path)
        if target.parent and not target.parent.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.raw, indent=2, ensure_ascii=False), encoding="utf-8")
