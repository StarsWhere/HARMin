from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import yaml


@dataclass
class RateLimitConfig:
    requests_per_second: Optional[float] = None
    max_concurrent: int = 1


@dataclass
class ClientConfig:
    timeout: float = 20.0
    proxies: Dict[str, str] = field(default_factory=dict)
    verify_tls: bool = True
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)


@dataclass
class HeaderMinConfig:
    enabled: bool = True
    protected: List[str] = field(default_factory=lambda: ["host", "cookie"])
    ignore: List[str] = field(default_factory=lambda: ["content-length"])
    candidate_regex: List[str] = field(default_factory=list)


@dataclass
class BodyMinConfig:
    enabled: bool = True
    body_type: str = "auto"  # 可选 auto|json|form|raw
    protected_keys: List[str] = field(default_factory=list)
    only_keys: List[str] = field(default_factory=list)
    treat_empty_as_absent: bool = True


@dataclass
class MinimizationConfig:
    headers: HeaderMinConfig = field(default_factory=HeaderMinConfig)
    body: BodyMinConfig = field(default_factory=BodyMinConfig)
    order: List[str] = field(default_factory=lambda: ["headers", "body"])


@dataclass
class ComparatorConfig:
    status_code: bool = True
    length_check: bool = False
    length_tolerance: float = 0.05
    need_all: List[str] = field(default_factory=list)
    need_any: List[str] = field(default_factory=list)
    regex: List[str] = field(default_factory=list)
    logic: str = "AND"  # AND 或 OR


@dataclass
class FilterConfig:
    methods: List[str] = field(default_factory=list)
    hosts: List[str] = field(default_factory=list)
    url_regex: List[str] = field(default_factory=list)
    index_range: Optional[Tuple[int, int]] = None


@dataclass
class ScopeConfig:
    include_urls: List[str] = field(default_factory=list)
    include_regex: List[str] = field(default_factory=list)


@dataclass
class Config:
    input_har: str
    report_path: str = "min_report.json"
    output_har: Optional[str] = None
    filters: FilterConfig = field(default_factory=FilterConfig)
    scope: ScopeConfig = field(default_factory=ScopeConfig)
    comparator: ComparatorConfig = field(default_factory=ComparatorConfig)
    minimization: MinimizationConfig = field(default_factory=MinimizationConfig)
    client: ClientConfig = field(default_factory=ClientConfig)
    max_rounds_per_request: int = 200
    update_har_metadata: bool = True


def _load_raw_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        content = handle.read()
    if path.endswith(('.yaml', '.yml')):
        return yaml.safe_load(content) or {}
    if path.endswith('.json'):
        return json.loads(content)
    # 默认尝试以 YAML 格式解析
    return yaml.safe_load(content) or {}


def _merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(a)
    for key, value in b.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: str, overrides: Optional[Dict[str, Any]] = None) -> Config:
    raw = _load_raw_config(path)
    overrides = overrides or {}
    raw = _merge(raw, overrides)
    if "input_har" not in raw:
        raise ValueError("配置文件必须包含 input_har 字段")
    return Config(
        input_har=os.path.abspath(raw["input_har"]),
        report_path=os.path.abspath(raw.get("report_path", "min_report.json")),
        output_har=os.path.abspath(raw["output_har"]) if raw.get("output_har") else None,
        filters=FilterConfig(**raw.get("filters", {})),
        scope=ScopeConfig(**raw.get("scope", {})),
        comparator=ComparatorConfig(**raw.get("comparator", {})),
        minimization=_build_min_config(raw.get("minimization", {})),
        client=_build_client_config(raw.get("client", {})),
        max_rounds_per_request=int(raw.get("max_rounds_per_request", 200)),
        update_har_metadata=bool(raw.get("update_har_metadata", True)),
    )


def _build_min_config(data: Dict[str, Any]) -> MinimizationConfig:
    return MinimizationConfig(
        headers=HeaderMinConfig(**data.get("headers", {})),
        body=BodyMinConfig(**data.get("body", {})),
        order=data.get("order", ["headers", "body"]),
    )


def _build_client_config(data: Dict[str, Any]) -> ClientConfig:
    rate = data.get("rate_limit", {})
    return ClientConfig(
        timeout=float(data.get("timeout", 20.0)),
        proxies=data.get("proxies", {}),
        verify_tls=bool(data.get("verify_tls", True)),
        rate_limit=RateLimitConfig(
            requests_per_second=rate.get("requests_per_second"),
            max_concurrent=int(rate.get("max_concurrent", 1)),
        ),
    )
