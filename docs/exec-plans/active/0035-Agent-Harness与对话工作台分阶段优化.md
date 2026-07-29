# 0035 — Agent Harness 与对话工作台分阶段优化

> 创建：2026-07-29 | 优先级：P0 | 状态：进行中  
> 最高权威：`docs/references/gerclaw设计要求.md`  
> 产品偏好：`MEDICAL_AGENT_SYSTEM_OPTIMIZATION_GUIDE.md`

## 1. 目标与边界

在不推倒现有 AgentScope、Runtime、Memory、RAG、Search、Skill、Workflow 和会话事实源的前提下，分阶段完成 Harness 模块化、Run 状态机、临床状态与动态规划、证据/能力治理、对话工作台重构、隔离离线演化和最终回归。

GerClaw 保持老年医学定位。眼科病灶定位不在本计划范围。在线请求不得自动修改 Prompt、Memory、Skill、路由、代码或安全门。

每一阶段必须是独立变更集，完成相关测试、真实 GUI 审阅和 Conventional Commit 后才能进入下一阶段。阶段内只跑相关测试；阶段 7 才跑全量回归。

## 2. 阶段与状态

| 阶段 | 交付目标 | 状态 |
|---|---|---|
| 0 | 冻结基线与真实运行审计 | 已完成：HTTP/API/测试、Playwright GUI、清理及独立审阅通过 |
| 1 | Harness 模块化与稳定合同 | 已完成：两轮审阅问题修复，最终独立审阅 ACCEPT |
| 2 | Run 事实源、状态机和恢复 | 已完成：两轮 P1 修复、真实 GUI 对抗审计、最终独立复审 ACCEPT |
| 3 | ClinicalState、动态规划与医疗门禁 | 已完成：四轮独立审阅修复、真实 GUI 与最终 ACCEPT |
| 4 | 证据、Memory 与受治理能力组合 | 实现与真实 GUI 审计完成，等待独立复审 |
| 5 | 对话工作台 UI 与交互重构 | 未开始 |
| 6 | 受控离线自进化 | 未开始 |
| 7 | 最终回归、真实 GUI 对抗审阅与发布 | 未开始 |

## 3. 阶段 0：冻结基线与真实运行审计

### 3.1 仓库基线

- 分支：`main`
- 基线 commit：`10511e783398bfff664ccd781e8634bd91e59150`
- 审计开始时工作区不是 clean；以下均视为用户已有改动，本计划不得覆盖或夹带：
  - 已修改：`AGENTS.md`、`README.md`、`scripts/verify_docs.py`
  - 已删除：`docs/PLANS.md`、`docs/QUALITY_SCORE.md`、`docs/REQUIREMENTS_MATRIX.md`、`docs/exec-plans/tech-debt-tracker.md`、`开发复盘.md`，以及 active 0023、0026、0029、0030、0032、0034
  - 未跟踪：`.github/skills/project-overview-builder/SKILL.md`、`MEDICAL_AGENT_SYSTEM_OPTIMIZATION_GUIDE.md`、`docs/AGENT_HARNESS.md`、`start.sh`
- 本计划只新增本文件；阶段提交必须使用精确 pathspec，不能提交上述已有改动。
- `README.md` 与未跟踪的 `docs/AGENT_HARNESS.md` 同时也是阶段 7 的预定更新目标。未来触碰前必须先保存并核对用户现有 diff、确认所有权与合并方式；精确 pathspec 只能防止误提交，不能防止内容覆盖。

### 3.2 运行环境与配置事实

审计环境：

- macOS，Asia/Shanghai
- Python：系统 `3.14.5`；后端使用现有 `apps/api/.venv`（Python 3.12）
- Node.js：`v24.16.0`
- npm：`11.16.0`
- Docker：`29.6.1`
- Docker Compose：`v5.3.0`
- 前端依赖与后端虚拟环境均已存在。

配置检查：

- `python3 scripts/check-root-env.py` 未通过：根 `.env` 的 `AGENT_PRIMARY_MODEL` 与 `.env.example` 非密钥默认值不一致。未输出实际模型名或密钥。
- 三个 Agent slot 均已提供配置：`primary/openai`、`backup1/dashscope`、`backup2/openai`；三者均声明 image、tool calling 和 structured output。
- RAG、AnySearch、Tavily、ASR、TTS、MinerU 的必要配置均已提供；阶段 0 未为证明“可用”而调用付费语音、搜索、MinerU 或模型服务。

### 3.3 真实启动与健康状态

实际执行：

```bash
python3 app.py
```

结果：

- PostgreSQL、Redis、Qdrant 启动成功。
- Alembic migration 成功。
- FastAPI 启动于 `http://127.0.0.1:8000`。
- Next.js 16.2.10 dev server 启动于 `http://127.0.0.1:3000`。
- `GET /health/live`：200，`alive`。
- Web 根页：200，`text/html`。
- `GET /health/ready`：503 / `not_ready`。PostgreSQL、Redis、Qdrant、436 份 Markdown、Memory、Search、AgentScope 均通过；RAG index 为 `0 documents / 0 chunks`，因此 readiness 失败。
- API 启动日志有 Qdrant 本地 HTTP + API key 的 insecure connection warning；这是本地开发连接，不是生产通过结论。

### 3.4 基线测试

关键后端测试使用真实独立 `gerclaw_test`、Redis DB 15 和 Qdrant 执行：

```bash
cd /Users/qizs/conclusion/gerclaw/gerclaw-main-codex
apps/api/.venv/bin/python -c '
import subprocess
import sys

sys.path.insert(0, ".")
import app

env = app.local_process_environment()
env["GERCLAW_RUN_INTEGRATION"] = "1"
for name in (
    "GERCLAW_TEST_DATABASE_URL",
    "GERCLAW_TEST_REDIS_URL",
    "GERCLAW_TEST_QDRANT_URL",
):
    env[name] = app.replace_service_host(env[name])
subprocess.run(
    [
        ".venv/bin/python", "-m", "pytest", "--no-cov", "-q",
        "tests/test_agent_harness.py",
        "tests/test_agent_harness_safety.py",
        "tests/test_runtime_budget.py",
        "tests/test_runtime_permission.py",
        "tests/test_runtime_registry.py",
        "tests/test_workflow_registry.py",
        "tests/test_chat_cancellation.py",
        "tests/test_chat_integration.py",
    ],
    cwd="apps/api",
    env=env,
    check=True,
)
'
```

