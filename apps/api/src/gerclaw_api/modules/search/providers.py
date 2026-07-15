"""Real AnySearch JSON-RPC and Tavily REST provider adapters."""

from __future__ import annotations

import re
import time
import uuid
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from gerclaw_api.metrics import SEARCH_PROVIDER_LATENCY, SEARCH_PROVIDER_REQUESTS
from gerclaw_api.modules.search.models import ProviderSearchResult, SearchDomain

_RESULT_HEADER = re.compile(r"(?m)^###\s+\d+\.\s+(.+?)\s*$")
_URL_LINE = re.compile(r"(?m)^-\s+\*\*URL\*\*:\s*(https?://\S+)\s*$")
_DATE = re.compile(
    r"\b(?:19|20)\d{2}[-/.](?:0?[1-9]|1[0-2])(?:[-/.](?:0?[1-9]|[12]\d|3[01]))?\b"
    r"|\b(?:January|February|March|April|May|June|July|August|September|October|November|"
    r"December)\s+(?:[1-9]|[12]\d|3[01]),?\s+(?:19|20)\d{2}\b",
    re.IGNORECASE,
)


class SearchProviderError(RuntimeError):
    """Safe provider failure that never includes query, response body, or credentials."""

    outcome: str = "unavailable"


class RetryableSearchProviderError(SearchProviderError):
    """Network, timeout, rate-limit, or server failure eligible for one retry."""


class SearchProviderTimeout(RetryableSearchProviderError):
    outcome = "timeout"


class SearchProviderNetworkError(RetryableSearchProviderError):
    outcome = "network_error"


class SearchProviderRateLimited(RetryableSearchProviderError):
    outcome = "rate_limited"


class SearchProviderUnavailable(RetryableSearchProviderError):
    outcome = "unavailable"


class SearchProviderRejected(SearchProviderError):
    outcome = "rejected"


class SearchProviderInvalidResponse(SearchProviderError):
    outcome = "invalid_response"


