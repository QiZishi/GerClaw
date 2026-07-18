# GerClaw

GerClaw 是面向老年患者与老年科医生的 Web 端 AI 双向诊疗平台。当前仓库已具备 Next.js BFF + FastAPI + AgentScope + PostgreSQL + Redis + Qdrant 的真实纵切面；它仍处于受控开发阶段，不能因页面、收集表单或基础设施可运行而表述为已完成生产临床交付。

最高产品权威是 [gerclaw设计要求.md](docs/references/gerclaw设计要求.md)，生产范围见 [PRD](docs/PRD.md)，真实完成度见 [需求矩阵](docs/REQUIREMENTS_MATRIX.md)。README 不作为“功能已完成”的单独证据。

## 当前状态

已实现并有代码、定向测试或真实运行证据的能力：

- AgentScope ReAct Agent Harness、三模型主备、SSE、取消、原子会话与 Trace
- 436 份本地知识库的 Agentic RAG、混合检索、重排和引用
- 加密 Memory/健康画像引擎与无 PHI Qdrant 语义索引
- AnySearch→Tavily 联网证据、SSRF 防护与不可信网页隔离
- 声明式 Skill 注册、版本、会话加载、AgentScope viewer 和安全策略；自定义 Skill 支持自然语言生成下一版待审阅草稿，且必须保持 ID、递增版本并由用户显式保存
- 访客短期 JWT/BFF、以及患者/医生本地账号的注册、登录、refresh 轮换、登出与改密；均由 scope、tenant/actor 隔离、限流、PHI-free 安全审计、readiness 与 metrics 保护
- PHQ-9、SAS、PSQI、Mini-Cog、MMSE 的版本化 FastAPI 状态机、确定性计分、加密持久化、本人历史、同版本数值对照与 Markdown/PDF/Word 导出；量表题目和选项使用版本绑定预录制 WAV，并保留受控实时 TTS 兜底
- MinerU 签名上传、轮询和 Markdown 下载的 Next.js BFF；FastAPI 将会话资料加密登记并按 tenant/actor/session 绑定
- 受限 BFF→FastAPI Voice Runtime：WAV/MP3 ASR、24kHz PCM16 TTS 和浏览器 WAV 播放封装；真实 TTS→ASR 回环已验证
- `input_output` 生产边界：Chat 输入在 Trace/存储/Harness 前规范化，SSE 终态只投影已审核的公开文本、引用与安全信息
- Chat/CGA 风险告警的本人范围账本与确认、慢病自述/测量账本，以及隔离的安全情感陪伴 workflow；均明确不替代临床审批或医生服务
- 五大处方对话式收集、证据绑定结构化草案、Markdown/PDF/Word 导出，以及用药审查：真实 API、加密持久化、乐观 revision 与 PHI-free Trace；审查依据 `medication-rules-v3` 返回 30 条可追溯 DDI、4 条日剂量、重复/多重用药和限定 Beers 信号，均不等同于可执行处方
- 用户反馈、加密 Bad Case 与 28 个合成确定性安全/输出安全/隐私/用药规则/Skill 草稿/Memory 提取 case 基线；golden case 不回放用户原文，也不调用模型或 RAG
- `security_evaluation` Runtime 门禁：Chat 实际启用的本地知识检索、本人记忆检索、外网搜索均有版本绑定风险档案；未匹配的风险/网络/数据类别、缺基础控制或外网缺服务端脱敏证明会拒绝加入 Toolkit
- 版本化 `privacy_redaction`：外部搜索 query 与 FastAPI TTS 正文/style 在 Provider 调用前最小化并脱敏，审计摘要只保留类别计数
- Docker Compose API 的 10 并发高风险安全短路 SSE，以及 10 并发确定性用药审查 workflow 证据；两者都不是模型/RAG/MinerU、完整处方或临床有效性的吞吐结论

已部分实现、但尚不能视为完整生产交付的能力：