结果：`103 passed, 9 warnings in 11.20s`。9 条 warning 均为测试环境 Qdrant HTTP + API key 提示。

前端定向契约：

```bash
cd /Users/qizs/conclusion/gerclaw/gerclaw-main-codex/apps/mvp
npm run test:feedback
npm run test:chat
npm run test:prescription-report
```

结果：`6 passed, 0 failed`。Node 报告 `.ts` 测试文件缺少 package `"type": "module"`，测试仍通过；该 warning 需在后续前端阶段处理或明确保留原因。

### 3.5 不经外部医疗服务的真实 BFF/API 演练

使用一个临时访客身份和临时会话，通过 Next.js BFF 实际执行后删除会话：

| 路径 | 结果 | 结论 |
|---|---|---|
| `POST /api/gerclaw/sessions` | 200，返回 owner-scoped active session | 已验证 |
| `GET /api/gerclaw/memory/profile` | 200，空 profile、空 facts | 已验证空态 |
| `GET /api/gerclaw/cga/scales` | 200，返回 PHQ-9、SAS、PSQI、Mini-Cog、MMSE 服务端量表 | 已验证合同 |
| `POST /api/gerclaw/chat`（胸痛、呼吸困难） | `agent_start → safety_notice → text_delta → done` | 已验证 SSE 与模型前红旗短路 |
| 红旗正文 | 明确“立即拨打 120 或尽快前往急诊”，带统一免责声明，无伪造引用 | 已验证医疗底线 |
| `DELETE /api/gerclaw/sessions/{id}` | 200，`deleted: true` | 已清理临时会话 |

本次红旗路径未调用模型、RAG、搜索或语音 Provider。

### 3.6 Playwright 真实 GUI 审计

用户指定使用项目内置 Playwright CLI。实际启动 Chrome headless 会话并开启 trace：

```bash
npx --yes --package @playwright/cli playwright-cli \
  -s=gerclaw-stage0 open http://127.0.0.1:3000 --browser chrome
npx --yes --package @playwright/cli playwright-cli \
  -s=gerclaw-stage0 tracing-start
```

审计使用真实 Next.js BFF、FastAPI、PostgreSQL、Redis 和 Qdrant，没有 route mock。证据保存在 gitignored 的
`output/playwright/stage0/` 和 `.playwright-cli/traces/trace-1785313900498.trace`；后端/前端联合日志为
`output/playwright/stage0/app.log`，网络清单为 `requests.txt`，控制台清单为 `console.txt`。

真实结论：

- 登录页、游客进入、注册、退出、重新登录均通过；登录后的 `/api/account/status` 返回
  `authenticated: true`、`role: patient`。测试账户仅用于本地审计，凭据未写入版本库。
- 游客红旗消息通过 GUI 发送，页面收到唯一完成态并高对比展示“立即拨打 120 或尽快前往急诊”及免责声明。
- 运行中出现带文字的“停止”按钮；点击后 UI 最终显示“回答已在发送前停止”，没有伪装为完整回答。现有 network
  只有原 `POST /chat` 的 200，不能据此证明服务端持久取消、fencing 或唯一终态；这些语义留待阶段 2 验证。
- “重新生成”替换旧回答而未复制用户消息，但当前仍是本地删除/重发语义；真实重试触发医学检索响应合同错误并失败。
- Markdown 测试文件 179 B 在浏览器真实上传并本地解析，显示“资料已解析，发送即可”；未使用真实患者数据、未调用 MinerU。
- Memory 健康档案面板真实请求 200，正确显示空态；右栏分隔条键盘 `ArrowLeft/ArrowRight` 可按 16 px 调宽并恢复。
- 语音按钮已在 headless Chrome 真实点击，但提示自动消失，现有截图和持久 YAML 只能证明点击，不能持久核验
  麦克风拒绝降级状态。真实 ASR/TTS Provider 均未调用，因此两者均判定未验证。
- 账号设置和模型配置可读取，API Key 不回显；本轮未保存配置。
- 分享对话可打开格式/消息选择器；选择用户消息后真实下载 Markdown，文件含所选正文和医疗免责声明。
- 1440×1000、1024×768、768×900、390×844 均无页面级横向溢出；患者老年模式可见文字最小 20 px。
  390 px 使用移动抽屉。公开“分析已完成”控件高度为 45 px，未达到本计划 48 px 目标。
- 游客工作台没有 Skill 管理入口；账号重新登录后，侧栏和 Composer 均出现“技能”，真实打开技能工作台并显示
  4 个系统技能及“加载到对话”操作。因此账号 Skill 浏览 GUI 已验证，游客限制符合当前权限设计；多选、组合和结果复用未验证。
- RAG readiness 为 0 documents / 0 chunks，无法生成可验证的真实引用；本轮判定“不可用”，没有用伪引用补齐。

关键截图：

- `desktop-login.png`、`desktop-login-success.png`、`desktop-guest-home.png`
- `desktop-redflag-done.png`、`desktop-stop.png`、`desktop-regenerate.png`
- `desktop-upload.png`、`desktop-voice.png`、`desktop-health-profile-panel.png`
- `desktop-skill.png`
- `desktop-guest-settings.png`、`desktop-account-settings.png`、`desktop-model-config.png`
- `tablet-1024-home.png`、`tablet-768-chat.png`
- `mobile-390-home.png`、`mobile-390-chat.png`、`mobile-390-menu.png`

发现的问题（阶段 0 只冻结事实，不修改生产行为）：

