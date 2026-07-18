# GerClaw

GerClaw 是面向老年患者、老年科医生与系统管理员的 Web 端 AI 辅助诊疗平台。它把多模态健康对话、CGA 综合评估、五大处方草案、用药审查、医学知识检索、语音交互与个人健康资料管理整合到一套可私有部署的系统中。

系统以循证辅助和人工复核为原则，不替代执业医生，不提供急救服务，也不把模型输出直接执行为处方或治疗操作。

## 产品简介

GerClaw 提供三个彼此隔离的使用空间：

- 患者端：适老化对话、语音输入与播报、文件和图片解读、CGA 量表、健康记录、五大处方草案及历史记录。
- 医生端：面向临床工作的患者资料整理、CGA 报告、处方草案、用药审查、证据检索、文档编辑、Skill 与辅助决策工具。
- 管理端：账户、角色和系统运行配置管理；管理员可切换患者端与医生端视角。

登录页是统一入口。使用者可以登录已有账户、创建账户，也可以选择无账号进入患者端。访客数据仍写入后台用于运行质量分析，但访客历史不会在下一次进入时恢复。医生与患者之间没有即时通信或消息互通功能。

## 核心功能

| 功能 | 能力 |
|---|---|
| AI 健康对话 | 支持文本、语音、图片和已解析文档；保留会话、引用、反馈与执行状态 |
| 五大处方 | 在聊天框接收最多 10 份资料和文本/语音信息，按模板最多补充询问 5 轮，生成药物、运动、营养、心理和康复处方草案 |
| CGA | 提供 PHQ-9、SAS、PSQI、Mini-Cog、MMSE 评估、计分、报告、导出和题目预录音频 |
| 用药审查 | 识别重复用药、部分 DDI、Beers 信号、剂量阈值与多重用药风险，并展示规则来源 |
| 医学 RAG | 对外部挂载的 Markdown 医学知识库执行分块、Embedding、Hybrid Retrieval、Rerank 和引用回溯 |
| 联网搜索 | AnySearch 为主、Tavily 为备用，将受治理的网页结果作为可追溯证据 |
| Memory | 按账户和访客会话提取、检索和管理长期健康事实，不在向量库保存 PHI 正文 |
| Skill | 导入 Markdown/ZIP Skill，使用自然语言生成或迭代 Skill 草稿，经人工审阅后保存 |
| 文档工作台 | 单页单栏编辑，输入时实时渲染预览，并支持 Markdown、PDF、DOCX 导出 |
| 多模态证据 | 图片进入支持视觉的模型上下文，同时获得 evidence ID，并以 base64 记录到受控 Trace |
| MinerU 文档解析 | PDF 等病例资料通过 MinerU 转换为 Markdown，作为当前患者输入和处方证据，不写入公共知识库 |

## 快速开始

### 运行条件

- Docker Engine 24 或更新版本
- Docker Compose v2
- 至少 8 GB 可用内存；索引大型知识库时建议 16 GB 以上
- 可用的 LLM、Embedding 与 Rerank 服务配置
- 需要语音、联网搜索或文档解析时，准备对应 Provider 配置

### 一键部署

```bash
cp .env.example .env
```

编辑 `.env`，至少完成以下配置：

1. `AGENT_PRIMARY_*`：主模型 URL、API Key、模型名、协议与能力声明。
2. `SILICONFLOW_API_KEY`、`EMBEDDING_MODEL`、`RERANK_MODEL`：知识库索引与检索。
3. `GERCLAW_KNOWLEDGE_BASE_HOST_PATH`：宿主机医学知识库目录。
4. 生产部署必须设置 `GERCLAW_AUTH_JWT_SECRET`、`GERCLAW_GUEST_IDENTITY_SECRET` 和 `GERCLAW_DATA_ENCRYPTION_KEY`。

首次启动并建立知识库索引：

```bash
./docker.sh init
```

浏览器访问：

- GerClaw Web：`http://127.0.0.1:3000`
- API 健康检查：`http://127.0.0.1:8000/health/ready`