class _RPCText(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["text"]
    text: str = Field(min_length=1)


class _RPCResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    content: list[_RPCText] = Field(min_length=1)
    isError: bool = False


class _RPCError(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code: int | str | None = None
    message: str = Field(min_length=1)


class _RPCPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    jsonrpc: Literal["2.0"]
    id: str | int
    result: _RPCResult | None = None
    error: _RPCError | None = None


class _TavilyItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(min_length=1, max_length=2_000)
    url: str = Field(min_length=1, max_length=4_096)
    content: str = Field(min_length=1)
    published_date: str | None = None
    score: float | None = Field(default=None, ge=0, le=1)


class _TavilySearchPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    results: list[_TavilyItem]


class _TavilyExtractItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    raw_content: str = Field(min_length=1)


class _TavilyExtractPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    results: list[_TavilyExtractItem] = Field(min_length=1)


def _endpoint(base_url: str, suffix: str) -> str:
    normalized = base_url.rstrip("/")
    return normalized if normalized.endswith(suffix) else f"{normalized}{suffix}"


def _status_error(status_code: int) -> SearchProviderError:
    if status_code == 429:
        return SearchProviderRateLimited("search provider rate limited the request")
    if status_code >= 500:
        return SearchProviderUnavailable("search provider is temporarily unavailable")
    return SearchProviderRejected("search provider rejected the request")


def _record(provider: str, operation: str, outcome: str, started: float) -> None:
    SEARCH_PROVIDER_REQUESTS.labels(provider=provider, operation=operation, outcome=outcome).inc()
    SEARCH_PROVIDER_LATENCY.labels(provider=provider, operation=operation).observe(
        time.perf_counter() - started
    )


class AnySearchProvider:
    """AnySearch MCP-compatible JSON-RPC 2.0 adapter."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: SecretStr | None,
        timeout_seconds: float,
        max_response_bytes: int,
        max_content_characters: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        headers = {"Content-Type": "application/json"}
        if api_key is not None:
            headers["Authorization"] = f"Bearer {api_key.get_secret_value()}"
        self._client = httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(timeout_seconds),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=40),
            transport=transport,
        )
        self._url = _endpoint(base_url, "/mcp")
        self._max_response_bytes = max_response_bytes
        self._max_content_characters = max_content_characters

    async def _call(self, name: str, arguments: dict[str, Any]) -> str:
        started = time.perf_counter()
        outcome = "invalid_response"
        try:
            try:
                response = await self._client.post(
                    self._url,
                    json={
                        "jsonrpc": "2.0",
                        "id": f"gerclaw-{uuid.uuid4().hex}",
                        "method": "tools/call",
                        "params": {"name": name, "arguments": arguments},
                    },
                )
            except httpx.TimeoutException as error:
                outcome = "timeout"
                raise SearchProviderTimeout("AnySearch request timed out") from error
            except httpx.RequestError as error:
                outcome = "network_error"
                raise SearchProviderNetworkError("AnySearch network request failed") from error
            if response.status_code >= 400:
                provider_error = _status_error(response.status_code)
                outcome = provider_error.outcome
                raise provider_error
            if len(response.content) > self._max_response_bytes:
                raise SearchProviderInvalidResponse("AnySearch response exceeded the size limit")
            try:
                payload = _RPCPayload.model_validate(response.json())
            except (ValueError, ValidationError) as error:
                raise SearchProviderInvalidResponse(
                    "AnySearch returned an invalid JSON-RPC response"
                ) from error
            if payload.error is not None or payload.result is None or payload.result.isError:
                outcome = "rejected"
                raise SearchProviderRejected("AnySearch tool call failed")
            text = "\n".join(item.text for item in payload.result.content)
            if not text.strip() or len(text) > self._max_content_characters:
                raise SearchProviderInvalidResponse("AnySearch content is invalid")
            outcome = "success"
            return text
        finally:
            _record("anysearch", name, outcome, started)

    async def search(
        self,
        query: str,
        *,
        max_results: int,
        domain: SearchDomain,
    ) -> list[ProviderSearchResult]:
        arguments: dict[str, Any] = {"query": query, "max_results": max_results}
        if domain != "general":
            arguments["domain"] = domain
        text = await self._call("search", arguments)
        results = self._parse_search_markdown(text, max_results=max_results)
        if not results and not re.search(r"\b(?:0 results|no results)\b", text, re.IGNORECASE):
            raise SearchProviderInvalidResponse("AnySearch search results could not be parsed")
        return results

    @staticmethod
    def _parse_search_markdown(text: str, *, max_results: int) -> list[ProviderSearchResult]:
        headings = list(_RESULT_HEADER.finditer(text))
        results: list[ProviderSearchResult] = []
        for index, heading in enumerate(headings[:max_results]):
            end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
            body = text[heading.end() : end]
            url_match = _URL_LINE.search(body)
            if url_match is None:
                continue
            snippet_lines = [
                line.removeprefix("- ").strip()
                for line in body.splitlines()
                if line.strip() and _URL_LINE.fullmatch(line.strip()) is None
            ]
            snippet = " ".join(snippet_lines)[:4_000].strip()
            if not snippet:
                continue
            date_match = _DATE.search(snippet)
            try:
                result = ProviderSearchResult(
                    title=heading.group(1)[:512],
                    snippet=snippet,
                    url=url_match.group(1).rstrip(".,)"),
                    published_date=date_match.group(0) if date_match else None,
                )
            except ValidationError:
                continue
            results.append(result)
        return results

    async def extract_content(self, url: str) -> str:
        return await self._call("extract", {"url": url})

    async def aclose(self) -> None:
        await self._client.aclose()


class TavilyProvider:
    """Tavily search/extract fallback with strict response projection."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: SecretStr,
        timeout_seconds: float,
        max_response_bytes: int,
        max_content_characters: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {api_key.get_secret_value()}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(timeout_seconds),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=40),
            transport=transport,
        )
        self._search_url = _endpoint(base_url, "/search")
        self._extract_url = _endpoint(base_url, "/extract")
        self._max_response_bytes = max_response_bytes
        self._max_content_characters = max_content_characters

    async def _post(self, url: str, payload: dict[str, Any], operation: str) -> httpx.Response:
        started = time.perf_counter()
        outcome = "invalid_response"
        try:
            try:
                response = await self._client.post(url, json=payload)
            except httpx.TimeoutException as error:
                outcome = "timeout"
                raise SearchProviderTimeout("Tavily request timed out") from error
            except httpx.RequestError as error:
                outcome = "network_error"
                raise SearchProviderNetworkError("Tavily network request failed") from error
            if response.status_code >= 400:
                provider_error = _status_error(response.status_code)
                outcome = provider_error.outcome
                raise provider_error
            if len(response.content) > self._max_response_bytes:
                raise SearchProviderInvalidResponse("Tavily response exceeded the size limit")
            outcome = "success"
            return response
        finally:
            _record("tavily", operation, outcome, started)

    async def search(
        self,
        query: str,
        *,
        max_results: int,
        domain: SearchDomain,
    ) -> list[ProviderSearchResult]:
        del domain
        response = await self._post(
            self._search_url,
            {
                "query": query,
                "search_depth": "advanced",
                "max_results": max_results,
                "include_answer": False,
            },
            "search",
        )
        try:
            payload = _TavilySearchPayload.model_validate(response.json())
        except (ValueError, ValidationError) as error:
            raise SearchProviderInvalidResponse(
                "Tavily returned an invalid search response"
            ) from error
        results: list[ProviderSearchResult] = []
        for item in payload.results[:max_results]:
            try:
                results.append(
                    ProviderSearchResult(
                        title=item.title[:512],
                        snippet=item.content[:4_000],
                        url=item.url,
                        published_date=(item.published_date[:64] if item.published_date else None),
                        score=item.score,
                    )
                )
            except ValidationError:
                continue
        if payload.results and not results:
            raise SearchProviderInvalidResponse("Tavily search results failed validation")
        return results

    async def extract_content(self, url: str) -> str:
        response = await self._post(
            self._extract_url,
            {"urls": [url], "extract_depth": "advanced"},
            "extract",
        )
        try:
            payload = _TavilyExtractPayload.model_validate(response.json())
        except (ValueError, ValidationError) as error:
            raise SearchProviderInvalidResponse(
                "Tavily returned an invalid extraction response"
            ) from error
        content = payload.results[0].raw_content
        if len(content) > self._max_content_characters:
            raise SearchProviderInvalidResponse("Tavily extracted content exceeded the limit")
        return content

    async def aclose(self) -> None:
        await self._client.aclose()
