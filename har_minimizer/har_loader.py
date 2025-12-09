from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse, parse_qs

from .models import RequestData


@dataclass
class HarEntry:
    index: int
    request: RequestData


class HarLoader:
    def __init__(self, path: str):
        self.path = Path(path)
        self.raw_data: Optional[Dict] = None

    def load(self) -> List[HarEntry]:
        with self.path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        self.raw_data = data
        entries = data.get("log", {}).get("entries", [])
        wrapped: List[HarEntry] = []
        for idx, entry in enumerate(entries):
            req = entry.get("request", {})
            headers = req.get("headers", [])
            parsed_url = urlparse(req.get("url", ""))
            query = {k: v[0] if len(v) == 1 else v for k, v in parse_qs(parsed_url.query).items()}
            request = RequestData(
                index=idx,
                method=req.get("method", "GET"),
                url=req.get("url", ""),
                path=parsed_url.path,
                query=query,
                headers=headers,
                body_text=(req.get("postData", {}) or {}).get("text"),
                mime_type=(req.get("postData", {}) or {}).get("mimeType"),
                raw_entry=entry,
            )
            wrapped.append(HarEntry(index=idx, request=request))
        return wrapped

    def get_raw(self) -> Dict:
        if self.raw_data is None:
            raise RuntimeError("HAR 内容尚未加载")
        return self.raw_data
