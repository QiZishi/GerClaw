# 05_RAG知识库检索 — AgentScope 开发参考索引

> **对应GerClaw模块**：05_RAG知识库检索（临床指南检索、RAGMiddleware嵌入式、RAG Service分布式）
> **AgentScope版本**：v2.0.3
> **整理时间**：2026-07-02

---

## 1. 模块映射总览

GerClaw老年医疗AI平台的RAG知识库检索需求，在AgentScope中对应两套API形态和一套中间件，分别映射如下：

| GerClaw需求场景 | AgentScope对应组件 | 部署形态 | 关键入口 |
|---|---|---|---|
| **嵌入式RAG**：Agent在推理时自动/按需检索临床指南 | `RAGMiddleware` + `KnowledgeBase` + `QdrantStore` | 库模式（同进程） | `agentscope.middleware.RAGMiddleware` |
| **知识库管理**：临床指南/药品说明书的创建、上传、索引、检索 | `KnowledgeBase`（运行时句柄） | 库模式 | `agentscope.rag.KnowledgeBase` |
| **分布式RAG Service**：多科室/多院区共享医学知识库、HTTP API、异步索引、横向扩容 | `create_app(knowledge_base_manager=...)` + `CollectionPerKbManager` + `run_worker` | 服务模式（FastAPI + Redis + Qdrant） | `agentscope.app.create_app`、`agentscope.app.rag.run_worker` |
| **Embedding模型**：中文医学文本向量化 | `DashScopeEmbeddingModel`（推荐）/ 自定义 `EmbeddingModelBase` 子类 | 库/服务通用 | `agentscope.embedding.DashScopeEmbeddingModel` |
| **文档解析**：PDF指南/Markdown教材/药品说明书HTML | `TextParser`、`PDFParser`、`PPTParser`、`ImageParser` | 库/服务通用 | `agentscope.rag.TextParser`、`agentscope.rag.PDFParser` |
| **分块**：按指南章节/临床问题切分 | `ApproxTokenChunker`（内置）/ 自定义 `ChunkerBase` 子类 | 库/服务通用 | `agentscope.rag.ApproxTokenChunker` |
| **向量存储**：医学知识向量持久化 | `QdrantStore`（内置，支持内存/本地/远程三种模式） | 库/服务通用 | `agentscope.rag.QdrantStore` |

**AgentScope RAG模块架构（building blocks）**：

```
原始文件(bytes/路径)
    │
    ▼
Parser（TextParser/PDFParser/...）  →  Section[]（自然边界：页/幻灯片/段落）
    │
    ▼
Chunker（ApproxTokenChunker/自定义） →  Chunk[]（最终索引单元）
    │
    ▼
EmbeddingModel（DashScopeEmbeddingModel/...） → 向量
    │
    ▼
VectorStore（QdrantStore/自定义） → 持久化向量+元数据
    │
    ▼
KnowledgeBase（一站式句柄：insert_document / search / list_documents / delete_document）
    │
    ├──► RAGMiddleware（嵌入式：static自动注入 / agentic工具调用）
    │
    └──► KnowledgeBaseManager（服务模式：多租户CRUD + 异步索引流水线）
             │
             ├──► BlobStore（LocalBlobStore/S3BlobStore）
             ├──► IndexWorker（嵌入式或分布式）
             └──► REST API（/knowledge_bases/...）
```

---

## 2. 核心API参考

### 2.1 RAGMiddleware 配置参数

**位置**：`src/agentscope/middleware/_rag.py`，类 `RAGMiddleware`。

**构造签名**：

```python
RAGMiddleware(
    knowledge_bases: list[KnowledgeBase],
    parameters: RAGMiddleware.Parameters | None = None,
)
```

**`RAGMiddleware.Parameters` 字段**：

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `mode` | `"static"` \| `"agentic"` | `"agentic"` | 集成模式。`static`=首次推理自动检索并注入HintBlock；`agentic`=暴露`search_knowledge`工具由模型自主调用 |
| `top_k` | `int` (1–50) | `5` | 单次检索返回的最大命中数 |
| `score_threshold` | `float \| None` | `None` | 命中相似度下限（cosine/dot-product有意义） |
| `emit_hint_event` | `bool` | `True` | `static`模式下是否额外发出`HintBlockEvent`（供前端展示匹配片段） |
| `persist_hint` | `bool` | `False` | `static`模式下注入的HintBlock是否持久留在上下文（默认一次调用后清除） |
| `hint_template` | `str` | 见下 | 包装检索结果的提示模板，必须含一个`{context}`占位符 |

