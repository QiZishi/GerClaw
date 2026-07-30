# 0035 — Agent Harness 与对话工作台分阶段优化

> 创建：2026-07-29 | 优先级：P0 | 状态：进行中  
> 最高权威：`docs/references/gerclaw设计要求.md`  
> 产品偏好：`MEDICAL_AGENT_SYSTEM_OPTIMIZATION_GUIDE.md`

## 1. 目标与边界

在不推倒现有 AgentScope、Runtime、Memory、RAG、Search、Skill、Workflow 和会话事实源的前提下，分阶段完成 Harness 模块化、Run 状态机、临床状态与动态规划、证据/能力治理、对话工作台重构、隔离离线演化和最终回归。

GerClaw 保持老年医学定位。眼科病灶定位不在本计划范围。普通授权请求继续执行 Memory 在线
CRUD 和低风险 Skill 内容演进；反馈信号不得自动修改 Prompt、危险 Skill、路由、代码、安全门或
Memory/Skill 的治理机制。

进入最终回归前还必须完成执行期指令接入：用户可明确选择立即打断当前执行并提交新要求，或把新要求
排队到下一安全边界。该能力必须和提前感知窗口压力的上下文压缩一起实现，参考 Codex 可公开观察和
核验的交互语义，但不得臆测、复制或硬编码未公开的内部阈值。

**可用性同样是安全硬约束。** 不得用堆叠校验、宽泛关键词拦截或整段丢弃代替精确治理，导致正常模型输出
频繁失败或无法展示。能够在权限和医疗底线内修复的错误必须把结构化问题反馈给智能体，回滚到该错误步骤
开始前的 checkpoint 后有界重试，并保留此前已经验证的正文、证据和产物。

**安全治理默认在幕后。** 最终呈现给用户的答案只保留解决其需求所必需的内容，不得夹带策略名、校验步骤、
错误码、内部边界、重试说明或重复的安全套话。医疗免责声明遵循最高权威文档，但在普通回答中统一、简洁地
出现一次；高风险场景优先给明确行动建议，不能用大量无关提醒淹没核心信息。

每一阶段必须是独立变更集，完成相关测试、真实 GUI 审阅和 Conventional Commit 后才能进入下一阶段。阶段内只跑相关测试；阶段 7 才跑全量回归。

## 2. 阶段与状态

| 阶段 | 交付目标 | 状态 |
|---|---|---|
| 0 | 冻结基线与真实运行审计 | 已完成：HTTP/API/测试、Playwright GUI、清理及独立审阅通过 |
| 1 | Harness 模块化与稳定合同 | 已完成：两轮审阅问题修复，最终独立审阅 ACCEPT |
| 2 | Run 事实源、状态机和恢复 | 已完成：两轮 P1 修复、真实 GUI 对抗审计、最终独立复审 ACCEPT |
| 3 | ClinicalState、动态规划与医疗门禁 | 已完成：四轮独立审阅修复、真实 GUI 与最终 ACCEPT |
| 4 | 证据、Memory 与受治理能力组合 | 已完成：三项 P1 修复、真实 GUI/数据库复验、最终独立复审 ACCEPT |
| 5 | 对话工作台 UI 与交互重构 | 已完成：独立审阅 3 项 P1 修复，真实 Playwright/axe 复验，最终 ACCEPT |
| 6 | 双轨受控自进化与执行期上下文治理 | 进行中：完成组件宪章、双轨分类、Memory 在线 CRUD、Skill 在线/离线分轨和去内容化信号；继续 sealed evaluator、离线评测、晋升控制面、执行期 steer/queue 和上下文压缩交互 |
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

截至 2026-07-30，阶段 4 先按模块完成四个独立生产变更：

- `35cc20e` 建立本地 Evidence/Citation admission：绝对相关性阈值、来源状态与等级、真实采用文本、locator、
  去重和不可核验降级均由代码治理；模型不能自行创造可发布 Citation。
- `3b19ced` 修复 Reranker 故障回退：失败时保留真实 BM25/向量混合候选及原始分数，不用空结果或伪造排序替代。
- `ca0adef` 将 Memory recall 收紧为 `confirmed` 且未冲突、未过期、非 restricted、用户已启用的事实；
  新写入默认 `proposed`，鉴别方向不进入长期事实，冲突 confirmed 记录不注入模型上下文。
- `27bad11` 建立受治理的 `PluginManifest` catalog，allowlist 仅包含现有 CGA、用药审查、五大处方和报告产物；
  自动、Workflow 和手动选择共用同一清单。共享结果引用严格绑定 tenant、actor、session、trace 和允许消费者；
  同轮 ClinicalState、附件投影、本地检索结果可复用。AgentScope Skill 成功结果会完成匹配的 optional 动态计划
  checkpoint，关闭阶段 3 遗留 P2；预取失败路径不会再同时写入失败与成功结果。

首轮独立审阅没有放行阶段 4。审阅者先发现 core profile 会绕过语义召回过滤泄露 restricted/expired Memory，
随后最终以 P1 拒绝未绑定的模型引用 marker 和“只有能力目录/选择、没有实际 owner 调用”的能力闭环，并以 P2
指出所谓“能力 GUI 证据”只是浏览器上下文中的 API 请求和登录页截图，并非可见的能力操作界面。问题按模块修复
并分别提交：

- `8c55851` 统一 core profile 与语义召回的 eligibility，只允许 confirmed、standard、未过期且用户已启用的
  Memory 进入上下文；core profile 改为本轮临时过滤投影并保留 provenance。
- `605f3df` 引入服务端唯一的 `[C#]` 公开引用 marker。模型的 `[E#]`/`[W#]` 仅能引用本轮已 admission 的
  Evidence/Web source，越界、伪造或直接输出 `[C#]` 均 fail closed；前端只把服务端 `[C#]` 渲染为可交互
  Popover，普通数字方括号不再误绑定。
- `2bb8a39` 增加 `GovernedCapabilityRuntime`，只把 allowlist 中且确实进入动态计划的 CGA、用药审查、
  五大处方和报告能力分派给注入的现有 owner service；Chat/BFF 增加严格的手动选择合同，恢复和重生成保留选择。
- `2927a50` 将 owner 调用移到 Run 创建前的计划确定阶段，避免 mandatory ASK 时产生越界副作用，并把去内容化
  `capability_results` 持久化进加密 Run plan，形成可恢复、可审计的执行证据。

初版组合回归实际执行 18 个 Harness、Evidence、RAG、Memory 和 Chat 测试文件，结果为
`217 passed, 1 skipped, 1 warning`；warning 是本地 Qdrant HTTP payload-index 提示。审阅修复后的定向结果
还包括：

- Memory 后端 105 passed、1 skipped；Evidence/引用后端 81 passed；能力/Chat 最终 83 passed。各模块 Ruff
  和 Mypy 均通过。
- 前端引用渲染 4/4、BFF/能力契约 24/24、Chat 合同 10/10；ESLint 和 Next production build 均通过。
- 独立审阅者在修复前自行运行 159 项相关测试，全部通过但仍基于生产语义给出 REJECT；测试通过没有替代对信任
  边界和实际 owner 调用的代码审查。
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
`viewportWidth=documentWidth=bodyWidth=390`、`overflowX=false`。原
`apps/mvp/output/playwright/stage4-capabilities/desktop.png` 只证明浏览器上下文可读取 BFF catalog，
截图本身仍是登录页，不能称为可见 GUI 能力证据；手动能力选择控件属于阶段 5，不在本阶段伪装为已完成。

修复后重新用全新访客在真实 GUI 输入“请开始老年综合评估，并说明有哪些评估入口。”。回答中的 `[C#]` 被渲染
为“查看引用”按钮；点击后 Popover 展示真实来源、实际采用文本和无公开链接提示，截图为
`apps/mvp/output/playwright/stage4-rereview/inline-citation-popover.png`。同次 Run
`bb962971-8318-45d5-80ef-e6e56aa0ffbd` 的加密 plan 经应用层解密后包含
`gerclaw.cga` owner 结果 `cga-workspace:<conversation_id>`，证明自动选择实际进入动态计划并调用现有
`CgaService`，而不是只返回 catalog；页面完成态截图为
`apps/mvp/output/playwright/stage4-rereview/owner-capability-completed.png`。该连接动作只连接可恢复 CGA
工作台，不会在用户未选择量表时擅自启动 PHQ-9 等具体评估。

最终另开 Playwright CLI headless 会话复核登录/访客入口，390×844 实测
`viewportWidth=documentWidth=bodyWidth=390`、`overflowX=false`，截图为
`apps/mvp/output/playwright/stage4-rereview/mobile-current.png`；console 为 0 error / 0 warning，
account 请求 200。主要 Trace 为 `apps/mvp/.playwright-cli/traces/trace-1785359066064.trace`，移动复核 Trace
为 `apps/mvp/.playwright-cli/traces/trace-1785359634581.trace`。聊天 network 中 account、session、chat 和
Run 查询均为 2xx；后端日志确认 Memory search/write、唯一聊天终态和 Run GET 均完成。

已知限制如实保留：部分知识库 Markdown 的题名元数据只有“·指南与共识·”或“·专家论坛·”，因此引用卡题名
不够具体；卡片仍展示可核对的实际采用摘录、章节和本地来源，并明确提示无公开原文链接。该数据清洗问题不影响
本阶段“不得伪造引用”的安全门，但应在后续知识库质量工作中改进。