| 级别 | 现象 | 证据 / 后续 |
|---|---|---|
| P0 | 无 | — |
| P1 | 重生成失败时把 Zod `invalid_type` 细节原样展示给患者，违反公开摘要与信任边界要求 | `desktop-regenerate.png`；阶段 1/5 修复错误映射 |
| P1 | RAG 有 436 份源文档但索引为 0，readiness 503，真实引用闭环不可用 | `app.log`；阶段 4 处理索引和引用门禁 |
| P2 | 注册账号名的 HTML `pattern` 在 Chrome `/v` 规则下报无效字符类 | trace console；阶段 5 修复并加浏览器测试 |
| P2 | 右栏打开后桌面 Composer 工具区在缩窄内容列中拥挤/裁切 | `desktop-health-profile-panel.png`；阶段 5 |
| P2 | 390 px Composer 隐藏处方信息、评估、档案三个入口 | `mobile-390-chat.png`；阶段 5 明确溢出菜单或保留入口 |
| P2 | “分析已完成”高度 45 px，低于计划中的患者控件 48 px | Playwright DOM 测量；阶段 5 |

### 3.7 需求—现状—缺口矩阵

| 核心路径 | 当前事实 | 结论 | 主要缺口/后续阶段 |
|---|---|---|---|
| 统一登录 / 游客入口 | 真实点击游客、注册、退出和重新登录；账号状态由服务端返回 patient | 已验证 | 阶段 7 再覆盖医生角色 |
| 游客会话 | BFF 自动签发 session cookie；会话、Memory、CGA BFF 实调成功 | 已验证 | 历史恢复留待 Run 事实源 |
| 发送 / SSE | 红旗输入完整收到唯一 `done` | 已验证高风险短路 | 普通模型、RAG 引用因 index 未就绪尚未验证 |
| 停止 / 取消 | GUI 运行中停止并呈现未完成安全态；没有持久取消请求/终态证据 | UI 已验证，服务端语义未验证 | 阶段 2 增加持久化唯一终态和 fencing |
| 重生成 | GUI 替换旧回答但仍删除本地 AI 消息后重发；真实重试暴露 Zod 错误 | 降级 | 阶段 2 改为 AnswerVersion，阶段 5 隐藏内部错误 |
| 上传 / MinerU | Markdown GUI 上传和本地解析通过；MinerU 未调用 | 部分已验证 | 阶段 4 验证解析复用，阶段 7 测 PDF |
| Skill | 账号 selection API 200；账号 GUI 可浏览 4 个系统技能并提供加载操作；游客无管理入口 | 账号浏览已验证 | 阶段 4/5 验证多选、组合和结果复用 |
| Memory | GUI profile 200 空态并显示真实空态 | 已验证空态 | proposed/confirmed 冲突治理在阶段 4 |
| 引用 | SSE `done.references` 合同与前端内联 Popover 存在 | 合同存在 | RAG index 为空，无法验证真实引用闭环 |
| 语音 | headless Chrome 已真实点击语音按钮；拒绝提示未形成可持久核验证据，Provider 未调用 | ASR/TTS 未验证 | 阶段 5/7 做真实 ASR/TTS、降级与停止分段 |
| 设置 | 账号模型配置真实读取，密钥不回显，未写入 | 读取已验证 | 阶段 7 验证保存/reload |
| 导出 | 浏览器真实下载 Markdown 并核对正文与免责声明 | 已验证 MD | 阶段 5/7 覆盖 PDF/DOCX/JPG |
| 右栏 | Memory 空态和键盘调宽真实通过 | 部分已验证 | 修复 Composer 拥挤，落实产物优先 |
| 响应式 / 老年模式 | 四个断点无页面横向溢出，最小可见字号 20 px，移动抽屉可用 | 部分通过 | 修复 45 px 控件和移动端隐藏入口 |

### 3.8 已确认结构债务

- `agent_harness/harness.py`：1340 行。
- `ChatInput.tsx`：1161 行。
- `ChatArea.tsx`：1006 行。
- `MessageBubble.tsx`：920 行。
- `Sidebar.tsx`：984 行。

上述文件明显超过项目“小组件、单一职责，超过 200 行考虑拆分”的约束，是阶段 1 和阶段 5 的直接输入。

### 3.9 浏览器工具决策记录

`browser:control-in-app-browser` 技能已按要求初始化，但运行时返回 `No browser is available`，浏览器发现结果为空。因此本轮不能：

- 点击登录/游客/发送/停止/重生成/上传/Skill/语音/设置/导出/右栏；
- 采集桌面、平板、手机和患者老年模式截图；
- 读取浏览器 console、network、下载文件；
- 完成独立 headless GUI 审阅。

随后用户明确指定项目 Playwright CLI。该路径成功启动独立 headless Chrome，完成上述审计并产出 trace；原 Browser MCP
不可用不再是阶段 0 阻塞。

### 3.10 阶段 0 收尾与证据边界

- `console.txt` 是退出、重新登录后的最终导航快照，因此显示 0 error；完整 trace 仍保留注册 `pattern` 错误，文档未将
  最终快照误报为全程无错误。
- 健康响应已另存为 `output/playwright/stage0/health-live.json` 和 `health-ready.json`：HTTP 分别为 200/503，
  后者明确记录 `source_documents: 436`、`indexed_documents: 0`、`indexed_chunks: 0`。
- trace 曾记录本轮测试账户的输入和会话 cookie。审计结束后已从 GUI 退出，Chrome context cookie 列表为空；本地测试账户
  `usr_account_197e74da5fb94ee29b12fc8cef5661ee` 已精确设为 `is_active=false`，trace 中的凭据不能再登录。
- Playwright 浏览器已关闭，API 与 Next.js 监听端口已释放；`postgres`、`redis`、`qdrant` Compose 服务均已停止，
  未删除 volume。
- `python3 scripts/verify_docs.py <workspace>` 当前失败于 `docs/PRD.md -> REQUIREMENTS_MATRIX.md`。目标文件属于审计开始前
  已存在的用户删除项，本阶段没有恢复或覆盖；该失败不冒充通过，并留待确认用户删除意图后处理。
