# -*- coding: utf-8 -*-
"""GerClaw 嵌入式RAG示例 — 老年便秘临床指南问答。

本示例演示 AgentScope RAGMiddleware 的嵌入式用法（library mode）：
  1. 将《中国老年慢性便秘诊疗专家共识》片段作为 Markdown 文本加载；
  2. 使用 TextParser + ApproxTokenChunker 完成解析与分块；
  3. 优先使用 QdrantStore(:memory:) + DashScopeEmbeddingModel 做真实向量检索；
     若 qdrant-client 未安装或无 DASHSCOPE_API_KEY，则自动降级为基于
     关键词重叠的简单字典模拟检索，保证示例在任何环境都可运行；
  4. 将 KnowledgeBase 通过 RAGMiddleware(mode="static") 挂载到 Agent；
  5. Agent 回答老年便秘临床问题时自动检索指南片段，并在回答中标注来源。

运行方式::

    # 真实向量检索（需要 DASHSCOPE_API_KEY 和 qdrant-client）：
    DASHSCOPE_API_KEY=sk-xxx python guideline_rag.py

    # Mock 模式（无需任何外部依赖）：
    python guideline_rag.py
"""
from __future__ import annotations

import asyncio
import math
import os
import re
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# 1. 模拟老年便秘临床指南片段（真实场景中来自 PDFParser 解析的临床指南 PDF）
# ---------------------------------------------------------------------------
GUIDELINE_DOCS: dict[str, bytes] = {
    "老年慢性便秘诊疗共识_非手术治疗.md": (
        "# 中国老年慢性便秘诊疗专家共识（2023）— 非手术治疗\n\n"
        "## 一、基础治疗\n\n"
        "生活方式调整是老年慢性便秘的首选基础治疗措施，包括：\n"
        "1. 充足膳食纤维摄入：推荐每日25-30g膳食纤维，优先选择蔬菜、水果、全谷物；\n"
        "2. 充足饮水：每日饮水1500-1700ml，少量多次，避免一次性大量饮水增加心脏负担；\n"
        "3. 规律运动：鼓励散步、太极拳等有氧运动，每日30分钟，每周至少5次；\n"
        "4. 建立良好排便习惯：建议晨起或餐后2小时内尝试排便，每次不超过10分钟，避免用力。\n\n"
        "## 二、渗透性泻剂（一线用药）\n\n"
        "聚乙二醇（PEG）是老年便秘患者的首选泻剂，不被肠道吸收，安全性高。"
        "推荐剂量10-20g/日，溶于150-250ml水中服用。乳果糖适用于合并肝性脑病的老年患者，"
        "起始剂量15-30ml/日，注意可能引起腹胀和排气增多。\n\n"
        "## 三、刺激性泻剂（短期使用）\n\n"
        "比沙可啶、番泻叶等刺激性泻剂仅推荐短期（不超过2周）间断使用，"
        "长期使用可导致结肠黑变病和电解质紊乱，老年患者尤其应避免长期依赖。\n\n"
        "## 四、促分泌药物\n\n"
        "利那洛肽可用于成人慢性特发性便秘，老年患者（>65岁）使用时应注意腹泻不良反应，"
        "建议从最低剂量起始。鲁比前列酮适用于女性便秘型肠易激综合征。\n\n"
    ).encode("utf-8"),
    "老年便秘_特殊人群注意事项.md": (
        "# 老年便秘患者特殊人群用药注意事项\n\n"
        "## 一、合并心血管疾病的老年患者\n\n"
        "合并高血压、冠心病、心力衰竭的老年便秘患者，"
        "应避免使用可能引起电解质紊乱的刺激性泻剂（番泻叶、大黄）。"
        "排便时过度用力（Valsalva动作）可诱发心绞痛、心肌梗死甚至猝死，"
        "应指导患者保持大便通畅，首选聚乙二醇等渗透性泻剂。\n\n"
        "## 二、合并糖尿病的老年患者\n\n"
        "糖尿病合并便秘患者可选用聚乙二醇，避免使用乳果糖（可能影响血糖）。"
        "乳果糖虽然不被人体吸收，但部分制剂含少量游离糖，血糖控制不佳者慎用。\n\n"
        "## 三、合并肾功能不全的老年患者\n\n"
        "肾功能不全患者应避免使用含镁盐的泻剂（如镁乳、氢氧化镁），"
        "镁离子蓄积可导致高镁血症，严重者可引起呼吸抑制和心律失常。"
        "推荐聚乙二醇作为首选。\n\n"
        "## 四、多重用药的老年患者\n\n"
        "老年人常服用多种药物，需注意药物性便秘："
        "钙剂、铁剂、抗胆碱能药物、阿片类镇痛药、部分抗抑郁药和抗帕金森药均可加重便秘。"
        "应评估用药清单，必要时调整药物或加用预防性泻剂。\n\n"
    ).encode("utf-8"),
}