**默认`hint_template`**：
```
<system-reminder>The following content is retrieved from the knowledge base(s) and may be helpful for the current request:
<content>{context}</content></system-reminder>
```

**两种模式对比**：

| 特性 | `static`模式 | `agentic`模式 |
|---|---|---|
| 触发时机 | 每次reply首次reasoning前 | 模型自主调用`search_knowledge`工具 |
| 检索query | 用户输入消息 | 模型自行构造（要求自包含、无代词） |
| 注入方式 | HintBlock注入上下文 | 工具返回结果 |
| 前端展示 | 可通过`emit_hint_event`推送 | 通过ToolCall事件展示 |
| 工具注册 | 无需注册 | 需通过`mw.list_tools()`注册到Toolkit |
| GerClaw适用 | 老年常见病标准问答（必检索） | 复杂鉴别诊断（模型判断是否检索） |

**跨KB检索**：中间件`_search_across()`并发搜索所有绑定的KB，结果合并后按分数降序取top_k。注意：不同embedding模型的分数**不严格可比**，多KB混合建议使用RRF融合。

### 2.2 KnowledgeBase 管理

**位置**：`src/agentscope/rag/_knowledge.py`，类 `KnowledgeBase`。

**构造参数**：

```python
KnowledgeBase(
    name: str,                           # Agent面向的知识库名（工具描述/前端展示）
    description: str,                    # Agent面向的描述（LLM决定何时检索）
    embedding_model: EmbeddingModelBase, # 查询和插入共用的embedding模型
    vector_store: VectorStoreBase,       # 共享的vector store连接（需在async with内）
    collection: str,                     # 物理集合名，首次操作懒创建
    metadata_filter: dict | None = None, # 防御性payload过滤（多租户隔离）
)
```

**核心方法**：

| 方法 | 签名 | 说明 |
|---|---|---|
| `insert_document` | `async (chunks: list[Chunk], document_id=None, document_metadata=None) -> str` | 批量embedding并插入；metadata优先级：metadata_filter > chunk.metadata > document_metadata；自动生成UUID document_id |
| `search` | `async (queries: list[str\|TextBlock\|DataBlock], top_k=5, score_threshold=None) -> list[VectorSearchResult]` | 批量embedding后并发搜索；按`(document_id, chunk_index)`去重，按分数降序取top_k |
| `delete_document` | `async (document_id: str) -> None` | 删除源文档所有记录 |
| `list_documents` | `async () -> list[DocumentSummary]` | 列出所有源文档摘要（含metadata_filter过滤） |
| `ensure_collection` | `async () -> None` | 幂等创建集合并记忆化（首次后零开销） |

**`metadata_filter` 深度防御机制**：
- `search`/`list_documents`严格按`key==value`过滤记录；
- `insert_document`强制覆盖每个chunk的同名metadata字段，防止跨租户泄漏。

### 2.3 QdrantStore 向量存储

**位置**：`src/agentscope/rag/_vdb/_qdrant.py`，类 `QdrantStore`。

**构造参数**：

```python
QdrantStore(
    location: str | None = None,    # ":memory:" 内存模式（测试/原型）
    url: str | None = None,         # 远程Qdrant Server/Cloud URL，如 "http://localhost:6333"
    path: str | None = None,        # 本地磁盘持久化路径
    api_key: str | None = None,     # Qdrant Cloud API Key
    distance: Literal["Cosine","Dot","Euclid","Manhattan"] = "Cosine",
    client_kwargs: dict | None = None,
)
```

**三种部署模式**：
- `location=":memory:"` — 进程内、临时，适合开发测试和示例；
- `path="/path/to/db"` — 进程内、持久化到本地磁盘，适合单机生产；
- `url="http://host:6333"` — 远程Qdrant服务，适合分布式/GerClaw院内生产部署。

**生命周期**：`QdrantStore`是async context manager，必须通过`async with store:`使用，进入时打开客户端连接，退出时关闭。

**抽象接口（`VectorStoreBase`）**：子类必须实现 `create_collection` / `delete_collection` / `has_collection` / `insert` / `delete` / `search` / `list_documents` 七个异步方法。

### 2.4 EmbeddingModel 配置 — DashScopeEmbeddingModel