端口可通过 `.env` 中的 `WEB_PORT` 和 `API_PORT` 修改。

## 配置指南

### 模型与服务

部署者可以在 `.env` 设置系统默认 Provider。登录账户还可以从“设置 → 模型与服务配置”保存自己的账户级配置；账户配置采用加密存储，读取页面只显示是否已配置，不回显 API Key。未设置账户覆盖时使用部署默认值。

配置页包含：

- 主模型、备用模型一、备用模型二
- Embedding 与 Rerank
- AnySearch 与 Tavily
- ASR 与 TTS
- MinerU

每组配置下方都有默认折叠的获取与填写说明。模型插槽必须如实声明图片输入、工具调用和结构化输出能力；需要处理图片的对话必须选择支持 image input 的模型。

### 关键环境变量

| 配置组 | 主要变量 |
|---|---|
| Web/API | `WEB_PORT`、`API_PORT`、`GERCLAW_API_URL`、`GERCLAW_CORS_ORIGINS` |
| 身份与加密 | `GERCLAW_AUTH_JWT_SECRET`、`GERCLAW_GUEST_IDENTITY_SECRET`、`GERCLAW_DATA_ENCRYPTION_KEY` |
| Agent 模型 | `AGENT_PRIMARY_*`、`AGENT_BACKUP1_*`、`AGENT_BACKUP2_*` |
| RAG | `SILICONFLOW_API_KEY`、`SILICONFLOW_URL`、`EMBEDDING_MODEL`、`RERANK_MODEL` |
| 搜索 | `ANYSEARCH_*`、`TAVILY_*` |
| 语音 | `MIMO_API_KEY`、`MIMO_ASR_URL`、`MIMO_TTS_URL`、`ASR_MODEL`、`TTS_MODEL`、`TTS_VOICE` |
| 文档 | `MINERU_URL`、`MINERU_API_KEY`、`MINERU_ALLOWED_HOSTS` |
| 知识库 | `GERCLAW_KNOWLEDGE_BASE_HOST_PATH`、`GERCLAW_RAG_COLLECTION_NAME` |

完整字段、默认值和说明以 [.env.example](.env.example) 为准。Provider URL、模型名、协议、密钥和端口均从配置读取，不需要修改源码。

## 使用指南

### 患者端

1. 在登录页登录、注册，或选择无账号使用。
2. 从患者工作台选择健康对话、CGA、五大处方或个人健康记录。
3. 在聊天框输入文字、录音，或上传图片和文档；长任务顶部会持续显示运行动画和已执行时间。
4. 播放回答或量表题目时，可以暂停、继续、停止并查看播放进度。
5. 医疗建议的风险提示集中显示在内容末尾，正文保留证据、条件和可操作信息。

### 医生端

1. 使用医生账户登录医生工作台。
2. 选择临床对话、CGA、五大处方、用药审查、知识检索、文档或 Skill 工具。
3. 检查模型结论的 evidence ID、引用来源、适用条件和输入资料。
4. 将处方草案和量表结果作为辅助资料复核；系统不会自动签署、发布或执行临床决定。

患者端和医生端的“帮助”按钮分别打开对应角色的完整教程，不展示另一端的操作说明。

## Docker 管理

根目录 [docker.sh](docker.sh) 是完整系统的统一入口：

```bash
./docker.sh init       # 首次构建、启动、索引知识库并检查 readiness
./docker.sh up         # 构建并启动 Web、API 和数据服务
./docker.sh down       # 停止服务并保留数据库、缓存和向量卷
./docker.sh restart    # 重启 Web 与 API
./docker.sh index      # 在知识库变化后增量更新索引
./docker.sh status     # 查看容器及 live/ready 状态
./docker.sh logs       # 持续查看 Web 与 API 日志
./docker.sh test       # 使用隔离测试数据库运行后端集成测试
```

Compose 服务包括 Web、API、Alembic migration、PostgreSQL、Redis、Qdrant，以及按需执行的 RAG index 和 test-api。Web 与 API 容器使用非 root 用户运行，数据保存在命名卷中；`down` 不删除数据卷。