- Runtime PermissionEngine 的 ALLOW/DENY/ASK、持久化 HITL、预算与 checkpoint 已有；临床副作用的恢复 executor、多智能体临床复核尚未接入
- Voice 已经由受限 BFF 接入 FastAPI Runtime、PCM16 流和 provider egress audit；缺真实人声质量、取消、浏览器播放完整 E2E 与 adapter version 协商
- MinerU 已以用户指定病例 PDF 实测解析并登记为会话输入；缺私有长文档检索、跨会话保留、授权与独立病毒扫描
- CGA 的 Mini-Cog/MMSE 动作、书写、阅读和时钟绘制仍仅记录本人作答，不能冒充专业人员观察；医生授权查看仍未实现
- 五大处方可生成基于本地/联网/上传资料证据的 `needs_clinician_review` 草案，用药审查可输出有限规则结论；两者均缺经临床治理批准的完整规则库、医生批准与患者授权发布闭环
- 风险预警、慢病管理、情感陪伴均只具当前最小的本人范围 workflow；缺通知升级、医学审核规则、人工升级、患者授权与医生队列
- 医生资质、患者授权与跨患者访问；账号已支持注册、登录、刷新轮换、登出、改密、账户停用与管理端基础后台，但没有账号验证、找回、MFA 和临床授权
- Bad Case 的授权脱敏晋升、模型/RAG/医疗评测、趋势指标与安全回放闭环
- Skill 的自然语言修订不会自动发布、启用或执行；版本绑定的草稿审核提示已有合成回归，但医疗业务 Skill 的审核发布和外部模型持续质量评测仍未完成
- 安全风险档案当前仅接入上述三种 Chat 工具；Agent、Skill、workflow、Memory 和 RAG 数据源的上线档案、统一 red-team 语料及发布门禁仍未完成
- 隐私策略已覆盖外部搜索、模型 prompt、FastAPI TTS/ASR 和 MinerU egress audit；字段级分类、同意、导出、生命周期、透明度及剩余出口尚未统一接入
- 全站响应式/适老化 E2E、临床 workflow E2E 与最终发布验收

`apps/mvp` 是当前唯一功能性 Web 客户端，`apps/web` 仍是二阶段预留目录。任何 mock、占位内容或仅本地 UI 状态均不得作为生产能力使用；逐项完成状态以[需求矩阵](docs/REQUIREMENTS_MATRIX.md)为准。

## 仓库结构

```text
apps/
  api/                 FastAPI、AgentScope、数据库和生产模块
  mvp/                 Next.js 16 患者端/医生端/BFF
docs/
  references/          最高权威设计要求
  product-specs/       产品行为规格
  design-docs/         技术与交互决策
  exec-plans/          活跃/已完成里程碑与证据
output/playwright/     已选取的浏览器验收证据
docker-compose.yml     生产形态基础编排
docker-compose.dev.yml 本地数据端口与测试库覆盖
```

## 系统架构

浏览器只连接 Next.js BFF；BFF 使用 server-only 短期凭证调用 FastAPI。FastAPI 在服务端执行认证/授权、Zod/Pydantic 边界校验、AgentScope Runtime、临床规则和安全后处理，再访问 PostgreSQL、Redis、Qdrant、本地知识库及显式配置的 Provider。

```text
Patient/Doctor Browser
        │ HTTPS + browser-safe payload
        ▼
Next.js BFF ── short-lived JWT ──> FastAPI/API boundary
                                      ├─ Runtime Agent Harness ──> LLM/Search/ASR/TTS
                                      ├─ Clinical modules
                                      ├─ PostgreSQL + Redis
                                      └─ Qdrant + local knowledge base
```

浏览器输入、上传文件、检索片段、工具结果、Provider 响应和数据库记录都是信任边界；任何边界失败必须 fail closed。模块依赖和数据分层以 [ARCHITECTURE](ARCHITECTURE.md) 为准。

## 环境变量

完整字段、格式和开发占位值以根目录 [.env.example](.env.example) 为唯一模板。关键分组如下：

- 身份与加密：`GERCLAW_AUTH_JWT_SECRET`、`GERCLAW_GUEST_IDENTITY_SECRET`、`GERCLAW_DATA_ENCRYPTION_KEY`。
- 数据依赖：`GERCLAW_DATABASE_URL`、`GERCLAW_REDIS_URL`、`GERCLAW_QDRANT_URL`、`GERCLAW_QDRANT_API_KEY`。
- 模型与工具：各 Provider 的 URL、Key、model、embedding、rerank、search、ASR/TTS 配置；Key 只能在服务端 Secret Manager 注入。
- 前端 BFF：`GERCLAW_API_URL`；不得使用 `NEXT_PUBLIC_*` 暴露 Provider 或数据库凭证。
- 测试隔离：`GERCLAW_TEST_DATABASE_URL`（必须以 `_test` 结尾）、`GERCLAW_TEST_REDIS_URL`、`GERCLAW_TEST_QDRANT_URL`、`GERCLAW_TEST_QDRANT_API_KEY`、`GERCLAW_TEST_KNOWLEDGE_BASE_PATH`。
- 显式授权：`GERCLAW_RUN_INTEGRATION=1`、`GERCLAW_RUN_EXTERNAL=1`；浏览器 smoke 使用本地 `GERCLAW_E2E_BASE_URL`。

