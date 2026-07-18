"""Environment-backed lifecycle for production Search providers."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import SecretStr

from gerclaw_api.config import Settings
from gerclaw_api.modules.search.models import SearchStatus
from gerclaw_api.modules.search.module import ProductionSearchModule
from gerclaw_api.modules.search.providers import AnySearchProvider, TavilyProvider


@dataclass(slots=True)
class SearchRuntime:
    module: ProductionSearchModule
    primary: AnySearchProvider
    fallback: TavilyProvider | None
    capability_version: str

    async def aclose(self) -> None:
        await self.primary.aclose()
        if self.fallback is not None:
            await self.fallback.aclose()

    def status(self) -> SearchStatus:
        return SearchStatus(
            ready=self.fallback is not None,
            capability_version=self.capability_version,
            primary_configured=True,
            fallback_configured=self.fallback is not None,
        )


def create_search_runtime(settings: Settings) -> SearchRuntime:
    if settings.anysearch_url is None:
        raise ValueError("AnySearch URL is required for online search")
    if not settings.anysearch_supports_structured_results:
        raise ValueError("AnySearch does not declare the required structured-results capability")
    primary = AnySearchProvider(
        base_url=str(settings.anysearch_url),
        api_key=(
            SecretStr(settings.anysearch_api_key.get_secret_value())
            if settings.anysearch_api_key is not None
            else None
        ),
        timeout_seconds=settings.search_timeout_seconds,
        max_response_bytes=settings.search_max_response_bytes,
        max_content_characters=settings.search_max_content_characters,
    )
    fallback = None
    if settings.tavily_url is not None and settings.tavily_api_key is not None:
        if not settings.tavily_supports_structured_results:
            raise ValueError("Tavily does not declare the required structured-results capability")
        fallback = TavilyProvider(
            base_url=str(settings.tavily_url),
            api_key=SecretStr(settings.tavily_api_key.get_secret_value()),
            timeout_seconds=settings.search_timeout_seconds,
            max_response_bytes=settings.search_max_response_bytes,
            max_content_characters=settings.search_max_content_characters,
        )
    module = ProductionSearchModule(
        primary=primary,
        fallback=fallback,
        max_retries=settings.search_max_retries,
        max_content_characters=settings.search_max_content_characters,
    )
    return SearchRuntime(
        module=module,
        primary=primary,
        fallback=fallback,
        capability_version=settings.search_capability_version,
    )
