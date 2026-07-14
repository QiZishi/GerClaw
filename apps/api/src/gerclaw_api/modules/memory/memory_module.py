"""Production MemoryModule over encrypted PostgreSQL and PHI-free Qdrant."""

from __future__ import annotations

import hashlib
import hmac
import unicodedata
import uuid
from datetime import UTC, datetime

from pydantic import TypeAdapter, ValidationError

from gerclaw_api.database.models import MemoryFact, Message
from gerclaw_api.modules.memory.compressor import AgentScopeContextCompressor
from gerclaw_api.modules.memory.extractor import RealMemoryExtractor
from gerclaw_api.modules.memory.models import (
    HealthProfileRead,
    MemoryFactDecisionRead,
    MemoryFactDecisionRequest,
    MemoryUpdateResult,
    MemoryVectorRecord,
)
from gerclaw_api.modules.memory.profile import empty_profile, rebuild_profile, render_core_profile
from gerclaw_api.modules.memory.protocols import (
    MemoryFactView,
    MemoryMessage,
    UserProfile,
)
from gerclaw_api.modules.memory.store import (
    QdrantMemoryStore,
    memory_namespace,
    memory_point_id,
)
from gerclaw_api.modules.rag.providers import SiliconFlowEmbeddingModel
from gerclaw_api.repositories.memory import (
    MemoryConflictError,
    MemoryNotFoundError,
    MemoryRepository,
)
from gerclaw_api.security import JsonValue

_PROFILE = TypeAdapter(dict[str, JsonValue])


class MemoryDataError(RuntimeError):
    """Raised when decrypted Memory state violates the current schema."""


class MemoryUnavailableError(RuntimeError):
    """Safe signal for a required model, vector, or persistence failure."""


