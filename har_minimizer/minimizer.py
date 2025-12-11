from __future__ import annotations

import json
import logging
import math
import re
from copy import deepcopy
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlencode, parse_qsl

from .config import Config
from .http_client import HttpClient
from .models import MinimizationResult, RequestData, ResponseSnapshot
from .comparator import ResponseComparator


logger = logging.getLogger(__name__)


def _headers_list_to_dict(headers: Sequence[Dict[str, str]]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for header in headers:
        name = header.get("name")
        if not name:
            continue
        result[name] = header.get("value", "")
    return result


def resolve_body_kind(request: RequestData, mode: str) -> str:
    mime = (request.mime_type or "").lower()
    if mode == "auto":
        if "json" in mime:
            return "json"
        if "x-www-form-urlencoded" in mime:
            return "form"
        return "raw"
    return mode


def _parse_body(request: RequestData, mode: str) -> Tuple[str, Optional[Dict[str, str]]]:
    body = request.body_text or ""
    kind = resolve_body_kind(request, mode)
    if kind == "json":
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            return "raw", None
        if isinstance(parsed, dict):
            return "json", {k: parsed[k] for k in parsed}
        return "raw", None
    if kind == "form":
        pairs = dict(parse_qsl(body, keep_blank_values=True))
        return "form", pairs
    return "raw", None


def _build_body_text(kind: str, data: Optional[Dict[str, str]]) -> Optional[str]:
    if data is None:
        return None
    if kind == "json":
        return json.dumps(data, separators=(",", ":"))
    if kind == "form":
        return urlencode(data)
    return None


def count_body_fields(kind: str, body_text: Optional[str]) -> int:
    if not body_text:
        return 0
    if kind == "json":
        try:
            parsed = json.loads(body_text)
        except json.JSONDecodeError:
            return 0
        if isinstance(parsed, dict):
            return len(parsed)
        return 0
    if kind == "form":
        return len(parse_qsl(body_text, keep_blank_values=True))
    return 0


def _ddmin(items: Sequence, test_func, max_tests: Optional[int]) -> Tuple[List, int]:
    collection = list(items)
    if not collection:
        return [], 0
    if max_tests is not None and max_tests <= 0:
        return collection, 0
    n = 2
    tests = 0
    while len(collection) >= 1:
        subset_size = math.ceil(len(collection) / n)
        start = 0
        removed = False
        while start < len(collection):
            if max_tests is not None and tests >= max_tests:
                return collection, tests
            subset = collection[start : start + subset_size]
            remainder = collection[:start] + collection[start + subset_size :]
            tests += 1
            if test_func(remainder):
                collection = remainder
                n = max(n - 1, 2)
                removed = True
                break
            start += subset_size
        if not removed:
            if n >= len(collection):
                break
            n = min(len(collection), n * 2)
    return collection, tests


class RequestMinimizer:
    def __init__(self, config: Config, client: HttpClient, comparator: ResponseComparator):
        self.config = config
        self.client = client
        self.comparator = comparator

    def minimize(self, request: RequestData) -> Tuple[Optional[ResponseSnapshot], MinimizationResult]:
        logger.info("正在处理请求 #%s %s", request.index, request.url)
        original_headers = deepcopy(request.headers)
        base_headers_dict = _headers_list_to_dict(original_headers)
        baseline = self.client.send(request, base_headers_dict, request.body_text)
        if not baseline.ok():
            logger.warning("请求 %s 的基线执行失败：%s", request.index, baseline.error)
            result = MinimizationResult(
                headers=original_headers,
                body_text=request.body_text,
                response=baseline,
                matched=False,
                header_candidates=len(original_headers),
                body_candidates=0,
                minimized_headers=len(original_headers),
                minimized_body_fields=0,
            )
            return baseline, result

        remaining_tests = self.config.max_rounds_per_request
        body_kind = resolve_body_kind(request, self.config.minimization.body.body_type)
        headers_state = original_headers
        header_candidates = 0
        best_header_combo = (headers_state, baseline)

        if "headers" in self.config.minimization.order and self.config.minimization.headers.enabled:
            headers_state, header_candidates, best_header_combo, tests = self._minimize_headers(
                request,
                headers_state,
                baseline,
                max(0, remaining_tests),
            )
            remaining_tests = max(0, remaining_tests - tests)

        body_state = request.body_text
        body_candidates = 0
        best_body_combo = (body_state, best_header_combo[1])
        if "body" in self.config.minimization.order and self.config.minimization.body.enabled:
            (
                body_state,
                body_candidates,
                best_body_combo,
                tests,
            ) = self._minimize_body(request, headers_state, baseline, max(0, remaining_tests))
            remaining_tests = max(0, remaining_tests - tests)

        final_headers = headers_state
        final_body = body_state
        final_response = self.client.send(request, _headers_list_to_dict(final_headers), final_body)
        matched = self.comparator.equivalent(baseline, final_response)
        if not matched:
            logger.info("最终校验失败，正在尝试回退策略（请求 %s）", request.index)
            fallback_headers, fallback_response = best_header_combo
            fallback_body, fallback_body_response = best_body_combo
            if fallback_body_response and self.comparator.equivalent(baseline, fallback_body_response):
                final_body = fallback_body
                final_headers = final_headers
                final_response = fallback_body_response
                matched = True
            elif fallback_response and self.comparator.equivalent(baseline, fallback_response):
                final_headers = fallback_headers
                final_body = request.body_text
                final_response = fallback_response
                matched = True
            else:
                final_headers = original_headers
                final_body = request.body_text
                final_response = baseline
                matched = True  # 回退至基线请求
        # 额外尝试将剩余字段值置空
        if matched and self.config.minimization.body.try_blank_values:
            blank_attempt = self._try_blank_body_values(
                request=request,
                headers=final_headers,
                baseline=baseline,
                body_kind=body_kind,
                current_body=final_body,
            )
            if blank_attempt is not None:
                final_body, final_response = blank_attempt
                matched = self.comparator.equivalent(baseline, final_response)
        final_body_fields = count_body_fields(body_kind, final_body)
        result = MinimizationResult(
            headers=final_headers,
            body_text=final_body,
            response=final_response,
            matched=matched,
            header_candidates=header_candidates,
            body_candidates=body_candidates,
            minimized_headers=len(final_headers),
            minimized_body_fields=final_body_fields,
        )
        return baseline, result

    def _minimize_headers(
        self,
        request: RequestData,
        current_headers: List[Dict[str, str]],
        baseline: ResponseSnapshot,
        max_tests: int,
    ) -> Tuple[List[Dict[str, str]], int, Tuple[List[Dict[str, str]], ResponseSnapshot], int]:
        cfg = self.config.minimization.headers
        protected = {h.lower() for h in cfg.protected}
        ignored = {h.lower() for h in cfg.ignore}
        regexes = [re.compile(pattern, re.IGNORECASE) for pattern in cfg.candidate_regex]
        candidates: List[Dict[str, str]] = []
        fixed: List[Dict[str, str]] = []
        for header in current_headers:
            name = header.get("name", "").lower()
            if name in protected or name in ignored:
                fixed.append(header)
                continue
            if regexes and not any(r.search(name) for r in regexes):
                fixed.append(header)
                continue
            candidates.append(header)
        if not candidates:
            return current_headers, 0, (current_headers, baseline), 0

        best_state = (current_headers, baseline)

        def test(active_headers: List[Dict[str, str]]) -> bool:
            nonlocal best_state
            headers = fixed + active_headers
            response = self.client.send(request, _headers_list_to_dict(headers), request.body_text)
            if self.comparator.equivalent(baseline, response):
                best_state = (headers, response)
                return True
            return False

        minimized, tests = _ddmin(candidates, test, max_tests)
        minimized_headers = fixed + minimized
        if best_state[0] != minimized_headers:
            minimized_headers = best_state[0]
        return minimized_headers, len(candidates), best_state, tests

    def _minimize_body(
        self,
        request: RequestData,
        headers: List[Dict[str, str]],
        baseline: ResponseSnapshot,
        max_tests: int,
    ) -> Tuple[Optional[str], int, Tuple[Optional[str], ResponseSnapshot], int]:
        cfg = self.config.minimization.body
        kind, parsed = _parse_body(request, cfg.body_type)
        if parsed is None or not parsed:
            return request.body_text, 0, (request.body_text, baseline), 0
        protected = set(cfg.protected_keys)
        only = set(cfg.only_keys) if cfg.only_keys else None
        candidates = {k: v for k, v in parsed.items() if k not in protected and (not only or k in only)}
        if not candidates:
            return request.body_text, 0, (request.body_text, baseline), 0

        fixed = {k: v for k, v in parsed.items() if k not in candidates}
        candidate_items = list(candidates.items())
        best_state = (request.body_text, baseline)

        candidate_keys = [k for k, _ in candidate_items]

        def build_body(active_items: List[Tuple[str, str]]) -> Dict[str, str]:
            merged = dict(fixed)
            active_lookup = {k: v for k, v in active_items}
            for key, value in active_lookup.items():
                merged[key] = value
            if not cfg.treat_empty_as_absent:
                for key in candidate_keys:
                    if key not in active_lookup:
                        merged[key] = ""
            return merged

        def test(active_items: List[Tuple[str, str]]) -> bool:
            nonlocal best_state
            body_map = build_body(active_items)
            body_text = _build_body_text(kind, body_map)
            response = self.client.send(request, _headers_list_to_dict(headers), body_text)
            if self.comparator.equivalent(baseline, response):
                best_state = (body_text, response)
                return True
            return False

        minimized, tests = _ddmin(candidate_items, test, max_tests)
        final_body, _ = best_state
        if final_body is None:
            final_body = _build_body_text(kind, build_body(minimized))
        return final_body, len(candidate_items), best_state, tests

    def _try_blank_body_values(
        self,
        request: RequestData,
        headers: List[Dict[str, str]],
        baseline: ResponseSnapshot,
        body_kind: str,
        current_body: Optional[str],
    ) -> Optional[Tuple[Optional[str], ResponseSnapshot]]:
        if body_kind not in {"json", "form"} or not current_body:
            return None
        cfg = self.config.minimization.body
        try:
            if body_kind == "json":
                parsed = json.loads(current_body) if current_body else {}
                if not isinstance(parsed, dict):
                    return None
            else:
                parsed = dict(parse_qsl(current_body, keep_blank_values=True))
        except json.JSONDecodeError:
            return None
        protected = set(cfg.protected_keys)
        only = set(cfg.only_keys) if cfg.only_keys else None
        candidate_keys = [k for k in parsed.keys() if k not in protected and (not only or k in only)]
        if not candidate_keys:
            return None
        best_state: Tuple[Optional[str], Optional[ResponseSnapshot]] = (current_body, None)

        def build_body(active_keys: List[str]) -> Dict[str, str]:
            # active_keys = 保留原值的键，其余置空
            body_map = dict(parsed)
            keep = set(active_keys)
            for key in candidate_keys:
                if key not in keep:
                    body_map[key] = ""
            return body_map

        def test(active_keys: List[str]) -> bool:
            nonlocal best_state
            body_map = build_body(active_keys)
            body_text = _build_body_text(body_kind, body_map)
            response = self.client.send(request, _headers_list_to_dict(headers), body_text)
            if self.comparator.equivalent(baseline, response):
                best_state = (body_text, response)
                return True
            return False

        minimized_keep, _ = _ddmin(candidate_keys, test, None)
        body_map = build_body(minimized_keep)
        body_text = _build_body_text(body_kind, body_map)
        response = self.client.send(request, _headers_list_to_dict(headers), body_text)
        if self.comparator.equivalent(baseline, response):
            best_state = (body_text, response)
        if best_state[1] and best_state[0] != current_body:
            return best_state  # 返回更精简且校验通过的版本
        return None