- 独立审阅先提出 trace 凭据、取消证据边界、console/voice/health 和服务清理问题；上述问题均已修正或降级为
  “未验证”。复核后无 P0/P1，接受进入阶段 1。

## 4. 后续阶段验收摘要

### 阶段 1

拆分 Harness routing、planning、clinical_state、context_snapshot、run_lifecycle、evidence、plugin_runtime、evolution_signals；公共 facade 保持兼容。每个组件有 `AGENTS.md`、`README.md`、Protocol、强类型错误和独立测试；预算/阈值/超时/重试只从配置注入。

#### 阶段 1 实施记录（2026-07-29）

- 建立全部 8 个组件目录。每个目录均有大写 `AGENTS.md`、`README.md`、版本化 Pydantic 合同和公共 `__init__`。
- 将 `AgentContext`/历史合同迁入 `context_snapshot`，保留原 `protocols` import 兼容；将上传资料/图片投影迁入
  `UploadedInputProjector`。
- 将稳定 Harness 错误、句级医疗安全 buffer 和 canonical text stream 迁入 `run_lifecycle`；根 facade 保留旧私有别名，
  既有测试与消费者无需修改。
- 新增 `ResolvedHarnessConfig`，由 `Settings` 在组合边界一次解析。ReAct 轮数、输出上限、证据候选数、Memory 候选数和
  阈值不再由 Harness 各处分散读取。
- routing、planning、ClinicalState、Evidence、Plugin Runtime、Evolution Signal 本阶段只建立可独立构造/校验的合同，
  未激活第二套路由、检索、Memory、能力系统或在线演化。动态计划拒绝自引用、未知节点和依赖环。
- 根 `harness.py` 从 1340 行降至 27 行，只保留兼容 facade；生产组合入口为 745 行的 `orchestrator.py`。
  AgentScope 构造、上传输入投影、审批持久化、工具组合和安全事件投影分别由 `planning`、`context_snapshot`、
  `plugin_runtime` 和 `run_lifecycle` 所有。`run_lifecycle` 通过静态门禁禁止导入具体 Runtime、Memory、RAG、
  Search、Skill、Workflow 或持久化实现；组合入口后续在阶段 2–4 继续提取观测与 Evidence 协调端口。
- 首轮独立审阅判定不通过，指出根 Harness 仍集中、8 个组件 Protocol/DI 不完整、Emergency 默认允许模型、
  EvolutionSignal 可承载内容、配置仍有散落常量，以及 Context/Evidence 合同约束不足。修复后：
  - 8 个组件均有 Protocol、强类型错误和 `HarnessComponents` 注入槽；
  - Emergency 合同拒绝 `model_allowed=True`；
  - EvolutionSignal 使用枚举、受限 ID 和无内容 error code；
  - Context 字符串逐项限长；Evidence unavailable 禁止伪 locator/adopted text；
  - 输出字节、审批 TTL、Context ratio 统一进入 `ResolvedHarnessConfig`；
  - facade 边界和组件禁止直接读取环境变量由静态测试锁定。
  - `HarnessComponents.run_lifecycle` 与 `context_snapshot_assembler` 已在生产路径真实消费；
  - `ClinicalState` 的嵌套值、unknown/conflict 单项已限界，confirmed fact 必须含 trusted-tool provenance；
  - Context 身份不匹配使用 `ContextSnapshotError`，不再泄漏通用 `ValueError`。

实际验证：

```text
组件 + Harness/RAG/Memory/取消定向：177 passed, 1 warning
Ruff：All checks passed
Mypy：Success: no issues found in 36 source files
关键回归（原 103 + 新增 13）：116 passed, 9 warnings in 11.13s
```

第一次 integration 运行因只加载 base Compose、未发布 Redis 主机端口而得到 `101 passed, 9 errors`；确认容器健康后，
改用 `docker-compose.yml + docker-compose.dev.yml` 发布本地端口并完整重跑；初版合同得到 111/111，复审修复后再次
完整重跑得到上述 116/116。没有把基础设施错误
记为通过。

最终真实 Playwright CLI 回归使用无 mock 的游客会话发送“我现在胸痛、呼吸困难”：

- BFF session 201、chat 200；
- 页面显示“立即拨打 120 或尽快前往急诊”和统一免责声明；
- 完成后无停止按钮，桌面 `scrollWidth == clientWidth == 1280`；
- 390×844 下 `scrollWidth == clientWidth == 390`，急诊提示仍可见；
- console 0 error / 0 warning；
- 证据：`output/playwright/stage1-final/desktop-redflag.png`、
  `output/playwright/stage1-final/mobile-redflag.png` 和
  `.playwright-cli/traces/trace-1785328682710.trace`。

较早的测试脚本曾额外等待红旗回答的“重新生成”按钮并超时；Emergency 卡本来不显示该操作，随后直接检查完成态通过。
该 locator 超时不是生产请求失败。

阶段 1 GUI 审计后已关闭 Playwright 浏览器，停止 API、Next.js、PostgreSQL、Redis 和 Qdrant；3000、8000、5432、
6379、6333 均无监听，volume 未删除。

独立审阅先以 P1 拒绝“仅搬移单体”、具体 owner 依赖、装饰性 DI 和配置硬编码；第二轮修复后独立复测
68 个 Harness 核心/组件/合同/安全用例、Ruff 和 Mypy，最终判定 ACCEPT（P0/P1 均无）。审阅遗留的
ClinicalState 限界、Context typed error 和 Planning 文档 P2 已在 ACCEPT 后分别以独立提交收口；移动端长急诊卡
被 sticky Composer 部分遮挡但可滚动，登记阶段 5 UI 修复。

### 阶段 2

建立 `AgentRun`、`RunEvent`、`AnswerVersion`、`Artifact`、`FeedbackState` 事实源和唯一终态状态机；支持 sequence replay、断线、取消、恢复、服务端版本化重生成和反馈 reconciliation。

#### 阶段 2 实施记录（2026-07-29）

- PostgreSQL 成为 Conversation、Message、AgentRun、RunEvent、AnswerVersion、Artifact 和 FeedbackState
  的事实源；新增迁移、owner-scoped repository/service、Pydantic 响应合同和 BFF Zod 校验。