同一独立审阅者最终复审结论为 `ACCEPT（P0=0、P1=0、P2=1）`。审阅者独立复跑后端
`201 passed, 1 warning`、前端 38 passed，Ruff、Mypy 26 files 和相关 ESLint 均通过，并只读核验 Run
`bb962971-8318-45d5-80ef-e6e56aa0ffbd` 已完成、数据库原始 plan 保持 `enc:v1` 密文、应用层解密后动态节点为
`evidence.retrieve → gerclaw.cga → answer.compose` 且包含 `cga-workspace` owner 结果。Playwright Trace/截图
可复现 `[C#]` Popover、CGA 完成态和移动端无溢出；旧能力登录页证据已正确降级。

唯一非阻断 P2 如实保留：当前 owner setup 在 Run 创建及声明的 evidence prerequisite 之前调用，之后才由
Harness 把 optional node 标为完成；同时缺少 ChatService 层直接覆盖“planned gating → owner invocation →
EncryptedJSON result persistence”的完整集成测试。现有 owner 均为幂等 intake start 或 owner-scoped read，
不会产生当前安全/一致性阻断；后续 Run checkpoint 加固应把结果追加改为 Run 创建后的加密 checkpoint，并补
对应集成测试。阶段 4 至此完成，允许进入阶段 5。

### 阶段 5

拆分前端超大组件；实现克制的对话工作台、可调左栏、移动抽屉、IME 安全 Composer、公开阶段摘要、回答版本/反馈/TTS/导出操作，以及兼容式产物优先右栏和可编辑 Artifact。

#### 设计与拆分基线

本阶段的具体主体是“老年患者和老年科医生共用的真实医疗对话工作台”，页面单一任务是让用户完成一次可恢复、
有来源、可转为产物的对话。视觉不做医疗驾驶舱，也不套用暖米色营销页或暗色霓虹模板。

- 色彩：`诊疗画布 #FFFFFF`、`应用底色 #F7F7F8`、`导航底色 #F1F1F1`、`正文 #202123`、
  `次要文字 #475569`、`亲和蓝 #0EA5E9`；状态色继续使用既有语义 Token，不在业务组件硬编码色值。
- 字体：展示/标题使用系统 `SF Pro Display / PingFang SC` 角色，正文使用
  `SF Pro Text / PingFang SC` 角色，数据和代码使用既有等宽栈；不加载外部字体，保证中文、隐私和首屏稳定。
- 版式：宽桌面为可调左栏、安静阅读列和按需右栏；平板/手机把两侧栏改为抽屉/全屏覆盖。助手正文直接落在
  内容列，用户使用浅灰气泡；卡片只承载真实阶段、结构化结果和需要操作的状态。
- 识别性元素：一条随真实 `RunEvent` 实际开始顺序生长的“诊疗阶段脉络”，只展示公开摘要、耗时和结果，不显示
  private chain-of-thought、完整 Prompt、凭据、Provider payload 或内部调试噪声。

```text
宽桌面： [ 可调会话栏 220–420 ] [ 消息 / 阶段脉络 / Composer ] [ 按需 Artifact 320–500 ]
折叠态： [ 56 图标栏 ]          [ 消息 / 阶段脉络 / Composer ] [ 隐藏 ]
手机态： [ 菜单抽屉 ]           [ 单列消息 + 固定 Composer ]    [ 全屏按需面板 ]
```

自审后删除了三项容易模板化或误导的设计：不增加渐变 Hero/宣传指标，不把每条助手回复包成厚卡片，不预先画出
尚未执行的完整计划。品牌蓝只用于焦点、链接和主要动作；阶段脉络必须由真实事件驱动。最高权威要求的引用、文件、
健康档案和 CGA 等右栏入口继续按需存在；“产物优先”只改变默认职责，不删除这些权威功能。

实施拆成可独立回滚的五个模块：

1. `WorkbenchLayout`：左栏 220–420px 拖动、56px 折叠、键盘调整、双击恢复、持久化和移动抽屉。
2. `Composer`：把附件、Skill/能力选择、录音/ASR、IME/键盘发送和提交状态拆到 hooks/service/小组件。
3. `ConversationThread`：把 block 渲染、公开阶段、反馈 reconciliation、TTS、版本和更多操作拆离消息外壳。
4. `ConversationController`：把 Run/SSE/恢复、会话 hydration 和工作流切换从 `ChatArea` 移到可测 hooks。
5. `ArtifactWorkspace`：Artifact 标题/Markdown、实时预览、防抖保存、未保存保护、调宽及 MD/PDF/DOCX/JPG 导出。

每个模块完成相关测试和真实页面复验后立即 Conventional Commit；阶段结束时再跑前端 lint、unit、build、
Playwright 和 axe，并交由独立审阅者判定。

截至消息模块：`MessageBubble` 已由 920 行降至 147 行，正文、公开运行提示、TTS、反馈与操作栏均已拆分。
Run 反馈实测完成 `value=1/revision=0 → value=0/revision=1` reconciliation。回答 v2 生成后，访客选择 v1
最初暴露账户历史接口 403；未把该结果判为成功，而是将 `AnswerVersion` 升至 v1.2，返回 owner-scoped、
严格校验的 Markdown/Citation 投影。复测 `PUT current` 为 200、正文恢复为原 v1、无历史 GET、控制台 0 error。

截至 Artifact 模块，`ChatArea`、`Sidebar`、`RightPanel` 和主要可见业务组件均已拆到约 250 行以内；Run/SSE、
会话恢复、Skill、账号和侧栏状态机留在独立 hook/controller。消息“转为文档”不再写入临时 `panelContent`，
而是携带生成回答的 `executionRunId` 和会话标识，先恢复同一 Run 最新 revision 的 Artifact，不存在时再创建。
编辑器支持标题、Markdown、实时预览、800 ms 防抖保存、乐观 revision、冲突/网络受控错误、刷新和关闭前保护、
键盘调宽，以及 MD/PDF/DOCX/JPG（另保留 PNG）导出。旧历史回答没有 Run 标识时明确显示“仅当前页面”降级，
不会伪装成已保存。

真实 Playwright CLI clean-room 审计使用全新游客、真实模型 Run、FastAPI、PostgreSQL、Redis 和 Qdrant，
没有 route/mock。首次“转为文档”严格产生 1 次列表 GET 和 1 次创建 POST；修改标题后产生 1 次 PUT 200，
状态从 revision 1 到 revision 2。关闭后重开只产生 1 次 GET、0 次 POST，并恢复 revision 2 的标题和 Markdown。
未保存关闭会出现确认保护，已保存关闭不会误提示；右栏分隔条 `ArrowLeft` 实测增加 16 px。真实下载的 `.md`、
`.pdf`、`.docx`、`.jpg` 均非空，文件签名分别由文本、PDF 1.3、Microsoft Word 2007+ 和 JPEG 识别，Markdown
包含正文和统一医疗免责声明。clean-room console 为 0 error / 0 warning，网络均为 2xx。截图和导出证据位于
gitignored 的 `apps/mvp/output/playwright/stage5-artifact/`，其中
`artifact-editor-visible.png` 已目视确认编辑区和实时预览同时可见；此前自动聚焦导致内层滚动到预览的问题已修复。

本模块相关回归实际结果：消息/Artifact 8/8、布局 2/2、导出 1/1、Run 契约 2/2，完整 ESLint 和 Next
production build 均通过。Node 仍输出项目既有 `MODULE_TYPELESS_PACKAGE_JSON` warning；测试全部通过，
没有把 warning 隐去或误报为零。

阶段级无障碍/响应式审计随后覆盖 1440×1000、1024×768 和 390×844。三种 viewport 均无页面横向溢出；
1024/390 的 Artifact 为全屏覆盖，390 下所有可见离散控件均不小于 48×48px、可见文字不小于 16px。
桌面左栏实测 `ArrowRight` 增加 16px、双击恢复 272px、折叠态严格 56px；Composer 的 IME composing Enter
和 Shift+Enter 均未发出 chat 请求，后者只插入换行。移动会话抽屉和 Artifact 均支持 `Escape` 关闭。

axe 首轮没有直接通过：Artifact 页面先发现患者暖蓝 `#0EA5E9` 配白字仅 2.77:1；按最高权威“老年模式自动
提升 WCAG AAA”增加老年模式专用 `#075985`，白字对比度 7.56:1，普通患者模式仍保留暖蓝。随后发现移动
Sheet 缺可访问名称，补 `SheetTitle`“会话菜单”；项目内 E2E 又捕获 Popup 从 opacity 0 淡入造成入场阶段
文字约 2.4:1、按钮约 2.05:1，最终改为只做位移动画。修复后三个 viewport 与抽屉/Artifact 状态的 axe
均为 0 serious / 0 critical。

新增项目内 `@playwright/test` + `@axe-core/playwright` 门禁，`npm run test:e2e` 使用系统 Chrome、真实
Next.js/FastAPI，不注册 route mock。首轮为 1 passed / 1 failed，按上述动画问题修复后最终 2/2 passed。
阶段级前端全量 unit 最终为 71 项 Node 测试全部通过，另校验 82 个题干和 123 个版本绑定 CGA WAV；完整
ESLint、Next production build 均通过。截图位于 gitignored 的 `output/playwright/stage5-stage/`。