**位置**：`src/agentscope/embedding/_dashscope/_model.py`，类 `DashScopeEmbeddingModel`。

**构造示例**：

```python
from agentscope.credential import DashScopeCredential
from agentscope.embedding import DashScopeEmbeddingModel

embedding_model = DashScopeEmbeddingModel(
    credential=DashScopeCredential(api_key=os.environ["DASHSCOPE_API_KEY"]),
    model="text-embedding-v4",   # 或 "text-embedding-v3"
    dimensions=1024,             # v4支持指定维度
)
```

**支持的文本模型**：
- `text-embedding-v3`：1024维（默认），中文效果优秀；
- `text-embedding-v4`：支持灵活维度（如256/512/1024/2048），推荐生产使用。

**支持的多模态模型**（前缀路由）：`multimodal-embedding-*`、`tongyi-embedding-vision-*`、`qwen*-vl-embedding`。

**GerClaw推荐**：`DashScopeEmbeddingModel(model="text-embedding-v4", dimensions=1024)`，中文医学文本效果稳定，API调用无需本地GPU部署；后续私有化部署可替换为本地BGE-M3（通过自定义`EmbeddingModelBase`子类接入）。

### 2.5 RAG Service 分布式模式 API

**核心入口**：`agentscope.app.create_app`（位置：`src/agentscope/app/_app.py`）。

**RAG相关create_app参数**：

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `knowledge_base_manager` | `KnowledgeBaseManagerBase \| None` | `None` | KB生命周期管理器，内置`CollectionPerKbManager`采用每KB一个Qdrant collection策略 |
| `knowledge_parsers` | `list[ParserBase] \| dict \| None` | `[TextParser()]` | 上传链路parser列表（list按media_type路由，dict显式映射） |
| `knowledge_chunker` | `ChunkerBase \| None` | `ApproxTokenChunker()` | 全局共享chunker |
| `blob_store` | `BlobStoreBase \| None` | `LocalBlobStore('./blobs')` | 上传文档暂存后端（LocalBlobStore / S3BlobStore） |
| `enable_index_worker` | `bool` | `True` | True=嵌入式部署（API进程内启动IndexWorker+IndexSweeper）；False=分布式部署（独立worker消费message bus任务） |

**CollectionPerKbManager 构造**：

```python
from agentscope.app.rag.knowledge_base_manager import CollectionPerKbManager

kb_manager = CollectionPerKbManager(
    storage=redis_storage,        # StorageBase实例（RedisStorage）
    vector_store=qdrant_store,    # VectorStoreBase实例（QdrantStore）
)
```

**分布式Worker启动**（库方式）：

```python
from agentscope.app.rag import run_worker

await run_worker(
    storage=storage,
    message_bus=message_bus,
    blob_store=blob_store,
    knowledge_base_manager=kb_manager,
    parsers=[TextParser(), PDFParser(), PPTParser(), ImageParser()],
    chunker=ApproxTokenChunker(chunk_size=512, overlap=50),
    worker_max_concurrency=4,     # 单worker并发文档处理上限
    consumer_max_batch=32,        # 单次信号最多拉取任务条数
)
```

**分布式Worker启动**（CLI方式）：设置`AGENTSCOPE_WORKER_BOOTSTRAP`环境变量指向bootstrap函数，运行`python -m agentscope.app.rag.index_worker`。

**文档状态机**（`KnowledgeDocumentStatus`）：`pending` → `parsing` → `chunking` → `indexing` → `ready`（或`error`）。

**BlobStore两种实现**：
- `LocalBlobStore(root_dir="./blobs")`：本地文件系统，适合单机开发；
- `S3BlobStore(bucket, endpoint_url=None, ...)`：S3兼容对象存储，适合院内分布式部署。