- Run 状态机覆盖
  `running/waiting_for_user/completed/completed_with_warnings/failed/cancelled/interrupted`。RunEvent
  使用单调 sequence 和幂等 event ID；取消、反馈 reconciliation、Artifact CRUD/导出和回答版本切换均校验
  tenant/actor 所有权。
- 成功终态在同一 request-scoped 数据库事务中提交 assistant Message、AnswerVersion、回答组 current 指针、
  AgentRun completed、唯一 `done/completed` RunEvent 和 Trace success。最终写入再次校验 regeneration 的
  expected current version；fencing 或版本校验失败会整体 rollback，旧 worker 不能留下孤立回答或覆盖新版本。
- Redis worker lease 与启动恢复 guard 使用同一 Lua 互斥协议。恢复器只有取得 guard 后才能把无主
  `running/waiting_for_user` Run 标记为 `interrupted`；worker 在 guard 存在时不能取得 lease，消除了先
  `EXISTS` 后写数据库的 TOCTOU。guard 在整个数据库事务期间按 owner token 续租，并在 commit 前再次确认
  owner；guard 丢失或 Redis 异常均 rollback、fail closed。TTL 由
  `GERCLAW_AGENT_RUN_RECOVERY_GUARD_TTL_SECONDS` 配置。
- 新增 `GET /api/v1/conversations/{conversation_id}/recoverable-run`、
  `GET /api/v1/runs/{run_id}/events?after_sequence=N` 和
  `GET /api/v1/runs/{run_id}/stream?after_sequence=N`、`POST /api/v1/runs/{run_id}/resume`。恢复服务只接受当前主体的 `interrupted` Run，且要求无已提交回答、
  Trace 仍为 running，并从加密持久化输入精确重建文本、Skill、文档、图片和 regeneration 身份；材料损坏时
  fail closed，不猜测或静默丢弃。regeneration 恢复按 source Run 读取原输入，不要求新 Run 的 Trace 与原
  Message Trace 相同。
- 浏览器 transport 断开只分离 SSE consumer，不等同于用户取消；owner producer 继续持有 lease/fencing 并持久化
  RunEvent。同一页面的 transport reconnect 从已渲染的最后 sequence 继续；页面刷新后的历史 hydration 没有渲染任何
  RunEvent，因此 `running` Run 必须从 sequence 0 通过 GET stream 完整重建，避免 Run 恰在 history/recoverable
  查询间完成时订阅到终态之后的空流。`interrupted` Run 才显式 POST resume；若恢复检查时 Run 已终态，则重新读取
  PostgreSQL 消息。前端按 Run ID 和单调 sequence 去重、拒绝跨 Run 游标；停止仍走显式取消协议。访客历史按既有产品
  边界不跨页面恢复。
- 公共 SSE Pydantic 校验边界使用 `exclude_none` 投影可选字段，保证实时和重放 `tool_result` 与前端 Zod
  “缺省或有效值”合同一致；Schema 漂移继续 fail closed，不能把部分输出包装成成功。

针对性验证：

```text
成功终态/版本/fencing：38 unit passed；14 real chat integration passed
恢复 lease/guard：20 unit passed；4 real recovery integration passed
显式恢复：36 unit passed；3 real recovery integration passed
实时 sequence stream 与断线续传：60 unit passed；4 real integration passed
公共 SSE 可选字段合同：30 targeted passed（`--no-cov`）
应用与配置：47 passed
前端 BFF/Run/聊天历史：21 + 2 + 7 passed
刷新终态竞态策略：10 chat tests passed
Ruff：All checks passed
Mypy：Success: no issues found in 244 source files
ESLint：0 warnings
Next production build：passed
```

真实 Playwright CLI 使用本地真实 PostgreSQL、Redis、API、Next.js 和实际模型，以测试患者账户审计
`interrupted` 恢复和运行中刷新续流：

- 网络顺序为 history 200 → recoverable-run 200 → `events?after_sequence=0` 200 → resume 200；
- 页面显示“正在恢复上次中断的回答”，最终仅有一条用户消息和一条 assistant 回答；
- “我现在胸痛并且呼吸困难”在模型前走急症短路，正文明确“立即拨打 120 或尽快前往急诊”并包含统一免责声明；
- API 回读确认 2 条消息、AnswerVersion 1、完成后 recoverable Run 为 null；
- 运行中页面刷新后，网络顺序为 history → recoverable-run → events → Run read →
  `GET /runs/{id}/stream?after_sequence=2`；同一 Run 最终为 `completed`、sequence 1–5 单调、只有一个
  `done`，会话仍只有 user/assistant 各一条；
- 首次真实普通医疗问题审计还发现 `tool_result` 可选字段被序列化成 `null` 的 Pydantic/Zod 漂移，修复并提交
  `87b743c` 后复验通过。另一次模型自主调用 `search_knowledge` 的失败如实落成唯一 `failed` Run，页面没有伪成功；
- 独立复审发现 Run 恰在 refresh 查询期间完成时会丢弃已重放 `done` 并订阅空流，判定 P1、阶段 2 拒绝关闭。
  `04c1bf2` 将历史恢复与实时 reconnect 的 cursor 所有权分开：运行中历史恢复从 0 重建，终态刷新数据库消息。
  Playwright CLI 仅注入“history 尚无 assistant、recoverable 仍显示 running”的竞态快照，其余 Run read、SSE 和 UI
  均走真实系统；请求确认 `GET /stream?after_sequence=0`，最终仍只有一条 user 和一条 assistant，console 0/0；