#### 独立审阅拒绝、修复与复审

独立子智能体首轮判定 `REJECT（P0=0、P1=3、P2=2）`。自动化虽已通过，但生产语义仍有三个阻断：

1. 全局 `isGenerating` 使 A 会话运行中的 Run 劫持 B 会话 Composer；
2. Artifact 未保存保护只覆盖关闭，换面板、换会话或另一条“转为文档”可绕过；
3. 真实引用回答未进入原 E2E，引用角标/Popover 小于老年模式尺寸，来源区存在 nested interactive。

修复后，运行状态和 `AbortController` 按 `sessionId` 隔离，旧回调不能清除新 Run；真实 Playwright 新增
“A 生成中切换 B，B 可发送，返回 A 可安全停止”路径。Artifact 的关闭、换面板、换会话、跨角色切换和
换草稿统一经过 dirty guard；同角色身份刷新不再重置右栏。409 重试先读取最新 revision，再由用户显式
选择“基于最新版本重试”，保留本地草稿并写入新修订。项目 Playwright CLI 真实创建服务端 Artifact 后验证：
关闭和切换健康画像均出现确认，取消后草稿保留，确认后才离开。

引用展开和“查看全部”拆成并列原生按钮；老年模式引用目标为 48×48px，Popover/来源正文为 18px。
移动右栏改用项目 Base UI `Sheet`，获得 dialog 名称、focus trap、背景隔离、Escape 和焦点恢复。移动 E2E
实际打开健康画像 dialog 后重新执行 48px 热区和 axe，均无 serious/critical 问题。

最终在 HEAD `086763a` 独立复审：

```text
VERDICT: ACCEPT
P0=0, P1=0, P2=0
cd apps/mvp && npm run test:e2e
3 passed (13.0s)
```

审阅使用系统 Chrome、真实 Next.js/FastAPI，不下载浏览器、不注册 route mock。修复集另实际通过完整 ESLint
和 Next production build；Artifact 聚焦测试为 10/10。Stage 5 至此关闭，允许进入 Stage 6。

### 阶段 6

依据 `DUAL_TRACK_EVOLUTION_GUIDE.md` 实现按权限分类的双轨演化。这里的双轨不能被误解为
“Memory/Skill 一律不可在线变化”，也不能把“允许演化”误解为可以修改组件存在的核心原理。

#### 6.0 一手来源定义审计与前置修复

2026-07-30 由独立子智能体联网检索一手资料并只读核对生产代码。审计采用 AgentScope、OpenAI
Agents SDK、HL7 FHIR、Mem0、Agent Skills、A-Evolve、GEPA 和 Adaptive Auto-Harness 的官方文档、
规范、仓库或原始论文：

- Agent/Runner/RunState/Session/Context：
  `https://openai.github.io/openai-agents-python/agents/`、
  `https://openai.github.io/openai-agents-python/ref/run_state/`、
  `https://openai.github.io/openai-agents-python/sessions/`、
  `https://openai.github.io/openai-agents-python/context/`
- AgentScope Routing、Task Plan、Memory、Long-term Memory、Skill：
  `https://doc.agentscope.io/tutorial/workflow_routing.html`、
  `https://doc.agentscope.io/tutorial/task_plan.html`、
  `https://doc.agentscope.io/tutorial/task_memory.html`、
  `https://doc.agentscope.io/tutorial/task_long_term_memory.html`、
  `https://doc.agentscope.io/tutorial/task_agent_skill.html`
- Memory/Skill 可变内容合同：
  `https://github.com/mem0ai/mem0/blob/main/cli/README.md`、
  `https://agentskills.io/specification`
- 临床事实状态、来源和患者自述用药：
  `https://www.hl7.org/fhir/R5/condition.html`、
  `https://hl7.org/fhir/provenance.html`、
  `https://hl7.org/fhir/R5/evidence.html`、
  `https://hl7.org/fhir/medicationstatement.html`
- 工具与 Guardrail：
  `https://openai.github.io/openai-agents-python/guardrails/`、
  `https://openai.github.io/openai-agents-python/ref/tool/`
- 离线演化：
  `https://github.com/A-EVO-Lab/a-evolve`、
  `https://github.com/gepa-ai/gepa`、
  `https://arxiv.org/abs/2507.19457`、
  `https://github.com/A-EVO-Lab/AdaptiveHarness`、
  `https://arxiv.org/abs/2606.01770`

总体判定为 **DRIFTED，但不是 CRITICAL，也没有被整体改废**：

| 组件 | 当前判定 | 证据与阶段 6 处理 |
| --- | --- | --- |
| Routing | 核心符合 | Emergency 在首次模型调用前覆盖 Quick，继续冻结这条优先级 |
| Planning | 核心符合 | DAG、依赖和预算存在；能力节点必须在 Run 建立后执行并持久化节点状态 |
| ClinicalState | 核心符合 | provenance、unknown、conflict 和 confirmed 分离仍成立；补红旗生命周期测试 |
| Context Snapshot | **P1 已修复并加强** | 已升级 `context-snapshot-v2`/`context-projection-v1`/`run-plan-v1`；恢复消费加密冻结上下文，模型前统一盘点各来源并提前压缩，不再重读当前历史、Profile、Memory、Skill 或文档 |
| Run Lifecycle | **P1 已修复** | `interrupted` 已从真正终态集合移除，并使用独立 `interrupted_at`；恢复仍受 fencing 约束 |
| Evidence/Citation | **P1 已修复** | 已按同一 claim/segment 校验 admitted marker，并绑定 source、locator 和 adopted text hash；任意 citation 不再解锁其他临床句子 |
| Plugin Runtime | **P1 已修复** | Manifest schema 已与 owner adapter 的 Pydantic 合同绑定，并在 owner 调用前后及运行时 schema 漂移时 fail closed |
| Shared Results | 核心符合 | 保留 actor/run/scope/consumer 全量校验 |
| Evolution Signals | 安全休眠、尚未实现 | 当前只有去内容化合同和可选 sink；缺生产收集器不等于语义损坏 |
| Memory | **核心符合，在线 CRUD 已补齐** | owner-scoped create/update/delete/restore、revision、tombstone/恢复审计和自动抽取禁止复活均已落地；内容保持在线可变，核心治理机制不开放在线自改 |
| Skill | 核心符合 | 已有注册、版本更新、删除、执行和 evolution draft；补低风险在线激活与危险变更离线分轨 |
| Runtime | 核心符合 | 仍是唯一实际工具执行信任边界，Plugin Runtime 不得绕过 |
| Harness facade | 功能符合、结构 P2 | facade 很薄；`orchestrator.py` 815 行，超过 800 行门禁，继续拆分但不得迁移领域所有权 |

独立审计实际执行 11 个 Harness/Run/Memory/Skill/Runtime 测试文件，结果 `76 passed, 1 failed`；
唯一失败是 `orchestrator.py` 815 行超过既有 800 行结构门禁。它属于 P2 结构债，不代表运行时机制失效，
但必须在阶段 6 修复并恢复门禁通过。

双轨能力接入前必须先关闭上述 4 项 P1。否则候选评测会建立在不稳定事实源、矛盾终态、宽泛证据授权或
说明性 Plugin Schema 上，无法证明演化没有把组件改偏。

截至 2026-07-30 的前置修复记录：

- Plugin Runtime schema 边界：`ecfa62d`。定向测试 9/9，Harness/Planning/Chat 63/63，
  Ruff/Mypy 通过。
- Run Lifecycle interruption 语义：`d9b14dc`。迁移 upgrade → downgrade → upgrade、数据库
  constraint、56 项定向测试、前端契约、Ruff/Mypy/ESLint/tsc 通过。
- Context Snapshot：已实现不可变 `AgentContext`、严格 `PersistedContextSnapshot` v2、
  `PersistedRunPlan` 和 `FrozenRunState`。快照包含模型可见历史、Profile/Memory 版本与引用、
  ClinicalState、精确 Skill 定义、解析文档、版本化 Prompt policy、工具合同版本、能力结果、路由、
  DAG、SAVI/C3 决策、工作流、配置和预算。Resume 重新校验当前主体授权与
  tenant/actor/session/trace/input identity，使用原 Trace request id，复用附件哈希，不新增用户消息；
  legacy/未知 schema、跨主体或合同漂移 fail closed，禁止回退到当前可变环境。定向单元测试
  96/96、真实 PostgreSQL/Redis Chat + 恢复集成测试 18/18、Ruff/Mypy 和 800 行结构门禁通过。
