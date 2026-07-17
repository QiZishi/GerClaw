"""Production MemoryModule over encrypted PostgreSQL and PHI-free Qdrant."""

from __future__ import annotations

import hashlib
import hmac
import logging
import unicodedata
import uuid
from datetime import UTC, datetime

from pydantic import TypeAdapter, ValidationError

from gerclaw_api.database.models import MemoryFact, MemoryFactRevision, Message
from gerclaw_api.modules.memory.compressor import AgentScopeContextCompressor
from gerclaw_api.modules.memory.extractor import RealMemoryExtractor, evidence_has_negation
from gerclaw_api.modules.memory.models import (
    HealthProfileRead,
    MemoryFactDecisionRead,
    MemoryFactDecisionRequest,
    MemoryFactHistoryRead,
    MemoryFactRevisionRead,
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
_LOGGER = logging.getLogger("gerclaw.memory")


class MemoryDataError(RuntimeError):
    """Raised when decrypted Memory state violates the current schema."""


class MemoryUnavailableError(RuntimeError):
    """Safe signal for a required model, vector, or persistence failure."""


def _fact_key(
    secret: bytes,
    *,
    category: str,
    entity: str,
    event_identity: str | None = None,
) -> str:
    normalized = unicodedata.normalize("NFKC", entity).strip().casefold()
    identity = f":{event_identity}" if event_identity is not None else ""
    return hmac.new(
        secret,
        f"memory:fact:{category}:{normalized}{identity}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _event_identity(
    *, occurred_at: datetime | None, trace_id: str, evidence_span: str
) -> str | None:
    """Keep distinct events while making a replay of one source idempotent."""

    if occurred_at is not None:
        normalized = occurred_at
        if normalized.tzinfo is None:
            normalized = normalized.replace(tzinfo=UTC)
        return f"occurred:{normalized.astimezone(UTC).isoformat()}"
    evidence_hash = hashlib.sha256(
        unicodedata.normalize("NFKC", evidence_span).strip().encode()
    ).hexdigest()
    return f"source:{trace_id}:{evidence_hash}"


def _revision_snapshot(fact: MemoryFact) -> dict[str, JsonValue]:
    """Serialize the complete pre-update projection for encrypted audit storage."""

    return {
        "source_session_id": str(fact.source_session_id) if fact.source_session_id else None,
        "source_trace_id": fact.source_trace_id,
        "category": fact.category,
        "memory_type": fact.memory_type,
        "status": fact.status,
        "statement": fact.statement,
        "details": _PROFILE.validate_python(fact.details),
        "confidence": fact.confidence,
        "revision": fact.revision,
        "vector_revision": fact.vector_revision,
        "occurred_at": fact.occurred_at.isoformat() if fact.occurred_at else None,
        "confirmed_at": fact.confirmed_at.isoformat() if fact.confirmed_at else None,
        "updated_at": fact.updated_at.isoformat() if fact.updated_at else None,
    }


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


def _revision_view(revision: MemoryFactRevision) -> MemoryFactRevisionRead:
    """Validate a decrypted pre-mutation snapshot before returning it to its owner."""

    try:
        snapshot = _PROFILE.validate_python(revision.snapshot)
        return MemoryFactRevisionRead(
            revision=revision.revision,
            category=snapshot["category"],
            memory_type=snapshot["memory_type"],
            status=snapshot["status"],
            statement=snapshot["statement"],
            details=snapshot["details"],
            confidence=snapshot["confidence"],
            source_trace_id=snapshot.get("source_trace_id"),
            occurred_at=snapshot.get("occurred_at"),
            confirmed_at=snapshot.get("confirmed_at"),
            updated_at=snapshot.get("updated_at"),
            recorded_at=revision.created_at,
        )
    except (KeyError, TypeError, ValidationError) as error:
        raise MemoryDataError("stored memory fact revision is invalid") from error


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
        self._uncommitted_vector_point_ids: set[uuid.UUID] = set()
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
            event_identity = (
                _event_identity(
                    occurred_at=candidate.occurred_at,
                    trace_id=self._trace_id,
                    evidence_span=candidate.evidence_span,
                )
                if candidate.category == "event" or candidate.memory_type == "event"
                else None
            )
            fact_key = _fact_key(
                self._namespace_secret,
                category=candidate.category,
                entity=candidate.entity,
                event_identity=event_identity,
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
                    "polarity": "negative" if candidate.action == "deactivate" else "positive",
                    "source": "user_self_report",
                }
            )
            # The model's free-form statement is never persisted: only the
            # extractor-validated exact user evidence can become durable text.
            statement = f"用户自述: {candidate.evidence_span.strip()}"
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
            # Uncertainty must never erase an already confirmed high-risk fact.
            # Without a separate candidate table, preserve the authoritative row
            # and wait for either an explicit inactive correction or a user API
            # rejection before changing the active profile.
            if existing.status == "confirmed" and status == "pending":
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
            await self._repository.add_fact_revision(
                MemoryFactRevision(
                    id=uuid.uuid4(),
                    tenant_id=self._tenant_id,
                    user_id=self._user_id,
                    fact_id=existing.id,
                    revision=existing.revision,
                    snapshot=_revision_snapshot(existing),
                )
            )
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
            self._uncommitted_vector_point_ids.update(
                memory_point_id(fact.id, fact.revision) for fact in confirmed
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

    async def read_fact_history(self, fact_id: uuid.UUID, *, limit: int) -> MemoryFactHistoryRead:
        """Return only the caller's encrypted, immutable previous fact versions."""

        if not 1 <= limit <= 50:
            raise ValueError("memory fact history limit must be between 1 and 50")
        fact = await self._repository.get_fact(
            tenant_id=self._tenant_id, user_id=self._user_id, fact_id=fact_id
        )
        if fact is None:
            raise MemoryNotFoundError("memory fact not found")
        revisions = await self._repository.list_fact_revisions(
            tenant_id=self._tenant_id,
            user_id=self._user_id,
            fact_id=fact.id,
            limit=limit,
        )
        return MemoryFactHistoryRead(
            fact_id=fact.id,
            items=[_revision_view(revision) for revision in revisions],
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
        if fact.status == "inactive" or (
            fact.status == "confirmed" and decision.decision == "confirm"
        ):
            raise MemoryConflictError("memory fact does not accept this decision")
        try:
            stored_details = _PROFILE.validate_python(fact.details)
        except ValidationError as error:
            raise MemoryDataError("stored memory fact is invalid") from error
        evidence = stored_details.get("evidence_span")
        entity = stored_details.get("entity")
        negative_evidence = stored_details.get("polarity") == "negative" or (
            isinstance(evidence, str)
            and evidence_has_negation(
                evidence,
                category=fact.category,
                entity=entity if isinstance(entity, str) else None,
            )
        )
        if decision.decision == "confirm" and negative_evidence:
            raise MemoryConflictError("negative memory fact cannot become active")
        await self._repository.add_fact_revision(
            MemoryFactRevision(
                id=uuid.uuid4(),
                tenant_id=self._tenant_id,
                user_id=self._user_id,
                fact_id=fact.id,
                revision=fact.revision,
                snapshot=_revision_snapshot(fact),
            )
        )
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
            self._uncommitted_vector_point_ids.add(memory_point_id(fact.id, fact.revision))
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

        try:
            await self._repository.commit()
        except BaseException:
            await self.compensate_uncommitted_vectors()
            raise
        self.mark_vectors_committed()

    async def rollback(self) -> None:
        """Rollback standalone profile API or terminal chat changes."""

        try:
            await self._repository.rollback()
        finally:
            await self.compensate_uncommitted_vectors()

    def mark_vectors_committed(self) -> None:
        """Release the cleanup snapshot only after PostgreSQL commit succeeds."""

        self._uncommitted_vector_point_ids.clear()

    async def compensate_uncommitted_vectors(self) -> bool:
        """Best-effort exact cleanup; PG revision fencing remains the read-side fallback."""

        point_ids = tuple(self._uncommitted_vector_point_ids)
        if not point_ids:
            return True
        try:
            await self._vector_store.delete_points(point_ids)
        except Exception:
            _LOGGER.warning(
                "memory_vector_compensation_failed",
                extra={"attributes": {"point_count": len(point_ids)}},
            )
            return False
        self._uncommitted_vector_point_ids.difference_update(point_ids)
        return True

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
