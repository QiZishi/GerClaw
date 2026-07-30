"""Production MemoryModule over encrypted PostgreSQL and PHI-free Qdrant."""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import unicodedata
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast

from pydantic import TypeAdapter, ValidationError

from gerclaw_api.database.models import HealthProfile, MemoryFact, MemoryFactRevision, Message
from gerclaw_api.modules.memory.compressor import (
    AgentScopeContextCompressor,
    compression_source_hash,
)
from gerclaw_api.modules.memory.extractor import RealMemoryExtractor, evidence_has_negation
from gerclaw_api.modules.memory.models import (
    HealthProfileRead,
    MemoryFactCreateRequest,
    MemoryFactDecisionRead,
    MemoryFactDecisionRequest,
    MemoryFactDeleteRequest,
    MemoryFactDetails,
    MemoryFactHistoryRead,
    MemoryFactMutationRead,
    MemoryFactRestoreRequest,
    MemoryFactRevisionRead,
    MemoryFactUpdateRequest,
    MemoryRecallPreferenceRead,
    MemoryRecallPreferenceRequest,
    MemoryUpdateResult,
    MemoryVectorRecord,
    validate_memory_fact_shape,
)
from gerclaw_api.modules.memory.profile import empty_profile, rebuild_profile, render_core_profile
from gerclaw_api.modules.memory.protocols import (
    MemoryAccessLevel,
    MemoryCategory,
    MemoryFactView,
    MemoryMessage,
    MemoryType,
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

if TYPE_CHECKING:
    from gerclaw_api.modules.agent_harness.evolution_governance import (
        EvolutionGovernancePolicy,
    )

_PROFILE = TypeAdapter(dict[str, JsonValue])
_MEMORY_TYPE: TypeAdapter[MemoryType] = TypeAdapter(MemoryType)
_MEMORY_ACCESS_LEVEL: TypeAdapter[MemoryAccessLevel] = TypeAdapter(MemoryAccessLevel)
_MEMORY_CATEGORY: TypeAdapter[MemoryCategory] = TypeAdapter(MemoryCategory)
_MEMORY_CATEGORIES: TypeAdapter[list[MemoryCategory]] = TypeAdapter(list[MemoryCategory])
_OPTIONAL_DATETIME: TypeAdapter[datetime | None] = TypeAdapter(datetime | None)
_FLOAT: TypeAdapter[float] = TypeAdapter(float)
_LOGGER = logging.getLogger("gerclaw.memory")
_TRANSIENT_CATEGORIES = frozenset({"medication", "vital_sign", "assessment"})
_DIFFERENTIAL_HYPOTHESIS = re.compile(r"(?:可能|怀疑|疑似|鉴别|考虑|待排|不能排除|也许|或许|倾向)")
_DETAIL_EVIDENCE_FIELDS = (
    "value",
    "unit",
    "dose",
    "frequency",
    "route",
    "reaction",
    "code",
    "level",
)
_EVIDENCE_ENUM_ALIASES = {
    "mild": ("mild", "轻度", "轻微"),
    "moderate": ("moderate", "中度"),
    "severe": ("severe", "严重", "重度"),
    "active": ("active", "正在", "目前", "现用"),
    "stopped": ("stopped", "停用", "停止"),
    "resolved": ("resolved", "已缓解", "已恢复"),
    "historical": ("historical", "既往", "曾经", "历史"),
}


class MemoryDataError(RuntimeError):
    """Raised when decrypted Memory state violates the current schema."""


class MemoryUnavailableError(RuntimeError):
    """Safe signal for a required model, vector, or persistence failure."""


class MemoryEvidenceError(ValueError):
    """Owner-authored structured content is not supported by its submitted statement."""


def _normalized_evidence(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value).casefold())