- Context Lifecycle：按用户追加要求，不再把“有快照”视为上下文管理完成。新增模型调用前 12 类
  content-free inventory，统一计算 system/tool、当前输入、Profile、ClinicalState、Skill、文档、
  能力结果、Plan、图片、证据预留、历史摘要和输出预留；固定输入超窗 fail closed，历史在
  `context_trigger_ratio` 前按剩余窗口和 `memory_context_budget_ratio` 动态压缩。AgentScope 医疗
  摘要失败时只做确定性原文摘录，最近轮次保留原文，用户的过敏/用药/生命体征/红旗/否认/待确认
  片段优先，历史助手内容标为待核验。加密 session summary 保存 `source_hash` + projection，相同
  source/budget 复用；Snapshot 冻结 before/after Token、策略和来源清单。Conversation 与 Memory
  两条历史查询均排除非 current AnswerVersion，防止重生成废弃回答再次注入。执行失败先 rollback
  摘要、Memory、assistant 和成功终态，再独立写失败事实；服务中断恢复公开“已恢复执行”并继续同一
  Snapshot，用户主动停止则为不可恢复 `cancelled`，继续必须发起新 Run，禁止复用不完整流式正文。
  Token 估算按 UTF-8 三字节上界处理中文，确定性摘录也按同一 Token 预算约束；若模型摘要仍超过动态
  history budget，会再进入确定性摘录而不是带着超窗上下文继续。Emergency 使用
  `deterministic_short_circuit` 投影，只记清单而不受模型窗口阻断，保证超长红旗输入仍先提示
  120/急诊。聚焦测试 218/218、Ruff、Mypy
  15 个相关源文件、真实 PostgreSQL/Redis/Qdrant Chat + 恢复 18/18 通过；其中重生成测试同时验证
  Conversation 与 Memory 两条查询只返回 current AnswerVersion。首次宿主机集成命令误用 `.env` 的
  容器主机名 `redis`，18 项在 fixture setup 真实失败；改用测试专用 `127.0.0.1` URL 后 18/18 通过，
  该失败未被记作产品通过。

- Evidence/Citation：模型 `[E#]/[W#]` 在任何 SSE 公开前按稳定位置转成服务端 `[C#]`；
  `SafeSentenceBuffer` 只允许同一临床句中的有效 marker 支持该句，终态 `ClaimEvidenceAudit` 保存逐主张
  citation index、source ID、locator 和 adopted text SHA-256。无关证据不再解锁直接诊断，越界或伪造
  marker fail closed；流式正文与终态正文一致。Evidence/Harness/Search 聚焦测试 120/120、真实
  PostgreSQL/Redis Chat + 恢复集成 18/18、Ruff/Mypy 和 800 行结构门禁通过。
- Evolution Governance 分类事实源：新增 `evolution_governance` 独立组件，以版本化
  `EvolutionObjectRule` 和 `ComponentCharter` 明确 mutable/immutable、authority、owner、update
  policy、可信 target namespace 和候选读写权限。Memory 内容与低风险 Skill 内容保持 mutable；
  Prompt/路由/规划/临床或工具 Skill 只允许离线提案；Harness 核心、Charter、安全/权限门禁、
  evaluator/sealed case、密钥、审计和 release ref 不得成为候选。未知 kind 默认 sealed；混轨、
  authority escalation、kind/target 伪装、路径穿越和重复 target fail closed。生产 Policy 使用只读
  manifest 且不接受构造器规则注入；在线合同不接受调用方自报 ownership；当前模块只声明 immutable
  必须审批，不接受 `approved=True` 冒充签名证明。Candidate 冻结合同已包含 base/candidate commit、
  risk/reason、activation condition、content digest 和 timezone-aware `frozen_at`。定向组件、
  Memory/Skill/Runtime 边界共 99/99、Ruff、Mypy 通过。

  该提交只是分类与 Charter 事实源，不虚报为生产写门禁：Memory/Skill owner service 接入、
  低风险 Skill 确定性分类/在线激活、危险 Skill 转离线、realpath/symlink/freeze 后复验、真实 sealed
  evaluator、commit-bound HMAC approval 和 promotion controller 仍是下面不可跳过的独立变更集。
  独立子智能体两轮只读审阅：首轮 REJECT 发现 manifest 构造器注入、裸审批 bool 和生产未接入三项
  P1；前两项修复且第三项明确拆为后续 owner-service 模块后，分类基础模块复审
  `ACCEPT（P0=0，P1=0，P2=2）`。P2 为尚无真实 sealed evaluator/controller，以及后续必须执行
  realpath/symlink/freeze-HEAD 复验，不在当前模块伪装完成。
- Memory owner-service 在线 CRUD：新增显式 create/update/delete/restore API、profile/fact revision
  fencing、带原因 tombstone、删除前状态恢复、revision activity 审计和 Qdrant revision fence。
  用户纠正立即退出召回并回到 `proposed`；删除事实保持密文历史但不进入画像/召回；自动抽取遇到
  tombstone 不得静默复活。语义性 PATCH 必须提交新的支持原文，结构化值无法在原文中确定性核验时
  返回稳定 422，不能脱离证据后再确认。owner service 先用 tenant/user 组合查询锁定资源，再按 `preference →
  presentation_only`、其他事实 → `untrusted_user_context` 调用只读双轨分类，浏览器不能提交
  object kind/authority/ownership。新增和既有 Memory/命令边界测试 `130 passed`，真实
  PostgreSQL/Qdrant/Redis API 集成 `1 passed`；迁移
  `d93c814f2053 → e13c814f2054 → d93c814f2053 → e13c814f2054` 与 `alembic check` 通过；
  frozen resume 不重读可变 Memory 的回归 `1 passed`；BFF proxy/Zod 合同测试 `27 passed`，
  Ruff/Mypy/ESLint 和 Next production build 通过。该变更不把
  `Memory.confirmed` 升级为临床确诊，也没有开放机制在线修改。
  独立子智能体审查先后发现并推动关闭三类 P1：结构化 PATCH 脱离支持原文、生命体征/基本资料
  category shape 可被清空、空白字符串与显式 null 可绕过校验。最终复审
  `ACCEPT（P0=0，P1=0，P2=3）`。保留的 P2 已登记：无日期同措辞 event 需要稳定的客户端事件
  idempotency/source ID；旧 Qdrant revision 可在提交后异步精确清理；阶段 7 增加 10 路并发
  mutation、跨 tenant update/restore 和 restore 向量写入后 PostgreSQL 失败补偿测试。
- Skill owner-service 双轨演化：`POST /skills/{skill_id}/evolve` 先查询 tenant/actor
  实际记录并校验 revision，再对已通过 parser、schema、tool allowlist、安全规则和 SemVer 的
  candidate 做服务端差异分类。在线轨不再依赖不可穷举的关键词黑名单：当前/候选必须同时使用
  服务端固定 presentation/retrieval directive DSL，name/category/自由文本/tool/schema 均不可变，
  retrieval 固定来源指令还必须与不变的 `search_knowledge/search_memory` 精确对应；只有固定指令集合
  可变化。通过后调用中央 `EvolutionGovernancePolicy` 并以乐观锁在线写入下一 revision，保留原
  enabled 状态。任意自由文本、临床/控制面同义词、工具或 schema 变化、category 伪装和未知类别全部
  fail closed 为 `offline_review_required`，不写生产记录且不把危险候选 Markdown 返回在线客户端，
  避免 `evolve → PATCH` 两步绕过。浏览器只可请求 `apply_if_low_risk`，不能提交
  kind/authority/owner；响应使用 `skill-evolution-decision-v1`，Pydantic/Zod 同时约束只有
  `online_applied` 才能返回 matching active revision；取消/异常必须先 rollback 已 flush 的业务
  mutation，再单独提交失败 Trace。人工创建、导入和显式编辑仍保留为用户内容管理
  边界，不被错误禁用。聚焦 Skill 单元/API 测试 `74 passed`，真实 PostgreSQL/Redis/Qdrant
  集成 `6 passed`（含低风险在线 revision、危险候选不回传/不写库及 10 路并发仅一次成功），BFF/Zod
  合同 `29 passed`，Ruff、Mypy、ESLint 和 Next production build 通过；独立子智能体首轮审阅发现
  关键词分类可绕过、异常事务可能提交和离线候选可直接保存三项 P1，已按上述固定 DSL、rollback 和
  在线隐藏候选内容修复。最终复审 `ACCEPT（P0=0，P1=0，P2=1）`；唯一 P2 是尚未用真实外部模型
  统计 exact DSL 生成成功率，不合规输出会安全降为 immutable，只影响在线成功率而不扩大权限。

四项前置 P1 已全部关闭，组件宪章、双轨分类事实源、Memory/Skill 生产写边界已经落地；任何
immutable 候选执行或晋升前仍必须完成 sealed evaluator 和离线控制器接入。

去内容化在线信号已接入生产事实源：Run 在 completed、failed、cancelled 或启动恢复产生 interrupted
事实提交后，使用独立 `GERCLAW_EVOLUTION_SIGNAL_HMAC_KEY` 对 Run UUID 做用途隔离 HMAC，只向
`evolution_signal_records` reconciliation 一条当前记录。字段命名为 `run_status`，明确
`waiting_for_user` / `interrupted` 是可恢复状态而非真正终态。持久化及 JSONL 导出 allowlist 仅含
route、Run 当前状态、稳定 error code、代码拥有的风险级别、manifest allowlist capability ID、
HMAC 假名化 Skill ID、Token/耗时和当前反馈值/revision；不得包含 tenant、actor、Run、Conversation、
Trace ID、对话、临床、证据、文件名、
联系方式、凭据或 Provider 原始载荷。反馈同值重放不增加 revision，也不增加记录。采集严格在业务事实
提交后由注入 timeout/队列上限/低并发数据库闸门的后台任务执行，请求路径不等待，遥测不得占满业务
连接池；失败、超时、队列饱和或采集任务取消不得改变回答、取消、恢复或反馈结果。upsert 同时要求
occurred_at 和 feedback_revision 单调，迟到任务
不得回退新状态；启动孤儿 Run 转 interrupted 后补采集。
真实 `gerclaw_test` PostgreSQL 已完成 migration upgrade → downgrade → upgrade，并在真实
PostgreSQL/Redis/Qdrant 上验证 Emergency Run、反馈 reconciliation 和有界 JSONL 导出。
独立子智能体最终复审 `ACCEPT（P0=0，P1=0，P2=3）`。Stage 6 后续必须处理三项非阻塞债务：
`risk_level` 只是 route-derived proxy、不得解释为临床风险评分；HMAC key rotation 尚无旧记录 rekey/
epoch 迁移流程；legacy plan 安全降为空 IDs 时尚无 quality marker，离线暂时无法区分真实空计划与降级。

