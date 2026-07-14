"""PHI-free Qdrant vector index for encrypted PostgreSQL memory facts."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import uuid
from collections.abc import Sequence

from qdrant_client import AsyncQdrantClient, models

from gerclaw_api.modules.memory.models import MemoryVectorCandidate, MemoryVectorRecord

_DENSE_VECTOR = "dense"
_PAYLOAD_INDEXES: tuple[tuple[str, models.PayloadSchemaType], ...] = (
    ("tenant_namespace", models.PayloadSchemaType.KEYWORD),
    ("user_namespace", models.PayloadSchemaType.KEYWORD),
    ("fact_id", models.PayloadSchemaType.KEYWORD),
    ("category", models.PayloadSchemaType.KEYWORD),
    ("status", models.PayloadSchemaType.KEYWORD),
    ("revision", models.PayloadSchemaType.INTEGER),
)


class MemoryStoreError(RuntimeError):
    """Safe signal for incompatible or invalid user-memory vector state."""


def memory_namespace(secret: bytes, *, tenant_id: str, user_id: uuid.UUID) -> tuple[str, str]:
    """Return non-enumerable Qdrant filter values without exposing principals."""

    tenant = hmac.new(secret, f"memory:tenant:{tenant_id}".encode(), hashlib.sha256).hexdigest()
    user = hmac.new(
        secret,
        f"memory:user:{tenant_id}:{user_id}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return tenant, user


def _match(key: str, value: str | int) -> models.FieldCondition:
    return models.FieldCondition(key=key, match=models.MatchValue(value=value))


def memory_point_id(fact_id: uuid.UUID, revision: int) -> uuid.UUID:
    """Fence vector revisions so a rolled-back writer cannot replace committed state."""

    return uuid.uuid5(fact_id, f"memory-revision:{revision}")


class QdrantMemoryStore:
    """Dense vector references whose free text remains encrypted in PostgreSQL."""

    def __init__(
        self,
        client: AsyncQdrantClient,
        *,
        collection: str,
        dimensions: int,
        min_score: float,
    ) -> None:
        self._client = client
        self.collection = collection
        self.dimensions = dimensions
        self._min_score = min_score
        self._ready = False
        self._ensure_lock = asyncio.Lock()

    async def ensure_collection(self, *, force: bool = False) -> None:
        """Create or validate the collection, optionally bypassing the hot-path cache."""

        if self._ready and not force:
            return
        async with self._ensure_lock:
            if self._ready and not force:
                return
            if not await self._client.collection_exists(self.collection):
                try:
                    await self._client.create_collection(
                        collection_name=self.collection,
                        vectors_config={
                            _DENSE_VECTOR: models.VectorParams(
                                size=self.dimensions,
                                distance=models.Distance.COSINE,
                                on_disk=True,
                            )
                        },
                        on_disk_payload=True,
                    )
                except Exception:
                    # Another API replica may have won the create race. Only
                    # suppress that race after the shared service confirms the
                    # collection now exists; auth/network/schema errors re-raise.
                    if not await self._client.collection_exists(self.collection):
                        raise
            info = await self._client.get_collection(self.collection)
            for field_name, schema in _PAYLOAD_INDEXES:
                if field_name not in info.payload_schema:
                    try:
                        await self._client.create_payload_index(
                            collection_name=self.collection,
                            field_name=field_name,
                            field_schema=schema,
                            wait=True,
                        )
                    except Exception:
                        # Payload-index creation is also shared across replicas.
                        # Re-read authoritative state before treating a response
                        # as the harmless loser of an initialization race.
                        refreshed = await self._client.get_collection(self.collection)
                        if field_name not in refreshed.payload_schema:
                            raise
            info = await self._client.get_collection(self.collection)
            vectors = info.config.params.vectors
            if not isinstance(vectors, dict) or _DENSE_VECTOR not in vectors:
                raise MemoryStoreError("memory collection is missing its dense vector")
            if vectors[_DENSE_VECTOR].size != self.dimensions:
                raise MemoryStoreError(
                    "memory collection vector dimensions do not match configuration"
                )
            self._ready = True

    async def upsert(
        self,
        records: Sequence[MemoryVectorRecord],
        vectors: Sequence[list[float]],
        *,
        tenant_namespace: str,
        user_namespace: str,
    ) -> None:
        """Index fact references and revisions without persisting fact text."""

        if len(records) != len(vectors):
            raise ValueError("memory records and vectors must have equal length")
        if not records:
            return
        await self.ensure_collection()
        points: list[models.PointStruct] = []
        for record, vector in zip(records, vectors, strict=True):
            if record.status != "confirmed":
                raise MemoryStoreError("only confirmed memory facts may be indexed")
            if len(vector) != self.dimensions:
                raise MemoryStoreError("memory embedding dimensions are invalid")
            points.append(
                models.PointStruct(
                    id=memory_point_id(record.id, record.revision),
                    vector={_DENSE_VECTOR: vector},
                    payload={
                        "tenant_namespace": tenant_namespace,
                        "user_namespace": user_namespace,
                        "fact_id": str(record.id),
                        "category": record.category,
                        "status": record.status,
                        "revision": record.revision,
                    },
                )
            )
        await self._client.upsert(
            collection_name=self.collection,
            points=points,
            wait=True,
        )

    async def delete(self, fact_ids: Sequence[uuid.UUID]) -> None:
        """Delete an explicit fact-ID snapshot, never a broad future-matching filter."""

        if not fact_ids or not await self._client.collection_exists(self.collection):
            return
        point_ids: list[int | str | uuid.UUID] = []
        offset: int | str | uuid.UUID | None = None
        fact_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="fact_id",
                    match=models.MatchAny(any=[str(item) for item in fact_ids]),
                )
            ]
        )
        while True:
            points, offset = await self._client.scroll(
                collection_name=self.collection,
                scroll_filter=fact_filter,
                limit=256,
                offset=offset,
                with_payload=False,
                with_vectors=False,
            )
            point_ids.extend(point.id for point in points)
            if offset is None:
                break
        if not point_ids:
            return
        await self._client.delete(
            collection_name=self.collection,
            points_selector=models.PointIdsList(points=point_ids),
            wait=True,
        )

    async def delete_points(self, point_ids: Sequence[uuid.UUID]) -> None:
        """Delete only exact fenced revisions created by the current unit of work."""

        if not point_ids or not await self._client.collection_exists(self.collection):
            return
        await self._client.delete(
            collection_name=self.collection,
            points_selector=models.PointIdsList(points=list(dict.fromkeys(point_ids))),
            wait=True,
        )

    async def search(
        self,
        vector: list[float],
        *,
        tenant_namespace: str,
        user_namespace: str,
        limit: int,
        point_ids: Sequence[uuid.UUID] | None = None,
    ) -> list[MemoryVectorCandidate]:
        """Return bounded references scoped by HMAC namespaces."""

        await self.ensure_collection()
        if len(vector) != self.dimensions:
            raise MemoryStoreError("memory query embedding dimensions are invalid")
        conditions: list[models.Condition] = [
            _match("tenant_namespace", tenant_namespace),
            _match("user_namespace", user_namespace),
            _match("status", "confirmed"),
        ]
        if point_ids is not None:
            if not point_ids:
                return []
            conditions.append(models.HasIdCondition(has_id=list(point_ids)))
        response = await self._client.query_points(
            collection_name=self.collection,
            query=vector,
            using=_DENSE_VECTOR,
            query_filter=models.Filter(must=conditions),
            score_threshold=self._min_score,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        candidates: list[MemoryVectorCandidate] = []
        for point in response.points:
            payload = point.payload or {}
            raw_id = payload.get("fact_id")
            raw_revision = payload.get("revision")
            raw_category = payload.get("category")
            if (
                not isinstance(raw_id, str)
                or isinstance(raw_revision, bool)
                or not isinstance(raw_revision, int)
                or not isinstance(raw_category, str)
            ):
                raise MemoryStoreError("stored memory vector payload is invalid")
            try:
                candidate = MemoryVectorCandidate(
                    fact_id=uuid.UUID(raw_id),
                    revision=raw_revision,
                    category=raw_category,
                    score=max(0.0, min(1.0, float(point.score))),
                )
            except (TypeError, ValueError) as error:
                raise MemoryStoreError("stored memory vector reference is invalid") from error
            if str(point.id) != str(memory_point_id(candidate.fact_id, candidate.revision)):
                raise MemoryStoreError("memory point ID does not match its fenced revision")
            candidates.append(candidate)
        return candidates

    async def count(self) -> int:
        """Return the exact indexed fact count for readiness and tests."""

        if not await self._client.collection_exists(self.collection):
            return 0
        await self.ensure_collection()
        result = await self._client.count(collection_name=self.collection, exact=True)
        return int(result.count)