def _validate_owner_evidence(
    *,
    category: str,
    entity: str,
    statement: str,
    details: MemoryFactDetails,
    occurred_at: datetime | None,
) -> None:
    """Reject owner-authored structured values that are absent from their evidence."""

    evidence = _normalized_evidence(statement)
    if not evidence:
        raise MemoryEvidenceError("memory statement cannot be blank")
    if (
        category not in {"basic_info", "vital_sign", "assessment", "goal"}
        and _normalized_evidence(entity) not in evidence
    ):
        raise MemoryEvidenceError("memory statement does not support its entity")
    detail_values = details.model_dump(mode="python", exclude_unset=True)
    for field in _DETAIL_EVIDENCE_FIELDS:
        value = detail_values.get(field)
        if value is not None:
            normalized_value = _normalized_evidence(str(value))
            if not normalized_value:
                raise MemoryEvidenceError(f"memory detail field cannot be blank: {field}")
            if normalized_value not in evidence:
                raise MemoryEvidenceError(
                    f"memory statement does not support detail field: {field}"
                )
    for field in ("severity", "source_status"):
        value = detail_values.get(field)
        if value in {None, "unknown"}:
            continue
        aliases = _EVIDENCE_ENUM_ALIASES.get(str(value), (str(value),))
        if not any(_normalized_evidence(alias) in evidence for alias in aliases):
            raise MemoryEvidenceError(f"memory statement does not support detail field: {field}")
    if occurred_at is not None:
        normalized = (
            occurred_at if occurred_at.tzinfo is not None else occurred_at.replace(tzinfo=UTC)
        )
        date = normalized.astimezone(UTC).date()
        date_aliases = (
            date.isoformat(),
            f"{date.year}年{date.month}月{date.day}日",
        )
        if not any(_normalized_evidence(alias) in evidence for alias in date_aliases):
            raise MemoryEvidenceError("memory statement does not support occurred_at")


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

    expires_at = getattr(fact, "expires_at", None)
    tombstoned_at = getattr(fact, "tombstoned_at", None)
    return {
        "source_session_id": str(fact.source_session_id) if fact.source_session_id else None,
        "source_trace_id": fact.source_trace_id,
        "category": fact.category,
        "memory_type": fact.memory_type,
        "status": fact.status,
        "access_level": fact.access_level or "standard",
        "statement": fact.statement,
        "details": _PROFILE.validate_python(fact.details),
        "confidence": fact.confidence,
        "revision": fact.revision,
        "vector_revision": fact.vector_revision,
        "occurred_at": fact.occurred_at.isoformat() if fact.occurred_at else None,
        "confirmed_at": fact.confirmed_at.isoformat() if fact.confirmed_at else None,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "tombstoned_at": tombstoned_at.isoformat() if tombstoned_at else None,
        "tombstone_reason": getattr(fact, "tombstone_reason", None),
        "tombstone_previous_status": getattr(fact, "tombstone_previous_status", None),
        "updated_at": fact.updated_at.isoformat() if fact.updated_at else None,
    }


def _fact_view(fact: MemoryFact, *, relevance_score: float | None = None) -> MemoryFactView:
    try:
        details = _PROFILE.validate_python(fact.details)
        return MemoryFactView.model_validate(
            {
                "id": fact.id,
                "category": fact.category,
                "memory_type": fact.memory_type,
                "status": fact.status,
                "access_level": fact.access_level or "standard",
                "statement": fact.statement,
                "details": details,
                "confidence": fact.confidence,
                "revision": fact.revision,
                "source_trace_id": fact.source_trace_id,
                "occurred_at": fact.occurred_at,
                "confirmed_at": fact.confirmed_at,
                "expires_at": getattr(fact, "expires_at", None),
                "tombstoned_at": getattr(fact, "tombstoned_at", None),
                "tombstone_reason": getattr(fact, "tombstone_reason", None),
                "can_restore": getattr(fact, "tombstoned_at", None) is not None,
                "updated_at": fact.updated_at,
                "relevance_score": relevance_score,
            }
        )
    except ValidationError as error:
        raise MemoryDataError("stored memory fact is invalid") from error


def _is_cross_session_recall_eligible(fact: MemoryFact, *, now: datetime) -> bool:
    """Keep every prompt projection behind the same owner-controlled recall gate."""

    expires_at = getattr(fact, "expires_at", None)
    return (
        fact.status == "confirmed"
        and (fact.access_level or "standard") == "standard"
        and (expires_at is None or cast(datetime, expires_at) > now)
    )


