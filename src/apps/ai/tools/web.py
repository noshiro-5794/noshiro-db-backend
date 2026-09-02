"""Web evidence tools for enrichment and user-facing agents.

These tools are read-only and bound: search delegates to a configured provider
(Tavily), fetch caps response size, and every result is content-hashed so it can
be linked to an ``AIClaim`` as durable evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from urllib.parse import urlparse

import httpx
from django.conf import settings

from shared.outbound import httpx_client_kwargs

from .registry import ToolDefinition, ToolInput, ToolOutput, ToolRegistry


class WebSearchInput(ToolInput):
    query: str
    max_results: int = 5
    language: str = ""


class WebSearchOutput(ToolOutput):
    available: bool
    results: list[dict[str, Any]]


class WebFetchInput(ToolInput):
    url: str
    max_bytes: int = 65536


class WebFetchOutput(ToolOutput):
    url: str
    title: str = ""
    text: str = ""
    byte_size: int = 0
    truncated: bool = False


class WebSearchTool:
    """Tavily-backed search with a hard fail-open when no key is configured."""

    name = "web.search"
    version = "1.0.0"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                **httpx_client_kwargs(
                    base_url=settings.WEB_SEARCH_BASE_URL,
                    timeout=settings.WEB_SEARCH_TIMEOUT,
                    follow_redirects=True,
                )
            )
        return self._client

    def execute(self, value: WebSearchInput) -> WebSearchOutput:
        if settings.WEB_SEARCH_PROVIDER != "tavily" or not settings.WEB_SEARCH_API_KEY:
            return WebSearchOutput(available=False, results=[])
        payload = {
            "api_key": settings.WEB_SEARCH_API_KEY,
            "query": value.query,
            "max_results": max(1, min(value.max_results, 10)),
            "include_answer": False,
            "include_raw_content": False,
        }
        if value.language:
            payload["search_depth"] = "basic"
        response = self.client.post("/search", json=payload)
        response.raise_for_status()
        data = response.json()
        results = [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", ""),
                "score": item.get("score"),
            }
            for item in data.get("results") or []
            if isinstance(item, dict) and item.get("url")
        ]
        return WebSearchOutput(available=True, results=results)


class WebFetchTool:
    """Fetch one page with a hard size cap and naive text extraction."""

    name = "web.fetch"
    version = "1.0.0"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                **httpx_client_kwargs(
                    headers={"User-Agent": "NoshiroDBHarness/1.0"},
                    timeout=settings.WEB_FETCH_TIMEOUT,
                    follow_redirects=True,
                )
            )
        return self._client

    def execute(self, value: WebFetchInput) -> WebFetchOutput:
        parsed = urlparse(value.url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("web.fetch requires an absolute http(s) URL.")
        max_bytes = max(1024, min(value.max_bytes, settings.WEB_FETCH_MAX_BYTES))
        with self.client.stream("GET", value.url) as response:
            response.raise_for_status()
            chunks: list[bytes] = []
            size = 0
            truncated = False
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > max_bytes:
                    chunks.append(chunk[: max(0, max_bytes - (size - len(chunk)))])
                    truncated = True
                    break
                chunks.append(chunk)
        raw = b"".join(chunks)
        text = _extract_text(raw)
        return WebFetchOutput(
            url=value.url,
            title=_extract_title(raw),
            text=text,
            byte_size=len(raw),
            truncated=truncated,
        )


def _extract_title(raw: bytes) -> str:
    head = raw[:8192].decode("utf-8", errors="ignore")
    match = re.search(r"<title[^>]*>(.*?)</title>", head, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip()[:512]


def _extract_text(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="ignore")
    text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"&(?:amp|lt|gt|quot|#39);", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:16000]


web_search_tool = WebSearchTool()
web_fetch_tool = WebFetchTool()


def register_web_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolDefinition(
            name="web.search",
            description="Search the public web for factual ACG metadata.",
            input_model=WebSearchInput,
            output_model=WebSearchOutput,
            handler=web_search_tool.execute,
            version=WebSearchTool.version,
            records_evidence=True,
            timeout_seconds=30,
            rate_limit_per_minute=10,
        )
    )
    registry.register(
        ToolDefinition(
            name="web.fetch",
            description="Fetch and extract text from one public web page.",
            input_model=WebFetchInput,
            output_model=WebFetchOutput,
            handler=web_fetch_tool.execute,
            version=WebFetchTool.version,
            records_evidence=True,
            timeout_seconds=30,
            rate_limit_per_minute=20,
        )
    )


def content_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, default=str
    ).encode()
    return hashlib.sha256(encoded).hexdigest()
