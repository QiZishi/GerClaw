"""AgentScope Mem0Middleware client adapter backed by GerClaw MemoryModule."""

from __future__ import annotations

from typing import Any

from gerclaw_api.modules.memory.memory_module import ProductionMemoryModule
from gerclaw_api.modules.memory.protocols import MemoryMessage


class AgentScopeMemoryAdapterError(RuntimeError):
    """Safe adapter failure surfaced after AgentScope finishes its middleware chain."""


class GerClawMem0Client:
    """Duck-typed async mem0 client preserving AgentScope's native middleware lifecycle.

    AgentScope accepts a prebuilt async client. This adapter is intentional: mem0's
    default SQLite history and plaintext vector payload cannot be the authority for
    encrypted clinical data, while the middleware/tool orchestration remains useful.
    """

    def __init__(
        self,
        module: ProductionMemoryModule,
        *,
        actor_id: str,
        source_user_message: str,
    ) -> None:
        self._module = module
        self._actor_id = actor_id
        self._source = MemoryMessage(
            role="user",
            content=[{"type": "text", "text": source_user_message}],
        )
        self._write_done = False
        self._error: Exception | None = None

    async def search(
        self,
        query: str,
        *,
        filters: dict[str, Any],
        top_k: int,
        threshold: float | None = None,
    ) -> dict[str, list[dict[str, str]]]:
        """Return relevance-filtered encrypted-PG facts in mem0's response shape."""

        del threshold
        self._validate_filters(filters)
        if not 1 <= top_k <= 20:
            raise AgentScopeMemoryAdapterError("memory search limit is invalid")
        try:
            profile = await self._module.get_long_term(self._actor_id, query=query)
        except Exception as error:
            self._error = error
            raise AgentScopeMemoryAdapterError("memory search failed") from error
        return {
            "results": [
                {"id": str(fact.id), "memory": fact.statement}
                for fact in profile.relevant_facts[:top_k]
            ]
        }

    async def add(
        self,
        messages: list[dict[str, str]] | str,
        *,
        user_id: str,
        agent_id: str | None = None,
        infer: bool = True,
    ) -> dict[str, list[dict[str, str]]]:
        """Extract only the actual user source, never agent-proposed tool text."""

        del messages, agent_id, infer
        if user_id != self._actor_id:
            raise AgentScopeMemoryAdapterError("memory write principal is invalid")
        if self._write_done:
            return self._result()
        try:
            await self._module.extract_and_update_profile(self._actor_id, [self._source])
        except Exception as error:
            self._error = error
            raise AgentScopeMemoryAdapterError("memory write failed") from error
        self._write_done = True
        return self._result()

    def raise_if_failed(self) -> None:
        """Counter AgentScope's intentionally fail-open static-memory hook for medical use."""

        if self._error is not None:
            raise AgentScopeMemoryAdapterError("required medical memory operation failed") from (
                self._error
            )

    def _result(self) -> dict[str, list[dict[str, str]]]:
        changed = self._module.last_update.changed_fact_ids
        if changed:
            results = [{"id": str(item), "memory": "evidenced_fact"} for item in changed]
        else:
            results = [{"id": "no-op", "memory": "no_durable_fact"}]
        return {"results": results}

    def _validate_filters(self, filters: dict[str, Any]) -> None:
        if filters.get("user_id") != self._actor_id:
            raise AgentScopeMemoryAdapterError("memory search principal is invalid")
