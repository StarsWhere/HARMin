from __future__ import annotations

import re
from typing import Iterable, List

from .config import FilterConfig, ScopeConfig
from .har_loader import HarEntry


class RequestFilter:
    def __init__(self, filter_config: FilterConfig, scope_config: ScopeConfig):
        self.config = filter_config
        self.scope = scope_config
        self._url_regex = [re.compile(p) for p in filter_config.url_regex]
        self._scope_regex = [re.compile(p) for p in scope_config.include_regex]

    def apply(self, entries: Iterable[HarEntry]) -> List[HarEntry]:
        results: List[HarEntry] = []
        for entry in entries:
            if not self._matches_filter(entry):
                continue
            if not self._matches_scope(entry):
                continue
            results.append(entry)
        return results

    def _matches_filter(self, entry: HarEntry) -> bool:
        request = entry.request
        cfg = self.config
        if cfg.methods and request.method.upper() not in {m.upper() for m in cfg.methods}:
            return False
        if cfg.hosts:
            if request.path and request.url:
                host = re.sub(r"^https?://", "", request.url).split("/")[0]
            else:
                host = ""
            if host not in cfg.hosts:
                return False
        if cfg.url_regex and not any(r.search(request.url) for r in self._url_regex):
            return False
        if cfg.index_range:
            start, end = cfg.index_range
            if not (start <= entry.index <= end):
                return False
        return True

    def _matches_scope(self, entry: HarEntry) -> bool:
        request = entry.request
        if not (self.scope.include_urls or self.scope.include_regex):
            return True
        url_matches = request.url in set(self.scope.include_urls)
        regex_matches = any(r.search(request.url) for r in self._scope_regex)
        return url_matches or regex_matches
