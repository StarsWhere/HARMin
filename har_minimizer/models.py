from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, MutableMapping, Optional


@dataclass
class RequestData:
    """从 HAR 请求条目中提取的结构化信息。"""

    index: int
    method: str
    url: str
    path: str
    query: Dict[str, Any]
    headers: List[Dict[str, str]]
    body_text: Optional[str]
    mime_type: Optional[str]
    raw_entry: Dict[str, Any]

    def header_dict(self) -> Dict[str, str]:
        return {h["name"].lower(): h.get("value", "") for h in self.headers}


@dataclass
class ResponseSnapshot:
    status_code: Optional[int]
    body: Optional[str]
    error: Optional[str]
    elapsed: float
    headers: MutableMapping[str, str] = field(default_factory=dict)

    @property
    def length(self) -> int:
        if self.body is None:
            return 0
        return len(self.body)

    def ok(self) -> bool:
        return self.error is None and self.status_code is not None


@dataclass
class MinimizationResult:
    headers: List[Dict[str, str]]
    body_text: Optional[str]
    response: Optional[ResponseSnapshot]
    matched: bool
    header_candidates: int
    body_candidates: int
    minimized_headers: int
    minimized_body_fields: int


@dataclass
class ReportEntry:
    index: int
    method: str
    url: str
    path: str
    query: Dict[str, Any]
    baseline_status: Optional[int]
    baseline_length: int
    final_status: Optional[int]
    final_length: int
    matched: bool
    header_counts: Dict[str, int]
    body_counts: Dict[str, int]
    minimized_headers: List[Dict[str, str]]
    minimized_body: Optional[str]
    error: Optional[str] = None


@dataclass
class ProcessedRequest:
    request: RequestData
    baseline: ResponseSnapshot
    result: MinimizationResult
