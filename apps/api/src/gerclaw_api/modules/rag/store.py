"""Qdrant dense+sparse RRF storage with strict medical-citation payloads."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from qdrant_client import AsyncQdrantClient, models

from gerclaw_api.modules.rag.lexical import LexicalEncoder
from gerclaw_api.modules.rag.models import (
    DocumentManifest,
    EmbeddedChunk,
    IndexChunk,
    StoredCandidate,
)
from gerclaw_api.modules.rag.protocols import RAGFilters

_DENSE_VECTOR = "dense"
_LEXICAL_VECTOR = "lexical"
_PAYLOAD_INDEXES: tuple[tuple[str, models.PayloadSchemaType], ...] = (
    ("document_id", models.PayloadSchemaType.KEYWORD),
    ("document_sha256", models.PayloadSchemaType.KEYWORD),
    ("source", models.PayloadSchemaType.KEYWORD),
    ("category", models.PayloadSchemaType.KEYWORD),
    ("source_type", models.PayloadSchemaType.KEYWORD),
    ("publish_year", models.PayloadSchemaType.INTEGER),
    ("chunk_index", models.PayloadSchemaType.INTEGER),
    ("index_version", models.PayloadSchemaType.KEYWORD),
    ("generation_id", models.PayloadSchemaType.KEYWORD),
    ("generation_complete", models.PayloadSchemaType.BOOL),
)


class RAGStoreError(RuntimeError):
    """Raised when the collection schema or stored payload is unsafe/incompatible."""


@dataclass(slots=True)
class _ManifestGroup:
    """One candidate generation reconstructed from completed point payloads."""

    document_id: str
    source: str
    document_sha256: str
    chunk_count: int
    index_version: str
    generation_id: str
    indexes: set[int] = field(default_factory=set)
    records: int = 0
    valid: bool = True


def _match_any(key: str, values: list[str]) -> models.FieldCondition:
    return models.FieldCondition(key=key, match=models.MatchAny(any=values))


def _match_value(key: str, value: str | bool | int) -> models.FieldCondition:
    return models.FieldCondition(key=key, match=models.MatchValue(value=value))


def _generation_filter(
    *,
    document_id: str,
    document_sha256: str,
    index_version: str,
    generation_id: str,
    complete: bool | None = None,
) -> models.Filter:
    must = [
        _match_value("document_id", document_id),
        _match_value("document_sha256", document_sha256),
        _match_value("index_version", index_version),
        _match_value("generation_id", generation_id),
    ]
    if complete is not None:
        must.append(_match_value("generation_complete", complete))
    return models.Filter(must=must)


def _point_id(chunk_id: str, index_version: str, generation_id: str) -> uuid.UUID:
    digest = hashlib.sha256(f"{chunk_id}:{index_version}:{generation_id}".encode()).hexdigest()
    return uuid.UUID(digest[:32])


def _query_filter(filters: RAGFilters | None) -> models.Filter | None:
    must: list[models.FieldCondition] = [_match_value("generation_complete", True)]
    if filters is not None and filters.categories:
        must.append(_match_any("category", filters.categories))
    if filters is not None and filters.source_types:
        must.append(_match_any("source_type", list(filters.source_types)))
    if filters is not None and filters.document_ids:
        must.append(_match_any("document_id", filters.document_ids))
    if filters is not None and (
        filters.publish_year_min is not None or filters.publish_year_max is not None
    ):
        must.append(
            models.FieldCondition(
                key="publish_year",
                range=models.Range(gte=filters.publish_year_min, lte=filters.publish_year_max),
            )
        )
    return models.Filter(must=must)


def _required_str(payload: dict[str, Any], key: str, *, maximum: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise RAGStoreError(f"stored RAG payload field {key} is invalid")
    return value


def _required_int(payload: dict[str, Any], key: str, *, minimum: int = 0) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise RAGStoreError(f"stored RAG payload field {key} is invalid")
    return value


def _chunk_from_payload(payload: dict[str, Any]) -> IndexChunk:
    source = _required_str(payload, "source", maximum=1_024)
    if source.startswith(("/", "\\")) or ".." in source.split("/"):
        raise RAGStoreError("stored RAG source is not knowledge-base-relative")
    source_type = _required_str(payload, "source_type", maximum=32)
    if source_type not in {"guideline", "consensus", "textbook", "literature"}:
        raise RAGStoreError("stored RAG source type is invalid")
    publish_year = payload.get("publish_year")
    if publish_year is not None and (
        isinstance(publish_year, bool)
        or not isinstance(publish_year, int)
        or not 1900 <= publish_year <= 2100
    ):
        raise RAGStoreError("stored RAG publish year is invalid")
    return IndexChunk(
        chunk_id=_required_str(payload, "chunk_id", maximum=64),
        document_id=_required_str(payload, "document_id", maximum=64),
        document_sha256=_required_str(payload, "document_sha256", maximum=64),
        source=source,
        title=_required_str(payload, "title", maximum=512),
        chapter=_required_str(payload, "chapter", maximum=1_024),
        category=_required_str(payload, "category", maximum=128),
        source_type=source_type,  # type: ignore[arg-type]
        publish_year=publish_year,
        chunk_index=_required_int(payload, "chunk_index"),
        total_chunks=_required_int(payload, "total_chunks", minimum=1),
        content=_required_str(payload, "content", maximum=8_000),
    )


def _lexical_document_text(chunk: IndexChunk) -> str:
    """Keep reviewed corpus classification searchable across document languages.

    Category is provider-independent, public corpus metadata.  Repeating it
    gives a bounded disease/topic label the same lexical emphasis as title
    while keeping user queries, session material and PHI out of the index.
    """

    return "\n".join(
        (
            chunk.category,
            chunk.category,
            chunk.title,
            chunk.title,
            chunk.chapter,
            chunk.content,
        )
    )


class QdrantHybridStore:
    """Own one named-vector collection and expose bounded hybrid operations."""

    def __init__(
        self,
        client: AsyncQdrantClient,
        *,
        collection: str,
        dimensions: int,
        upsert_batch_size: int,
    ) -> None:
        self._client = client
        self.collection = collection
        self.dimensions = dimensions
        self._upsert_batch_size = upsert_batch_size
        self._ready = False

    async def ensure_collection(self) -> None:
        """Create or validate the dense+sparse collection schema."""

        if self._ready:
            return
        exists = await self._client.collection_exists(self.collection)
        if not exists:
            await self._client.create_collection(
                collection_name=self.collection,
                vectors_config={
                    _DENSE_VECTOR: models.VectorParams(
                        size=self.dimensions,
                        distance=models.Distance.COSINE,
                        on_disk=True,
                    )
                },
                sparse_vectors_config={
                    _LEXICAL_VECTOR: models.SparseVectorParams(
                        index=models.SparseIndexParams(on_disk=True)
                    )
                },
                on_disk_payload=True,
            )
            for field_name, schema in _PAYLOAD_INDEXES:
                await self._client.create_payload_index(
                    collection_name=self.collection,
                    field_name=field_name,
                    field_schema=schema,
                    wait=True,
                )
        info = await self._client.get_collection(self.collection)
        for field_name, schema in _PAYLOAD_INDEXES:
            if field_name not in info.payload_schema:
                await self._client.create_payload_index(
                    collection_name=self.collection,
                    field_name=field_name,
                    field_schema=schema,
                    wait=True,
                )
        info = await self._client.get_collection(self.collection)
        vectors = info.config.params.vectors
        sparse_vectors = info.config.params.sparse_vectors
        if not isinstance(vectors, dict) or _DENSE_VECTOR not in vectors:
            raise RAGStoreError("RAG collection is missing its dense named vector")
        if vectors[_DENSE_VECTOR].size != self.dimensions:
            raise RAGStoreError("RAG collection dense-vector dimensions do not match configuration")
        if not isinstance(sparse_vectors, dict) or _LEXICAL_VECTOR not in sparse_vectors:
            raise RAGStoreError("RAG collection is missing its lexical sparse vector")
        self._ready = True

    async def replace_document(
        self,
        chunks: tuple[EmbeddedChunk, ...],
        *,
        index_version: str,
        generation_id: str,
    ) -> None:
        """Stage and activate a complete generation before removing stale points."""

        if not chunks:
            raise ValueError("replace_document requires at least one embedded chunk")
        if not 16 <= len(generation_id) <= 64 or any(
            character not in "0123456789abcdef-" for character in generation_id.casefold()
        ):
            raise ValueError("generation_id must be a bounded hexadecimal fencing token")
        await self.ensure_collection()
        document_id = chunks[0].chunk.document_id
        document_sha256 = chunks[0].chunk.document_sha256
        if any(
            item.chunk.document_id != document_id
            or item.chunk.document_sha256 != document_sha256
            or len(item.dense_vector) != self.dimensions
            for item in chunks
        ):
            raise RAGStoreError("embedded document batch is internally inconsistent")

        points: list[models.PointStruct] = []
        point_ids: list[models.ExtendedPointId] = []
        for item in chunks:
            chunk = item.chunk
            lexical = LexicalEncoder.encode(_lexical_document_text(chunk))
            payload: dict[str, Any] = {
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "document_sha256": chunk.document_sha256,
                "source": chunk.source,
                "title": chunk.title,
                "chapter": chunk.chapter,
                "category": chunk.category,
                "source_type": chunk.source_type,
                "chunk_index": chunk.chunk_index,
                "total_chunks": chunk.total_chunks,
                "content": chunk.content,
                "index_version": index_version,
                "generation_id": generation_id,
                "generation_complete": False,
            }
            if chunk.publish_year is not None:
                payload["publish_year"] = chunk.publish_year
            point_id = _point_id(chunk.chunk_id, index_version, generation_id)
            point_ids.append(point_id)
            points.append(
                models.PointStruct(
                    id=point_id,
                    vector={
                        _DENSE_VECTOR: list(item.dense_vector),
                        _LEXICAL_VECTOR: models.SparseVector(
                            indices=list(lexical.indices),
                            values=list(lexical.values),
                        ),
                    },
                    payload=payload,
                )
            )
        if await self._generation_is_complete(
            document_id=document_id,
            document_sha256=document_sha256,
            index_version=index_version,
            generation_id=generation_id,
            point_ids=point_ids,
        ):
            await self._delete_stale_points(document_id=document_id, point_ids=point_ids)
            return

        try:
            for offset in range(0, len(points), self._upsert_batch_size):
                await self._client.upsert(
                    collection_name=self.collection,
                    points=points[offset : offset + self._upsert_batch_size],
                    wait=True,
                )
            await self._client.set_payload(
                collection_name=self.collection,
                payload={"generation_complete": True},
                points=point_ids,
                wait=True,
            )
        except Exception:
            await self._delete_point_ids(point_ids)
            raise

        try:
            await self._delete_stale_points(document_id=document_id, point_ids=point_ids)
        except Exception:
            try:
                await self._delete_stale_points(document_id=document_id, point_ids=point_ids)
            except Exception as retry_error:
                raise RAGStoreError(
                    "new RAG generation is complete but stale-generation cleanup remains pending"
                ) from retry_error

    async def _delete_point_ids(self, point_ids: list[models.ExtendedPointId]) -> None:
        """Remove a failed staging generation without touching the previous complete one."""

        for offset in range(0, len(point_ids), self._upsert_batch_size):
            await self._client.delete(
                collection_name=self.collection,
                points_selector=point_ids[offset : offset + self._upsert_batch_size],
                wait=True,
            )

    async def _delete_stale_points(
        self,
        *,
        document_id: str,
        point_ids: list[models.ExtendedPointId],
    ) -> None:
        """Delete only IDs observed now, never a future writer generation."""

        keep = {uuid.UUID(str(point_id)) for point_id in point_ids}
        observed = await self._point_ids_matching(
            models.Filter(must=[_match_value("document_id", document_id)])
        )
        await self._delete_point_ids([point_id for point_id in observed if point_id not in keep])

    async def _point_ids_matching(
        self, scroll_filter: models.Filter
    ) -> list[models.ExtendedPointId]:
        """Snapshot point IDs so a delayed delete cannot include future points."""

        point_ids: list[models.ExtendedPointId] = []
        offset: int | str | uuid.UUID | None = None
        while True:
            records, offset = await self._client.scroll(
                collection_name=self.collection,
                scroll_filter=scroll_filter,
                limit=256,
                offset=offset,
                with_payload=False,
                with_vectors=False,
            )
            for record in records:
                try:
                    point_ids.append(uuid.UUID(str(record.id)))
                except (TypeError, ValueError, AttributeError) as error:
                    raise RAGStoreError("stored RAG point ID is invalid") from error
            if offset is None:
                return point_ids

    async def _generation_is_complete(
        self,
        *,
        document_id: str,
        document_sha256: str,
        index_version: str,
        generation_id: str,
        point_ids: list[models.ExtendedPointId],
    ) -> bool:
        """Verify the exact deterministic point set before treating a retry as complete."""

        expected = {uuid.UUID(str(point_id)) for point_id in point_ids}
        observed: set[uuid.UUID] = set()
        offset: int | str | uuid.UUID | None = None
        while True:
            records, offset = await self._client.scroll(
                collection_name=self.collection,
                scroll_filter=_generation_filter(
                    document_id=document_id,
                    document_sha256=document_sha256,
                    index_version=index_version,
                    generation_id=generation_id,
                    complete=True,
                ),
                limit=256,
                offset=offset,
                with_payload=False,
                with_vectors=False,
            )
            for record in records:
                try:
                    observed.add(uuid.UUID(str(record.id)))
                except (TypeError, ValueError, AttributeError):
                    return False
            if offset is None:
                break
        return observed == expected

    async def delete_documents(self, document_ids: Iterable[str]) -> int:
        """Delete complete documents and return the requested deletion count."""

        values = sorted(set(document_ids))
        if not values:
            return 0
        await self.ensure_collection()
        for offset in range(0, len(values), 50):
            point_ids = await self._point_ids_matching(
                models.Filter(must=[_match_any("document_id", values[offset : offset + 50])])
            )
            await self._delete_point_ids(point_ids)
        return len(values)

    async def delete_incomplete_points(self) -> int:
        """Remove abandoned fenced staging points from earlier failed workers."""

        if not await self._client.collection_exists(self.collection):
            return 0
        await self.ensure_collection()
        point_ids = await self._point_ids_matching(
            models.Filter(must=[_match_value("generation_complete", False)])
        )
        await self._delete_point_ids(point_ids)
        return len(point_ids)

    async def manifest(self) -> dict[str, DocumentManifest]:
        """Return only sources having exactly one complete, contiguous generation."""

        if not await self._client.collection_exists(self.collection):
            return {}
        await self.ensure_collection()
        groups: dict[tuple[str, str, str, str, str], _ManifestGroup] = {}
        offset: int | str | uuid.UUID | None = None
        while True:
            records, offset = await self._client.scroll(
                collection_name=self.collection,
                scroll_filter=models.Filter(must=[_match_value("generation_complete", True)]),
                limit=256,
                offset=offset,
                with_payload=[
                    "document_id",
                    "document_sha256",
                    "source",
                    "chunk_index",
                    "total_chunks",
                    "index_version",
                    "generation_id",
                ],
                with_vectors=False,
            )
            for record in records:
                payload = record.payload or {}
                document_id = _required_str(payload, "document_id", maximum=64)
                source = _required_str(payload, "source", maximum=1_024)
                if source.startswith(("/", "\\")) or ".." in source.split("/"):
                    raise RAGStoreError("stored RAG source is not knowledge-base-relative")
                document_sha256 = _required_str(payload, "document_sha256", maximum=64)
                chunk_count = _required_int(payload, "total_chunks", minimum=1)
                index_version = _required_str(payload, "index_version", maximum=128)
                raw_generation_id = payload.get("generation_id")
                generation_id = (
                    "legacy"
                    if raw_generation_id is None
                    else _required_str(payload, "generation_id", maximum=64)
                )
                chunk_index = _required_int(payload, "chunk_index")
                key = (source, document_id, document_sha256, index_version, generation_id)
                group = groups.setdefault(
                    key,
                    _ManifestGroup(
                        document_id=document_id,
                        source=source,
                        document_sha256=document_sha256,
                        chunk_count=chunk_count,
                        index_version=index_version,
                        generation_id=generation_id,
                    ),
                )
                group.records += 1
                if chunk_count != group.chunk_count or chunk_index >= group.chunk_count:
                    group.valid = False
                if chunk_index in group.indexes:
                    group.valid = False
                group.indexes.add(chunk_index)
            if offset is None:
                break
        candidates: dict[str, list[DocumentManifest]] = {}
        source_group_counts: dict[str, int] = {}
        for group in groups.values():
            source_group_counts[group.source] = source_group_counts.get(group.source, 0) + 1
            if (
                not group.valid
                or group.records != group.chunk_count
                or group.indexes != set(range(group.chunk_count))
            ):
                continue
            candidates.setdefault(group.source, []).append(
                DocumentManifest(
                    document_id=group.document_id,
                    source=group.source,
                    document_sha256=group.document_sha256,
                    chunk_count=group.chunk_count,
                    index_version=group.index_version,
                )
            )
        result = {
            source: manifests[0]
            for source, manifests in candidates.items()
            if len(manifests) == 1 and source_group_counts[source] == 1
        }
        return result

    async def document_inventory(self) -> dict[str, set[str]]:
        """Return every observed source/document ID, independent of generation validity."""

        if not await self._client.collection_exists(self.collection):
            return {}
        await self.ensure_collection()
        inventory: dict[str, set[str]] = {}
        offset: int | str | uuid.UUID | None = None
        while True:
            records, offset = await self._client.scroll(
                collection_name=self.collection,
                limit=256,
                offset=offset,
                with_payload=["document_id", "source"],
                with_vectors=False,
            )
            for record in records:
                payload = record.payload or {}
                source = _required_str(payload, "source", maximum=1_024)
                if source.startswith(("/", "\\")) or ".." in source.split("/"):
                    raise RAGStoreError("stored RAG source is not knowledge-base-relative")
                document_id = _required_str(payload, "document_id", maximum=64)
                inventory.setdefault(source, set()).add(document_id)
            if offset is None:
                return inventory

    async def search(
        self,
        *,
        dense_vector: list[float],
        lexical_query: str,
        limit: int,
        filters: RAGFilters | None,
    ) -> list[StoredCandidate]:
        """Fuse dense and sparse retrieval using Qdrant RRF."""

        await self.ensure_collection()
        if len(dense_vector) != self.dimensions:
            raise RAGStoreError("query embedding dimensions do not match the RAG collection")
        lexical = LexicalEncoder.encode(lexical_query)
        query_filter = _query_filter(filters)
        if lexical.indices:
            response = await self._client.query_points(
                collection_name=self.collection,
                prefetch=[
                    models.Prefetch(
                        query=dense_vector,
                        using=_DENSE_VECTOR,
                        limit=limit,
                        filter=query_filter,
                    ),
                    models.Prefetch(
                        query=models.SparseVector(
                            indices=list(lexical.indices), values=list(lexical.values)
                        ),
                        using=_LEXICAL_VECTOR,
                        limit=limit,
                        filter=query_filter,
                    ),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
        else:
            response = await self._client.query_points(
                collection_name=self.collection,
                query=dense_vector,
                using=_DENSE_VECTOR,
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
        candidates: dict[tuple[str, int], StoredCandidate] = {}
        for point in response.points:
            chunk = _chunk_from_payload(point.payload or {})
            key = (chunk.document_id, chunk.chunk_index)
            candidate = StoredCandidate(chunk=chunk, hybrid_score=float(point.score))
            if key not in candidates or candidate.hybrid_score > candidates[key].hybrid_score:
                candidates[key] = candidate
        return sorted(candidates.values(), key=lambda item: item.hybrid_score, reverse=True)[:limit]

    async def stats(self) -> tuple[int, int]:
        """Return exact document and chunk counts for readiness."""

        if not await self._client.collection_exists(self.collection):
            return 0, 0
        await self.ensure_collection()
        documents = await self._client.count(
            collection_name=self.collection,
            count_filter=models.Filter(
                must=[
                    _match_value("chunk_index", 0),
                    _match_value("generation_complete", True),
                ]
            ),
            exact=True,
        )
        chunks = await self._client.count(
            collection_name=self.collection,
            count_filter=models.Filter(must=[_match_value("generation_complete", True)]),
            exact=True,
        )
        return int(documents.count), int(chunks.count)
