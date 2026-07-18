# -*- coding: utf-8 -*-
"""GerClaw RAG Service 模式概念演示 — 知识库全生命周期Mock。

本示例演示 AgentScope RAG Service 模式下 KnowledgeBase 的完整 API 调用流程，
不启动真实的 FastAPI/Redis/Qdrant 服务，全部使用内存 Mock 对象，帮助理解：

  1. CollectionPerKbManager 创建知识库（KB 元数据落"库" + 分配 collection）；
  2. 文档上传 → BlobStore 暂存 → 状态置为 pending → 入队索引任务；
  3. IndexWorker 消费任务：抢 lease → Parser → Chunker → Embedding → 向量写入；
  4. 文档状态机轮询（pending → processing → ready）；
  5. POST /knowledge_bases/{kb_id}/search 语义检索流程。

示例数据：
  - 老年高血压管理指南片段
  - 老年2型糖尿病管理指南片段

本示例**不需要任何外部依赖**，直接 ``python medical_rag_service.py`` 即可运行。
真实部署时只需将 Mock 组件替换为：
  - RedisStorage         → 真实 Redis
  - InMemoryVectorStore  → QdrantStore(url="http://...")
  - InMemoryBlobStore    → LocalBlobStore / S3BlobStore
  - 调用 run_worker()    → 启动分布式索引 Worker

运行方式::

    python medical_rag_service.py
"""
from __future__ import annotations

import asyncio
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# 1. 模拟医学指南文档数据
# ---------------------------------------------------------------------------
MEDICAL_GUIDELINES: dict[str, dict[str, Any]] = {
    "老年高血压管理指南2023.md": {
        "content": (
            "# 中国老年高血压管理指南（2023）\n\n"
            "## 一、诊断标准\n"
            "65岁及以上老年人，在未使用降压药物的情况下，非同日3次测量血压，"
            "收缩压≥140mmHg和/或舒张压≥90mmHg，可诊断为老年高血压。"
            "80岁及以上高龄老年人，诊断标准相同，但降压目标可适当放宽。\n\n"
            "## 二、降压目标\n"
            "65-79岁老年人：首先将血压降至<140/90mmHg，如能耐受可降至<130/80mmHg。"
            "80岁及以上高龄老年人：降压目标为<150/90mmHg，"
            "衰弱老年人应根据个体化情况设定降压目标，避免过度降压导致跌倒风险。\n\n"
            "## 三、药物治疗推荐\n"
            "初始治疗推荐小剂量单药：噻嗪类利尿剂（吲达帕胺）、钙通道阻滞剂（氨氯地平）、"
            "ACEI/ARB类药物。合并糖尿病或蛋白尿者首选ACEI/ARB。"
            "联合用药推荐：CCB+ACEI/ARB，或CCB+噻嗪类利尿剂。\n\n"
            "## 四、注意事项\n"
            "老年高血压患者体位性低血压发生率高，起始用药后应监测立位血压。"
            "避免使用可能引起体位性低血压的α受体阻滞剂作为一线用药。"
            "降压速度不宜过快，2-3个月内逐渐达标。\n"
        ),
        "metadata": {"source_type": "guideline", "publish_year": 2023, "evidence_level": "A"},
    },
    "老年2型糖尿病管理.md": {
        "content": (
            "# 中国老年2型糖尿病防治临床指南（2022）\n\n"
            "## 一、血糖控制目标\n"
            "老年糖尿病患者应根据健康状况分层设定血糖控制目标："
            "健康状况良好（HbA1c<7.0%）、中等复杂（HbA1c<7.5%）、"
            "健康状况差/衰弱（HbA1c<8.0-8.5%），避免低血糖。\n\n"
            "## 二、药物治疗\n"
            "二甲双胍为一线用药，但eGFR<30ml/min/1.73m²禁用。"
            "SGLT2抑制剂（达格列净、恩格列净）有心肾保护作用，"
            "推荐合并心血管疾病或慢性肾病的老年患者使用。"
            "老年患者应慎用磺脲类药物（格列美脲等），低血糖风险高。\n\n"
            "## 三、低血糖预防\n"
            "老年糖尿病患者低血糖危害大，可诱发心脑血管事件和跌倒。"
            "应优先选择低血糖风险低的降糖药物，避免使用格列本脲。"
            "血糖监测：使用口服药者每周监测2-4次空腹及餐后血糖，"
            "使用胰岛素者应加强监测。\n\n"
            "## 四、综合管理\n"
            "老年糖尿病患者需综合管理血压（<130/80mmHg）、血脂（LDL-C<1.8mmol/L），"
            "每年筛查糖尿病视网膜病变、肾病和周围神经病变，"
            "进行老年综合评估（CGA），关注认知功能和跌倒风险。\n"
        ),
        "metadata": {"source_type": "guideline", "publish_year": 2022, "evidence_level": "A"},
    },
}