# ---------------------------------------------------------------------------
# 2. 轻量级模拟组件（在无 qdrant-client / 无 DASHSCOPE_API_KEY 时使用）
# ---------------------------------------------------------------------------
@dataclass
class _MockChunk:
    """模拟 agentscope.rag.Chunk 的最小子集。"""
    content_text: str
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class _MockSearchResult:
    """模拟 VectorSearchResult。"""
    score: float
    document_id: str
    chunk: _MockChunk


class _KeywordKnowledgeBase:
    """基于关键词重叠的简易检索，模拟 KnowledgeBase 接口。

    实现策略：将文本按中文分句，检索时用 query 与每个 chunk 做字符级
    Jaccard 相似度排序。仅用于演示，不代表生产检索质量。
    """

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self._chunks: list[tuple[str, _MockChunk]] = []  # (doc_id, chunk)
        self._doc_counter = 0

    async def insert_document(
        self,
        chunks: list[dict[str, Any]],
        document_metadata: dict[str, Any] | None = None,
    ) -> str:
        self._doc_counter += 1
        doc_id = f"doc-{self._doc_counter:04d}"
        for c in chunks:
            self._chunks.append(
                (doc_id, _MockChunk(
                    content_text=c["text"],
                    source=c.get("source", ""),
                    metadata={**(document_metadata or {}), **c.get("metadata", {})},
                )),
            )
        return doc_id

    async def search(
        self,
        queries: list[str],
        top_k: int = 5,
        score_threshold: float | None = None,
    ) -> list[_MockSearchResult]:
        if not queries:
            return []
        query = queries[0]
        qchars = set(re.sub(r"\s+", "", query))
        scored: list[_MockSearchResult] = []
        for doc_id, chunk in self._chunks:
            cchars = set(re.sub(r"\s+", "", chunk.content_text))
            if not qchars or not cchars:
                continue
            inter = len(qchars & cchars)
            union = len(qchars | cchars)
            score = inter / union if union else 0.0
            if score_threshold is not None and score < score_threshold:
                continue
            scored.append(_MockSearchResult(score=score, document_id=doc_id, chunk=chunk))
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]


def _chunk_text_simple(text: str, source: str, chunk_size: int = 200, overlap: int = 30):
    """按字符近似分块（模拟 ApproxTokenChunker 效果），保持中文段落完整。"""
    # 先按双换行切分段落
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[dict[str, Any]] = []
    buf = ""
    for para in paragraphs:
        if len(buf) + len(para) <= chunk_size:
            buf += para + "\n\n"
        else:
            if buf:
                chunks.append({"text": buf.strip(), "source": source, "metadata": {}})
            # 段落过长则进一步切分
            while len(para) > chunk_size:
                chunks.append({"text": para[:chunk_size], "source": source, "metadata": {}})
                para = para[chunk_size - overlap:]
            buf = para + "\n\n"
    if buf.strip():
        chunks.append({"text": buf.strip(), "source": source, "metadata": {}})
    # 补充分块索引
    for i, c in enumerate(chunks):
        c["metadata"]["chunk_index"] = i
        c["metadata"]["total_chunks"] = len(chunks)
    return chunks


