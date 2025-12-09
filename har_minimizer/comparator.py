from __future__ import annotations

import math
import re
from typing import List

from .config import ComparatorConfig
from .models import ResponseSnapshot


class ResponseComparator:
    def __init__(self, config: ComparatorConfig):
        self.config = config
        self._regex = [re.compile(expr, re.MULTILINE) for expr in config.regex]

    def equivalent(self, baseline: ResponseSnapshot, candidate: ResponseSnapshot) -> bool:
        if not baseline.ok() or not candidate.ok():
            return False
        checks = [
            (self.config.status_code, self._status_equal(baseline, candidate)),
            (self.config.length_check, self._length_within(baseline, candidate)),
            (bool(self.config.need_all), self._need_all(candidate)),
            (bool(self.config.need_any), self._need_any(candidate)),
            (bool(self._regex), self._regex_match(candidate)),
        ]
        active = [result for enabled, result in checks if enabled]
        if not active:
            return True
        if self.config.logic.upper() == "OR":
            return any(active)
        return all(active)

    def _status_equal(self, base: ResponseSnapshot, cand: ResponseSnapshot) -> bool:
        return base.status_code == cand.status_code

    def _length_within(self, base: ResponseSnapshot, cand: ResponseSnapshot) -> bool:
        if base.length == 0:
            return cand.length == 0
        delta = abs(base.length - cand.length) / base.length
        return delta <= self.config.length_tolerance

    def _need_all(self, cand: ResponseSnapshot) -> bool:
        if cand.body is None:
            return False
        return all(token in cand.body for token in self.config.need_all)

    def _need_any(self, cand: ResponseSnapshot) -> bool:
        if cand.body is None:
            return False
        return any(token in cand.body for token in self.config.need_any)

    def _regex_match(self, cand: ResponseSnapshot) -> bool:
        if cand.body is None:
            return False
        return all(pattern.search(cand.body) for pattern in self._regex)