**REST API端点（/knowledge_bases前缀）**：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/knowledge_bases/embedding_models` | 列出维度兼容的嵌入模型 |
| GET | `/knowledge_bases/supported_content_types` | 列出支持的MIME类型/扩展名 |
| GET | `/knowledge_bases/middleware/parameters_schema` | 获取RAGMiddleware.Parameters的JSON Schema |
| POST | `/knowledge_bases` | 创建知识库 |
| GET | `/knowledge_bases` | 列出知识库 |
| PATCH | `/knowledge_bases/{kb_id}` | 更新知识库（name/description） |
| DELETE | `/knowledge_bases/{kb_id}` | 删除知识库（级联清理） |
| POST | `/knowledge_bases/{kb_id}/documents` | 上传文档 |
| GET | `/knowledge_bases/{kb_id}/documents` | 列出文档 |
| GET | `/knowledge_bases/{kb_id}/documents/status?ids=...` | 批量查询文档状态 |
| DELETE | `/knowledge_bases/{kb_id}/documents/{doc_id}` | 删除文档 |
| POST | `/knowledge_bases/{kb_id}/search` | 语义检索 |

### 2.6 文档解析器/分块器配置

**Parser类**：

| 类 | 支持类型 | 说明 |
|---|---|---|
| `TextParser` | text/plain, text/markdown, text/csv, text/html, text/x-rst, application/json, application/xml, application/x-yaml | 整文件作为一个Section，由下游chunker切分 |
| `PDFParser` | application/pdf | **每页一个Section**，metadata含`page`字段（从1开始）。需`pip install agentscope[rag]` |
| `PPTParser` | application/vnd.openxmlformats-officedocument.presentationml.presentation | 按幻灯片遍历，metadata含`slide`字段。需`pip install agentscope[rag]` |
| `ImageParser` | image/png, image/jpeg, image/gif, image/bmp, image/webp | 整张图片作为一个Section |

**Parser调用形态**：`parser.parse(file: bytes | str, filename: str) -> list[Section]`
- `bytes`：直接作为原始文件内容；
- `str`：二进制解析器中表示文件路径；TextParser中若指向存在文件则读盘，否则视为已解码文本。

**Chunker类**：

| 类 | 构造参数 | 说明 |
|---|---|---|
| `ApproxTokenChunker` | `chunk_size: int = 512, overlap: int = 50` | 近似token计数（`len(utf8_bytes)//4`），无需tokenizer依赖；DataBlock整块透传 |

**自定义Parser**：继承`ParserBase`，声明`supported_media_types`，实现`async def parse(file, filename) -> list[Section]`。

**自定义Chunker**：继承`ChunkerBase`，实现`async def chunk(sections) -> list[Chunk]`；约定不跨Section合并，`chunk_index`连续编号，DataBlock直通。

**关键数据结构**：

```python
Section(content: TextBlock | DataBlock, source: str, metadata: dict)
Chunk(content: TextBlock | DataBlock, source: str, chunk_index: int, total_chunks: int, metadata: dict)
VectorRecord(vector: list[float], document_id: str, chunk: Chunk)
VectorSearchResult(score: float, document_id: str, chunk: Chunk)
DocumentSummary(document_id: str, source: str, chunk_count: int, metadata: dict)
```

---

## 3. 源码路径索引

> 源码根目录：`references/agentscope/src/agentscope/`

| 组件 | 源码路径（相对src/agentscope/） |
|---|---|
| **RAG模块入口（公共导出）** | `rag/__init__.py` |
| KnowledgeBase | `rag/_knowledge.py` |
| Section / Chunk 数据结构 | `rag/_document.py` |
| ChunkerBase 抽象基类 | `rag/_chunker/_base.py` |
| ApproxTokenChunker | `rag/_chunker/_approx_token_chunker.py` |
| ParserBase 抽象基类 | `rag/_parser/_base.py` |
| TextParser | `rag/_parser/_text.py` |
| PDFParser | `rag/_parser/_pdf.py` |
| PPTParser | `rag/_parser/_ppt.py` |
| ImageParser | `rag/_parser/_image.py` |
| VectorStoreBase + 数据模型 | `rag/_vdb/_vector_store.py` |
| QdrantStore | `rag/_vdb/_qdrant.py` |
| **RAGMiddleware** | `middleware/_rag.py` |
| MiddlewareBase 抽象基类 | `middleware/_base.py` |
| **Embedding基类** | `embedding/_embedding_base.py` |
| DashScopeEmbeddingModel | `embedding/_dashscope/_model.py` |
| EmbeddingCacheBase | `embedding/_cache_base.py` |
| DashScopeCredential | `credential/_dashscope.py` |
| **RAG Service — create_app工厂** | `app/_app.py` |
| KnowledgeBase路由 | `app/_router/_knowledge_base.py` |
| KnowledgeBase服务层 | `app/_service/_knowledge_base.py` |
| CollectionPerKbManager | `app/rag/knowledge_base_manager/_collection_per_kb.py` |
| KnowledgeBaseManagerBase | `app/rag/knowledge_base_manager/_base.py` |
| DimensionPolicy | `app/rag/knowledge_base_manager/_dimension_policy.py` |
| BlobStoreBase | `app/rag/blob_store/_base.py` |
| LocalBlobStore | `app/rag/blob_store/_local.py` |
| S3BlobStore | `app/rag/blob_store/_s3.py` |
| 分布式Worker入口（CLI） | `app/rag/index_worker/__main__.py` |
| IndexWorker核心 | `app/_service/_index_worker.py` |
| IndexTaskConsumer | `app/_service/_index_task_consumer.py` |
| IndexSweeper | `app/_service/_index_sweeper.py` |
| RedisStorage | `app/storage/_redis_storage.py` |
| RedisMessageBus | `app/message_bus/_redis_message_bus.py` |
| InMemoryMessageBus | `app/message_bus/_in_memory_message_bus.py` |
| KnowledgeBase存储模型 | `app/storage/_model/_knowledge_base.py` |
| KnowledgeDocument存储模型 | `app/storage/_model/_knowledge_document.py` |
| Embedding模型配置模型 | `app/storage/_model/_base.py`（EmbeddingModelConfig） |

