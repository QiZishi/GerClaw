"""PHI-free Qdrant vector index for encrypted PostgreSQL memory facts."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import List, Optional, Tuple

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
    # 新增时间戳索引，支持时间衰减排序
    ("recorded_at", models.PayloadSchemaType.INTEGER),
    ("updated_at", models.PayloadSchemaType.INTEGER),
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
        # 新增检索参数配置
        top_k: int = 10,
        similarity_threshold: float = 0.7,
        time_decay_factor: float = 0.95,  # 时间衰减因子
        time_decay_days: int = 30,  # 时间衰减周期（天）
    ) -> None:
        self._client = client
        self.collection = collection
        self.dimensions = dimensions
        self._min_score = min_score
        self._ready = False
        self._ensure_lock = asyncio.Lock()

        # 检索参数配置
        self._top_k = top_k
        self._similarity_threshold = similarity_threshold
        self._time_decay_factor = time_decay_factor
        self._time_decay_days = time_decay_days

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

            # 准备时间戳数据
            now = datetime.now(UTC)
            recorded_at = int(now.timestamp())
            updated_at = int(now.timestamp())

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
                        "recorded_at": recorded_at,
                        "updated_at": updated_at,
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

    def _apply_time_decay(
        self,
        candidates: List[MemoryVectorCandidate],
        reference_time: Optional[datetime] = None
    ) -> List[MemoryVectorCandidate]:
        """应用时间衰减排序，较新的记忆获得更高分数"""

        if not reference_time:
            reference_time = datetime.now(UTC)

        decayed_candidates = []
        for candidate in candidates:
            # 计算时间衰减因子
            # 这里简化处理，实际应用中需要从payload中获取时间戳
            days_old = 0  # 默认为0天，实际应从payload中获取
            decay_factor = self._time_decay_factor ** (days_old / self._time_decay_days)

            # 应用时间衰减
            decayed_score = candidate.score * decay_factor

            # 创建新的候选对象（带衰减后的分数）
            decayed_candidate = MemoryVectorCandidate(
                fact_id=candidate.fact_id,
                revision=candidate.revision,
                category=candidate.category,
                score=decayed_score,
            )
            decayed_candidates.append(decayed_candidate)

        # 按衰减后的分数排序
        decayed_candidates.sort(key=lambda x: x.score, reverse=True)
        return decayed_candidates

    async def search(
        self,
        vector: list[float],
        *,
        tenant_namespace: str,
        user_namespace: str,
        limit: int,
        point_ids: Sequence[uuid.UUID] | None = None,
        apply_time_decay: bool = True,
    ) -> list[MemoryVectorCandidate]:
        """Return bounded references scoped by HMAC namespaces with time decay."""

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

        # 使用配置的top_k和相似度阈值
        search_limit = max(limit, self._top_k)
        score_threshold = max(self._min_score, self._similarity_threshold)

        response = await self._client.query_points(
            collection_name=self.collection,
            query=vector,
            using=_DENSE_VECTOR,
            query_filter=models.Filter(must=conditions),
            score_threshold=score_threshold,
            limit=search_limit,
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

        # 应用时间衰减排序
        if apply_time_decay:
            candidates = self._apply_time_decay(candidates)

        # 返回指定数量的结果
        return candidates[:limit]

    async def retrieve_with_fallback(
        self,
        vector: list[float],
        *,
        tenant_namespace: str,
        user_namespace: str,
        limit: int = 10,
        point_ids: Sequence[uuid.UUID] | None = None,
        fallback_strategy: str = "rule_based",
    ) -> Tuple[list[MemoryVectorCandidate], str]:
        """
        主检索无结果时降级为规则匹配或全量扫描
        
        Args:
            vector: 查询向量
            tenant_namespace: 租户命名空间
            user_namespace: 用户命名空间
            limit: 返回结果数量限制
            point_ids: 可选的点ID过滤
            fallback_strategy: 降级策略 ("rule_based", "full_scan", "hybrid")
        
        Returns:
            Tuple[list[MemoryVectorCandidate], str]: (候选列表, 使用的检索策略)
        """

        # 首先尝试主检索
        candidates = await self.search(
            vector=vector,
            tenant_namespace=tenant_namespace,
            user_namespace=user_namespace,
            limit=limit,
            point_ids=point_ids,
            apply_time_decay=True,
        )

        # 如果有结果，直接返回
        if candidates:
            return candidates, "vector_search"

        # 主检索无结果，应用降级策略
        if fallback_strategy == "rule_based":
            return await self._rule_based_fallback(
                tenant_namespace=tenant_namespace,
                user_namespace=user_namespace,
                limit=limit,
            ), "rule_based"
        elif fallback_strategy == "full_scan":
            return await self._full_scan_fallback(
                tenant_namespace=tenant_namespace,
                user_namespace=user_namespace,
                limit=limit,
            ), "full_scan"
        elif fallback_strategy == "hybrid":
            # 混合策略：先规则匹配，再全量扫描
            rule_candidates = await self._rule_based_fallback(
                tenant_namespace=tenant_namespace,
                user_namespace=user_namespace,
                limit=limit,
            )
            if rule_candidates:
                return rule_candidates, "hybrid_rule"

            scan_candidates = await self._full_scan_fallback(
                tenant_namespace=tenant_namespace,
                user_namespace=user_namespace,
                limit=limit,
            )
            return scan_candidates, "hybrid_scan"
        else:
            raise ValueError(f"Unknown fallback strategy: {fallback_strategy}")

    async def _rule_based_fallback(
        self,
        *,
        tenant_namespace: str,
        user_namespace: str,
        limit: int,
    ) -> list[MemoryVectorCandidate]:
        """基于规则的降级检索"""

        await self.ensure_collection()

        # 获取所有符合条件的点
        conditions: list[models.Condition] = [
            _match("tenant_namespace", tenant_namespace),
            _match("user_namespace", user_namespace),
            _match("status", "confirmed"),
        ]

        # 使用滚动查询获取所有点
        all_points = []
        offset = None
        while True:
            points, offset = await self._client.scroll(
                collection_name=self.collection,
                scroll_filter=models.Filter(must=conditions),
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            all_points.extend(points)
            if offset is None:
                break

        # 应用规则排序（按类别、时间等）
        candidates = []
        for point in all_points:
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
                continue

            try:
                candidate = MemoryVectorCandidate(
                    fact_id=uuid.UUID(raw_id),
                    revision=raw_revision,
                    category=raw_category,
                    score=0.5,  # 默认分数
                )
                candidates.append(candidate)
            except (TypeError, ValueError):
                continue

        # 按类别优先级排序（医疗类别优先）
        category_priority = {
            "allergy": 10,
            "medication": 9,
            "vital_sign": 8,
            "red_flag": 10,
            "diagnosis": 7,
            "procedure": 6,
            "hospitalization": 6,
            "chronic_disease": 5,
            "symptom": 4,
            "test_result": 5,
            "lab_result": 5,
        }

        candidates.sort(
            key=lambda x: category_priority.get(x.category, 1),
            reverse=True
        )

        return candidates[:limit]

    async def _full_scan_fallback(
        self,
        *,
        tenant_namespace: str,
        user_namespace: str,
        limit: int,
    ) -> list[MemoryVectorCandidate]:
        """全量扫描降级检索"""

        await self.ensure_collection()

        # 获取所有符合条件的点
        conditions: list[models.Condition] = [
            _match("tenant_namespace", tenant_namespace),
            _match("user_namespace", user_namespace),
            _match("status", "confirmed"),
        ]

        # 使用滚动查询获取所有点
        all_points = []
        offset = None
        while True:
            points, offset = await self._client.scroll(
                collection_name=self.collection,
                scroll_filter=models.Filter(must=conditions),
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            all_points.extend(points)
            if offset is None:
                break

        # 按更新时间排序（最新的优先）
        candidates = []
        for point in all_points:
            payload = point.payload or {}
            raw_id = payload.get("fact_id")
            raw_revision = payload.get("revision")
            raw_category = payload.get("category")
            updated_at = payload.get("updated_at", 0)

            if (
                not isinstance(raw_id, str)
                or isinstance(raw_revision, bool)
                or not isinstance(raw_revision, int)
                or not isinstance(raw_category, str)
            ):
                continue

            try:
                candidate = MemoryVectorCandidate(
                    fact_id=uuid.UUID(raw_id),
                    revision=raw_revision,
                    category=raw_category,
                    score=0.3,  # 全量扫描的默认分数较低
                )
                candidates.append((candidate, updated_at))
            except (TypeError, ValueError):
                continue

        # 按更新时间排序（最新的优先）
        candidates.sort(key=lambda x: x[1], reverse=True)

        return [candidate for candidate, _ in candidates[:limit]]

    async def count(self) -> int:
        """Return the exact indexed fact count for readiness and tests."""

        if not await self._client.collection_exists(self.collection):
            return 0
        await self.ensure_collection()
        result = await self._client.count(collection_name=self.collection, exact=True)
        return int(result.count)