# ---------------------------------------------------------------------------
# 2. Mock 基础设施组件
# ---------------------------------------------------------------------------
class DocStatus(str, Enum):
    """模拟 KnowledgeDocumentStatus 状态机。"""
    PENDING = "pending"
    PARSING = "parsing"
    CHUNKING = "chunking"
    INDEXING = "indexing"
    READY = "ready"
    ERROR = "error"


@dataclass
class _KBRecord:
    kb_id: str
    name: str
    description: str
    collection_name: str
    embedding_model: str
    dimensions: int
    created_at: float


@dataclass
class _DocRecord:
    doc_id: str
    kb_id: str
    filename: str
    status: DocStatus
    chunk_count: int = 0
    error: str | None = None
    created_at: float = field(default_factory=time.time)


class _InMemoryBlobStore:
    """模拟 BlobStore：内存中暂存上传的文件字节。"""

    def __init__(self) -> None:
        self._blobs: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes) -> None:
        self._blobs[key] = data

    async def get(self, key: str) -> bytes:
        return self._blobs[key]

    async def delete(self, key: str) -> None:
        self._blobs.pop(key, None)


class _InMemoryVectorStore:
    """模拟 QdrantStore：使用字符级 Jaccard 相似度做简易检索。

    接口模拟 VectorStoreBase 的 insert/search/delete/list_documents。
    """

    def __init__(self) -> None:
        self._collections: dict[str, list[dict[str, Any]]] = {}

    async def create_collection(self, name: str, dimensions: int) -> None:
        self._collections.setdefault(name, [])

    async def insert(self, collection: str, records: list[dict[str, Any]]) -> None:
        self._collections.setdefault(collection, []).extend(records)

    async def delete(self, collection: str, document_id: str) -> None:
        if collection in self._collections:
            self._collections[collection] = [
                r for r in self._collections[collection] if r["document_id"] != document_id
            ]

    async def search(
        self,
        collection: str,
        query_text: str,
        top_k: int = 5,
        score_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        records = self._collections.get(collection, [])
        qchars = set(re.sub(r"\s+", "", query_text))
        scored = []
        for r in records:
            cchars = set(re.sub(r"\s+", "", r["text"]))
            if not qchars or not cchars:
                continue
            inter = len(qchars & cchars)
            union = len(qchars | cchars)
            score = inter / union if union else 0.0
            if score_threshold is not None and score < score_threshold:
                continue
            scored.append({**r, "score": round(score, 4)})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    async def list_documents(self, collection: str) -> list[dict[str, Any]]:
        records = self._collections.get(collection, [])
        docs: dict[str, dict[str, Any]] = {}
        for r in records:
            did = r["document_id"]
            if did not in docs:
                docs[did] = {
                    "document_id": did,
                    "source": r["source"],
                    "chunk_count": 0,
                    "metadata": r.get("metadata", {}),
                }
            docs[did]["chunk_count"] += 1
        return list(docs.values())


class _MockStorage:
    """模拟 RedisStorage：KB/Doc 元数据持久化。"""

    def __init__(self) -> None:
        self.kbs: dict[str, _KBRecord] = {}
        self.docs: dict[str, _DocRecord] = {}

    def upsert_kb(self, kb: _KBRecord) -> None:
        self.kbs[kb.kb_id] = kb

    def get_kb(self, kb_id: str) -> _KBRecord | None:
        return self.kbs.get(kb_id)

    def list_kbs(self) -> list[_KBRecord]:
        return list(self.kbs.values())

    def delete_kb(self, kb_id: str) -> None:
        self.kbs.pop(kb_id, None)
        doc_ids = [did for did, d in self.docs.items() if d.kb_id == kb_id]
        for did in doc_ids:
            self.docs.pop(did, None)

    def upsert_doc(self, doc: _DocRecord) -> None:
        self.docs[doc.doc_id] = doc

    def get_doc(self, doc_id: str) -> _DocRecord | None:
        return self.docs.get(doc_id)

    def list_docs(self, kb_id: str) -> list[_DocRecord]:
        return [d for d in self.docs.values() if d.kb_id == kb_id]


# ---------------------------------------------------------------------------
# 3. Mock CollectionPerKbManager + KB Service
# ---------------------------------------------------------------------------
@dataclass
class _MockKBManager:
    """模拟 CollectionPerKbManager。"""
    storage: _MockStorage
    vector_store: _InMemoryVectorStore
    blob_store: _InMemoryBlobStore
    _collection_counter: int = 0

    async def create_knowledge_base(
        self,
        name: str,
        description: str,
        embedding_model: str = "text-embedding-v4",
        dimensions: int = 1024,
    ) -> _KBRecord:
        self._collection_counter += 1
        kb_id = f"kb-{uuid.uuid4().hex[:10]}"
        collection = f"kb_collection_{self._collection_counter}"
        await self.vector_store.create_collection(collection, dimensions)
        kb = _KBRecord(
            kb_id=kb_id,
            name=name,
            description=description,
            collection_name=collection,
            embedding_model=embedding_model,
            dimensions=dimensions,
            created_at=time.time(),
        )
        self.storage.upsert_kb(kb)
        return kb

    async def delete_knowledge_base(self, kb_id: str) -> bool:
        kb = self.storage.get_kb(kb_id)
        if not kb:
            return False
        # 级联清理：删除vector collection中的所有文档
        all_docs = await self.vector_store.list_documents(kb.collection_name)
        for d in all_docs:
            await self.vector_store.delete(kb.collection_name, d["document_id"])
        self.storage.delete_kb(kb_id)
        return True

    def get_collection(self, kb_id: str) -> str:
        kb = self.storage.get_kb(kb_id)
        if not kb:
            raise ValueError(f"KB {kb_id} not found")
        return kb.collection_name


# ---------------------------------------------------------------------------
# 4. Mock 索引流水线（Parser → Chunker → Embedding → Insert）
# ---------------------------------------------------------------------------
def _mock_parse(content: bytes) -> list[str]:
    """模拟 TextParser：将 Markdown 按章节标题切为 Section（纯文本段落）。"""
    text = content.decode("utf-8")
    sections: list[str] = []
    current = ""
    for line in text.split("\n"):
        if line.startswith("## ") and current:
            sections.append(current.strip())
            current = line + "\n"
        else:
            current += line + "\n"
    if current.strip():
        sections.append(current.strip())
    return sections


def _mock_chunk(sections: list[str], chunk_size: int = 200, overlap: int = 20) -> list[str]:
    """模拟 ApproxTokenChunker：近似按字符长度切分。"""
    chunks: list[str] = []
    for sec in sections:
        text = sec
        while len(text) > chunk_size:
            chunks.append(text[:chunk_size])
            text = text[chunk_size - overlap:]
        if text.strip():
            chunks.append(text.strip())
    return chunks


def _mock_embed(texts: list[str]) -> list[list[float]]:
    """模拟 Embedding：返回随机向量（真实场景调用 DashScopeEmbeddingModel）。"""
    # 使用确定性的"伪向量"——基于文本hash生成，保证相同文本向量一致
    import hashlib
    vectors = []
    for t in texts:
        h = hashlib.md5(t.encode("utf-8")).digest()
        # 生成1024维确定性向量
        vec = [(b / 255.0) for b in h * 32][:1024]  # 16*64=1024
        vectors.append(vec)
    return vectors


async def _run_index_pipeline(
    kb_manager: _MockKBManager,
    kb_id: str,
    doc: _DocRecord,
    file_content: bytes,
    metadata: dict[str, Any],
) -> None:
    """模拟 IndexWorker 处理一个文档的完整索引流程。"""
    collection = kb_manager.get_collection(kb_id)
    try:
        # 1. Parsing
        doc.status = DocStatus.PARSING
        kb_manager.storage.upsert_doc(doc)
        print(f"    [Worker] 解析文档 {doc.filename} ...")
        await asyncio.sleep(0.05)
        sections = _mock_parse(file_content)

        # 2. Chunking
        doc.status = DocStatus.CHUNKING
        kb_manager.storage.upsert_doc(doc)
        print(f"    [Worker] 分块中 ...")
        await asyncio.sleep(0.05)
        chunks = _mock_chunk(sections)

        # 3. Embedding + Insert
        doc.status = DocStatus.INDEXING
        kb_manager.storage.upsert_doc(doc)
        print(f"    [Worker] 向量化并写入向量库（{len(chunks)} 个chunk）...")
        await asyncio.sleep(0.05)
        vectors = _mock_embed(chunks)
        records = [
            {
                "vector": vec,
                "document_id": doc.doc_id,
                "text": chunk,
                "source": doc.filename,
                "metadata": {**metadata, "doc_id": doc.doc_id},
            }
            for vec, chunk in zip(vectors, chunks)
        ]
        await kb_manager.vector_store.insert(collection, records)

        # 4. Ready
        doc.status = DocStatus.READY
        doc.chunk_count = len(chunks)
        kb_manager.storage.upsert_doc(doc)
        print(f"    [Worker] ✓ 文档 {doc.filename} 索引完成（{len(chunks)} chunks）")
    except Exception as e:
        doc.status = DocStatus.ERROR
        doc.error = str(e)
        kb_manager.storage.upsert_doc(doc)
        print(f"    [Worker] ✗ 文档 {doc.filename} 索引失败: {e}")


# ---------------------------------------------------------------------------
# 5. 模拟 REST API 调用流程
# ---------------------------------------------------------------------------
async def _demo_service_flow() -> None:
    """完整演示：创建KB → 上传文档 → 索引 → 状态轮询 → 检索。"""

    # ---- 5.1 初始化基础设施 ----
    print("=" * 60)
    print("GerClaw RAG Service 模式概念演示（Mock）")
    print("=" * 60)

    storage = _MockStorage()
    vector_store = _InMemoryVectorStore()
    blob_store = _InMemoryBlobStore()
    kb_manager = _MockKBManager(storage=storage, vector_store=vector_store, blob_store=blob_store)

    # ---- 5.2 POST /knowledge_bases （创建知识库）----
    print("\n[步骤1] 创建知识库 —— POST /knowledge_bases")
    kb = await kb_manager.create_knowledge_base(
        name="gerclaw-elderly-guidelines",
        description="GerClaw老年医学临床指南知识库（高血压、糖尿病等老年常见病）",
        embedding_model="text-embedding-v4",
        dimensions=1024,
    )
    print(f"  ✓ 知识库已创建: id={kb.kb_id}")
    print(f"    name={kb.name}")
    print(f"    collection={kb.collection_name}")
    print(f"    embedding_model={kb.embedding_model} (dim={kb.dimensions})")

    # ---- 5.3 POST /knowledge_bases/{kb_id}/documents （上传文档）----
    print("\n[步骤2] 上传临床指南文档 —— POST /knowledge_bases/{kb_id}/documents")
    upload_tasks: list[tuple[_DocRecord, bytes, dict]] = []
    for filename, info in MEDICAL_GUIDELINES.items():
        doc_id = f"doc-{uuid.uuid4().hex[:10]}"
        content_bytes = info["content"].encode("utf-8")
        blob_key = f"{kb.kb_id}/{doc_id}/{filename}"
        await blob_store.put(blob_key, content_bytes)
        doc = _DocRecord(
            doc_id=doc_id,
            kb_id=kb.kb_id,
            filename=filename,
            status=DocStatus.PENDING,
        )
        storage.upsert_doc(doc)
        upload_tasks.append((doc, content_bytes, info["metadata"]))
        print(f"  ✓ 上传 {filename} → doc_id={doc_id} [status=pending]")

    # ---- 5.4 IndexWorker 消费索引任务 ----
    print("\n[步骤3] IndexWorker 消费索引任务（模拟分布式Worker）")
    index_jobs = [
        _run_index_pipeline(kb_manager, kb.kb_id, doc, content, meta)
        for doc, content, meta in upload_tasks
    ]
    await asyncio.gather(*index_jobs)

    # ---- 5.5 GET /knowledge_bases/{kb_id}/documents/status （状态轮询）----
    print("\n[步骤4] 查询文档状态 —— GET /knowledge_bases/{kb_id}/documents/status")
    for doc in storage.list_docs(kb.kb_id):
        print(
            f"  · {doc.filename}: status={doc.status.value}, "
            f"chunks={doc.chunk_count}"
        )

    # ---- 5.6 GET /knowledge_bases （列出知识库）----
    print("\n[步骤5] 列出所有知识库 —— GET /knowledge_bases")
    for k in storage.list_kbs():
        doc_count = len(storage.list_docs(k.kb_id))
        print(f"  · {k.name} (id={k.kb_id}, docs={doc_count})")

    # ---- 5.7 POST /knowledge_bases/{kb_id}/search （语义检索）----
    print("\n[步骤6] 语义检索演示 —— POST /knowledge_bases/{kb_id}/search")
    queries = [
        "80岁以上老人血压控制到多少合适？",
        "老年糖尿病患者首选什么降糖药？肾功能不好要注意什么？",
        "老年高血压服药后头晕要警惕什么？",
    ]
    collection = kb_manager.get_collection(kb.kb_id)
    for q in queries:
        print(f"\n  [Query] {q}")
        results = await vector_store.search(
            collection=collection,
            query_text=q,
            top_k=2,
            score_threshold=0.05,
        )
        if not results:
            print("    (无检索结果)")
            continue
        for rank, r in enumerate(results, 1):
            snippet = r["text"].replace("\n", " ").strip()
            if len(snippet) > 100:
                snippet = snippet[:97] + "..."
            print(f"    [{rank}] score={r['score']:.3f} source={r['source']}")
            print(f"        {snippet}")

    # ---- 5.8 DELETE /knowledge_bases/{kb_id} （清理）----
    print("\n[步骤7] 清理知识库 —— DELETE /knowledge_bases/{kb_id}")
    await kb_manager.delete_knowledge_base(kb.kb_id)
    remaining = len(storage.list_kbs())
    print(f"  ✓ 知识库已删除（级联清理vector collection和文档记录）")
    print(f"  剩余知识库数: {remaining}")

    print("\n" + "=" * 60)
    print("RAG Service 概念演示完成。")
    print("=" * 60)
    print("\n迁移到生产环境的步骤：")
    print("  1. 将 _MockStorage 替换为 RedisStorage(host=..., port=6379)")
    print("  2. 将 _InMemoryVectorStore 替换为 QdrantStore(url='http://qdrant:6333')")
    print("  3. 将 _InMemoryBlobStore 替换为 LocalBlobStore(root_dir='/data/blobs')")
    print("     或 S3BlobStore(bucket='gerclaw-blobs')")
    print("  4. 将 _mock_embed 替换为 DashScopeEmbeddingModel（或本地BGE-M3）")
    print("  5. 将 _mock_parse/_mock_chunk 替换为 TextParser/PDFParser + ApproxTokenChunker")
    print("  6. 使用 create_app(knowledge_base_manager=CollectionPerKbManager(...)) 启动API")
    print("  7. 分布式部署：enable_index_worker=False，python -m agentscope.app.rag.index_worker")


# ---------------------------------------------------------------------------
# 6. 入口
# ---------------------------------------------------------------------------
async def main() -> None:
    await _demo_service_flow()


if __name__ == "__main__":
    asyncio.run(main())