---

## 4. 官方示例参考

> 示例根目录：`references/agentscope/examples/`

| 示例 | 路径 | 覆盖场景 |
|---|---|---|
| **索引+检索（库模式）** | `examples/rag/index_and_search.py` | TextParser → ApproxTokenChunker → DashScopeEmbeddingModel + QdrantStore(:memory:) → KnowledgeBase.insert_document / search，无Agent |
| **RAGMiddleware集成Agent** | `examples/rag/integrate_with_agent.py` | 同一KnowledgeBase分别挂载到static模式Agent和agentic模式Agent，对比两种检索触发方式 |
| **RAG Service完整配置** | `examples/agent_service/main.py` | create_app + RedisStorage + QdrantStore(:memory:) + CollectionPerKbManager + LocalWorkspaceManager + InMemoryMessageBus，含CORS中间件 |
| **Mem0长期记忆**（相关） | `examples/long_term_memory/mem0/oss_demo.py` | Mem0Middleware + 本地Qdrant，展示middleware模式下的记忆读写（与RAGMiddleware模式类似，可参考其工具注册方式） |

**测试参考**（`references/agentscope/tests/`）：

| 测试文件 | 覆盖内容 |
|---|---|
| `middleware_rag_test.py` | RAGMiddleware的static/agentic两种模式行为、工具注册、HintBlock注入 |
| `storage_redis_knowledge_base_test.py` | RedisStorage对KnowledgeBase/KnowledgeDocument的CRUD、级联删除、租约机制 |
| `service_knowledge_base_upload_test.py` | 知识库创建、文档上传、索引流程端到端测试 |
| `service_enqueue_index_task_test.py` | 索引任务入队、worker消费、状态流转测试 |

---

## 5. 文档链接

| 文档 | 位置 | 说明 |
|---|---|---|
| AgentScope RAG building blocks | 离线文档 `agentscope文档离线/group_B9-11_C_D.md` 第1节（行8–367） | 解析器/分块器/Embedding/向量库/KnowledgeBase/RAGMiddleware/自定义扩展 |
| AgentScope RAG Service | 离线文档 `group_B9-11_C_D.md` 第6节（行1036–1256） | create_app参数、部署形态、分布式Worker、REST API、容错自愈 |
| AgentScope源码映射（工具/RAG） | `agentscope文档离线/source_map_tools.md` | middleware/_rag.py的RAGMiddleware实现细节 |
| AgentScope源码映射（高级/RAG Service） | `agentscope文档离线/source_map_advanced.md` 第1、3、5节 | rag/目录完整结构、KnowledgeBase API、create_app参数表、KB Manager、BlobStore、索引流水线 |
| GerClaw RAG调研 | `gerclaw前期调研/各部分调研/05_RAG知识库检索.md` | RAG技术演进、向量DB/Embedding/Reranker选型、Chunking策略、医疗知识库构建、Agentic RAG架构 |
| Qdrant官方文档 | https://qdrant.tech/documentation/ | Qdrant部署、配置、过滤查询 |
| DashScope Embedding API | https://help.aliyun.com/zh/model-studio/text-embedding | 通义千问文本嵌入模型说明 |

---