# ---------------------------------------------------------------------------
# 3. 尝试使用真实 AgentScope 组件；失败则降级到 mock
# ---------------------------------------------------------------------------
_real_rag_available = False
_Reason: str = ""

try:
    from agentscope.agent import Agent  # noqa: F401
    from agentscope.credential import DashScopeCredential
    from agentscope.embedding import DashScopeEmbeddingModel
    from agentscope.message import TextBlock, UserMsg
    from agentscope.middleware import RAGMiddleware
    from agentscope.model import DashScopeChatModel
    from agentscope.rag import (
        ApproxTokenChunker,
        KnowledgeBase,
        QdrantStore,
        TextParser,
    )
    from agentscope.tool import Toolkit
    _HAS_AGENTSCOPE = True
except ImportError as e:
    _HAS_AGENTSCOPE = False
    _Reason = f"agentscope 未安装: {e}"


async def _build_real_knowledge_base() -> tuple[KnowledgeBase, Any, Any, Any]:
    """构建真实 KnowledgeBase（Qdrant + DashScopeEmbedding）。"""
    api_key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not api_key:
        raise RuntimeError("DASHSCOPE_API_KEY 未设置")
    credential = DashScopeCredential(api_key=api_key)
    embedding_model = DashScopeEmbeddingModel(
        credential=credential,
        model="text-embedding-v4",
        dimensions=1024,
    )
    parser = TextParser()
    chunker = ApproxTokenChunker(chunk_size=256, overlap=32)
    store = QdrantStore(location=":memory:")
    await store.__aenter__()
    knowledge = KnowledgeBase(
        name="elderly-constipation-guidelines",
        description="中国老年慢性便秘诊疗专家共识及特殊人群用药注意事项",
        embedding_model=embedding_model,
        vector_store=store,
        collection="gerclaw_constipation",
    )
    for filename, content_bytes in GUIDELINE_DOCS.items():
        sections = await parser.parse(file=content_bytes, filename=filename)
        chunks = await chunker.chunk(sections)
        doc_id = await knowledge.insert_document(
            chunks,
            document_metadata={"filename": filename},
        )
        print(f"  [真实向量库] 已索引 {filename} → {doc_id} ({len(chunks)} 个chunk)")
    return knowledge, store, parser, chunker  # type: ignore[return-value]


async def _build_mock_knowledge_base() -> _KeywordKnowledgeBase:
    """构建 mock KnowledgeBase。"""
    kb = _KeywordKnowledgeBase(
        name="elderly-constipation-guidelines",
        description="中国老年慢性便秘诊疗专家共识及特殊人群用药注意事项",
    )
    for filename, content_bytes in GUIDELINE_DOCS.items():
        text = content_bytes.decode("utf-8")
        chunks = _chunk_text_simple(text, source=filename)
        doc_id = await kb.insert_document(
            chunks,
            document_metadata={"filename": filename},
        )
        print(f"  [Mock检索] 已索引 {filename} → {doc_id} ({len(chunks)} 个chunk)")
    return kb