配置值不应写入命令日志、Trace、截图、Git 或前端 bundle。生产启动会拒绝缺失或不安全的核心配置。

## 本地启动

最快方式是从仓库根目录运行：

```bash
python3 app.py
```

它默认启动 PostgreSQL、Redis、Qdrant、本地 FastAPI 与当前 MVP 前端（`http://127.0.0.1:3000`），并在 API 启动前执行迁移。`python3 app.py --api` 保留为兼容的同义命令；仅进行前端视觉审阅时使用 `python3 app.py --frontend-only`，它不会启动数据服务或 API。当根 `.env` 使用 Docker 服务名时，脚本只在宿主机 API 子进程中改用已发布的 localhost 地址，不修改或打印配置值。`python3 app.py --help` 可查看端口等选项。

启动器仅在前端进程通过初始启动检查后才显示启动地址；若同一工作目录已有 Next 开发服务，它会明确报告失败，避免将不可用的端口误报为已启动。

### 1. 配置

```bash
cp .env.example .env
```

将 `.env` 中所有 `replace-me` 和示例 Provider 配置替换为真实值。生产环境必须从 Secret Manager 注入 JWT、访客身份和数据加密密钥，不能使用本地默认密码或 HTTP 外部 endpoint。

### 2. 启动数据依赖

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres redis qdrant
```

### 3. 后端

```bash
cd apps/api
uv sync --all-extras --dev
GERCLAW_DATABASE_URL='postgresql+asyncpg://gerclaw:local-postgres-only@127.0.0.1:5432/gerclaw' uv run alembic upgrade head
uv run gerclaw-api
```

首次或语料变化后，从仓库根 `.env` 配置真实 embedding/rerank，再执行：

```bash
cd apps/api
uv run gerclaw-rag-index
```

索引任务的知识库路径必须指向仓库同级 `../本地知识库/md`。API readiness 在未完成有效 generation 前会 fail closed。

### 4. 前端

```bash
cd apps/mvp
npm install
npm run dev
```

默认地址：前端 `http://127.0.0.1:3000`，后端 `http://127.0.0.1:8000`。前端 BFF 通过 server-only `GERCLAW_API_URL` 连接 FastAPI；Provider Key 不得进入浏览器包。

## 验证

### 默认门禁

```bash
scripts/quality-gate.sh quick
```

默认 pytest 使用两位小数执行 branch coverage ≥80% 门禁；低于阈值必须非零退出。
完整模式和真实依赖的前置条件见 [Development Harness](docs/DEVELOPMENT_HARNESS.md)。

### 真实依赖

集成测试只允许专用 `_test` 数据库：

```bash
cd apps/api
GERCLAW_TEST_DATABASE_URL='postgresql+asyncpg://gerclaw:local-postgres-only@127.0.0.1:5432/gerclaw_test' \
GERCLAW_TEST_REDIS_URL='redis://:local-redis-only@127.0.0.1:6379/15' \
GERCLAW_TEST_QDRANT_URL='http://127.0.0.1:6333' \
GERCLAW_TEST_QDRANT_API_KEY='local-qdrant-only' \
GERCLAW_TEST_KNOWLEDGE_BASE_PATH='/absolute/path/to/本地知识库/md' \
GERCLAW_RUN_INTEGRATION=1 \
uv run pytest -q -m 'not external'
```

真实外部测试会调用 Provider 并可能产生费用，必须显式启用：

```bash
# 从仓库根执行，并沿用上一段的五个 GERCLAW_TEST_* 隔离资源变量
GERCLAW_RUN_EXTERNAL=1 scripts/quality-gate.sh external
```

`external` 内部同时设置 integration 授权；缺少任一隔离资源变量都会在 Provider 调用前失败。

## Docker

基础编排包含一次性 migration、API、PostgreSQL、Redis、Qdrant 和可选 RAG index job：

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile ops run --rm rag-index
docker compose -f docker-compose.yml -f docker-compose.dev.yml ps
```

当前 Docker Compose 已通过独立空卷迁移、应用 health、受控 RAG index、非 root 与重启持久化 smoke。它证明部署运行基础，不替代临床 workflow E2E、容量验收或尚未完成的医生授权/审核闭环。

空卷 smoke 使用独立的 Compose 项目和临时卷，完成后自动清理。它在空卷中构建受控的
代表性 RAG 语料，因而会调用已配置的 embedding Provider，必须显式授权：

```bash
GERCLAW_RUN_DOCKER_SMOKE=1 \
GERCLAW_RUN_EXTERNAL=1 \
GERCLAW_DOCKER_SMOKE_API_PORT=18080 \
scripts/quality-gate.sh docker-smoke
```

该 gate 验证迁移、RAG index、`/health/live`、`/health/ready`、非 root API 和 API
重启后 readiness；它不会替代临床 workflow 的 E2E 或容量验收。

容器内真实依赖测试使用独立 `test` profile，不发布数据服务端口，也不会使用业务数据库。它仍会读取根 `.env` 的 server-only 模型配置，但默认排除会实际调用 Provider 的 `external` 用例：

```bash
docker compose --profile test up --build --abort-on-container-exit \
  --exit-code-from test-api test-api
