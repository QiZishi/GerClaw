"""Production AnySearch-first router for online medical evidence."""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TypeVar
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import ValidationError

from gerclaw_api.metrics import SEARCH_EXECUTIONS, SEARCH_LATENCY
from gerclaw_api.modules.search.models import (
    ProviderSearchResult,
    SearchAttempt,
    SearchDomain,
    SearchProviderName,
    SearchResult,
)
from gerclaw_api.modules.search.protocols import SearchProvider
from gerclaw_api.modules.search.providers import (
    RetryableSearchProviderError,
    SearchProviderError,
)
from gerclaw_api.modules.search.security import PublicURLGuard, sanitize_search_query

T = TypeVar("T")
_TRACKING_PARAMETERS = frozenset(
    {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "referrer", "source"}
)
_D_AUTHORITY_DOMAINS = (
    "reddit.com",
    "quora.com",
    "zhihu.com",
    "tieba.baidu.com",
    "weibo.com",
    "facebook.com",
    "x.com",
)
_S_AUTHORITY_DOMAINS = (
    "who.int",
    "fda.gov",
    "nih.gov",
    "ncbi.nlm.nih.gov",
    "cdc.gov",
    "nhc.gov.cn",
    "nmpa.gov.cn",
    "gov.cn",
)
_A_AUTHORITY_DOMAINS = (
    "nice.org.uk",
    "heart.org",
    "acc.org",
    "nccn.org",
    "escardio.org",
    "cma.org.cn",
    "cochranelibrary.com",
    "nejm.org",
    "thelancet.com",
    "jamanetwork.com",
    "bmj.com",
)
_B_AUTHORITY_DOMAINS = (
    "mayoclinic.org",
    "medscape.com",
    "uptodate.com",
    "dxy.cn",
    "msdmanuals.com",
)
_ADVERTISING = re.compile(r"(?:广告|推广|购买|折扣|代购|优惠券|sponsored)", re.IGNORECASE)

_ATTEMPT_CAPTURE: ContextVar[list[SearchAttempt] | None] = ContextVar(
    "gerclaw_search_attempt_capture", default=None
)


@contextmanager
def capture_search_attempts() -> Iterator[list[SearchAttempt]]:
    """Capture only bounded, PHI-free attempt metadata in the current task."""

    attempts: list[SearchAttempt] = []
    token = _ATTEMPT_CAPTURE.set(attempts)
    try:
        yield attempts
    finally:
        _ATTEMPT_CAPTURE.reset(token)


class SearchUnavailableError(RuntimeError):
    """Raised when neither configured provider can produce trustworthy output."""


def _host_matches(hostname: str, suffixes: tuple[str, ...]) -> bool:
    return any(hostname == suffix or hostname.endswith(f".{suffix}") for suffix in suffixes)


def classify_authority(hostname: str, title: str, snippet: str) -> str | None:
    """Return S/A/B/C or None for D-level sources that must be discarded."""

    host = hostname.casefold().removeprefix("www.")
    if _host_matches(host, _D_AUTHORITY_DOMAINS) or _ADVERTISING.search(f"{title} {snippet}"):
        return None
    if (
        _host_matches(host, _S_AUTHORITY_DOMAINS)
        or host.endswith(".gov")
        or host.endswith(".gov.cn")
    ):
        return "S"
    if _host_matches(host, _A_AUTHORITY_DOMAINS):
        return "A"
    if _host_matches(host, _B_AUTHORITY_DOMAINS):
        return "B"
    return "C"