生产部署应在反向代理后启用 TLS，使用 Secret Manager 注入密钥，并根据容量需求改用托管 PostgreSQL、Redis 和 Qdrant。不要把数据库、Redis 或 Qdrant 端口直接暴露到公网。

## 数据与知识库

知识库使用外部只读挂载，不复制进镜像。默认宿主机目录为 `../本地知识库/md`，可通过以下变量指定任意目录：

```dotenv
GERCLAW_KNOWLEDGE_BASE_HOST_PATH=/absolute/path/to/medical-knowledge/md
```

外挂目录保持“主题文件夹 / Markdown 文档”的递归结构即可扩展语料。修改文档后执行：

```bash
./docker.sh index
```

索引器根据内容哈希增量处理文档。公共医学知识库进入 Qdrant；患者上传的文档、图片、聊天、量表答案和处方资料保存在账户或会话边界内，不会混入公共 RAG 语料。

PostgreSQL 是账户、会话、消息、临床产物、授权和 Trace 的事实源；Redis 保存限流、会话 lease 与取消状态；Qdrant 保存公共知识向量和不含 PHI 正文的 Memory reference vector。

## 本地源码运行

不使用 Docker 时，可从根目录启动：

```bash
python3 app.py
```

该入口启动前端与 API，并输出本地访问地址。其他模式可通过以下命令查看：

```bash
python3 app.py --help
```

## 安全与医疗声明

- GerClaw 是辅助工具，不替代医生面诊、诊断、处方签署或紧急医疗服务。
- 出现胸痛、呼吸困难、意识改变、疑似卒中等紧急情况时，应立即联系当地急救服务。
- 模型可以在存在本地知识库、联网搜索或用户上传资料证据时给出诊断方向、用药调整候选和临床建议；用户必须结合证据和专业判断复核。
- 患者端在高风险内容末尾统一提示风险；医生端保留证据绑定的完整建议，不做机械屏蔽。
- 生产环境必须更换示例密码和密钥、启用 TLS、设置备份，并限制 Provider 和数据库网络访问。

## 故障排查

### 首次执行提示填写配置

`docker.sh` 会在缺少 `.env` 时复制模板并退出。填写配置后重新执行 `./docker.sh init`。

### API live 正常但 ready 失败

执行 `./docker.sh status` 查看具体检查项。常见原因是知识库尚未索引、Embedding/Rerank 配置无效，或 PostgreSQL、Redis、Qdrant 尚未就绪。修正配置后执行 `./docker.sh index`。

### Web 无法访问 API

Docker 内部 BFF 固定使用 `http://api:8000`。检查 `web` 和 `api` 是否处于 healthy 状态，并通过 `./docker.sh logs` 查看请求错误。源码运行时，`GERCLAW_API_URL` 应指向本机 API 地址。

### 知识库目录为空

确认 `GERCLAW_KNOWLEDGE_BASE_HOST_PATH` 是 Docker 可读取的绝对路径，目录中包含 `.md` 文件。macOS 或 Windows 使用 Docker Desktop 时，还需要允许共享该宿主机目录。

### Provider 调用失败

检查 URL、API Key、模型名、协议和能力声明是否属于同一 Provider。账户级配置不完整时不会覆盖系统默认配置。

## 项目结构

```text
app.py                 本地源码启动入口
docker.sh              完整 Docker 部署与管理入口
docker-compose.yml     Web、API、数据服务和运维任务
apps/mvp/              Next.js 前端与 server-only BFF
apps/api/              FastAPI、AgentScope、领域模块和数据库迁移
docs/references/       产品设计要求与报告模板
docs/                  产品、安全、可靠性与维护文档
ARCHITECTURE.md         系统架构说明
开发复盘.md             项目问题、工程化设计与 Bad Case 复盘
```

系统设计与扩展边界见 [ARCHITECTURE.md](ARCHITECTURE.md)，完整开发复盘见 [开发复盘.md](开发复盘.md)。
