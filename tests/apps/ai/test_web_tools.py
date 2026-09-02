from unittest.mock import MagicMock, Mock

import pytest
from django.test import override_settings

from apps.ai.tools.registry import create_default_tool_registry
from apps.ai.tools.web import WebFetchInput, WebFetchTool, WebSearchInput, WebSearchTool


@override_settings(WEB_SEARCH_PROVIDER="none", WEB_SEARCH_API_KEY=None)
def test_web_search_fails_open_without_provider() -> None:
    result = WebSearchTool().execute(WebSearchInput(query="Fate/stay night"))

    assert result.available is False
    assert result.results == []


@override_settings(
    WEB_SEARCH_PROVIDER="tavily",
    WEB_SEARCH_API_KEY="test-key",
    WEB_SEARCH_BASE_URL="https://api.tavily.test",
)
def test_web_search_parses_tavily_results() -> None:
    http_client = Mock()
    http_client.post.return_value.json.return_value = {
        "results": [
            {
                "title": "Fate/stay night",
                "url": "https://example.org/fate",
                "content": "summary",
            },
            {"url": ""},
            {"title": "Broken", "content": "no url"},
        ]
    }
    tool = WebSearchTool(http_client)

    result = tool.execute(WebSearchInput(query="Fate/stay night", max_results=10))

    assert result.available is True
    assert result.results == [
        {
            "title": "Fate/stay night",
            "url": "https://example.org/fate",
            "content": "summary",
            "score": None,
        }
    ]
    payload = http_client.post.call_args.kwargs["json"]
    assert payload["query"] == "Fate/stay night"
    assert payload["max_results"] == 10


def test_web_fetch_caps_size_and_extracts_text() -> None:
    http_client = MagicMock()
    stream = http_client.stream.return_value.__enter__.return_value
    stream.iter_bytes.return_value = [
        b"<html><head><title>Hello</title></head><body><script>x</script><p>AC G text</p></body></html>",
        b" more bytes",
    ]

    result = WebFetchTool(http_client).execute(
        WebFetchInput(url="https://example.org/page", max_bytes=65536)
    )

    assert result.url == "https://example.org/page"
    assert result.title == "Hello"
    assert "AC G text more bytes" in result.text
    assert result.truncated is False


def test_web_fetch_rejects_non_http_urls() -> None:
    with pytest.raises(ValueError, match="absolute http"):
        WebFetchTool(Mock()).execute(WebFetchInput(url="file:///etc/passwd"))


def test_default_registry_registers_web_tools() -> None:
    registry = create_default_tool_registry()

    search = registry.get("web.search")
    fetch = registry.get("web.fetch")

    assert search.records_evidence is True
    assert fetch.records_evidence is True
    assert search.permission == "knowledge:read"