- 桌面与 390×844 移动端均无横向溢出，console 0 error / 0 warning，后端无 ERROR、Traceback 或 5xx；
- 证据：
  `output/playwright/stage2-resume/recovered-emergency.png`、
  `output/playwright/stage2-resume/recovered-emergency-mobile.png`、
  `output/playwright/stage2-resume/requests.txt`、
  `output/playwright/stage2-resume/console.txt`、
  `output/playwright/stage2-resume/app.log` 和
  `.playwright-cli/traces/trace-1785342025605.trace`；运行中刷新证据为
  `output/playwright/stage2-live-reconnect/desktop-reconnect-success.png`、
  `output/playwright/stage2-live-reconnect/requests-success.txt`、
  `output/playwright/stage2-live-reconnect/console-success.txt`、
  `output/playwright/stage2-live-reconnect/durable-state-success.txt`、
  `output/playwright/stage2-live-reconnect/app-fixed.log` 和
  `.playwright-cli/traces/trace-1785344802903.trace`。终态竞态证据为
  `output/playwright/stage2-terminal-race/recovered-terminal-race.png`、
  `output/playwright/stage2-terminal-race/requests.txt`、
  `output/playwright/stage2-terminal-race/console.txt`、
  `output/playwright/stage2-terminal-race/app.log` 和
  `.playwright-cli/traces/trace-1785345955687.trace`。

最终独立复审重新执行后端目标单测 62/62、真实 PostgreSQL+Redis 集成 18/18、前端目标测试 30/30、
Ruff、ESLint 和 Next production build，确认 P0/P1 均为 0，结论 ACCEPT。复审所留“终态 history 回读可能覆盖
极窄窗口内新生成”的 P2 已由 `22d001f` 在写 store 前复验 `isGenerating`，再次通过 10 个 chat tests、ESLint
和 production build。

审计后已精确删除两个测试会话（均返回 200），通过真实账户停用对话框停用
`gerclaw_reconnect_20260730`（204），关闭 Playwright 浏览器和 API/Next 进程，并停止 PostgreSQL、Redis、
Qdrant 容器；未删除 volume。3000、8000、5432、6379、6333 均无监听。移动端 sticky Composer 对较长急症卡的
既有遮挡问题仍登记在阶段 5；本阶段未用恢复功能扩大 UI 重构范围。

### 阶段 3

实现版本化 `ClinicalState` reducer、Quick/Standard/Deep/Emergency 路由、动态 DAG、模型前预算预检、SAVI 风格动作选择、C3 候选证据结构和 STEP 风格治疗门禁。红旗必须在首次模型调用前短路。

截至 2026-07-30：

- `3c4b762` 实现来源约束的 `ClinicalState` reducer；同值合并 provenance，冲突候选不覆盖，unknown 不转成阴性证据。
- `bf8718c` 接入确定性四级路由并把决策写入 `AgentRun.route`；Emergency 在模型前短路。
- `3dc484a` 根据真实测试日志关闭 Quick 的 Memory/RAG middleware、检索工具和 Memory 更新。
- `18c4880` 实现 route/附件/能力/报告意图驱动的动态 DAG、离散 SAVI 动作选择和模型调用前预算/上下文预检；完整 DAG 保留在恢复兼容的 `AgentRun.plan.dynamic_plan`。
- `9626e0d` 实现 GerClaw 范围内的 C3 鉴别方向结构和 STEP `TreatmentContext`/前提门禁；不移植其他项目的封闭疾病 catalog。五大处方的私有模型输入使用 STEP 上下文，年龄、过敏、完整用药、重要基础病等未结构化确认时，调药候选降级为循证审核基线。
- 开发中分别通过规划相关用例 157/157、C3/STEP/处方相关用例 107/107、Run 恢复/重生成契约 29/29。阶段收尾重新组合执行 10 个受影响测试文件，结果为 128/128；Ruff 全部通过，Mypy 对 18 个受影响源文件检查通过。完整输出保存在 gitignored 的 `output/playwright/stage3-routing/pytest-stage3.txt`、`ruff-stage3.txt` 和 `mypy-stage3.txt`。

真实 Playwright CLI 审计使用本地真实 PostgreSQL、Redis、Qdrant、FastAPI、Next.js 与当前 Provider，没有设置任何
network route/mock。因为根 `.env` 的 `GERCLAW_API_URL=http://api:8000` 面向 Compose 网络，宿主机启动 Next.js 时
显式覆写为 `http://127.0.0.1:8000`；未修改配置文件。首次未覆写启动真实得到 BFF 会话 503，界面正确降级为
“本次回复未完成”，该失败也保留在证据中，没有冒充通过。

审计结论：

- Quick 输入“您好！”真实创建 `route=quick`、`status=completed` 的 Run，事件仅含 `agent_start`、
  `reasoning_summary`、`text_delta` 和唯一 `done`，没有 `tool_call`/`tool_result`；实际耗时约 7.23 秒。
- Emergency 输入“我现在胸痛、呼吸困难，感觉快要晕倒了”在约 99 ms 内创建
  `route=emergency`、`status=completed` 的 Run，事件为 `agent_start → safety_notice → text_delta → done`。
  页面以紧急警告明确要求立即拨打 120 或前往急诊并携带用药清单，不等待模型或检索。
- 普通防跌倒问题创建 `route=standard`，报告请求创建 `route=deep`；两者均实际执行本地医学检索，证明路由和
  动态能力分支已生效。
- Standard/Deep 同时暴露阶段 4 的真实 P1 缺口：当前 RAG 零命中时 Provider 仍生成不可核验的医学引用或经验性
  表述。现有最终安全校验把两次 Run 均标为 `failed`，页面明确显示“未经最终安全校验、请勿据此调整治疗或用药”，
  没有把不可信内容发布为成功答案；阶段 4 必须实现零命中真实降级、来源排序和引用闭环。
- 全程浏览器 console 为 0 error / 0 warning（仅 React dev/HMR log）。390×844 下
  `documentScrollWidth = bodyScrollWidth = innerWidth = 390`，移动抽屉与文字标签可用，无页面级横向溢出。

GUI 证据位于 gitignored 的 `output/playwright/stage3-routing/`：桌面和移动截图、YAML snapshot、network request、
解密后的 owner-scoped Run/Event API 结果、数据库 route/终态证据、前后端日志及
`.playwright-cli/traces/trace-1785348465377.trace`。浏览器已关闭。阶段 3 尚待独立审阅，因此此处不提前判定完成。