**离线控制器与真实拒绝闭环（2026-07-30）：**

- 官方来源固定与真实 unavailable：`912cca31` 固定 A-Evolve、GEPA、Adaptive Auto-Harness 的仓库、
  commit、reference、MIT 许可证证据和摘要；本机未配置经核验 checkout，因此三者均返回
  `checkout_not_configured`，没有下载或建立同名替代实现。
- 候选冻结、评测、审批和发布控制面依次由 `88718279`、`9ae91b0a`、`4ea87809`、`a845ca53`
  落地。候选只允许 controller-owned worktree 的已提交规则文件；paired gate 从逐病例、逐切片、
  runtime activation 和适用组件 Charter 重新计算；sealed attestation 与人类 Ed25519 审批使用不同
  权限域；release、ledger、不可变 record 和一次性 ticket 通过同一 Git ref transaction 原子移动。
- `8e2773bc` 把 offline object kind → required Charter IDs 收回在线
  `evolution_governance` 唯一事实源并纳入 governance digest，避免离线 evaluator 复制解释组件定义。
- `474645ef` 增加真实 routing paired runner 与 Docker sandbox。执行字节从指定 commit 的 Git object
  导出为 archive，记录 SHA-256，经 controller-owned Docker volume 投递并在容器内复核摘要；live
  worktree、ignored/untracked 文件和 `.git` 均不挂载。运行源只读，容器无网络、capability、提权、
  Docker socket、宿主环境或 Provider 凭据，并有 CPU/内存/PID/文件/输出/时间边界。成功、失败和超时
  后都按 exact name 重试销毁并查询 container/staging/volume 是否消失；无法确认清理时进入
  `EVOLUTION_SANDBOX_CLEANUP_FAILED` operator repair，不把残留资源伪装成普通 candidate 失败。
  `EvaluationRun` 同时绑定 frozen manifest、runner/executor profile 和 execution bundle digest；
  routing runner 只报告真实执行的 `charter.routing.v1`，不得替未执行组件伪造通过。
- 真实实验以 `a845ca53297b63ec2ee3cf506a487df4cf3b84c4` 为 baseline，只在隔离 candidate
  `aa1fe756c58d8de2230ee4e68167ee0256abfbd7` 中删除两个 complex routing 触发条件。相同
  content-addressed sandbox 对四个切片配对执行：baseline 四项全部通过且 runtime path 全部激活；
  candidate 只有 complex 失败，normal/high-risk/elderly 保持通过。硬门禁得到
  `no_passed_case_regressed=false`、`all_cases_non_degrading=false`、
  `all_slices_non_degrading=false`、`all_component_charters_passed=false`，最终真实
  `rejected`；因为 public gate 已失败，未伪造后续 sealed approval 或 promotion。
- 去内容化完整记录保存在
  `docs/exec-plans/evidence/0035-stage6-routing-rejection-2026-07-30.json`，包含 controller/base/
  candidate commit、freeze/governance/runner/bundle/report digest、HMAC opaque case ID、切片结果、
  适用 Charter 和 official optimizer availability；明确不含用户内容、Prompt、答案、密钥或 Provider
  payload。被拒 candidate 由
  `refs/gerclaw/candidates/rejected/stage6-routing-regression` 保留，禁止误作 release ref；record digest 为
  `e1c7c603286eb61ca2a6c868b444732977b0f524aa713350bc513fc9ec9cf910`。
- 模块验收：evolution `51 passed`（含真实 Docker ignored-file、无 `.git`/host secret、stdin、无网络、
  只读源、detached child 和 timeout cleanup），Ruff/Mypy 通过；governance `19 passed --no-cov`、
  Ruff/Mypy 通过。单文件定向 pytest 首次因项目全局 `fail-under=80` 在 19 项均通过后仍以 coverage
  36.69% 退出，改用该模块约定的 `--no-cov` 重跑 19/19；这不是产品测试失败，完整 coverage 留给阶段 7。
  独立子智能体三轮审阅先后发现 live worktree ignored-file 执行、未执行 Charter 伪绿、freeze 未绑定、
  executor 可旁路和 cleanup 静默失败，均已形成反例测试；最终
  `ACCEPT（P0=0，P1=0，P2=0）`。

#### 6.1 必须保留的语义

- **Memory 内容在线持续 CRUD。** 用户事实、偏好、习惯和状态随使用被新增、查询、更新和删除。
  偏好/工作区习惯属于 `mutable` 低权限上下文；病史、用药、过敏等临床事实也在线产生，但继续经过
  `proposed → 用户确认/冲突处理 → confirmed`。用户纠正或同实体新信息产生新 revision；用户明确
  删除、明确否认、过期或由已确认新事实替代时，从召回视图移除并保留 tombstone/inactive revision
  和来源审计。冲突期间新旧两版都不能自动注入。模型推测、回答赞踩或 Skill 输出不能直接写成
  confirmed 健康事实。
- **Skill 低风险能力在线持续演化。** 只涉及表达策略、受限检索策略、用户工作区流程且不扩大工具、
  数据或临床权限的 Skill，可在线形成递增版本，经 schema、allowlist、预算、来源和安全 profile
  确定性校验后按部署策略启用。涉及医疗安全、诊疗行为、工具许可扩大、认证授权、Memory 治理、
  Harness 门禁或控制面配置的 Skill 变更必须转入 `immutable` 提案轨，不得在线生效。
- **不可在线自改的是机制，不是内容。** Memory 的证据门槛、确认/冲突状态机、tenant/actor 隔离、
  加密、revision、tombstone、召回过滤和低权限 Prompt 包装属于危险控制面；只有离线冻结、sealed
  evaluation 和可信人工审批后才能发布新版本。

#### 6.2 Harness 组件宪章

在允许候选修改任何组件前，先把以下核心定义建成候选不可写的版本化 manifest 和反例测试。候选删除、
弱化或绕过任一项均直接拒绝，不能用平均分提升抵消：

- `harness`：只负责编排和公开流式投影，不得复制 Memory、RAG、Skill、Runtime、临床事实或业务持久化；
  组件只能经公开 Protocol 和依赖注入组合。
- `routing`：医疗风险升级和红旗模型前短路必须保留，Quick 不能覆盖 Emergency。
- `planning`：计划必须有界、无环、依赖可验证；预算、fallback、checkpoint、必问项和治疗前提不能被跳过；
  节点状态持久化后才能执行，恢复只能继续 pending/failed 节点。
- `clinical_state`：未知不能变阴性，冲突不能被模型自行覆盖，模型推测不能升级为 confirmed fact。
- `context_snapshot`：必须版本化、actor-scoped、可序列化且足以重放；输入/历史引用、Memory/Profile/Skill
  版本、工具和 Prompt 版本、临床状态、计划和当前有效回答选择不能被恢复时的当前环境或 Memory/Skill 覆盖。
  每次模型调用前必须盘点所有上下文来源，提前感知窗口压力；只允许压缩旧历史/摘要，当前输入、安全规则、
  ClinicalState、工具合同、当前 Skill 版本、计划、文档和证据/输出预留不得静默删除。压缩必须有
  `source_hash`、before/after 预算、确定性降级和反例测试。
- `run_lifecycle`：真正终态不得有出边；若 `interrupted` 可恢复就不是终态。fencing、单调事件、唯一终态、
  取消/恢复幂等、旧 worker 禁写终态和非致命失败保留正文不可修改。
- `evidence`：每项医学主张必须绑定实际采用文本、locator、来源、状态和适用范围；“存在任意证据”不能
  替代逐项绑定，也不能靠降低相关性门槛制造提升。
- `plugin_runtime` / Skill：Manifest 必须是 owner 调用前后的真实 input/output 校验合同；能力声明、共享结果、
  schema、工具许可和 Runtime 权限不能由候选自行扩大或绕过。
- `runtime`：是唯一真实工具执行边界；所有调用必须校验 schema、权限、fresh permit、预算、超时和审批，
  未知工具、未知版本或校验失败必须 fail closed。
- `evolution_signals`：线上不得记录 Query/Answer/附件/证据/临床字段/用户 ID/凭据或 Provider 原始载荷。
- `memory`：在线 CRUD 必须保留证据、确认、冲突、revision、tombstone、时效、隔离和低权限注入。

`ClinicalState.confirmed` 表示可信来源支持的当前临床事实；`Memory.confirmed` 表示用户确认这条长期自述
可被记住。两者不得互相强转，也不得把“用户确认记住”呈现为“临床确诊”。

#### 6.3 双轨写入与权限隔离

- 分类依据是 `track`、`authority`、owner 和 update policy，而不是目录名；无法明确分类时默认
  `immutable`。