## 6. GerClaw适配要点

### 6.1 医学知识库分块策略：按指南章节/临床问题分块

AgentScope内置的`ApproxTokenChunker`采用近似token数固定切分，适合通用文本，但**医学临床指南有明确的章节结构**，建议在GerClaw中自定义`ChunkerBase`子类或结合Parser阶段实现结构化分块：

1. **指南文档（PDF）**：先用`PDFParser`按页解析为Section，然后自定义Chunker按以下策略切分：
   - 识别章节标题（如"一、""（一）""1."等中文标题编号、或"## "等Markdown标记），每个推荐意见/诊疗要点作为独立Chunk；
   - Chunk大小控制在256–512 tokens（约300–700中文字），overlap 64 tokens；
   - 表格（剂量表、禁忌表）单独提取为Chunk，附加上下文说明。

2. **药品说明书**：按标准章节标签分块（【成分】/【适应症】/【用法用量】/【不良反应】/【禁忌】/【注意事项】/【药物相互作用】），每个章节作为独立Chunk，在metadata中记录`section_type`字段用于过滤检索。

3. **Chunk元数据规范**（每个Chunk必须携带）：
   ```python
   metadata = {
       "source_type": "guideline" | "textbook" | "drug_label" | "literature",
       "doc_title": "中国老年慢性便秘诊疗专家共识(2023)",
       "chapter": "三、非手术治疗",
       "page": 12,
       "publish_year": 2023,
       "evidence_level": "A" | "B" | "C" | "D",  # 循证证据等级
       "icd_codes": ["K59.0"],                  # 相关ICD-10编码（可选）
   }
   ```

4. **实现路径**：可参考离线文档第1.6.2节"自定义切块器"的`FixedCharChunker`示例，继承`ChunkerBase`实现按章节/临床问题切分。

### 6.2 推荐配置：RAGMiddleware + DashScopeEmbedding

**Phase 1（MVP，嵌入式RAG）推荐配置**：

```python
# Embedding
embedding_model = DashScopeEmbeddingModel(
    credential=DashScopeCredential(api_key=os.environ["DASHSCOPE_API_KEY"]),
    model="text-embedding-v4",
    dimensions=1024,
)

# 向量存储（开发: :memory:；院内生产: url="http://内网qdrant:6333"）
store = QdrantStore(location=":memory:")  # 或 path="./gerclaw_qdrant_data"

# Chunker
chunker = ApproxTokenChunker(chunk_size=512, overlap=64)

# Parser（多格式支持）
parsers = [TextParser(), PDFParser()]

# KnowledgeBase
knowledge = KnowledgeBase(
    name="gerclaw-elderly-guidelines",
    description="老年医学临床指南、药品说明书、老年综合征管理规范",
    embedding_model=embedding_model,
    vector_store=store,
    collection="gerclaw_guidelines",
)

# RAGMiddleware —— 老年慢病标准问答建议static模式（必检索，降低幻觉）
rag_mw = RAGMiddleware(
    knowledge_bases=[knowledge],
    parameters=RAGMiddleware.Parameters(
        mode="static",         # 自动检索注入
        top_k=5,
        score_threshold=0.3,   # 医学场景设置阈值过滤低相关片段
        emit_hint_event=True,  # 前端展示引用片段
    ),
)

# Agent装配
agent = Agent(
    name="gerclaw-medical-assistant",
    system_prompt=(
        "你是GerClaw老年医疗AI助手。仅根据检索到的临床指南内容回答问题，"
        "回答时标注来源指南名称和章节。如果检索内容不足以回答，请说明需要查阅更多资料，"
        "并建议用户咨询医生。"
    ),
    model=chat_model,
    toolkit=Toolkit(),
    middlewares=[rag_mw],
)
```

**Phase 2/3（RAG Service分布式）**：通过`create_app`启用`CollectionPerKbManager`，使用RedisStorage + RedisMessageBus + 远程Qdrant，支持多科室知识库隔离、文档异步索引、横向扩容。

### 6.3 风险：医学知识时效性/检索结果需标注来源

