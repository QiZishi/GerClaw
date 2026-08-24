# GerClaw

[English](README.md) | 中文

GerClaw 是一个基于 DeepSeek Harness、按账号完全隔离的健康工作台。它把健康对话、五大处方、CGA 固定计分、用药核对、慢病记录、本地医学 RAG、文档解析和结果下载放在同一套面向医生与患者的界面中。

> GerClaw 用于健康信息整理和辅助复核，不能替代诊断、治疗、处方、急救服务或专业判断。

## Run

需要 Node.js 24+、pnpm 10+，以及已配置的根目录 `.env`。

## Run from source

```bash
pnpm install
pnpm build:lib:host
pnpm gerclaw
```

打开 <http://127.0.0.1:3000>。启动器只读取项目根目录 `.env`；缺少配置时只报告变量名，不输出变量值。

`pnpm gerclaw:dump-config` 可核对真实 Loader 组合。非 localhost 环境要使用浏览器麦克风时，请在服务前配置可信 HTTPS 反向代理。

## 核心能力

- 注册、登录、恢复码重置、游客空间和账号独立子 Host。
- DSH 原生会话、Workspace、文件、产物、Memory、工具、Plan 和 Goal。
- GerClaw 专属 System Prompt，以及随访问卷、风险评估、健康宣教、用药提醒四项可调用技能。
- 药物、运动、营养、心理、康复五章处方草案。
- PHQ-9、SAS、PSQI、Mini-Cog、MMSE 固定规则计分。
- 可追溯用药规则、结构化健康档案、慢病测量、风险提醒和陪伴模式。
- 对话输入框内的 Qianwen 实时 ASR 与流式 TTS；不保存原始音频。
- 固定本地知识库、SiliconFlow embedding/rerank、`dsh-library`、MinerU、PubMed、openFDA、MedlinePlus。
- Markdown、HTML、DOCX、PDF、PNG、JPG、JSON 七种导出。

## 系统架构

`@gerclaw/launcher` 通过真实 DSH Web Loader 启动账号网关。网关为每个注册账号或游客启动一个只监听 loopback 的子 Host。子 Host 加载 `packages/gerclaw/profile-bundle/cordis.patch.yml`：停用默认系统提示语和开发者 Web 界面，挂载 GerClaw 插件，同时保留原生运行服务。

每个注册账号分别拥有 `DSH_HOME`、Workspace、session log、SQLite storage、Memorix 目录、上传文件、RAG 索引和产物。网关只认证与代理，不读取医疗内容。医生与患者只改变称呼，功能和数据权限完全相同。

## 配置

以 `.env.example` 为变量清单，在现有根目录 `.env` 中填写实际值。

| 用途 | 变量 |
| --- | --- |
| 主模型 | `AGENT_PRIMARY_API_KEY`、`AGENT_PRIMARY_URL`、`AGENT_PRIMARY_MODEL` |
| Qianwen ASR | `MODEL_ASR_KEY`、`MODEL_ASR_URL`、`ASR_MODEL` |
| Qianwen TTS | `MODEL_TTS_KEY`、`MODEL_TTS_URL`、`TTS_MODEL` |
| 本地 RAG | `SILICONFLOW_API_KEY`、`SILICONFLOW_URL`、`EMBEDDING_MODEL`、`RERANK_MODEL` |
| MinerU | `MINERU_API_KEY`、`MINERU_URL` |

ASR 固定使用 `qwen3-asr-flash-realtime`，TTS 固定使用 `qwen3-tts-instruct-flash-realtime`。SiliconFlow 只用于 embedding 与 rerank，不进入语音代码路径。

## 医学知识库与 MinerU

根目录 `knowledge-base/` 是 `gerclaw-main-codex/knowledge-base` 的完整校验副本。账号启动时只补充缺失文件；同名内容冲突会停止，不会覆盖。`@gerclaw/local-rag` 对全部 Markdown/text 原文进行保留来源路径的分片索引，检索结果包含原文件相对路径与块号。

更新知识库时，应在根目录 `knowledge-base/` 中有意增改源文件并审查 diff，然后为新索引调整 library 版本或创建新账号索引；不要直接修改账号目录中的生成索引。

PDF 和 DOCX 通过 GerClaw 的“文档资料”页面上传，由 `dsh-mineru@0.1.9` 真实解析后进入本账号个人索引。Markdown 和 text 文件直接索引。任何账号都不能查询另一个账号的上传文件。

## GerClaw 专属插件位置

| 插件 | 路径 | 职责 |
| --- | --- | --- |
| 业务 App | `packages/gerclaw/client` | 类型化业务 API、任务状态、session events 与导出 |
| 产品前端 | `packages/gerclaw/client-ui` | 原生对话工作台主题、医疗入口、任务卡与产物侧栏 |
| CGA | `packages/gerclaw/cga` | 五种固定规则量表 |
| 慢病管理 | `packages/gerclaw/chronic-care` | 测量与趋势 |
| 陪伴模式 | `packages/gerclaw/companion` | 支持性对话与危险信号 |
| 健康档案 | `packages/gerclaw/health-profile` | 权威结构化资料 |
| 本地 RAG | `packages/gerclaw/local-rag` | 固定知识库与个人资料检索 |
| 医学证据 | `packages/gerclaw/medical-evidence` | PubMed、openFDA、MedlinePlus |
| 用药审查 | `packages/gerclaw/medication-review` | DDI、剂量、重复、多药、Beers 信号 |
| 五大处方 | `packages/gerclaw/prescription` | 证据约束的五章报告 |
| 风险提醒 | `packages/gerclaw/risk-alert` | 多来源确定性提醒 |
| 技能 | `packages/gerclaw/skills` | 四项 GerClaw DSH skill |
| 系统提示语 | `packages/gerclaw/system-prompt` | GerClaw 专属模型边界 |
| 语音 | `packages/gerclaw/voice` | 对话内 ASR/TTS 桥接 |
| Profile Bundle | `packages/gerclaw/profile-bundle` | 真实 Cordis Loader 接入 |
| 账号网关 | `packages/gerclaw/tenant-gateway` | 认证、隔离、子 Host |
| 启动器 | `packages/gerclaw/launcher` | 环境检查与启动 |

每个目录都有面向后续开发者的 README，说明职责和非职责、复用能力、服务与类型、数据恢复、卸载、扩展、测试和限制。

## 验证

```bash
pnpm gerclaw:dump-config
pnpm test
pnpm typecheck
pnpm lint
pnpm build
pnpm docs:check
pnpm check:all
```

最终用户验收要在 GerClaw 浏览器界面真实执行，包括主模型、Qianwen 语音、本地 RAG、MinerU、全部量表、七种导出、账号隔离、响应式布局和卸载残留检查。

## 项目结构

```text
knowledge-base/
packages/gerclaw/
apps/cli/
packages/
.env.example
icon.png
```

## 医疗使用边界

GerClaw 的处方、量表、用药核对、风险和陪伴结果都保持辅助决策定位。严重风险会提示立即求助，但不会增加医患角色门禁、审批链或功能限制。开始、停用或调整药物必须由专业人员结合完整临床资料复核。

## 许可证与来源

DSH 底座保留原许可证。语音派生实现的 `dsh-talk@0.1.3` 和 `dsh-speech-plugin` 来源、许可证与修改记录位于 `packages/gerclaw/voice/NOTICE` 和 `LICENSES/`。社区依赖使用锁定版本并保留上游许可证。