```

测试结束后执行 `docker compose --profile test rm -sf test-api test-db-init` 清理已退出的 test job；该命令不会停止 API/数据服务，也不会删除数据卷。

## 测试与性能状态

历史全量门禁数字、独立审阅与完整命令见 [Development Harness](docs/DEVELOPMENT_HARNESS.md) 和各 active exec-plan，不能因后续变更自动继承。本次近期可复现实证包括：`apps/mvp` 的 `npm test`（42 个 Node 行为/契约检查与 CGA 音频资源校验）、`npm run lint` 与 `npm run build`；`scripts/quality-gate.sh quick` 已在当前工作树通过，包含 API Ruff/Mypy、迁移图与 `698 passed、36 skipped`（coverage `80.46%`）、MVP lint/build 及 Harness 负向自测。Docker Compose 的确定性安全短路报告见 [`docs/evidence/`](docs/evidence/)，空卷 Docker smoke 已通过。全站 E2E、临床 workflow 压测与完整产品发布验收仍需在交付前重新执行。

当前没有千级吞吐能力结论。Compose 已实际验证 10 个并发的确定性高风险安全短路 SSE（10/10 done、失败率 0、p50 153ms、p95 154ms、Trace/消息/跨访客隔离均通过）；test image 中经显式 opt-in 的合成 RAG 评测为 6/6（五个本地老年医学主题命中绑定文档，非医学问题无证据为空）。两者均不能替代模型、临床 workflow、取消/限流/幂等的统一性能报告，后者仍归属 `OPS-04/OPS-08`。

## 风险与改进

| 风险 | 当前控制 | 下一交付点 |
|---|---|---|
| 有限临床规则/草案可能被误当成正式建议 | 处方与用药均显示来源、范围与待临床复核状态；患者风险提示只在内容末尾统一出现 | 0029 医学规则治理、审批与授权 |
| Runtime 临床副作用恢复/复核尚未接线 | Permission/HITL/预算/checkpoint 基础已存在，但临床 executor 仍 fail closed | 0021 与各临床 workflow 接入 |
| IAM 仍未完整 | 本地账号会话、账户后台和 BFF HttpOnly Cookie/CSRF 已落地；医生资质、授权和跨患者访问尚未完成 | 0025、0032 |
| 全出口 PHI/密钥泄露面未统一验证 | 核心日志/Trace/vector 有局部测试；文档、导出和临床流程尚未完整覆盖 | 0022 Privacy 与 0026 Eval/Bad Case |
| 风险预警/慢病管理/情感陪伴尚未形成完整临床闭环 | 当前仅有本人范围告警确认、非临床测量趋势与隔离陪伴；不宣称通知、干预或医生服务 | 0023、0030、0031 后续 workflow |
| 容量与临床 workflow 证据不足 | 只声明已真实验证的范围 | 0026 并发、完整临床 E2E |
| 前端 `next` 传递依赖的 PostCSS 中危告警 | 当前 `npm audit --omit=dev --audit-level=high` 不阻断；尚无兼容的非 breaking 修复 | 跟踪 Next/PostCSS 上游修复，发布前复审并更新 lockfile |

## 医疗安全

- 禁止确定性诊断；模型输出必须经过安全后处理。
- 所有医疗输出强制附加：“内容由 AI 生成，仅供参考。身体不适请及时就医。”
- 胸痛、呼吸困难、意识障碍、大出血等红旗症状必须优先提示立即就医；自伤风险必须展示危机干预。
- 医学建议必须带可点击、可追踪来源；无证据时 fail closed。
- 不记录隐藏 Chain-of-Thought；仅记录简短 reasoning summary、工具状态和 PHI-free Trace metadata。

## 贡献流程

从 `docs/exec-plans/active/` 中编号最小的计划开始。每个变更集只做一个里程碑，更新规格与矩阵，实际运行必要测试，使用 conventional commit，并由独立审阅者复现后才能归档。