| 风险点 | 说明 | AgentScope层面缓解措施 | GerClaw额外措施 |
|---|---|---|---|
| **医学知识时效性** | 指南每3-5年更新，过期指南可能导致错误诊疗建议 | Chunk metadata中记录`publish_year`，可自定义VectorStore在search时按年份过滤/加权 | 建立指南版本管理机制，旧版标记`status="deprecated"`；检索时优先返回近5年指南；定期增量更新Pipeline |
| **幻觉风险** | LLM可能在检索不充分时编造医学建议 | `score_threshold`过滤低相关片段；`static`模式自动注入真实检索结果；system prompt约束"仅基于检索内容回答" | 实现CRAG式质量评估：top1分数低于阈值时触发"信息不足"回复；高风险问题（用药/急症）强制要求`[Fully Supported]`级证据 |
| **来源标注** | 医学回答必须可溯源到具体指南/文献 | `VectorSearchResult.chunk.source`携带源文件名；`chunk.metadata`携带章节/页码 | 在system prompt中强制要求"每个医学声明标注[来源:指南名,章节,页码]"；前端Hover展示引用片段 |
| **多租户数据隔离** | 不同科室/院区知识库不应串库 | `KnowledgeBase.metadata_filter`提供深度防御；服务模式下`CollectionPerKbManager`每KB独占collection | 按科室/用户角色设置KB访问权限；敏感病历知识库使用独立Qdrant collection |
| **Embedding中文医学术语覆盖** | 通用Embedding对罕见病名/中文医学术语召回不足 | DashScope text-embedding-v4中文能力较强 | 构建本地医学术语同义词表，在Query预处理阶段做术语扩展；积累bad case后微调Embedding或接入本地bge-m3-medical-cn |
| **PDF解析质量** | 扫描版PDF/双栏排版/表格可能解析错误 | PDFParser依赖pypdf等库，复杂排版效果有限 | 关键指南使用MinerU/marker-pdf预解析为Markdown后再入库；表格单独人工校验 |

---

## 7. 可运行示例指引

本参考配套2个可运行Python示例，位于 `agentscope-examples/05_rag/` 目录：

### 示例1：`guideline_rag.py` — 嵌入式RAGMiddleware演示

- **场景**：老年便秘临床指南片段入库，Agent挂载`RAGMiddleware`（static模式），用户提问时自动检索相关指南片段并生成循证回答
- **核心演示**：
  - 使用内置`QdrantStore(location=":memory:")`做内存向量存储
  - `TextParser` + `ApproxTokenChunker` 解析分块
  - `DashScopeEmbeddingModel` 从环境变量读取API Key
  - `KnowledgeBase` 承载指南知识库
  - `RAGMiddleware(mode="static")` 自动检索注入
  - 如未安装qdrant-client，自动降级为简单字典模拟向量检索
- **运行前提**：
  ```bash
  export DASHSCOPE_API_KEY=sk-xxx
  # 可选（有qdrant-client时走真实向量检索）：
  pip install qdrant-client agentscope
  python agentscope-examples/05_rag/guideline_rag.py
  ```

### 示例2：`medical_rag_service.py` — RAG Service分布式模式API流程演示（Mock）

- **场景**：演示RAG Service模式下KnowledgeBase的完整生命周期——创建知识库、上传文档、索引构建（含状态轮询）、语义检索，不启动真实FastAPI/Redis/Qdrant服务，用Mock对象演示API调用流程
- **核心演示**：
  - 模拟`CollectionPerKbManager`的KB创建流程
  - 模拟文档上传→BlobStore→索引任务入队→Worker消费→状态变更的流水线
  - 模拟`POST /knowledge_bases/{kb_id}/search`语义检索
  - 展示文档状态机（pending→processing→ready）
  - 老年高血压指南和糖尿病指南作为示例数据
- **运行前提**：
  ```bash
  # 无需额外依赖（纯mock演示，不需要qdrant/redis）：
  python agentscope-examples/05_rag/medical_rag_service.py
  ```

### 示例到生产的迁移路径

1. 将`QdrantStore(location=":memory:")`替换为`QdrantStore(url="http://内网qdrant:6333")`连接院内Qdrant集群；
2. 将mock的`InMemoryVectorStore`/字典检索替换为真实`QdrantStore` + `DashScopeEmbeddingModel`；
3. 将示例中的指南片段替换为通过`PDFParser`/MinerU解析的真实临床指南PDF；
4. 当知识库规模扩大到多科室共享时，参考`examples/agent_service/main.py`启用`create_app` + `CollectionPerKbManager` + `RedisStorage`构建RAG Service；
5. 高并发场景下设置`enable_index_worker=False`，部署独立`run_worker`进程分布式消费索引任务。