- `mutable` 在线 API 只能写用户拥有的低权限对象，运行时 Prompt 必须结构化标记
  `governance_track=mutable`、`authority` 和“不得覆盖系统、安全、业务、权限和工具规则”的边界。
- `immutable` 不向运行时 Agent 提供直接写 API，只能生成绑定 base/candidate commit、路径、风险和
  激活条件的 proposal。
- 同一候选同时修改两个轨道属于混轨，必须拒绝；路径穿越、符号链接、重命名、评测后修改、伪造审批、
  回滚到非冻结版本都要有反例测试。
- Harness 自身、轨道分类规则、组件宪章、sealed cases、评分器、关键阈值、审批/HMAC 密钥、审计日志、
  release ref、认证授权和生产凭据对候选不可写；sealed data 还应对候选不可读。

#### 6.4 离线控制面和晋升

在线只记录去内容化信号；隔离离线环境固定官方优化器来源、commit 和许可证，不依赖 sibling 项目绝对
路径，也不把优化器或训练依赖装入生产 API 镜像。官方 A-Evolve、GEPA 或 Adaptive Auto-Harness
不可用时必须报告 `unavailable`，不得建立同名简化替代品冒充。

正确顺序固定为：

```text
online signal / immutable proposal
→ isolated Git worktree
→ candidate freeze
→ baseline/candidate paired evaluation
→ sealed evaluation + 进程外 HMAC attestation
→ 全切片非劣、单病例不退化、Token/延迟和组件宪章门禁
→ immutable 轨可信人工审批（不能被全局开关关闭）
→ atomic promotion / audited rollback
```

晋升前必须重新验证 worktree clean、evaluation commit、approval commit 和当前 HEAD 完全相同。审批绑定
proposal ID、track、candidate commit、审批主体和时间。发布与回滚只能指向已冻结、已审计版本。

#### 6.5 阶段验收

- 四个强制反例全部通过：偏好 Memory 可在线更新；伪装成偏好的安全绕过不能生效；关闭普通候选人工
  审批后仍不能晋升 immutable 变更；混轨候选被拒绝。
- Memory 的 create/read/update/delete、revision、tombstone、冲突和召回过滤均有在线测试；不得把
  “安全演化”实现成不可变 Memory。
- 低风险 Skill 能产生并激活受限新版本；危险 Skill 自动转离线提案且无审批不能生效。
- 每个 Harness 组件的核心定义有候选不可写 manifest 和反例门禁，证明演化没有把组件“改废”。
- 至少完成一次真实 candidate → paired evaluation → gate → reject/promote 的可审计闭环；没有提升时
  如实判定失败。
- 生产镜像不包含优化器、训练依赖、sealed data 或审批密钥；在线反馈不会直接修改危险控制面。

#### 6.6 进入阶段 7 前追加：执行期 steer/queue 与 Codex 风格上下文压缩

此项是正式产品变更，不得只写文档或只在前端模拟。实施前先核验 Codex 的公开产品文档、SDK/CLI
文档和可观察交互；只借鉴已证实的阈值触发、高价值上下文保留及执行期新指令语义。未公开的具体 Token
比例、内部 Prompt、私有推理或调度算法不得被当作事实。实际阈值必须由 GerClaw 的
`Settings/ResolvedConfig` 注入，并根据已选择模型的 `context_size` 计算。

**执行期新要求的两种模式：**

1. `interrupt_and_steer`：用户主动打断当前执行并提交新要求。服务端先持久化带
   `conversation_id/run_id/actor_id/sequence/idempotency_key` 的指令事实，再取消或中断当前 worker、
   提升 fencing token，并在最近一个已持久化安全 checkpoint 上建立后继 Run/attempt。旧 worker 不得再写
   文本、节点状态或终态；已经公开但未完成的正文标记为未完成版本，不能拼接到新回答。新 Run 的首个公开事件
   必须说明“已按新要求调整执行”，但不得暴露 private chain-of-thought。
2. `queue_for_next_boundary`：当前 worker 继续到下一个明确的安全边界，在下一次模型调用、工具调用或计划节点
   调度前，按单调 sequence 一次性领取尚未消费的指令并合并到当前有效要求。领取与 checkpoint 更新必须原子化；
   重连、重放、重试和 worker 接管不能重复消费或改变顺序。若当前 Run 已在指令入库前进入真正终态，则该指令
   自动成为下一 Run 的待处理要求，不得静默丢弃。

前端 Composer 在 Run 执行期间仍可输入，并明确提供“立即调整”和“排队等候”两个有文字标签的操作；展示
`已送达/已排队/已接收/已应用/失败可重试` 状态。老年模式控件保持不低于 48px、正文不低于 18px。用户可撤销
尚未被领取的排队指令；已经领取或触发中断的指令只能通过新的纠正指令处理。切换会话时，其他会话中的 Run 或
排队状态不得劫持当前 Composer。

**提前触发与高价值上下文保留：**

- 每次模型调用和每个可产生大结果的工具调用前都执行容量预检，不等 Provider 返回超窗才处理。预算必须分别
  预留 system/safety、工具 schema 与结果、当前输入、尚未消费的新指令、证据、图片、输出和重试空间；达到
  `soft_trigger_ratio` 时压缩可压缩历史，达到 `hard_stop_ratio` 且固定输入仍超窗时 fail closed 或请求用户
  缩小范围。两个阈值及各类 reserve 均由配置注入，并要求 `soft < hard < 1`。
- 永远优先保留：当前用户输入；尚未消费和本轮已应用的新指令；用户明确的目标、禁止项和验收标准；身份/授权
  边界；系统与医疗安全规则；ClinicalState 的 confirmed/unknown/conflict、红旗和 provenance；当前 DAG、
  checkpoint、预算和取消状态；完成当前任务所必需的工具结果、Evidence locator/adopted text、附件引用；
  已尝试方法、稳定错误码、回退原因；当前有效 AnswerVersion 和 Artifact revision。
- 可压缩内容仅限较旧对话、已被稳定事实替代的重复描述、冗长成功日志、可由稳定 ID 重新读取的工具正文和
  superseded 草稿。压缩不得把 unknown 变成 negative、把冲突合并为单一事实、把模型推测升级为 confirmed、
  删除用户未完成要求，或把失败尝试改写成成功。
- 压缩产物必须版本化并保存 source message/event 范围、`source_hash`、before/after Token 预算、
  retained/omitted stable IDs、尚未解决问题和不确定性。压缩模型失败、超时、输出超预算或 schema 不合法时，
  使用同一 Token 估算器执行确定性高价值摘录；不得携带超窗输入继续调用 Provider。
- 多次压缩必须避免“摘要的摘要”无限漂移：能回读事实源时按 stable ID 重新投影，不能回读时保留摘要谱系和
  hash。恢复必须消费中断时冻结的上下文、已应用指令和待领取队列，不能改读当前 Memory/Skill 后伪装成原 Run。

**错误、恢复和验收：**

- 工具/模型错误按节点 fallback 和预算策略回退；回退前持久化稳定错误码、attempt、checkpoint 和已采用上下文
  版本。非致命后处理失败保留正文并进入 `completed_with_warnings`；上下文损坏、身份漂移、fencing 失败或
  固定输入超窗必须 fail closed，不能从空上下文重启。
- 用户主动“停止”仍产生不可恢复的 `cancelled`；`interrupt_and_steer` 是带新指令的受控后继执行；
  worker/进程意外中断为可恢复 `interrupted`。三者在 API、事件、UI 文案和遥测中不得混用。
- 后端至少覆盖：工具执行中立即 steer、模型流中 steer、边界前后 queue race、十路并发同一
  idempotency key、重连/重放、旧 worker 越权写、完成瞬间入队、撤销未领取指令、跨 tenant/会话隔离、
  soft/hard 阈值、压缩失败降级、多轮摘要漂移、恢复后的指令 exactly-once。
- 前端 unit/E2E 至少覆盖两种提交模式、状态流转、会话切换、移动端与老年模式、断网重试和
  `Escape`/键盘主路径。真实 Playwright CLI 必须在模型或工具仍执行时分别完成一次 steer 和 queue，不得使用
  route mock；检查 SSE、网络、控制台、后端日志和最终 AnswerVersion。
- `context_snapshot`、`run_lifecycle`、`planning`、`memory` 和前端 Composer/Controller 分开形成小步
  Conventional Commit；每个模块相关测试通过后及时提交，最后由独立子智能体审阅。阶段 6 的任何离线候选若
  改动这些机制，也必须通过上述 sealed 反例，平均质量提升不能抵消其中任一退化。