首轮独立审阅判定 REJECT（P0=0、P1=4、P2=1）：Emergency 仍在 Skill/Memory/文档依赖之后短路；
`ClinicalState` 尚未进入生产多轮上下文；SAVI/C3/DAG 只持久化而未治理实际执行；STEP 关键词门禁可被
“把阿司匹林改为氯吡格雷75mg每日一次”等表达绕过；C3 标签仍可写成确定性诊断。随后按模块修复并分别提交：

- `dfe2086` 将 Emergency 路由提前到依赖初始化之前，任何 Skill、Memory、文档故障均不能阻断 120/急诊提示。
- `ebbcf8e` 将来源约束的 `ClinicalState` reducer 接入生产消息投影、加密 Run snapshot、多轮回读和 Harness
  私有上下文；模型推测仍不能成为 confirmed fact。
- `f29f341` 让 SAVI 选择改变生产计划与副作用顺序；治疗前提缺失时执行唯一 `clinical.ask` 节点，并在 RAG/
  模型前返回。`DynamicPlanExecutor` 强制依赖和 required checkpoint，C3 方向只能引用非冲突事实且拒绝确定性
  标签。新增严格 `clinical_clarification` 响应类型：无模型、无伪引用、带安全审计标记。
- `007b5e5` 引入代码所有的 `MedicationActionClassifier`，覆盖开始、停用、替换、剂量和新剂量频次表达；
  用户原样提供的用药记录仍可保留，但缺少 STEP 前提的调药候选一律降级为循证审核基线。

修复后组合执行 9 个 Harness/Chat/处方测试文件，135/135 通过；Ruff 通过；Mypy 对 53 个生产文件检查通过。
第二轮真实 Playwright CLI 仍未设置 route/mock：Quick SSE 200、约 7.139 秒；Emergency SSE 200、约 549 ms，
持久化 Run 为 `emergency/completed`，事件严格为
`agent_start → safety_notice → text_delta → done`，owner-scoped Run 查询和 `after_sequence=0` replay 均为
200。1280 桌面和 390×844 手机均无页面级横向溢出，console 为 0 error / 0 warning。截图、API 日志和 Trace
归档在 `output/playwright/stage3-rereview/`，原始 Trace 为
`.playwright-cli/traces/trace-1785351076153.trace`。视觉复核同时确认既有移动端 sticky Composer 会遮挡较长
急症卡下半部、顶部标题与菜单空间偏紧，继续作为阶段 5 的 UI 重构项，不在本阶段扩大范围。修复集仍待独立复审，
因此阶段 3 继续保持未完成状态。

第二轮独立复审仍为 REJECT（P0=0、P1=2、P2=1）。已确认上一轮 Emergency、已有 unknown 的 ASK、指定 STEP
原句、C3 标签和内建 checkpoint 均闭环，但发现真实新会话的 ClinicalState 没有预置 unknown，调药请求仍选择
ANSWER；并复现“阿司匹林换氯吡格雷”“不要继续服用阿司匹林”“阿司匹林替成氯吡格雷”三种 STEP 绕过。
修复继续按模块提交：

- `0de7cff` 从实际 source-linked state 推导年龄、过敏状态、完整当前用药和基础病/肝肾功能缺口，使空状态调药
  请求也执行 mandatory ASK；问题写回 Run ClinicalState。用户消息投影增加有界、确定性的年龄、明确过敏/
  过敏否认、当前用药、症状、病史和时间线识别，仍只产生 `reported` 用户来源事实。
- `22931a1` 扩展停换药归一化，阻断裸 `换`、`替成` 和“不要继续服用”，同时通过负向测试保留“不要自行停药”
  这类安全劝阻。

再次组合执行 9 个相关测试文件，140/140 通过；Ruff 通过；Mypy 对 53 个生产文件检查通过。最终真实
Playwright CLI 使用全新访客和空会话输入“这些药需要怎么调整剂量?”，SSE 200、约 423 ms，页面直接要求补充
四类 STEP 信息且没有证据检索阶段；持久化 Run 为 `standard/completed`，事件仅
`agent_start → text_delta → done`，Trace 没有 `model.call` 或 `tool.call`。截图、API 日志和最终 Trace 位于
`output/playwright/stage3-rereview/mandatory-ask-desktop.png`、`api-final.log` 和
`.playwright-cli/traces/trace-1785351953743.trace`。选中 Skill 的 AgentScope 调用尚未进入 checkpoint、当前
optional node 如实为 `skipped`，保留为阶段 4 能力组合 P2，不宣称完整能力 DAG 已闭环。阶段 3 等待第三轮独立
复审。

第三轮独立复审确认空状态 ASK 和三类 STEP 绕过均闭环，但仍判定 REJECT（P0=0、P1=1、P2=1）：显式年龄、
过敏和用药投影仍使用消息 UUID，跨轮不同值不会进入 reducer 的同语义冲突分支。`e265369` 将年龄、药物过敏
状态和当前用药清单改为稳定语义 ID；跨消息不同值现在保留全部候选并统一标记 `conflicted`，同一消息 replay
保持幂等，重复性症状/病史/时间线继续使用消息级 ID 以免制造虚假冲突。年龄、过敏否认→明确过敏、用药剂量
变化三组回归均通过。阶段组合回归更新为 143/143，Ruff 通过，Mypy 对 53 个生产文件通过；等待第四轮独立复审。

第四轮独立复审最终 ACCEPT（P0=0、P1=0、P2=1）。审阅者独立复现年龄、过敏状态和当前用药三组跨轮冲突，
全部得到两个保留候选、统一 `conflicted` 状态、稳定 conflict ID，且同 message ID replay 幂等；同时抽查空状态
mandatory ASK、Emergency 依赖前短路、C3 确定性标签、DAG dependency、STEP 三种简写绕过及“不要自行停药”
均无回归。独立命令结果为指定场景 18/18、组合 157/157、Ruff 通过、Mypy 对 35 个源文件通过。唯一 P2 是选中
Skill 的 optional checkpoint 尚未接入 AgentScope 实际工具完成回调，已如实进入阶段 4 能力组合范围。阶段 3
至此关闭。