def _fact_key(secret: bytes, *, category: str, entity: str) -> str:
    normalized = unicodedata.normalize("NFKC", entity).strip().casefold()
    return hmac.new(
        secret,
        f"memory:fact:{category}:{normalized}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _fact_view(fact: MemoryFact, *, relevance_score: float | None = None) -> MemoryFactView:
    try:
        details = _PROFILE.validate_python(fact.details)
        return MemoryFactView(
            id=fact.id,
            category=fact.category,
            memory_type=fact.memory_type,
            status=fact.status,
            statement=fact.statement,
            details=details,
            confidence=fact.confidence,
            revision=fact.revision,
            source_trace_id=fact.source_trace_id,
            occurred_at=fact.occurred_at,
            confirmed_at=fact.confirmed_at,
            updated_at=fact.updated_at,
            relevance_score=relevance_score,
        )
    except ValidationError as error:
        raise MemoryDataError("stored memory fact is invalid") from error


class ProductionMemoryModule:
    """One principal/session-scoped Memory implementation with no shared user state."""

    def __init__(
        self,
        *,
        repository: MemoryRepository,
        extractor: RealMemoryExtractor,
        compressor: AgentScopeContextCompressor,
        embedding_model: SiliconFlowEmbeddingModel,
        vector_store: QdrantMemoryStore,
        namespace_secret: bytes,
        tenant_id: str,
        actor_id: str,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        trace_id: str,
        retrieval_top_k: int,
        retrieval_candidates: int,
    ) -> None:
        self._repository = repository
        self._extractor = extractor
        self._compressor = compressor
        self._embedding_model = embedding_model
        self._vector_store = vector_store
        self._namespace_secret = namespace_secret
        self._tenant_id = tenant_id
        self._actor_id = actor_id
        self._user_id = user_id
        self._session_id = session_id
        self._trace_id = trace_id
        self._retrieval_top_k = retrieval_top_k
        self._retrieval_candidates = retrieval_candidates
        self._cached_queries: dict[str, UserProfile] = {}
        self.last_update = MemoryUpdateResult(profile_version=0)

    async def get_short_term(self, session_id: str, max_turns: int = 20) -> list[MemoryMessage]:
        """Load encrypted session history in chronological order."""

        resolved = self._validate_session_id(session_id)
        if not 1 <= max_turns <= 100:
            raise ValueError("max_turns must be between 1 and 100")
        await self._repository.require_session(
            resolved,
            tenant_id=self._tenant_id,
            actor_id=self._actor_id,
        )
        messages = await self._repository.list_messages(
            resolved,
            tenant_id=self._tenant_id,
            limit=max_turns * 2,
        )
        projected: list[MemoryMessage] = []
        for message in messages:
            if message.trace_id == self._trace_id:
                continue
            try:
                projected.append(MemoryMessage(role=message.role, content=message.content))
            except ValidationError as error:
                raise MemoryDataError("stored short-term memory is invalid") from error
        return projected

    async def get_long_term(self, user_id: str, query: str | None = None) -> UserProfile:
        """Return the structured snapshot plus version-checked semantic recall."""

        self._validate_actor(user_id)
        normalized_query = query.strip() if query is not None else ""
        if len(normalized_query) > 4_000:
            raise ValueError("memory query cannot exceed 4,000 characters")
        if normalized_query and normalized_query in self._cached_queries:
            return self._cached_queries[normalized_query]

        stored_profile = await self._repository.get_profile(
            tenant_id=self._tenant_id,
            user_id=self._user_id,
        )
        if stored_profile is None:
            profile_value = empty_profile()
            schema_version = 1
            version = 0
        else:
            try:
                profile_value = _PROFILE.validate_python(stored_profile.profile)
            except ValidationError as error:
                raise MemoryDataError("stored health profile is invalid") from error
            schema_version = stored_profile.schema_version
            version = stored_profile.version

        relevant: list[MemoryFactView] = []
        if normalized_query:
            confirmed = await self._repository.list_facts(
                tenant_id=self._tenant_id,
                user_id=self._user_id,
                statuses=["confirmed"],
                limit=200,
            )
            if confirmed:
                embedding = await self._embedding_model([normalized_query])
                tenant_namespace, user_namespace = memory_namespace(
                    self._namespace_secret,
                    tenant_id=self._tenant_id,
                    user_id=self._user_id,
                )
                candidates = await self._vector_store.search(
                    embedding.embeddings[0],
                    tenant_namespace=tenant_namespace,
                    user_namespace=user_namespace,
                    limit=self._retrieval_candidates,
                    point_ids=[
                        memory_point_id(fact.id, fact.vector_revision) for fact in confirmed
                    ],
                )
                by_id = {
                    item.id: item
                    for item in await self._repository.list_facts(
                        tenant_id=self._tenant_id,
                        user_id=self._user_id,
                        statuses=["confirmed"],
                        fact_ids=[candidate.fact_id for candidate in candidates],
                        limit=self._retrieval_candidates,
                    )
                }
                for candidate in candidates:
                    fact = by_id.get(candidate.fact_id)
                    if (
                        fact is None
                        or fact.revision != candidate.revision
                        or fact.vector_revision != candidate.revision
                    ):
                        continue
                    relevant.append(_fact_view(fact, relevance_score=candidate.score))
                    if len(relevant) >= self._retrieval_top_k:
                        break

        result = UserProfile(
            schema_version=schema_version,
            version=version,
            profile=profile_value,
            provenance_refs=[str(item.id) for item in relevant],
            relevant_facts=relevant,
        )
        if normalized_query:
            self._cached_queries[normalized_query] = result
        return result

    async def save_message(self, session_id: str, message: MemoryMessage) -> None:
        """Persist a validated encrypted message through the scoped repository."""

        resolved = self._validate_session_id(session_id)
        await self._repository.require_session(
            resolved,
            tenant_id=self._tenant_id,
            actor_id=self._actor_id,
        )
        if not message.text():
            raise ValueError("memory message must contain a text block")
        await self._repository.add_message(
            Message(
                id=uuid.uuid4(),
                tenant_id=self._tenant_id,
                session_id=resolved,
                trace_id=None,
                role=message.role,
                content=message.content,
                message_metadata={"source": "memory_module"},
            )
        )
        await self._repository.commit()

    async def extract_and_update_profile(
        self, user_id: str, conversation: list[MemoryMessage]
    ) -> None:
        """Extract user-only facts, vectorize confirmed revisions, and stage profile changes."""

        self._validate_actor(user_id)
        user_texts = [message.text() for message in conversation if message.role == "user"]
        user_texts = [text for text in user_texts if text]
        if not user_texts:
            self.last_update = MemoryUpdateResult(profile_version=0)
            return

        candidates = []
        for text in user_texts:
            candidates.extend(await self._extractor.extract(text))
        profile = await self._repository.lock_or_create_profile(
            tenant_id=self._tenant_id,
            user_id=self._user_id,
        )
        changed: list[MemoryFact] = []
        now = datetime.now(UTC)
        for candidate, status in candidates:
            fact_key = _fact_key(
                self._namespace_secret,
                category=candidate.category,
                entity=candidate.entity,
            )
            existing = await self._repository.get_fact_by_key_for_update(
                tenant_id=self._tenant_id,
                user_id=self._user_id,
                fact_key=fact_key,
            )
            details = candidate.details.model_dump(mode="json")
            details.update(
                {
                    "entity": candidate.entity,
                    "evidence_span": candidate.evidence_span,
                    "source": "user_self_report",
                }
            )
            statement = candidate.statement.strip()
            if not statement.startswith("用户自述"):
                statement = f"用户自述: {statement}"
            if existing is None:
                fact = MemoryFact(
                    id=uuid.uuid4(),
                    tenant_id=self._tenant_id,
                    user_id=self._user_id,
                    source_session_id=self._session_id,
                    source_trace_id=self._trace_id,
                    category=candidate.category,
                    memory_type=candidate.memory_type,
                    fact_key=fact_key,
                    status=status,
                    statement=statement,
                    details=details,
                    confidence=candidate.confidence,
                    revision=1,
                    vector_revision=0,
                    occurred_at=candidate.occurred_at,
                    confirmed_at=now if status == "confirmed" else None,
                )
                await self._repository.add_fact(fact)
                changed.append(fact)
                continue
            unchanged = (
                existing.status == status
                and existing.statement == statement
                and existing.details == details
                and existing.memory_type == candidate.memory_type
                and existing.confidence == candidate.confidence
                and existing.occurred_at == candidate.occurred_at
            )
            if unchanged:
                continue
            existing.source_session_id = self._session_id
            existing.source_trace_id = self._trace_id
            existing.memory_type = candidate.memory_type
            existing.status = status
            existing.statement = statement
            existing.details = details
            existing.confidence = candidate.confidence
            existing.occurred_at = candidate.occurred_at
            existing.confirmed_at = now if status == "confirmed" else existing.confirmed_at
            existing.revision += 1
            changed.append(existing)

        if not changed:
            self.last_update = MemoryUpdateResult(profile_version=profile.version)
            return
        await self._repository.flush()
        confirmed = [fact for fact in changed if fact.status == "confirmed"]
        if confirmed:
            vector_records = [
                MemoryVectorRecord(
                    id=fact.id,
                    category=fact.category,
                    status=fact.status,
                    revision=fact.revision,
                    statement=fact.statement,
                )
                for fact in confirmed
            ]
            embedding = await self._embedding_model([item.statement for item in vector_records])
            tenant_namespace, user_namespace = memory_namespace(
                self._namespace_secret,
                tenant_id=self._tenant_id,
                user_id=self._user_id,
            )
            await self._vector_store.upsert(
                vector_records,
                embedding.embeddings,
                tenant_namespace=tenant_namespace,
                user_namespace=user_namespace,
            )
            for fact in confirmed:
                fact.vector_revision = fact.revision
        await self._repository.flush()
        all_facts = await self._repository.list_facts(
            tenant_id=self._tenant_id,
            user_id=self._user_id,
            limit=200,
        )
        profile.profile = rebuild_profile(all_facts)
        profile.schema_version = 1
        profile.version += 1
        await self._repository.flush()
        self._cached_queries.clear()
        self.last_update = MemoryUpdateResult(
            profile_version=profile.version,
            changed_fact_ids=[fact.id for fact in changed],
            confirmed_count=sum(fact.status == "confirmed" for fact in changed),
            pending_count=sum(fact.status == "pending" for fact in changed),
            inactive_count=sum(fact.status == "inactive" for fact in changed),
            categories=list(dict.fromkeys(fact.category for fact in changed)),
        )

    async def compress_context(
        self, messages: list[MemoryMessage], max_tokens: int
    ) -> list[MemoryMessage]:
        """Run AgentScope compression and stage the encrypted session summary."""

        session = await self._repository.require_session(
            self._session_id,
            tenant_id=self._tenant_id,
            actor_id=self._actor_id,
        )
        raw_summary = session.context_summary
        if not isinstance(raw_summary, dict):
            raise MemoryDataError("stored session summary is invalid")
        summary = raw_summary.get("text", "")
        if not isinstance(summary, str):
            raise MemoryDataError("stored session summary text is invalid")
        result = await self._compressor.compress(
            messages,
            session_id=str(self._session_id),
            max_tokens=max_tokens,
            existing_summary=summary,
        )
        if result.compressed:
            session.context_summary = {
                "schema_version": 1,
                "text": result.summary,
                "updated_at": datetime.now(UTC).isoformat(),
            }
            await self._repository.flush()
        return result.messages

    async def core_profile_context(self) -> tuple[str, int, list[str]]:
        """Return a bounded prompt projection and opaque provenance IDs."""

        profile = await self.get_long_term(self._actor_id)
        return (
            render_core_profile(profile.profile),
            profile.version,
            profile.provenance_refs,
        )

    async def read_profile(self) -> HealthProfileRead:
        """Return all current-user facts for an authenticated profile UI."""

        profile = await self.get_long_term(self._actor_id)
        facts = await self._repository.list_facts(
            tenant_id=self._tenant_id,
            user_id=self._user_id,
            limit=200,
        )
        return HealthProfileRead(
            schema_version=profile.schema_version,
            version=profile.version,
            profile=profile.profile,
            facts=[_fact_view(fact) for fact in facts],
        )

    async def decide_fact(
        self, fact_id: uuid.UUID, decision: MemoryFactDecisionRequest
    ) -> MemoryFactDecisionRead:
        """Confirm or retire one fact using optimistic revision validation."""

        profile = await self._repository.lock_or_create_profile(
            tenant_id=self._tenant_id,
            user_id=self._user_id,
        )
        fact = await self._repository.get_fact_for_update(
            tenant_id=self._tenant_id,
            user_id=self._user_id,
            fact_id=fact_id,
        )
        if fact is None:
            raise MemoryNotFoundError("memory fact not found")
        if fact.revision != decision.expected_revision:
            raise MemoryConflictError("memory fact revision is stale")
        fact.status = "confirmed" if decision.decision == "confirm" else "inactive"
        fact.revision += 1
        if fact.status == "confirmed":
            fact.confirmed_at = datetime.now(UTC)
            record = MemoryVectorRecord(
                id=fact.id,
                category=fact.category,
                status=fact.status,
                revision=fact.revision,
                statement=fact.statement,
            )
            embedding = await self._embedding_model([fact.statement])
            tenant_namespace, user_namespace = memory_namespace(
                self._namespace_secret,
                tenant_id=self._tenant_id,
                user_id=self._user_id,
            )
            await self._vector_store.upsert(
                [record],
                embedding.embeddings,
                tenant_namespace=tenant_namespace,
                user_namespace=user_namespace,
            )
            fact.vector_revision = fact.revision
        await self._repository.flush()
        all_facts = await self._repository.list_facts(
            tenant_id=self._tenant_id,
            user_id=self._user_id,
            limit=200,
        )
        profile.profile = rebuild_profile(all_facts)
        profile.version += 1
        await self._repository.flush()
        return MemoryFactDecisionRead(fact=_fact_view(fact), profile_version=profile.version)

    async def commit(self) -> None:
        """Commit standalone profile API changes."""

        await self._repository.commit()

    async def rollback(self) -> None:
        """Rollback standalone profile API or terminal chat changes."""

        await self._repository.rollback()

    def _validate_actor(self, actor_id: str) -> None:
        if actor_id != self._actor_id:
            raise MemoryNotFoundError("memory principal not found")

    def _validate_session_id(self, session_id: str) -> uuid.UUID:
        try:
            resolved = uuid.UUID(session_id)
        except ValueError as error:
            raise ValueError("memory session ID is invalid") from error
        if resolved != self._session_id:
            raise MemoryNotFoundError("memory session not found")
        return resolved
