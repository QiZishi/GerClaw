# GerClaw

面向老年患者与老年科医生的多模态 AI 诊疗与康养 Agent 应用。

[快速开始](#快速开始) · [核心能力](#核心能力) · [Agent Harness](#agent-harness) · [系统架构](#系统架构) · [配置](#配置) · [项目结构](#项目结构) · [文档](#文档)

![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB)
![FastAPI](https://img.shields.io/badge/FastAPI-0.116%2B-009688)
![AgentScope](https://img.shields.io/badge/AgentScope-2.0.4-6C5CE7)
![Next.js](https://img.shields.io/badge/Next.js-16-black)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED)

## 什么是 GerClaw？

GerClaw 把健康对话、CGA 老年综合评估、五大处方、用药审查、长期记忆、医学 RAG、语音交互与病例文档解析整合为一套可本地运行、可容器化部署的全栈系统。

系统提供三个相互隔离的工作台：

- **患者端**：语音优先、适老化对话、健康画像、CGA、五大处方与历史记录。
- **医生端**：临床资料整理、处方草案、用药审查、CGA 报告、循证检索与文档工具。
- **管理端**：账户、角色、模型服务配置与 Bad Case 管理；管理员可切换工作台视角。

登录页是统一入口。用户可登录或注册，也可选择无账号进入患者端；游客数据进入后台质量分析，但游客历史不会在下一次访问时恢复。医生和患者之间不提供即时通信。

## 为什么选择 GerClaw？

- **多模态且可追溯**：文本、语音、图片、PDF、Word 与 Markdown 进入同一对话；图片和上传资料拥有 evidence ID，并进入受控 Trace。
- **面向真实医疗工作流**：五大处方不是静态表单，而是最多 5 轮的信息补齐、证据检索、严格结构输出、规则审查和医生审核修订流程；模型初稿与医生修订版独立版本化保留，原始 AI 草稿不可变（SHA-256）。
- **AgentScope 原生能力**：使用 AgentScope 2.0.4 组织 Agent、Memory、RAG、Skill、工具调用与流式事件，不维护第二套简化 Agent 框架。
- **Agent Harness 核心运行边界**：每轮创建隔离的 AgentState，由 Harness 统一组装上下文、驱动 ReAct、治理证据与工具权限、执行医疗安全后处理，并以 SSE/Trace 交付可审阅终态。
- **真实使用数据的自动采集**：执行 Trace、用户反馈（👍/👎 + 分类 + 评论）与 Bad Case（执行失败或负面反馈自动生成）由系统自动记录并加密保存，为系统评测、回归与后续演化提供数据基础。
- **适老化交互**：患者端采用大字号、大触控区、高对比度、文字标签、可控语音播放，以及稳定不闪烁的加载状态与已执行时间。
- **可部署、可扩展**：PostgreSQL、Redis、Qdrant、FastAPI 与 Next.js 可通过 Docker Compose 一次启动；医学知识库使用外部只读挂载，便于持续扩充。

## 目录

- [快速开始](#快速开始)
  - [Docker 一键部署](#docker-一键部署)
  - [本地源码运行](#本地源码运行)
- [开始使用](#开始使用)
- [核心能力](#核心能力)
- [Agent Harness](#agent-harness)
- [系统架构](#系统架构)
- [配置](#配置)
- [医学知识库与 MinerU](#医学知识库与-mineru)
- [Docker 管理](#docker-管理)
- [项目结构](#项目结构)
- [文档](#文档)
- [医疗使用边界](#医疗使用边界)

## 快速开始

### Docker 一键部署

运行条件：Docker Engine 24+、Docker Compose v2、至少 8 GB 可用内存；索引大型知识库时建议 16 GB 以上。

```bash
cd gerclaw-main-codex
cp .env.example .env
```

打开根目录 `.env`，填写留空的模型、联网搜索、MinerU、认证和数据加密密钥。数据加密密钥可这样生成：

```bash
openssl rand -base64 32
```

首次构建、启动、迁移数据库并建立知识库索引：

```bash
./docker.sh init
```

启动完成后访问：

- Web：`http://127.0.0.1:3000`
- API readiness：`http://127.0.0.1:8000/health/ready`

### 本地源码运行

本地源码方式不使用 Docker，需要预先安装：

- Python 3.12 或 3.13
- Node.js 22 与 npm
- PostgreSQL 16
- Redis 7
- Qdrant 1.18.x

#### 1. 创建配置

```bash
cp .env.example .env
```

根 `.env` 同时服务于 FastAPI、Next.js/BFF、脚本和 Docker。不要在 `apps/api`、`apps/mvp` 或其他子目录创建第二份环境文件。

#### 2. 使用 Python venv 安装后端

以下命令会创建全新的虚拟环境，不要求本机预先存在 `.venv`，也不需要安装 `uv`：

```bash
python3.12 -m venv apps/api/.venv
source apps/api/.venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
deactivate
```

`requirements.txt` 包含锁定版本的后端运行依赖，并安装当前仓库中的 `gerclaw-api` 包及其命令行入口。如需运行测试与静态检查：

```bash
source apps/api/.venv/bin/activate
python -m pip install -r requirements-dev.txt
deactivate
```

#### 3. 安装前端

```bash
cd apps/mvp
npm ci
cd ../..
```

#### 4. 准备本地数据服务

本地服务需与 `.env` 对应：

| 服务 | 默认地址 | 默认数据库或凭据 |
|---|---|---|
| PostgreSQL | `127.0.0.1:5432` | 数据库 `gerclaw`，用户 `gerclaw` |
| Redis | `127.0.0.1:6379` | 密码与 `REDIS_PASSWORD` 一致 |
| Qdrant | `127.0.0.1:6333` | API Key 与 `GERCLAW_QDRANT_API_KEY` 一致 |

`app.py` 会在子进程中把根配置的 Docker 服务名转换为本机地址，不修改 `.env`，也不输出密钥。

#### 5. 建立医学知识索引

```bash
python3 app.py --index-only --no-docker
```

#### 6. 启动 Web 与 API

```bash
python3 app.py --no-docker
```

启动器会执行 Alembic migration，再并行启动 FastAPI 和 Next.js。仅启动前端可执行：

```bash
python3 app.py --frontend-only
```

## 开始使用

1. 打开 `http://127.0.0.1:3000`。
2. 登录已有账户、注册新账户，或选择无账号进入患者端。
3. 患者可直接在聊天框输入文字、录音，或上传图片和病例文档；医生可从工作台进入临床对话、CGA、五大处方、用药审查与知识检索。
4. 长任务会持续显示运行状态和已执行时间；语音播放支持播放、暂停、继续与停止。
5. 点击引用或 evidence ID 查看本地知识库、联网资料或患者上传信息对应的依据。

五大处方流程会在普通聊天框中接收最多 10 份资料以及文本或语音信息。MinerU 完成解析后，模型按输入模板判断缺失信息，并通过最多 5 轮对话补齐，再生成：

1. 药物处方
2. 运动处方
3. 营养处方
4. 心理处方
5. 康复处方

康复处方后端独立生成康复类型、功能评估、训练计划、辅助器具与安全注意事项。具体训练项目必须给出频次以及时长或强度；资料不足时会明确待完成的功能评估，不会用睡眠处方或普通运动建议替代。

医生端可在报告面板直接编辑各处方内容，核对循证来源后点「审核通过」或「退回」；模型初稿与医生修订版分别保留，原始 AI 草稿不可变，修改内容用于改进系统。

## 核心能力

| 能力 | 说明 |
|---|---|
| AI 健康对话 | 文本、语音、图片、文档、多轮上下文、流式输出、取消与重新生成 |
| Agent Harness | AgentScope ReAct、三模型 failover、Memory/RAG/Search/Skill 编排、Runtime 权限、医疗证据门、SSE、取消与重放 |
| 五大处方 | 最多 5 轮补充、273k 文档上下文、32,768 output token、证据绑定、医生审核修订与版本化初稿 |
| CGA | PHQ-9、SAS、PSQI、Mini-Cog、MMSE 的题目、计分、报告、导出与版本绑定音频 |
| 用药审查 | DDI、剂量阈值、重复用药、多重用药和有限 Beers 信号，显示规则来源 |
| Agentic RAG | Markdown 解析、章节切分、Dense + Sparse Hybrid Retrieval、RRF、Rerank 与引用定位 |
| Memory | 账户或匿名主体范围内的加密健康事实提取、跨会话检索、版本和生命周期管理 |
| Skill | Markdown/ZIP 导入、自然语言生成、迭代、审阅、注册和会话级加载；低风险技能在线演化，高风险技能走离线治理 |
| MinerU | PDF 等病例资料解析为 Markdown，进入当前患者上下文与证据链，不写入公共知识库 |
| ASR / TTS | MiMo 语音识别与合成、预录量表音频、播放协调；外部语音服务不可用时返回稳定错误码，前端如实降级提示 |
| 联网搜索 | AnySearch 主通道、Tavily 备用通道，结果经过结构校验并形成 evidence ID |
| 文档工作台 | 单页单栏实时编辑与实时渲染，支持 Markdown、PDF、DOCX 导出 |
| 隐私与脱敏 | 敏感正文加密存储、外发前脱敏、数据分类与最小披露边界 |
| 反馈 / Trace / Bad Case | 执行 Trace、👍/👎 反馈与失败分类可追踪；执行失败或负面反馈自动生成 Bad Case，管理端可分诊 |

## Agent Harness

GerClaw 的核心运行单元是 Agent Harness，而不是直接把用户消息发送给 LLM。每轮请求由服务端创建隔离的 AgentScope `AgentState`，然后依次经过：

```text
ChatTurnCoordinator
  → ProductionAgentHarness
  → AgentScope Agent + ReActConfig
  → MemoryMiddleware / RAGMiddleware / Search / Skill
  → GovernedToolRegistry + PermissionEngine
  → Model Router + 医疗安全后处理
  → SSE / Trace / PostgreSQL 终态
```

主要设计效果：

- 上下文、租户、主体和会话隔离，避免进程内用户串线；
- 医疗输入默认 local-first 检索，无证据时不凭模型记忆伪造个体化建议；
- 工具调用必须经过服务端 schema、scope、role、患者归属、超时和预算校验；
- 模型只在尚未产生可见内容时 fallback，部分输出断流时 fail closed；
- SSE 只展示安全的 reasoning summary、工具状态、引用和文本增量，不暴露原始 Chain-of-Thought；
- 红旗症状在模型调用前短路，医疗输出统一执行诊断措辞防护和免责声明；
- Trace、session lease、fencing、取消和 completed replay 保证一次 turn 只有一个可靠终态。

当前主路径是“单 Agent ReAct + 受治理 Middleware/Tools”，不是已完成的多智能体临床复核系统。CGA、陪伴和处方通过服务端 Workflow Registry 约束能力范围；其中陪伴 workflow 禁用医疗 Memory/RAG/Search/Skill/上传上下文，CGA 禁用联网搜索，处方保持证据绑定和审核优先。

完整的组件设计、设计原因、实际效果、上下文压缩、Memory、RAG、安全边界和后续缺口见 [Agent Harness 架构与安全边界](docs/AGENT_HARNESS.md)。

## 系统架构

```text
Browser
  └─ Next.js Web + server-only BFF
       └─ FastAPI API
            ├─ AgentScope Runtime / Harness
            │    ├─ ProductionAgentHarness（每轮隔离 AgentState）
            │    ├─ Model Router（主模型 + 两级备用）
            │    ├─ Memory / RAG / Search / Skill Middleware/Tools
            │    ├─ Runtime Permission / Budget / HITL
            │    └─ SSE / Trace / Lease / Fencing / Replay
            ├─ PostgreSQL（账户、会话、临床产物、Trace）
            ├─ Redis（限流、lease、取消与短期状态）
            └─ Qdrant（医学知识向量与 PHI-free Memory reference）
```

前端只通过同源 BFF 访问后端和外部 Provider；模型、搜索、语音、Embedding、Rerank 与 MinerU 密钥不会进入浏览器 bundle。Agent 输出、工具参数、RAG 证据、流式事件和 API 响应均在边界处执行 Pydantic 或 Zod 结构校验。

上下文不是共享的全局缓存：加密 PostgreSQL 保存消息、画像和压缩摘要，Redis 负责 lease/限流/取消，Qdrant 只保存医学知识向量和无 PHI 的 Memory reference；每轮 AgentState 从这些事实源重新组装。当前尚未实现 Provider-side Prompt Cache。

更完整的模块边界、数据流、部署拓扑和扩展策略见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 配置

仓库根 `.env` 是唯一运行配置源。[.env.example](.env.example) 提供相同变量集合；密钥和需要用户自行申请的服务地址可以留空，其余变量提供可直接使用的默认值。模板中每个变量上方都有中文说明和配置方法。

修改后可执行：

```bash
python3 scripts/check-root-env.py
```

该命令检查变量集合、非密钥值、中文注释和子目录环境文件，不打印任何密钥。

主要配置组：

| 配置组 | 变量 |
|---|---|
| 应用与端口 | `GERCLAW_APP_ENV`、`WEB_PORT`、`API_PORT`、`GERCLAW_API_URL` |
| 身份与加密 | `GERCLAW_AUTH_JWT_SECRET`、`GERCLAW_GUEST_IDENTITY_SECRET`、`GERCLAW_DATA_ENCRYPTION_KEY` |
| Agent 模型链 | `AGENT_PRIMARY_*`、`AGENT_BACKUP1_*`、`AGENT_BACKUP2_*` |
| Agent 运行参数 | `GERCLAW_AGENT_*`（路由、证据、上下文预算、ReAct 上限、运行恢复） |
| RAG | `SILICONFLOW_*`、`EMBEDDING_MODEL`、`RERANK_MODEL`、`GERCLAW_RAG_*` |
| 搜索 | `ANYSEARCH_*`、`TAVILY_*` |
| 语音 | `MIMO_*`、`ASR_MODEL`、`TTS_MODEL`、`TTS_VOICE` |
| MinerU | `MINERU_URL`、`MINERU_API_KEY`、`MINERU_ALLOWED_HOSTS` |
| 外挂知识库 | `GERCLAW_KNOWLEDGE_BASE_HOST_PATH`、`GERCLAW_KNOWLEDGE_BASE_PATH` |
| 演化信号 | `GERCLAW_EVOLUTION_SIGNAL_*`（HMAC 密钥、采集并发与超时） |

### API 与密钥获取入口

| 服务 | 对应配置 | 官方入口 |
|---|---|---|
| 阿里云百炼主模型与备用模型 | `AGENT_PRIMARY_*`、`AGENT_BACKUP1_*` | [模型市场与调用配置](https://bailian.console.aliyun.com/cn-beijing?tab=model#/model-market) · [模型调用抵用券入口](https://university.aliyun.com/?spm=a2c4g.11186623.0.0.664875b7jJElBm&scm=20140722.M_10513608._.V_1) |
| InternLM 备用模型 | `AGENT_BACKUP2_*` | [InternLM API 文档](https://internlm.intern-ai.org.cn/api/document?lang=zh) |
| MiMo ASR / TTS | `MIMO_*`、`ASR_MODEL`、`TTS_MODEL`、`TTS_VOICE` | [MiMo 开放平台控制台](https://platform.xiaomimimo.com/console/balance) |
| SiliconFlow Embedding / Rerank | `SILICONFLOW_*`、`EMBEDDING_MODEL`、`RERANK_MODEL` | [SiliconFlow 模型与密钥控制台](https://cloud.siliconflow.cn/me/models) |
| AnySearch 联网搜索 | `ANYSEARCH_*` | [AnySearch 控制台](https://www.anysearch.com/home) |
| Tavily 联网搜索 | `TAVILY_*` | [Tavily 平台](https://www.tavily.com/) |
| MinerU 文档解析 | `MINERU_*` | [MinerU API 管理与文档](https://mineru.net/apiManage/docs) |

登录账户还可以在“设置 → 模型与服务配置”保存账户级 Provider 覆盖；密钥加密存储，页面只显示是否已配置，不回显原值。未配置账户覆盖时使用根 `.env`。

## 医学知识库与 MinerU

仓库随附 `knowledge-base/md/` 初始医学语料，覆盖跌倒、衰弱、谵妄、肌少症、睡眠障碍等 18 个老年科高频主题。新用户从 `.env.example` 创建配置后，无需另行准备文档即可构建 RAG 索引：

```dotenv
GERCLAW_KNOWLEDGE_BASE_HOST_PATH=./knowledge-base/md
```

目录结构、索引命令和语料使用说明见 [初始医学知识库说明](knowledge-base/README.md)。

知识库仍不打入运行镜像，而是以只读目录挂载。需要使用更大或私有知识库时，将该变量改为其他绝对或相对目录；目录保持“主题文件夹 / Markdown 文档”的递归结构即可。新增、修改或删除文档后执行：

```bash
./docker.sh index
# 本地源码模式：python3 app.py --index-only --no-docker
```

索引器根据内容哈希增量更新 Qdrant。患者上传的病例、检查报告和图片不会混入公共 RAG；它们只属于当前账户或会话，并作为患者资料证据进入模型上下文。

MinerU 使用真实接口解析 PDF 等文档。`MINERU_ALLOWED_HOSTS` 必须包含解析 API、签名上传与 Markdown 下载所需的 HTTPS 域名；解析结果受文档数量、文件大小和 273k 合并上下文限制。

## Docker 管理

```bash
./docker.sh init       # 首次构建、启动、迁移、索引并检查 readiness
./docker.sh up         # 构建并启动全部服务
./docker.sh down       # 停止服务，保留数据卷
./docker.sh restart    # 重启 Web 与 API
./docker.sh index      # 增量更新医学知识库索引
./docker.sh status     # 查看容器和健康状态
./docker.sh logs       # 查看 Web/API 日志
./docker.sh test       # 使用隔离测试数据库运行后端测试
```

Compose 包含 Web、API、migration、PostgreSQL、Redis、Qdrant，以及按需运行的 RAG index 和 test-api。生产环境应置于 TLS 反向代理之后，使用 Secret Manager 注入密钥，并按容量需要替换为托管 PostgreSQL、Redis 与 Qdrant。

迁移到其他服务器时复制代码和根 `.env`，挂载相同递归结构的医学知识库，并按数据库规范备份或恢复命名卷数据。

## 项目结构

以下目录只展示版本库中的稳定源码、配置与用户文档；不会列出被 `.gitignore` 排除的环境文件、依赖、缓存、构建产物、工具目录或本地资料。

```text
gerclaw-main-codex/
├── .env.example                         唯一环境变量模板与中文配置说明
├── requirements.txt                     pip 后端运行依赖与本地 API 包安装入口
├── requirements-dev.txt                 pip 测试、类型与代码质量依赖
├── app.py                               本地 API/Web/迁移/RAG 索引统一入口
├── start.sh                             本地开发一键启动脚本（Docker 检查与命令入口）
├── docker.sh                            Docker 初始化、启停、索引、日志和测试入口
├── docker-compose.yml                   生产编排与运维任务
├── docker-compose.dev.yml               本地数据服务端口映射
├── README.md                            产品与使用说明
├── ARCHITECTURE.md                      系统架构与模块边界
├── AGENTS.md                            开发者代理操作规则与读取顺序
├── knowledge-base/
│   ├── README.md                        初始语料使用与扩展说明
│   └── md/                              按医学主题组织的 Markdown 知识库（18 个老年科主题）
├── apps/
│   ├── api/                             FastAPI + AgentScope 后端
│   │   ├── Dockerfile                   production/test 多阶段 Python 镜像
│   │   ├── pyproject.toml               Python 依赖、CLI 与质量工具配置
│   │   ├── uv.lock                      Python 依赖锁
│   │   ├── alembic.ini                  Alembic 配置
│   │   ├── migrations/
│   │   │   ├── env.py                   异步迁移运行环境
│   │   │   └── versions/                数据库版本迁移
│   │   ├── scripts/                     SSE 与用药工作流性能脚本
│   │   ├── tests/                       API、模块、契约与集成测试
│   │   └── src/gerclaw_api/
│   │       ├── main.py                  FastAPI/Uvicorn 入口
│   │       ├── application.py           应用依赖装配与生命周期
│   │       ├── config.py                根环境配置与 Provider 能力校验
│   │       ├── auth.py                  JWT、角色、账户和游客身份
│   │       ├── encryption.py            临床数据字段级加密
│   │       ├── security.py              安全原语与边界
│   │       ├── context.py / context_capacity.py  上下文预算与容量控制
│   │       ├── metrics.py / logging.py  运行指标与日志边界
│   │       ├── middleware.py            请求边界、限流、Trace 与错误处理
│   │       ├── api/routes/              Chat、Auth、CGA、处方、RAG、Skill、Voice 路由
│   │       ├── database/                SQLAlchemy 模型与异步会话
│   │       ├── repositories/            账户、会话、处方、Memory、Trace 数据访问
│   │       ├── services/                Chat、CGA、模型路由、处方与审计应用服务
│   │       └── modules/
│   │           ├── agent_harness/        Agent 执行、证据与输出治理（含 routing/planning/evidence/evolution）
│   │           ├── runtime/              注册、权限、预算、版本和工具契约
│   │           ├── orchestration/        对话协调与状态推进
│   │           ├── workflows/            医疗工作流注册与 profile
│   │           ├── prescription/         五大处方输入、生成、康复校验与报告 schema
│   │           ├── medication_review/    DDI、剂量、重复、多重用药与 Beers 规则
│   │           ├── cga/                  五类 CGA 量表定义与计分
│   │           ├── rag/                  解析、切分、索引、Hybrid Retrieval 与 Rerank
│   │           ├── memory/               健康事实提取、存储、检索与压缩
│   │           ├── skill/                Skill 导入、生成、质检、注册与执行
│   │           ├── document/             私有上传文档管理
│   │           ├── input_output/         文本、图片、附件和临床输入契约
│   │           ├── voice/                ASR/TTS 适配与音频 schema
│   │           ├── search/               AnySearch/Tavily、证据与降级
│   │           ├── chronic_care/         慢病记录与随访结构
│   │           ├── risk_alert/           风险信号与状态管理
│   │           ├── privacy_redaction/    统一隐私脱敏与数据分类
│   │           ├── security_evaluation/  运行时安全评测基线
│   │           ├── observability_feedback/ Trace、反馈与 Bad Case 聚合
│   │           ├── validation/           版本化结构校验
│   │           ├── consent/              授权数据结构
│   │           ├── identity/             账户密码能力
│   │           ├── companion/            情感陪伴响应边界
│   │           ├── evals/                RAG、Memory、Skill 与安全评测
│   │           └── tools/                Agent 工具协议
│   └── mvp/                              Next.js Web 与 server-only BFF
│       ├── Dockerfile                    standalone 多阶段 Node 镜像
│       ├── package.json                  dev/build/lint/test/start 命令
│       ├── next.config.ts                根配置加载与公开变量白名单
│       ├── public/audio/cga/              版本绑定的量表预录音频与 manifest
│       ├── scripts/                      根配置启动与量表音频生成脚本
│       ├── e2e/                          Playwright 端到端测试
│       └── src/
│           ├── app/                      页面入口和同源 API Routes
│           ├── components/
│           │   ├── account/              登录、注册、角色账户与管理员仪表盘
│           │   ├── chat/                 对话工作台、消息操作与反馈（👍/👎 + 评论）
│           │   ├── artifact/             产物工作台与导出
│           │   ├── prescription/         五大处方补充对话、报告与医生复核
│           │   ├── cga/                  CGA 评估界面
│           │   ├── chronic/              慢病账本
│           │   ├── consent/              患者授权
│           │   ├── risk-alert/           风险警报
│           │   ├── document/editor/      文档工作台与实时编辑渲染
│           │   ├── skills/               Skill 列表与生成
│           │   ├── search/health/        Web 搜索与健康画像
│           │   ├── settings/help/        模型配置与角色分离教程
│           │   ├── layout/runtime/       工作台布局与运行时状态
│           │   └── ui/                   无障碍组件、加载状态与执行时间线
│           ├── server/                   BFF 地址、游客身份与服务端访问
│           ├── services/                 API client、Zod schema、导出与 Provider 适配
│           ├── stores/                   会话与界面状态
│           ├── context/                  身份、主题和全局上下文
│           ├── hooks/                    交互与数据 hooks
│           ├── lib/                      Markdown、导出、语音与共享工具
│           ├── generated/                CGA 音频版本 manifest
│           └── types/                    前端 TypeScript 类型
├── docs/
│   ├── references/                       产品设计要求与五大处方模板
│   ├── product-specs/                    各业务功能产品契约
│   ├── design-docs/                      核心原则与技术设计
│   ├── exec-plans/                       版本化执行计划
│   ├── PRD.md                            产品需求基线
│   ├── AGENT_HARNESS.md                  Agent Harness 组件、上下文、Memory、RAG 与安全边界
│   ├── FRONTEND.md                       前端工程与交互规范
│   ├── DESIGN.md                         视觉设计规范
│   ├── SECURITY.md                       安全与医疗输出边界
│   ├── RELIABILITY.md                    超时、重试与降级规范
│   ├── PRODUCT_SENSE.md                  产品直觉与好坏判断
│   ├── DEVELOPMENT_HARNESS.md            开发运行时与测试基建
│   ├── SYSTEM_DESIGN_SPEC.md             系统设计规格
│   └── SUPPLY_CHAIN.md                   供应链安全基线
└── scripts/
    ├── check-root-env.py                 根环境配置一致性检查
    ├── docker-smoke.sh                   隔离 Docker 启动检查
    ├── quality-gate.sh                   测试、迁移与 E2E 命令入口
    ├── verify-docs.py                    文档与实现一致性检查
    └── generate_runtime_sbom.py          运行镜像 SBOM 生成
```

## 文档

- [系统架构](ARCHITECTURE.md)
- [Agent Harness 架构与安全边界](docs/AGENT_HARNESS.md)
- [产品需求](docs/PRD.md)
- [产品直觉](docs/PRODUCT_SENSE.md)
- [前端规范](docs/FRONTEND.md)
- [视觉设计](docs/DESIGN.md)
- [安全边界](docs/SECURITY.md)
- [可靠性](docs/RELIABILITY.md)
- [供应链安全](docs/SUPPLY_CHAIN.md)
- [开发运行时与测试基建](docs/DEVELOPMENT_HARNESS.md)
- [系统设计规格](docs/SYSTEM_DESIGN_SPEC.md)
- [五大处方产品规格](docs/product-specs/五大处方.md)

## 医疗使用边界

GerClaw 是临床辅助和健康管理工具，不替代医生面诊、诊断、处方签署或紧急医疗服务。

- 医疗建议必须结合本地知识库、联网搜索或用户上传资料中的可追溯证据。
- 存在证据的高风险建议可以输出；患者端在全文末尾统一提示风险，医生端保留完整证据与专业判断空间。
- 没有对应证据的高风险结论不会作为可执行建议展示。
- 出现胸痛、呼吸困难、意识改变、疑似卒中、自伤风险等紧急情况，应立即联系当地急救服务。