def _canonical_url(value: str) -> tuple[str, str] | None:
    parsed = urlsplit(value)
    if parsed.scheme.casefold() != "https" or not parsed.hostname:
        return None
    host = parsed.hostname.encode("idna").decode("ascii").casefold().removeprefix("www.")
    query = urlencode(
        [
            (key, item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.casefold().startswith("utm_") and key.casefold() not in _TRACKING_PARAMETERS
        ]
    )
    canonical = urlunsplit(("https", host, parsed.path or "/", query, ""))
    return canonical, host


class ProductionSearchModule:
    """Retry once on transient AnySearch failures, then fail over to Tavily."""

    def __init__(
        self,
        *,
        primary: SearchProvider,
        fallback: SearchProvider | None,
        max_retries: int = 1,
        max_content_characters: int = 50_000,
        url_guard: PublicURLGuard | None = None,
    ) -> None:
        if max_retries not in (0, 1):
            raise ValueError("search provider retries must be zero or one")
        self._primary = primary
        self._fallback = fallback
        self._max_retries = max_retries
        self._max_content_characters = max_content_characters
        self._url_guard = url_guard or PublicURLGuard()

    async def search(
        self,
        query: str,
        max_results: int = 5,
        domain: SearchDomain = "health",
    ) -> list[SearchResult]:
        if not 1 <= max_results <= 10:
            raise ValueError("max_results must be between 1 and 10")
        if domain not in {"general", "health", "academic"}:
            raise ValueError("unsupported search domain")
        safe_query = sanitize_search_query(query)
        started = time.perf_counter()
        outcome = "failed"
        try:
            try:
                raw = await self._with_retry(
                    provider="anysearch",
                    operation="search",
                    call=lambda: self._primary.search(
                        safe_query, max_results=max_results, domain=domain
                    ),
                    result_count=lambda value: len(value),
                )
                provider: SearchProviderName = "anysearch"
            except SearchProviderError as primary_error:
                fallback = self._fallback
                if fallback is None:
                    raise SearchUnavailableError(
                        "online search fallback is not configured"
                    ) from primary_error
                try:
                    raw = await self._with_retry(
                        provider="tavily",
                        operation="search",
                        call=lambda: fallback.search(
                            safe_query, max_results=max_results, domain=domain
                        ),
                        result_count=lambda value: len(value),
                    )
                    provider = "tavily"
                except SearchProviderError as fallback_error:
                    raise SearchUnavailableError(
                        "online search providers are unavailable"
                    ) from fallback_error
            results = self._project_results(raw, provider=provider, max_results=max_results)
            outcome = (
                "empty" if not results else ("fallback" if provider == "tavily" else "success")
            )
            return results
        finally:
            SEARCH_EXECUTIONS.labels(outcome=outcome).inc()
            SEARCH_LATENCY.observe(time.perf_counter() - started)

    async def extract_content(self, url: str) -> str:
        safe_url = await self._url_guard.validate(url)
        try:
            content = await self._with_retry(
                provider="anysearch",
                operation="extract",
                call=lambda: self._primary.extract_content(safe_url),
                result_count=lambda _value: 0,
            )
        except SearchProviderError as primary_error:
            fallback = self._fallback
            if fallback is None:
                raise SearchUnavailableError(
                    "online extraction fallback is not configured"
                ) from primary_error
            try:
                content = await self._with_retry(
                    provider="tavily",
                    operation="extract",
                    call=lambda: fallback.extract_content(safe_url),
                    result_count=lambda _value: 0,
                )
            except SearchProviderError as fallback_error:
                raise SearchUnavailableError(
                    "online content extraction providers are unavailable"
                ) from fallback_error
        normalized = content.strip()
        if not normalized or len(normalized) > self._max_content_characters:
            raise SearchUnavailableError("online extracted content is invalid")
        return normalized

    async def _with_retry(
        self,
        *,
        provider: SearchProviderName,
        operation: str,
        call: Callable[[], Awaitable[T]],
        result_count: Callable[[T], int],
    ) -> T:
        for retry_index in range(self._max_retries + 1):
            started = time.perf_counter()
            try:
                result = await call()
            except SearchProviderError as error:
                self._capture_attempt(
                    provider=provider,
                    operation=operation,
                    outcome=error.outcome,
                    retry_index=retry_index,
                    started=started,
                )
                if (
                    isinstance(error, RetryableSearchProviderError)
                    and retry_index < self._max_retries
                ):
                    continue
                raise
            count = result_count(result)
            self._capture_attempt(
                provider=provider,
                operation=operation,
                outcome="empty" if operation == "search" and count == 0 else "success",
                retry_index=retry_index,
                started=started,
                result_count=count,
            )
            return result
        raise AssertionError("bounded search retry loop exhausted unexpectedly")

    @staticmethod
    def _capture_attempt(
        *,
        provider: SearchProviderName,
        operation: str,
        outcome: str,
        retry_index: int,
        started: float,
        result_count: int = 0,
    ) -> None:
        capture = _ATTEMPT_CAPTURE.get()
        if capture is None:
            return
        capture.append(
            SearchAttempt.model_validate(
                {
                    "provider": provider,
                    "operation": operation,
                    "outcome": outcome,
                    "retry_index": retry_index,
                    "duration_ms": max(0, round((time.perf_counter() - started) * 1_000)),
                    "result_count": result_count,
                }
            )
        )

    @staticmethod
    def _project_results(
        raw_results: list[ProviderSearchResult],
        *,
        provider: SearchProviderName,
        max_results: int,
    ) -> list[SearchResult]:
        projected: list[SearchResult] = []
        seen: set[str] = set()
        for raw in raw_results:
            canonical = _canonical_url(str(raw.url))
            if canonical is None:
                continue
            url, hostname = canonical
            if url in seen:
                continue
            authority = classify_authority(hostname, raw.title, raw.snippet)
            if authority is None:
                continue
            try:
                result = SearchResult(
                    id=f"web_{hashlib.sha256(url.encode()).hexdigest()[:16]}",
                    title=raw.title,
                    snippet=raw.snippet,
                    url=url,
                    source=hostname,
                    published_date=raw.published_date,
                    authority_level=authority,
                    provider=provider,
                    score=raw.score,
                )
            except ValidationError:
                continue
            projected.append(result)
            seen.add(url)
        authority_order = {"S": 0, "A": 1, "B": 2, "C": 3}
        projected.sort(
            key=lambda item: (
                authority_order[item.authority_level],
                -(item.score if item.score is not None else 0),
            )
        )
        return projected[:max_results]
