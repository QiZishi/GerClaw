"""Production online medical evidence search public surface."""

from gerclaw_api.modules.search.agentscope_adapter import (
    build_web_search_tool,
    capture_agent_search_results,
    citations_from_search_results,
)
from gerclaw_api.modules.search.models import SearchAttempt, SearchResult, SearchStatus
from gerclaw_api.modules.search.module import (
    ProductionSearchModule,
    SearchUnavailableError,
    capture_search_attempts,
)
from gerclaw_api.modules.search.runtime import SearchRuntime, create_search_runtime
from gerclaw_api.modules.search.security import UnsafeSearchURLError

__all__ = [
    "ProductionSearchModule",
    "SearchAttempt",
    "SearchResult",
    "SearchRuntime",
    "SearchStatus",
    "SearchUnavailableError",
    "UnsafeSearchURLError",
    "build_web_search_tool",
    "capture_agent_search_results",
    "capture_search_attempts",
    "citations_from_search_results",
    "create_search_runtime",
]
