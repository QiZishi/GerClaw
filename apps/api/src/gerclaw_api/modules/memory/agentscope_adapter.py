"""AgentScope Mem0Middleware client adapter backed by GerClaw MemoryModule."""

from __future__ import annotations

import logging
from typing import Any

from gerclaw_api.modules.memory.protocols import MemoryMessage, MemoryModule

_LOGGER = logging.getLogger("gerclaw.memory.adapter")


class AgentScopeMemoryAdapterError(RuntimeError):
    """Safe adapter failure surfaced after AgentScope finishes its middleware chain."""


def _exception_chain(error: BaseException) -> list[str]:
    """Return bounded exception class names without messages, inputs, or provider identity."""

    chain: list[str] = []
    current: BaseException | None = error
    while current is not None and len(chain) < 8:
        chain.append(type(current).__name__)
        current = current.__cause__
    return chain


class GerClawMem0Client:
    """Duck-typed async mem0 client preserving AgentScope's native middleware lifecycle.

    AgentScope accepts a prebuilt async client. This adapter is intentional: mem0's
    default SQLite history and plaintext vector payload cannot be the authority for
    encrypted clinical data, while the middleware/tool orchestration remains useful.
    """

    def __init__(
        self,
        module: MemoryModule,
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
        self._write_requested = False
        self._write_done = False
        self._fatal_error: Exception | None = None
        self._boundary_error: Exception | None = None
        self._write_error: Exception | None = None

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
        try:
            self._validate_filters(filters)
            if not 1 <= top_k <= 20:
                raise ValueError("memory search limit is invalid")
            profile = await self._module.get_long_term(self._actor_id, query=query)
        except Exception as error:
            self._fatal_error = error
            _LOGGER.warning(
                "memory_adapter_search_failed",
                extra={"attributes": {"exception_chain": _exception_chain(error)}},
            )
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
        """Stage the actual user source; promotion owns the durable write."""

        del messages, agent_id, infer
        try:
            if user_id != self._actor_id:
                error = ValueError("memory write principal is invalid")
                self._boundary_error = error
                self._fatal_error = error
                raise error
            self._write_requested = True
        except Exception as error:
            self._fatal_error = error
            _LOGGER.warning(
                "memory_adapter_write_stage_failed",
                extra={"attributes": {"exception_chain": _exception_chain(error)}},
            )
            raise AgentScopeMemoryAdapterError("memory write failed") from error
        return self._result()

    async def commit_staged_write(self) -> None:
        """Persist once only after the owning answer candidate is fully valid."""

        if not self._write_requested or self._write_done:
            return
        self._write_done = True
        try:
            await self._module.extract_and_update_profile(self._actor_id, [self._source])
        except Exception as error:
            self._write_error = error
            _LOGGER.warning(
                "memory_adapter_write_failed",
                extra={"attributes": {"exception_chain": _exception_chain(error)}},
            )
            return
        self._write_error = None

    def discard_staged_write(self) -> None:
        """Make an invalidated attempt incapable of mutating Memory later."""

        self._write_requested = False

    def raise_if_failed(self) -> None:
        """Fail only when Memory's owner boundary was invalid.

        Memory retrieval is an optional context enhancement. A provider or
        database failure must not discard a completed model answer.
        """

        if self._boundary_error is not None:
            raise AgentScopeMemoryAdapterError("required medical memory operation failed") from (
                self._boundary_error
            )

    def warning_codes(self) -> tuple[str, ...]:
        """Project a transient post-answer write failure without exposing its content."""

        warnings: list[str] = []
        if self._fatal_error is not None and self._boundary_error is None:
            warnings.append("MEMORY_SEARCH_FAILED")
        if self._write_error is not None:
            warnings.append("MEMORY_WRITE_FAILED")
        return tuple(warnings)

    def _result(self) -> dict[str, list[dict[str, str]]]:
        changed = self._module.last_update.changed_fact_ids
        if changed:
            results = [{"id": str(item), "memory": "evidenced_fact"} for item in changed]
        else:
            results = [{"id": "no-op", "memory": "no_durable_fact"}]
        return {"results": results}

    def _validate_filters(self, filters: dict[str, Any]) -> None:
        if filters.get("user_id") != self._actor_id:
            error = AgentScopeMemoryAdapterError("memory search principal is invalid")
            self._boundary_error = error
            raise error
