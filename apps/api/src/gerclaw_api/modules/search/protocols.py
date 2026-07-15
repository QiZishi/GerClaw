"""Replaceable online search provider and module interfaces."""

from __future__ import annotations

from typing import Protocol

from gerclaw_api.modules.search.models import ProviderSearchResult, SearchDomain, SearchResult


class SearchProvider(Protocol):
    """One strict external search engine adapter."""

    async def search(
        self,
        query: str,
        *,
        max_results: int,
        domain: SearchDomain,
    ) -> list[ProviderSearchResult]: ...

    async def extract_content(self, url: str) -> str: ...

    async def aclose(self) -> None: ...


class SearchModule(Protocol):
    """Chapter 4.10 online search module boundary."""

    async def search(
        self,
        query: str,
        max_results: int = 5,
        domain: SearchDomain = "health",
    ) -> list[SearchResult]: ...

    async def extract_content(self, url: str) -> str: ...