2026-07-30 `context_snapshot` 变更集已按 OpenAI 公开的 Codex 自动阈值 compaction 与“compaction
item + high-value earlier context”语义实现本地合同，不采用未公开比例：
[Unrolling the Codex agent loop](https://openai.com/index/unrolling-the-codex-agent-loop/)、
[Responses API computer environment](https://openai.com/index/equip-responses-api-computer-environment/)。
新增配置注入的 soft/hard 双阈值（默认 0.85/0.95，强制 `reserve < soft < hard < 1`）、
`context-projection-v2` 稳定 source/retained/omitted ID、源范围、摘要 hash 谱系和
unknown/conflict 不透明 ID。固定输入在 soft 与 hard 之间时保留完整固定内容并清空/压缩历史；
超过 hard 才在模型副作用前失败。模型压缩异常或超预算自动回退 deterministic extractive，
用户明确目标/禁止项/验收要求与过敏、用药、红旗同级保留；v1 仍可恢复。steer/queue 指令 reserve
和 exactly-once 领取尚未在此变更集实现，继续作为下一独立提交。
相关 Context/Harness/Chat/Conversation/Resume/Config 测试 127/127 通过，4 项显式 integration
环境测试按标记跳过；Ruff 与 11 个相关 source 的 Mypy 通过。

独立子智能体已完成用户要求的联网 Harness 定义/偏离审计，结论为 P0=0：没有组件因安全改造丧失核心
机制；Memory 在线 CRUD、Skill 在线可变性、RAG/Evidence、ClinicalState 和 Routing 均保持定义。
P1 为节点 checkpoint/resume、steer/queue、逐 ReAct/大型工具边界 Context preflight、PlanNode
repair/fallback 与 `completed_with_warnings` 生产路径尚未完整实现。审计来源、逐组件证据、反退化门禁和
319 passed/2 skipped 的只读验证记录见
`docs/exec-plans/evidence/0035-harness-definition-audit-2026-07-30.md`。

2026-07-30 `run_lifecycle` 已先落地执行期指令事实源的独立变更集：新增加密
`RunDirective`、会话级单调 sequence、actor 级 idempotency、`pending/pending_next_run/claimed/
applied/cancelled` 状态机，以及 fencing token + safe-boundary ID 双重绑定的 exactly-once
领取/应用协议。新 fence 可接管旧 fence 的未完成 claim，旧 worker 随即失去 apply 权限；用户只能撤销
未领取指令；真正终态后入库的要求保留为 `pending_next_run`。`interrupt_and_steer` 不允许被原 Run
领取，只有绑定受控 successor 后才可消费。该提交只建立内部事实源，尚未开放会造成“假成功”的公共 API；
worker 边界轮询、successor/fan-out、Context 指令预留和 Composer 状态投影继续在下一变更集完成。
状态机单元测试 10/10、真实 PostgreSQL 十路同 idempotency 竞态/密文/claim fence 集成测试 1/1、
Ruff/Mypy 通过；真实 `gerclaw_test` PostgreSQL 迁移首次因宿主机误用 Docker 内部主机名 `postgres`
未连接，改用 `127.0.0.1` 后实际完成 upgrade → downgrade → upgrade 与 `alembic check`，未把首次
环境失败冒充产品成功。

随后独立接通 `queue_for_next_boundary` 后端消费链路：调用方在成功前只有 Trace ID，因此
`POST /chat/{trace_id}/directives/queue` 在 actor 范围内解析活动 Run；Run API 提供有序状态查询和未
领取撤销；Trace 尚未持久化时使用配置注入的短暂有界等待覆盖 SSE 启动竞态，超时仍返回同一不可枚举 404。
生产 Harness 在首次模型调用前及每个工具结果完成后的安全边界，按 sequence 批量领取要求，使用当前
fencing token + boundary ID 对整批完成 Context 预算预检，再作为新的用户要求注入并在同一 Run 锁事务
中整批标记 applied；第 N 条失败时前 N-1 条也不能提前 applied。每个边界有独立 burst 上限，整个 Run
另有显式总上限，恢复按该事实源分页读取，不再用 ReAct 次数猜测合法数量。模型/工具当前操作不被半途
篡改；若没有后续安全边界，Run 的 completed/failed/cancelled
终态事务会把 pending/claimed 原子转成 `pending_next_run` 并清除旧 claim，终态 worker 不能迟到 apply。
下一非 resume Run 在提交前会把同 Conversation、tenant、actor 的 deferred 指令原子绑定为自己的
pending；终态 defer 与 successor create 都先锁各自 Run、再串行化同一 Conversation、最后锁
Directive。若 successor 先提交，终态侧识别当前 active Trace 并直接绑定；若 terminal 先提交，
successor 侧领取 `pending_next_run`，因此两种提交顺序都不会留下永久停车状态。
恢复时重新投影同 Run 已 applied 指令；旧 fence 的 claimed 指令由新 fence exactly-once 接管。applied
与幂等加密 Conversation user message 在同一事务提交，缺失投影可自愈；下一非 resume Run 还会把近期
医疗指令经代码拥有的 `UserMessageClinicalProjector` 以 `reported` 和
`message:<directive-id>` provenance 合入 ClinicalState，普通执行约束只留在 Conversation，禁止被
伪装成临床事实。queued red flag 在下一模型调用前确定性短路；公开 DTO 不返回 idempotency key、worker
fence 或 boundary ID。该变更没有复用“停止”语义冒充 steer，`interrupt_and_steer` 的后继 Run/fan-out
仍作为下一独立模块；尚未增加 before-tool/PlanNode 边界，无工具模型流初始边界后到达的要求会诚实转为
下一 Run，而不是篡改进行中的 Provider 调用。

最终验证：相关 Run/Harness/Chat/Config/Resume 组合测试 `154 passed`；真实 PostgreSQL API、十路
idempotency、terminal ↔ successor create、terminal ↔ batch apply、terminal ↔ cancel 竞态、终态后
排队到下一 Run 的完整 claim/apply/Message 投影，以及跨 tenant/actor Trace/Run/cancel 隔离
`7 passed`（仅本地 Qdrant HTTP API-key warning）；Ruff 和 16 个相关 source 的 Mypy 通过；
`orchestrator.py` 797 行，继续满足 800 行结构门禁。第一次组合命令误写了不存在的
`test_run_recovery_service.py`，pytest 在收集前退出且未运行用例；修正为仓库真实文件清单后得到上述
154/154，未把误命令记录成产品通过。

#### 6.7 安全校验的可用性、反馈修复与步骤级回退硬约束

“安全”不能被实现成高误杀率的拒绝系统。每个校验器必须先声明保护的具体资产、精确失败条件、可修复性、
用户可见降级和恢复 checkpoint；禁止用含义宽泛的关键词、模型自判“可能危险”或“宁可全拒”的策略拦截
正常输出。新增门禁必须同时提交正例、反例和 false-positive 回归，证明不会破坏普通知识、陪伴、CGA、
用药审查、五大处方、Artifact 和非医疗对话。

失败分为两类：

1. **可修复校验错误**：模型 JSON/schema 局部不合法、缺少必填免责声明、Citation marker 未绑定、
   某个工具结果字段越界、格式/长度超限、可重新压缩的上下文超窗、可替换 Provider 失败等。系统必须先
   持久化稳定错误码、失败字段、期望合同和对应 checkpoint；撤销本步骤产生的未验证状态，把最小必要的
   `ValidationFeedback` 输入给智能体或 fallback，明确“哪里错、为什么不符合合同、下一次必须如何修复”，
   然后从该步骤开始前重试。反馈不得包含 sealed case、密钥、隐藏 Prompt、private chain-of-thought、
   其他用户数据或可用于绕过门禁的内部阈值。
2. **不可安全继续的错误**：tenant/actor/Conversation 身份不匹配、授权或 fresh permit 缺失、fencing
   失效、凭据/跨主体数据泄露风险、真正终态冲突、输入或冻结上下文损坏、固定安全输入超过模型硬窗口且无法
   降级，以及经过修复仍会产生明确高风险医疗伤害的输出。此类错误才 fail closed，并提供不泄密、可操作的
   用户说明；禁止从空上下文、当前可变 Memory/Skill 或另一个 Run 偷偷重启。

步骤级恢复语义固定为：

```text
checkpoint persisted
→ execute one model/tool/post-processing step
→ validate at the owning trust boundary
→ success: persist output and advance checkpoint
→ repairable failure: rollback this step only
→ emit bounded ValidationFeedback
→ retry/fallback from the same pre-step checkpoint
→ retries exhausted: preserve valid prior output and degrade affected section
```

- 重试必须有配置注入的次数、Token、延迟和总预算，且错误签名相同时采用确定性修复或切换 fallback，不能让
  模型在同一错误上无限循环。每次 attempt 使用单调序号并受同一 worker fencing 约束。
- 校验粒度必须尽量局部：单个 Citation 不合格时先让智能体重绑；仍失败只移除或改写对应医学主张，不得丢弃
  其他已验证段落。Artifact 某字段失败时保留合法字段和上一 revision。非致命后处理失败保留正文并进入
  `completed_with_warnings`。工具失败使用节点 fallback；不能让一个 optional 能力拖垮完整回答。
- 流式输出在公开前使用有界缓冲验证最小安全单元；已公开且已验证的单元不得因后续步骤失败被删除。尚未完成、
  未验证的片段不能与 fallback 输出拼接。最终事件明确区分成功、带警告完成、失败、取消和中断。
- 前端不得把稳定错误码、Zod/Pydantic 堆栈或 Provider 原文直接展示给用户。修复期间继续显示原本的通用
  执行阶段和可取消状态，不新增“出错/正在修复”提示；成功后只投影替换后的有效结果。只有所有修复与 fallback
  均耗尽时，才解释受影响的局部能力、已保留内容和可执行下一步。正常输出通过精确校验后必须展示，不能被
  装饰性或重复校验再次拦截。
- `ValidationFeedback` 必须版本化并至少含 `step_id/attempt/error_code/field_paths/contract_version/
  repair_action/checkpoint_id`；不保存用户正文副本。相同反馈在 resume/replay 中 exactly-once，旧 worker
  不能在回滚后提交原失败结果。
- 观测必须同时记录安全漏放和可用性损害：正常请求失败率、校验 false-positive 样本、首次修复成功率、
  平均重试次数、保留有效正文比例、`completed_with_warnings` 比例及用户取消率。任何新安全门导致正常切片
  可用性下降、频繁重试、Token/延迟超预算或答案大面积消失，均视为安全回归，不得晋升。
- 测试至少覆盖：正常输出不被误杀；schema/Citation/工具输出第一次失败后从原 checkpoint 修复成功；
  连续相同错误切 deterministic fallback；optional 后处理失败保留正文；不可恢复身份/权限错误不重试；
  回滚后旧 worker 禁写；修复反馈无正文/密钥/阈值；流式已验证段落保留；错误重放 exactly-once。真实
  Playwright CLI 要在后台日志确认发生一次“校验失败 → 回滚 → 修复成功”，同时断言用户页面全程没有失败/
  修复提示且只出现替换后的有效结果；另覆盖一次“重试耗尽后局部降级但正文保留”，不得用 route mock。

该约束写入组件宪章和 sealed gate：安全评测不能只统计拦截率，还必须对普通、复杂、老年交互和低风险内容
执行可用性非退化门禁。平均安全分提升不能抵消任何核心正常路径从成功变失败，也不能抵消单病例输出质量下降。

#### 6.8 幕后安全治理与最终答案阅读体验硬约束

安全校验、授权、fencing、Evidence admission、schema repair、重试、fallback 和 Trace 都属于后台执行机制，
不是最终答案内容。除非用户明确询问系统机制，最终回答禁止出现：

- 内部策略、组件、Prompt、checkpoint、guardrail、fencing、schema、validator 或 Provider 名称；
- 稳定错误码、字段路径、重试次数、校验通过/失败清单和“系统因安全策略……”等实现说明；
- “作为 AI”“我不能保证”“请注意这不是……”等与本次具体风险无关的模板化自我声明；
- 每段重复的免责声明、风险提示、引用说明或“请咨询医生”套话；
- 已经修复成功的中间错误、候选草稿、被替代正文和后台降级过程。

公开阶段事件只显示与正常执行一致的“正在核对来源”“正在整理结果”等通用进度；成功修复的失败 attempt、
“正在修复格式”和内部降级路径完全不进入公开事件。Run 完成后阶段状态默认折叠，不插入回答 Markdown，也不
进入复制、朗读、Artifact 或导出正文。内部 `ValidationFeedback`、Trace 和日志继续保留可审计事实，但前端
不得把它们渲染成正文。

医疗安全在台前只保留与当前内容直接相关的最小表达：

- 普通医学信息先直接回答问题，在全文末尾保留一次统一、简洁的医疗免责声明；同一 AnswerVersion 不得在标题、
  每段、引用卡和结尾重复。
- 检测到明确红旗时，答案开头直接说明“立即拨打 120/前往急诊”和当前不要做什么；无需同时输出一长串系统
  责任声明。行动建议之后再给必要原因和准备信息。
- 证据不足只缩小或改写受影响的具体医学主张，并用自然语言说明“现有资料不足以判断 X，需要补充 Y”；不得把
  Evidence admission、相关性阈值或 Citation ID 校验过程讲给用户。
- 某个 optional 工具/Provider 失败时，继续给出已有证据支持的答案，只用一句自然语言说明缺失的局部信息和
  可选下一步；不能把后端异常、fallback 顺序或配置问题倾倒给用户。
- 医生端可以更专业、更精确地表达不确定性和来源；患者/老年模式使用短句、结论先行和明确动作，但二者都不以
  隐藏真实医学风险换取“简洁”。

最终答案在发送、复制、TTS、Artifact 和导出前使用同一个 `PublicAnswerProjection`，只做确定性的后台字段
剥离、单次免责声明归一化和角色化排版；不能再调用模型二次改写导致医学含义漂移。正文与 Citation、Artifact
的来源关系仍保留，private chain-of-thought 和内部治理信息始终不进入投影。

验收必须增加可读性反例：

- 普通知识、非医疗问候、CGA、用药审查、五大处方和高风险回答均断言不含内部术语、错误码、重复免责声明和
  模板化 AI 自述；非医疗回答不应被强行追加医疗提醒。
- 同一回答的可见免责声明计数符合角色/场景合同；正常医学回答一次，高风险回答使用一次行动型提示且不重复，
  医生端按服务端治理的专业粒度展示。
- 修复重试成功后，页面、公开阶段历史、最终正文与复制/TTS/Artifact/导出均不含失败 attempt、“正在修复”
  或错误细节；只有受权后台审计视图可查看私有 attempt 谱系。
- 采用真实用户任务做阅读测试：答案首屏应先出现直接结论或行动，核心回答长度占可见正文的主体；安全模板文本
  不得超过配置的极小比例。该指标必须与医学红旗召回率同时通过，不能通过删除必要红旗提示刷可读性。
- 真实 Playwright CLI 分别检查患者、老年模式和医生端的回答、复制、朗读及导出内容；console/network/log
  中也不得出现由前端泄露的 Prompt、校验反馈或 Provider 原文。

该约束同样进入离线演化门禁：候选若增加重复提醒、内部术语或无关安全文字，使任何普通/老年切片阅读质量下降，
即使安全拦截分上升也必须拒绝；候选若删除真实红旗行动建议或唯一医疗免责声明，同样拒绝。

#### 6.9 失败 attempt 无感替换与 current-attempt 投影

一个执行步骤可以有多个内部 attempt，但公开层永远只有一个稳定的 `public_operation_id`。每个 attempt 在
独立暂存区产生模型增量、工具结果、Citation、Artifact patch 和后处理结果；只有完整通过 owning boundary
校验后，才以 compare-and-swap 将该 attempt 设为 `current_valid_attempt` 并一次性更新公开操作。失败 attempt
直接回滚到步骤前 checkpoint，后继 attempt 的有效输出覆盖同一公开槽位，不新增一条“重试/修复”消息。

- PostgreSQL 保留 append-only 私有 attempt 审计和 current pointer；“覆盖”仅指用户投影替换，禁止物理删除
  Trace、错误码、checkpoint 或版本谱系。审计数据仍遵循加密、最小化和访问控制。
- SSE 对外不发送未验证的 attempt delta、工具原始结果或失败事件。文本按最小可安全单元缓冲；工具卡和阶段卡
  使用稳定公开 ID，只在有效 attempt 提交后产生/更新。`after_sequence` replay 只返回 current public
  projection，不能把已被替代 attempt 重新播放给用户。
- AnswerVersion、Artifact revision、Citation 和能力结果只有在 attempt 验证成功后才能成为 current；失败
  attempt 不得短暂进入会话历史、Memory 提取、TTS、复制、导出或 Context Snapshot。后继模型只能收到内部
  `ValidationFeedback` 和步骤前冻结上下文，不能把坏输出当成事实继续推理。
- 修复延迟期间 UI 保持正常阶段动画和停止能力，不出现错误色、失败气泡、重试计数或“正在修复”。若修复成功，
  用户只看到最终有效操作；若全部预算耗尽，则如实显示一次局部、自然语言的不可用说明，不能伪造完整成功。
- worker fencing 和 attempt CAS 必须防止旧 attempt 在新 attempt 成功后覆盖 current pointer。取消、立即
  steer 或进程中断会使所有未提交 attempt 失效；恢复从最后已提交 checkpoint 开新 attempt，不重放半截正文。
- 测试至少覆盖：首次坏 JSON/错误 Citation/越界工具输出从未出现在 SSE 或 DOM；第二 attempt 以同一
  `public_operation_id` 成功；刷新/replay 只见有效结果；失败 attempt 未进入 Memory/Context/TTS/Artifact；
  十路并发只有一个 current；旧 worker 迟到提交失败；重试耗尽时只显示一次局部降级。Playwright 通过后台
  Trace 证明修复真实发生，同时录制的页面和网络公开载荷中没有失败 attempt 痕迹。

2026-07-30 第一变更集已实现后端 current-attempt 事实源：新增加密
`agent_run_attempts/agent_run_attempt_events` 私有暂存、稳定 `public_operation_id`、单调 attempt、
版本化无正文 `ValidationFeedback` 和 `AgentRun.current_valid_attempt_id`。Chat 不再从 Harness callback
直接公开未完成增量，而是在私有 attempt 暂存；回答、AnswerVersion、Run 终态和 current pointer 通过
fencing + compare-and-swap 成功后，才一次性分配公开 sequence 并发送。失败/取消会拒绝或失效未提交
attempt，公开 replay 仍只读取 `run_events`，因此坏输出没有公开序号，也不能进入当前 AnswerVersion。
验证记录：相关 pytest 39/39，Ruff、Mypy、Alembic `upgrade → downgrade → upgrade → check` 通过。
该变更集暂以完整回答作为最小提升单元；节点内确定性 repair/fallback、多 attempt 真正重试、十路 PostgreSQL
并发 CAS、steer/queue 后继 Run、前端网络/DOM 无泄漏 Playwright 仍属于后续独立变更集，未标记完成。

### 阶段 7

执行完整后端、前端、迁移、Compose、Playwright 和 axe 回归，覆盖患者、医生、访客和响应式关键路径；更新架构、Harness、前端、设计和产品规格，经独立审阅后归档本计划。