# ---------------------------------------------------------------------------
# 4. 真实 Agent 对话 / Mock 对话
# ---------------------------------------------------------------------------
async def _run_real_agent(knowledge: KnowledgeBase, store: Any) -> None:
    """使用真实 Agent + RAGMiddleware 进行问答。"""
    api_key = os.environ["DASHSCOPE_API_KEY"]
    credential = DashScopeCredential(api_key=api_key)
    chat_model = DashScopeChatModel(
        credential=credential,
        model="qwen-plus",
        stream=False,
    )
    rag_mw = RAGMiddleware(
        knowledge_bases=[knowledge],
        parameters=RAGMiddleware.Parameters(
            mode="static",
            top_k=3,
            score_threshold=0.3,
            emit_hint_event=False,
        ),
    )
    agent = Agent(
        name="gerclaw-constipation-advisor",
        system_prompt=(
            "你是GerClaw老年医疗AI助手，专注于老年慢性便秘的诊疗咨询。"
            "请严格基于检索到的临床指南内容回答用户问题，回答时务必标注"
            "[来源:文件名/章节]。如果检索内容不足以回答，请直接说明，"
            "并建议用户咨询消化科医生。不要编造医学建议。"
        ),
        model=chat_model,
        toolkit=Toolkit(),
        middlewares=[rag_mw],
    )

    questions = [
        "老年便秘患者首选什么泻剂？安全性如何？",
        "肾功能不全的老年人便秘不能用什么药？",
        "高血压老人便秘排便时需要注意什么？",
    ]
    for q in questions:
        print(f"\n[用户] {q}")
        reply = await agent.reply(UserMsg(name="user", content=q))
        print(f"[AI助手] {reply.get_text_content()}")

    await store.__aexit__(None, None, None)


async def _run_mock_qa(kb: _KeywordKnowledgeBase) -> None:
    """不依赖 LLM，直接展示检索结果 + 模板化回答（Mock 演示）。"""
    questions = [
        "老年便秘患者首选什么泻剂？安全性如何？",
        "肾功能不全的老年人便秘不能用什么药？",
        "高血压老人便秘排便时需要注意什么？",
    ]
    for q in questions:
        print(f"\n[用户] {q}")
        results = await kb.search(queries=[q], top_k=3, score_threshold=0.05)
        if not results:
            print("[AI助手（Mock）] 未检索到相关指南内容，建议咨询消化科医生。")
            continue
        print("[检索到的指南片段]：")
        for rank, r in enumerate(results, 1):
            snippet = r.chunk.content_text.replace("\n", " ").strip()
            if len(snippet) > 120:
                snippet = snippet[:117] + "..."
            print(f"  [{rank}] 相似度={r.score:.3f} 来源={r.chunk.source}")
            print(f"      {snippet}")
        # 模板化回答（真实场景由 LLM 生成）
        top = results[0]
        print(
            f"[AI助手（Mock）] 根据{top.chunk.source}中的相关内容，"
            f"建议参考上述指南片段，并在医生指导下进行治疗。"
            f"（真实场景由LLM基于检索结果生成循证回答）"
        )


# ---------------------------------------------------------------------------
# 5. 入口
# ---------------------------------------------------------------------------
async def main() -> None:
    print("=" * 60)
    print("GerClaw 嵌入式RAG示例 — 老年便秘临床指南问答")
    print("=" * 60)

    # 尝试真实 AgentScope RAG
    use_real = False
    knowledge: Any = None
    store: Any = None

    if _HAS_AGENTSCOPE:
        try:
            print("\n[1/3] 尝试加载真实向量检索组件（Qdrant + DashScopeEmbedding）...")
            knowledge, store, _parser, _chunker = await _build_real_knowledge_base()
            use_real = True
            print("  → 真实组件加载成功。")
        except Exception as e:
            print(f"  → 无法使用真实组件（{e}），降级到 Mock 检索模式。")
    else:
        print(f"\n[1/3] {_Reason}，使用 Mock 检索模式。")

    if not use_real:
        print("\n[1/3] 构建 Mock 知识库（基于关键词重叠的简易检索）...")
        knowledge = await _build_mock_knowledge_base()

    print("\n[2/3] 开始问答演示...")
    if use_real:
        await _run_real_agent(knowledge, store)
    else:
        await _run_mock_qa(knowledge)

    print("\n[3/3] 演示完成。")
    print("=" * 60)
    print("提示：设置 DASHSCOPE_API_KEY 并安装 qdrant-client 后，")
    print("     可运行真实 RAGMiddleware + LLM 循证问答。")


if __name__ == "__main__":
    asyncio.run(main())