### 阶段 4

完成 Evidence/Citation 真实闭环、Memory proposed/confirmed/conflict 治理和受治理 GerClaw 能力清单；附件、解析、检索和临床观察跨节点复用。

截至 2026-07-30，阶段 4 按模块完成四个独立生产变更：

- `35cc20e` 建立本地 Evidence/Citation admission：绝对相关性阈值、来源状态与等级、真实采用文本、locator、
  去重和不可核验降级均由代码治理；模型不能自行创造可发布 Citation。
- `3b19ced` 修复 Reranker 故障回退：失败时保留真实 BM25/向量混合候选及原始分数，不用空结果或伪造排序替代。
- `ca0adef` 将 Memory recall 收紧为 `confirmed` 且未冲突、未过期、非 restricted、用户已启用的事实；
  新写入默认 `proposed`，鉴别方向不进入长期事实，冲突 confirmed 记录不注入模型上下文。
- `27bad11` 建立受治理的 `PluginManifest` catalog，allowlist 仅包含现有 CGA、用药审查、五大处方和报告产物；
  自动、Workflow 和手动选择共用同一清单。共享结果引用严格绑定 tenant、actor、session、trace 和允许消费者；
  同轮 ClinicalState、附件投影、本地检索结果可复用。AgentScope Skill 成功结果会完成匹配的 optional 动态计划
  checkpoint，关闭阶段 3 遗留 P2；预取失败路径不会再同时写入失败与成功结果。

组合回归实际执行 18 个 Harness、Evidence、RAG、Memory 和 Chat 测试文件，结果为
`217 passed, 1 skipped, 1 warning`；warning 是本地 Qdrant HTTP payload-index 提示。阶段内最终定向结果还包括：

- 能力模块后端 95/95；Ruff 全部通过；Mypy 检查 263 个源文件通过。
- 前端 BFF/能力契约 24/24、Chat 合同 10/10；ESLint 和 Next production build 均通过。
- 开发中一次误写了不存在的 `test_agent_harness_integration.py`，pytest 因无测试而退出；随后立即改为真实测试
  路径。一次未加 `--no-cov` 的定向运行虽有 91 个测试通过，但暴露 `orchestrator.py` 914 行超过 800 行门禁及
  定向集合覆盖率不足；共享结果逻辑随后抽为独立模块，最终 `orchestrator.py` 为 790 行，正确命令全部通过。

阶段 0 记录的空索引已用项目自带 `gerclaw-rag-index` 真实修复，没有写入版本库或调用非配置 Provider：

- 对仓库现有 436 份 Markdown 完成全量同步，真实 SiliconFlow `BAAI/bge-m3` embedding、PostgreSQL advisory
  lock 和 Qdrant 均参与；结果为 `discovered=436`、`indexed=436`、`chunks_written=39837`、
  `failed=0`、`deleted=0`。
- 紧接着再次同步得到 `discovered=436`、`skipped=436`、`indexed=0`、`chunks_written=0`、
  `failed=0`，验证幂等。
- 通过真实 Next.js BFF 查询“老年人跌倒预防建议”，HTTP 200 并返回 3 条实际知识库结果，包含跌倒预防指南
  对比文献和《老年人衰弱预防中国专家共识(2022)》；浏览器 console 为 0 error / 0 warning。

最终 Playwright CLI 审计使用真实 PostgreSQL、Redis、Qdrant、FastAPI、Next.js 和当前模型 Provider，没有
network route/mock。全新访客在 GUI 输入“老年人如何预防跌倒？请给出有来源的建议。”，真实创建会话并执行
医学检索；BFF `POST /api/gerclaw/chat` 返回 200，页面公开阶段显示医学检索完成（约 865 ms），完整请求约
19.4 秒。回答在对应陈述附近使用 5 个 Evidence ID，统一免责声明可见；“查看全部”打开的引用面板逐条展示
本次实际采用文本、来源类型和无公开链接时的核验提示。后端日志确认 Memory 搜索、受治理写入、聊天终态均完成，
没有把 Provider payload 或私有推理暴露到页面。

桌面截图为 `apps/mvp/output/playwright/stage4-evidence/cited-chat-desktop.png`，390×844 手机截图为
`apps/mvp/output/playwright/stage4-evidence/cited-chat-mobile.png`；手机实测
`viewportWidth=documentWidth=bodyWidth=390`、`overflowX=false`。能力目录的独立 BFF GUI 证据为
`apps/mvp/output/playwright/stage4-capabilities/desktop.png`。完整 Trace 为
`apps/mvp/.playwright-cli/traces/trace-1785355601132.trace`，能力目录 Trace 为
`apps/mvp/.playwright-cli/traces/trace-1785355297551.trace`。最终浏览器 console 为
0 error / 0 warning，network 中 account、RAG、session 和 chat 请求均为 2xx。

已知限制如实保留：部分知识库 Markdown 的题名元数据只有“·指南与共识·”或“·专家论坛·”，因此引用卡题名
不够具体；卡片仍展示可核对的实际采用摘录、章节和本地来源，并明确提示无公开原文链接。该数据清洗问题不影响
本阶段“不得伪造引用”的安全门，但应在后续知识库质量工作中改进。阶段 4 尚待独立审阅，不提前标记完成。

### 阶段 5

拆分前端超大组件；实现克制的对话工作台、可调左栏、移动抽屉、IME 安全 Composer、公开阶段摘要、回答版本/反馈/TTS/导出操作，以及兼容式产物优先右栏和可编辑 Artifact。

### 阶段 6

在线只记录去内容化信号；隔离离线环境固定官方优化器来源、commit 和许可证。候选在独立 worktree 配对评测，经过全切片非劣、预算、HMAC sealed test 和人工审批后才能晋升。

### 阶段 7

执行完整后端、前端、迁移、Compose、Playwright 和 axe 回归，覆盖患者、医生、访客和响应式关键路径；更新架构、Harness、前端、设计和产品规格，经独立审阅后归档本计划。