def _revision_view(revision: MemoryFactRevision) -> MemoryFactRevisionRead:
    """Validate a decrypted pre-mutation snapshot before returning it to its owner."""

    try:
        snapshot = _PROFILE.validate_python(revision.snapshot)
        return MemoryFactRevisionRead.model_validate(
            {
                "revision": revision.revision,
                "activity": revision.activity or "legacy_update",
                "category": snapshot["category"],
                "memory_type": snapshot["memory_type"],
                "status": snapshot["status"],
                "access_level": snapshot.get("access_level", "standard"),
                "statement": snapshot["statement"],
                "details": snapshot["details"],
                "confidence": snapshot["confidence"],
                "source_trace_id": snapshot.get("source_trace_id"),
                "occurred_at": snapshot.get("occurred_at"),
                "confirmed_at": snapshot.get("confirmed_at"),
                "expires_at": snapshot.get("expires_at"),
                "tombstoned_at": snapshot.get("tombstoned_at"),
                "tombstone_reason": snapshot.get("tombstone_reason"),
                "updated_at": snapshot.get("updated_at"),
                "recorded_at": revision.created_at,
            }
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
        transient_fact_ttl_days: int = 90,
    ) -> None:
        # This import stays at the construction boundary.  Importing the
        # security registry while modules are merely being discovered would
        # otherwise create a package cycle through Runtime's tool registry.
        from gerclaw_api.modules.security_evaluation import (
            CORE_RUNTIME_ASSET_VERSION,
            MEMORY_ASSET_NAME,
            build_core_runtime_asset_security_registry,
        )

        build_core_runtime_asset_security_registry().assess_memory(
            name=MEMORY_ASSET_NAME,
            version=CORE_RUNTIME_ASSET_VERSION,
            owner_module="memory",
        )
        from gerclaw_api.modules.agent_harness.evolution_governance import (
            EvolutionGovernancePolicy,
        )

        self._governance: EvolutionGovernancePolicy = EvolutionGovernancePolicy()
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
        if not 1 <= transient_fact_ttl_days <= 3_650:
            raise ValueError("transient fact TTL must be between 1 and 3,650 days")
        self._transient_fact_ttl_days = transient_fact_ttl_days
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
                projected.append(
                    MemoryMessage.model_validate({"role": message.role, "content": message.content})
                )
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
        recall_enabled = (
            stored_profile.cross_session_recall_enabled is not False
            if stored_profile is not None
            else True
        )

        relevant: list[MemoryFactView] = []
        if normalized_query and recall_enabled:
            confirmed = await self._repository.list_facts(
                tenant_id=self._tenant_id,
                user_id=self._user_id,
                statuses=["confirmed"],
                limit=200,
            )
            now = datetime.now(UTC)
            confirmed = [
                fact for fact in confirmed if _is_cross_session_recall_eligible(fact, now=now)
            ]
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
                        or not _is_cross_session_recall_eligible(fact, now=now)
                    ):
                        continue
                    relevant.append(_fact_view(fact, relevance_score=candidate.score))
                    if len(relevant) >= self._retrieval_top_k:
                        break

        result = UserProfile(
            schema_version=schema_version,
            version=version,
            profile=profile_value,
            cross_session_recall_enabled=recall_enabled,
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
        for candidate, extracted_status in candidates:
            if (
                candidate.category in {"condition", "assessment"}
                and _DIFFERENTIAL_HYPOTHESIS.search(candidate.evidence_span) is not None
            ):
                continue
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
            if existing is not None and getattr(existing, "tombstoned_at", None) is not None:
                # A later model extraction cannot silently undo an explicit
                # owner deletion. Only the fenced restore API may resurrect it.
                continue
            details = candidate.details.model_dump(mode="json")
            details.update(
                {
                    "entity": candidate.entity,
                    "evidence_span": candidate.evidence_span,
                    "polarity": "negative" if candidate.action == "deactivate" else "positive",
                    "source": "user_self_report",
                    "proposal_source_status": extracted_status,
                }
            )
            # The model's free-form statement is never persisted: only the
            # extractor-validated exact user evidence can become durable text.
            statement = f"用户自述: {candidate.evidence_span.strip()}"
            expires_at = (
                now + timedelta(days=self._transient_fact_ttl_days)
                if candidate.category in _TRANSIENT_CATEGORIES
                else None
            )
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
                    status="proposed",
                    access_level="standard",
                    statement=statement,
                    details=details,
                    confidence=candidate.confidence,
                    revision=1,
                    vector_revision=0,
                    occurred_at=candidate.occurred_at,
                    confirmed_at=None,
                    expires_at=expires_at,
                )
                await self._repository.add_fact(fact)
                changed.append(fact)
                continue
            comparable_existing = {
                key: value
                for key, value in existing.details.items()
                if key
                not in {
                    "evidence_span",
                    "source",
                    "proposal_source_status",
                    "conflict_previous",
                }
            }
            comparable_candidate = {
                key: value
                for key, value in details.items()
                if key not in {"evidence_span", "source", "proposal_source_status"}
            }
            if (
                existing.status == "confirmed"
                and comparable_existing == comparable_candidate
                and existing.details.get("polarity") == details["polarity"]
            ):
                continue
            unchanged = (
                existing.status == "proposed"
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
                    activity="extraction_update",
                    snapshot=_revision_snapshot(existing),
                )
            )
            if existing.status == "confirmed":
                details["conflict_previous"] = _revision_snapshot(existing)
                next_status = "conflicted"
            elif existing.status == "conflicted":
                conflict_previous = existing.details.get("conflict_previous")
                if isinstance(conflict_previous, dict):
                    details["conflict_previous"] = conflict_previous
                next_status = "conflicted"
            else:
                next_status = "proposed"
            existing.source_session_id = self._session_id
            existing.source_trace_id = self._trace_id
            existing.memory_type = candidate.memory_type
            existing.status = next_status
            existing.access_level = "standard"
            existing.statement = statement
            existing.details = details
            existing.confidence = candidate.confidence
            existing.occurred_at = candidate.occurred_at
            existing.confirmed_at = None
            existing.expires_at = expires_at
            existing.revision += 1
            changed.append(existing)

        if not changed:
            self.last_update = MemoryUpdateResult(profile_version=profile.version)
            return
        await self._repository.flush()
        confirmed = [fact for fact in changed if fact.status == "confirmed"]
        if confirmed:
            vector_records = [
                MemoryVectorRecord.model_validate(
                    {
                        "id": fact.id,
                        "category": fact.category,
                        "status": fact.status,
                        "revision": fact.revision,
                        "statement": fact.statement,
                    }
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
            pending_count=sum(fact.status in {"proposed", "pending"} for fact in changed),
            inactive_count=sum(fact.status == "inactive" for fact in changed),
            categories=_MEMORY_CATEGORIES.validate_python(
                list(dict.fromkeys(fact.category for fact in changed))
            ),
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
        source_hash = compression_source_hash(messages, max_tokens=max_tokens)
        if raw_summary.get("source_hash") == source_hash:
            raw_projection = raw_summary.get("projection")
            if not isinstance(raw_projection, list):
                raise MemoryDataError("stored session context projection is invalid")
            try:
                return [MemoryMessage.model_validate(item) for item in raw_projection]
            except ValidationError as error:
                raise MemoryDataError("stored session context projection is invalid") from error
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
                "source_hash": source_hash,
                "projection": [item.model_dump(mode="json") for item in result.messages],
                "updated_at": datetime.now(UTC).isoformat(),
            }
            await self._repository.flush()
        return result.messages

    async def get_context_summary(self) -> str:
        """Read the current encrypted summary for whole-context preflight."""

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
        return summary

    async def core_profile_context(self) -> tuple[str, int, list[str]]:
        """Return a bounded prompt projection and opaque provenance IDs."""

        profile = await self.get_long_term(self._actor_id)
        if not profile.cross_session_recall_enabled:
            return "", profile.version, []
        now = datetime.now(UTC)
        confirmed = await self._repository.list_facts(
            tenant_id=self._tenant_id,
            user_id=self._user_id,
            statuses=["confirmed"],
            limit=200,
        )
        eligible = [fact for fact in confirmed if _is_cross_session_recall_eligible(fact, now=now)]
        return (
            render_core_profile(rebuild_profile(eligible)),
            profile.version,
            [str(fact.id) for fact in eligible],
        )

    async def read_profile(self) -> HealthProfileRead:
        """Return all current-user facts for an authenticated profile UI."""

        profile = await self.get_long_term(self._actor_id)
        facts = await self._repository.list_facts(
            tenant_id=self._tenant_id,
            user_id=self._user_id,
            limit=200,
        )
        return HealthProfileRead.model_validate(
            {
                "schema_version": profile.schema_version,
                "version": profile.version,
                "cross_session_recall_enabled": profile.cross_session_recall_enabled,
                "profile": profile.profile,
                "facts": [_fact_view(fact) for fact in facts],
            }
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

    def _classify_owner_mutation(self, fact: MemoryFact, *, expected_revision: int) -> None:
        """Classify content only after repository ownership has been proven."""

        from gerclaw_api.modules.agent_harness.evolution_governance import (
            OnlineMutationRequest,
        )

        is_preference = fact.category == "preference"
        self._governance.classify_online_mutation(
            OnlineMutationRequest(
                object_kind="memory.preference" if is_preference else "memory.clinical_fact",
                requested_authority=(
                    "presentation_only" if is_preference else "untrusted_user_context"
                ),
                expected_revision=expected_revision,
            )
        )

    async def _save_revision(
        self,
        fact: MemoryFact,
        *,
        activity: str,
        snapshot: dict[str, JsonValue] | None = None,
    ) -> None:
        await self._repository.add_fact_revision(
            MemoryFactRevision(
                id=uuid.uuid4(),
                tenant_id=self._tenant_id,
                user_id=self._user_id,
                fact_id=fact.id,
                revision=fact.revision,
                activity=activity,
                snapshot=snapshot if snapshot is not None else _revision_snapshot(fact),
            )
        )

    async def _upsert_confirmed_vector(self, fact: MemoryFact) -> None:
        record = MemoryVectorRecord.model_validate(
            {
                "id": fact.id,
                "category": fact.category,
                "status": fact.status,
                "revision": fact.revision,
                "statement": fact.statement,
            }
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

    async def _rebuild_after_owner_mutation(
        self,
        fact: MemoryFact,
        *,
        profile: HealthProfile | None = None,
    ) -> MemoryFactMutationRead:
        await self._repository.flush()
        if profile is None:
            profile = await self._repository.lock_or_create_profile(
                tenant_id=self._tenant_id,
                user_id=self._user_id,
            )
        all_facts = await self._repository.list_facts(
            tenant_id=self._tenant_id,
            user_id=self._user_id,
            limit=200,
        )
        profile.profile = rebuild_profile(all_facts)
        profile.version += 1
        await self._repository.flush()
        self._cached_queries.clear()
        return MemoryFactMutationRead(
            fact=_fact_view(fact),
            profile_version=profile.version,
        )

    async def create_fact(self, request: MemoryFactCreateRequest) -> MemoryFactMutationRead:
        """Create one owner-authored proposed fact without granting it factual authority."""

        existing_profile = await self._repository.get_profile(
            tenant_id=self._tenant_id,
            user_id=self._user_id,
        )
        profile = await self._repository.lock_or_create_profile(
            tenant_id=self._tenant_id,
            user_id=self._user_id,
        )
        expected_profile_version = 0 if existing_profile is None else existing_profile.version
        if request.expected_profile_version != expected_profile_version or (
            existing_profile is None and profile.version != 1
        ):
            raise MemoryConflictError("health profile version is stale")
        event_identity = (
            _event_identity(
                occurred_at=request.occurred_at,
                trace_id="explicit-owner-create",
                evidence_span=request.statement,
            )
            if request.category == "event" or request.memory_type == "event"
            else None
        )
        fact_key = _fact_key(
            self._namespace_secret,
            category=request.category,
            entity=request.entity,
            event_identity=event_identity,
        )
        duplicate = await self._repository.get_fact_by_key_for_update(
            tenant_id=self._tenant_id,
            user_id=self._user_id,
            fact_key=fact_key,
        )
        if duplicate is not None:
            raise MemoryConflictError("memory fact already exists")
        details = request.details.model_dump(mode="json")
        details.update(
            {
                "entity": request.entity,
                "evidence_span": request.statement,
                "polarity": "positive",
                "source": "user_explicit_create",
                "proposal_source_status": "owner_authored",
            }
        )
        _validate_owner_evidence(
            category=request.category,
            entity=request.entity,
            statement=request.statement,
            details=request.details,
            occurred_at=request.occurred_at,
        )
        now = datetime.now(UTC)
        fact = MemoryFact(
            id=uuid.uuid4(),
            tenant_id=self._tenant_id,
            user_id=self._user_id,
            source_session_id=None if self._session_id.int == 0 else self._session_id,
            source_trace_id=self._trace_id,
            category=request.category,
            memory_type=request.memory_type,
            fact_key=fact_key,
            status="proposed",
            access_level=request.access_level,
            statement=request.statement,
            details=details,
            confidence=1.0,
            revision=1,
            vector_revision=0,
            occurred_at=request.occurred_at,
            confirmed_at=None,
            expires_at=(
                now + timedelta(days=self._transient_fact_ttl_days)
                if request.category in _TRANSIENT_CATEGORIES
                else None
            ),
            tombstoned_at=None,
            tombstone_reason=None,
            tombstone_previous_status=None,
        )
        self._classify_owner_mutation(fact, expected_revision=0)
        await self._repository.add_fact(fact)
        return await self._rebuild_after_owner_mutation(fact, profile=profile)

    async def update_fact(
        self,
        fact_id: uuid.UUID,
        request: MemoryFactUpdateRequest,
    ) -> MemoryFactMutationRead:
        """Correct one owner fact and withdraw it from recall until re-confirmed."""

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
        self._classify_owner_mutation(fact, expected_revision=request.expected_revision)
        if fact.revision != request.expected_revision:
            raise MemoryConflictError("memory fact revision is stale")
        if getattr(fact, "tombstoned_at", None) is not None:
            raise MemoryConflictError("tombstoned memory must be restored before update")
        original = _revision_snapshot(fact)
        details = dict(_PROFILE.validate_python(fact.details))
        if request.details is not None:
            details.update(request.details.model_dump(mode="json", exclude_unset=True))
        next_statement = request.statement if request.statement is not None else fact.statement
        if request.statement is not None:
            details["evidence_span"] = next_statement
        details["source"] = "user_explicit_update"
        details.pop("conflict_previous", None)
        next_occurred_at = (
            request.occurred_at if "occurred_at" in request.model_fields_set else fact.occurred_at
        )
        public_details = MemoryFactDetails.model_validate(
            {key: value for key, value in details.items() if key in MemoryFactDetails.model_fields}
        )
        entity = details.get("entity")
        if not isinstance(entity, str):
            raise MemoryDataError("stored memory fact entity is invalid")
        try:
            validate_memory_fact_shape(
                category=_MEMORY_CATEGORY.validate_python(fact.category),
                entity=entity,
                details=public_details,
            )
        except ValueError as error:
            raise MemoryEvidenceError(str(error)) from error
        _validate_owner_evidence(
            category=fact.category,
            entity=entity,
            statement=next_statement,
            details=public_details,
            occurred_at=next_occurred_at,
        )
        fact.statement = next_statement
        fact.details = details
        if request.access_level is not None:
            fact.access_level = request.access_level
        if "occurred_at" in request.model_fields_set:
            fact.occurred_at = next_occurred_at
        fact.source_trace_id = self._trace_id
        fact.source_session_id = None if self._session_id.int == 0 else self._session_id
        fact.status = "proposed"
        fact.confirmed_at = None
        if fact.category in _TRANSIENT_CATEGORIES:
            fact.expires_at = datetime.now(UTC) + timedelta(days=self._transient_fact_ttl_days)
        if _revision_snapshot(fact) == original:
            raise MemoryConflictError("memory fact update does not change content")
        await self._save_revision(fact, activity="user_update", snapshot=original)
        fact.revision += 1
        return await self._rebuild_after_owner_mutation(fact, profile=profile)

    async def delete_fact(
        self,
        fact_id: uuid.UUID,
        request: MemoryFactDeleteRequest,
    ) -> MemoryFactMutationRead:
        """Soft-delete one owner fact; the tombstone is immediately non-recallable."""

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
        self._classify_owner_mutation(fact, expected_revision=request.expected_revision)
        if fact.revision != request.expected_revision:
            raise MemoryConflictError("memory fact revision is stale")
        if getattr(fact, "tombstoned_at", None) is not None:
            raise MemoryConflictError("memory fact is already tombstoned")
        await self._save_revision(fact, activity="user_delete")
        fact.tombstone_previous_status = fact.status
        fact.status = "inactive"
        fact.tombstoned_at = datetime.now(UTC)
        fact.tombstone_reason = request.reason
        fact.source_trace_id = self._trace_id
        fact.revision += 1
        return await self._rebuild_after_owner_mutation(fact, profile=profile)

    async def restore_fact(
        self,
        fact_id: uuid.UUID,
        request: MemoryFactRestoreRequest,
    ) -> MemoryFactMutationRead:
        """Restore only an explicit owner tombstone, retaining its immutable history."""

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
        self._classify_owner_mutation(fact, expected_revision=request.expected_revision)
        if fact.revision != request.expected_revision:
            raise MemoryConflictError("memory fact revision is stale")
        previous_status = getattr(fact, "tombstone_previous_status", None)
        if getattr(fact, "tombstoned_at", None) is None or previous_status is None:
            raise MemoryConflictError("memory fact is not restorable")
        await self._save_revision(fact, activity="user_restore")
        fact.status = previous_status
        fact.tombstoned_at = None
        fact.tombstone_reason = None
        fact.tombstone_previous_status = None
        fact.source_trace_id = self._trace_id
        fact.revision += 1
        if fact.status == "confirmed":
            fact.confirmed_at = datetime.now(UTC)
            await self._upsert_confirmed_vector(fact)
        return await self._rebuild_after_owner_mutation(fact, profile=profile)

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
        self._classify_owner_mutation(fact, expected_revision=decision.expected_revision)
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
        if not isinstance(entity, str):
            raise MemoryDataError("stored memory fact entity is invalid")
        try:
            stored_public_details = MemoryFactDetails.model_validate(
                {
                    key: value
                    for key, value in stored_details.items()
                    if key in MemoryFactDetails.model_fields
                }
            )
            validate_memory_fact_shape(
                category=_MEMORY_CATEGORY.validate_python(fact.category),
                entity=entity,
                details=stored_public_details,
            )
            if not _normalized_evidence(fact.statement):
                raise ValueError("memory statement cannot be blank")
        except (TypeError, ValueError, ValidationError) as error:
            raise MemoryDataError("stored memory fact category shape is invalid") from error
        negative_evidence = stored_details.get("polarity") == "negative" or (
            isinstance(evidence, str)
            and evidence_has_negation(
                evidence,
                category=fact.category,
                entity=entity,
            )
        )
        await self._save_revision(fact, activity="user_decision")
        conflict_previous = stored_details.get("conflict_previous")
        if (
            decision.decision == "reject"
            and fact.status == "conflicted"
            and isinstance(conflict_previous, dict)
        ):
            try:
                fact.memory_type = _MEMORY_TYPE.validate_python(conflict_previous["memory_type"])
                fact.status = "confirmed"
                fact.access_level = _MEMORY_ACCESS_LEVEL.validate_python(
                    conflict_previous.get("access_level", "standard")
                )
                fact.statement = str(conflict_previous["statement"])
                fact.details = _PROFILE.validate_python(conflict_previous["details"])
                fact.confidence = _FLOAT.validate_python(conflict_previous["confidence"])
                fact.occurred_at = _OPTIONAL_DATETIME.validate_python(
                    conflict_previous.get("occurred_at")
                )
                fact.confirmed_at = _OPTIONAL_DATETIME.validate_python(
                    conflict_previous.get("confirmed_at")
                )
                fact.expires_at = _OPTIONAL_DATETIME.validate_python(
                    conflict_previous.get("expires_at")
                )
            except (KeyError, TypeError, ValueError, ValidationError) as error:
                raise MemoryDataError("stored memory conflict is invalid") from error
        elif decision.decision == "confirm":
            fact.status = "inactive" if negative_evidence else "confirmed"
            fact.access_level = decision.access_level
        else:
            fact.status = "inactive"
        fact.revision += 1
        if fact.status == "confirmed":
            fact.confirmed_at = datetime.now(UTC)
            record = MemoryVectorRecord.model_validate(
                {
                    "id": fact.id,
                    "category": fact.category,
                    "status": fact.status,
                    "revision": fact.revision,
                    "statement": fact.statement,
                }
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

    async def set_recall_preference(
        self,
        request: MemoryRecallPreferenceRequest,
    ) -> MemoryRecallPreferenceRead:
        """Replace the owner-controlled cross-session recall choice."""

        existing = await self._repository.get_profile(
            tenant_id=self._tenant_id,
            user_id=self._user_id,
        )
        profile = await self._repository.lock_or_create_profile(
            tenant_id=self._tenant_id,
            user_id=self._user_id,
        )
        expected_version = 0 if existing is None else existing.version
        if request.expected_profile_version != expected_version or (
            existing is None and profile.version != 1
        ):
            raise MemoryConflictError("health profile version is stale")
        profile.cross_session_recall_enabled = request.enabled
        profile.version += 1
        await self._repository.flush()
        self._cached_queries.clear()
        return MemoryRecallPreferenceRead(
            enabled=request.enabled,
            profile_version=profile.version,
        )

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
