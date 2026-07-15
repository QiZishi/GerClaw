# GerClaw

GerClaw 是面向老年患者与老年科医生的 Web 端 AI 双向诊疗平台。当前仓库正在从已可用的 Next.js MVP 迁移到 FastAPI + AgentScope + PostgreSQL + Redis + Qdrant 的生产全栈。

最高产品权威是 [gerclaw设计要求.md](docs/references/gerclaw设计要求.md)，生产范围见 [PRD](docs/PRD.md)，真实完成度见 [需求矩阵](docs/REQUIREMENTS_MATRIX.md)。README 不作为“功能已完成”的单独证据。

## 当前状态

已通过独立审阅和真实依赖/模型验收的后端能力：

- AgentScope ReAct Agent Harness、三模型主备、SSE、取消、原子会话与 Trace
- 436 份本地知识库的 Agentic RAG、混合检索、重排和引用
- 加密 Memory/健康画像引擎与无 PHI Qdrant 语义索引
- AnySearch→Tavily 联网证据、SSRF 防护与不可信网页隔离
- 声明式 Skill 注册、版本、会话加载、AgentScope viewer 和安全策略
- 访客短期 JWT/BFF、scope、tenant/actor 隔离、限流、readiness 与 metrics

仍未完成生产交付的能力：

- Runtime PermissionEngine 的 ALLOW/DENY/ASK、HITL 和多智能体复核
- Voice、Privacy、MinerU Document 的完整 Python 后端
- CGA、五大处方、用药审查的后端状态机、规则、持久化和审批
- 风险预警、慢病管理、情感陪伴的真实前后端 workflow 与安全边界
- 患者/医生账号、角色/RBAC、患者授权
- Feedback→Bad Case→Eval 回放闭环、统一 10 并发报告
- 全站响应式/适老化 E2E 和最终 Docker 空卷验收

前端中仍存在的 `mock`、本地模拟或“Phase”注释都属于已登记缺口，不能作为生产能力使用。

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

当前 Docker 基础设施可用，但只有 [需求矩阵](docs/REQUIREMENTS_MATRIX.md) 的 `OPS-05` 完成最终空卷启动、应用 health、重启持久化和核心 E2E 后，才可声明生产容器交付完成。

## 测试与性能状态

截至 2026-07-15，本工作树已复现默认后端门禁 `349 passed, 31 skipped`、branch coverage `80.02%`；真实 PostgreSQL/Redis/Qdrant 集成为 `370 passed, 10 deselected`、coverage `87.06%`。MVP lint/build、Alembic upgrade/check 和 API image build 已通过。Bandit 通过；pip-audit 对 `uv.lock` 导出的完整适用依赖集报告无已知漏洞。任何后续代码变化仍须重新运行门禁，历史数字不能自动继承。

当前没有千级吞吐能力结论，也没有完成统一 10 并发验收。已有并发单测不能替代带资源、延迟、错误率、隔离与取消指标的性能报告；该验收归属 `OPS-04/OPS-08`。

## 风险与改进

| 风险 | 当前控制 | 下一交付点 |
|---|---|---|
| 临床页面仍有 mock，可能被误当成真实结果 | README/矩阵明确标记，生产验收 fail closed | 0023–0024 后端状态机与审批 |
| Runtime 缺统一 Permission/HITL/预算/checkpoint | 工具各自边界与 Trace 已有，不能代替统一合同 | 0021 Runtime Harness |
| 账号、RBAC、患者授权未完成 | 仅访客 scope/tenant 隔离，不声称生产 IAM | 0025 IAM 与授权生命周期 |
| 全出口 PHI/密钥泄露面未统一验证 | 核心日志/Trace/vector 有局部测试 | 0022 Privacy 与 0026 Eval/Bad Case |
| 风险预警/慢病管理/情感陪伴尚无真实闭环 | Chat 仅有红旗/自伤安全后处理，不等于业务功能 | 0023 临床 workflow 与安全陪伴 |
| 容量与容器恢复证据不足 | 只声明已真实验证的范围 | 0026 并发、0028 空卷 Docker 验收 |

## 医疗安全

- 禁止确定性诊断；模型输出必须经过安全后处理。
- 所有医疗输出强制附加：“内容由 AI 生成，仅供参考。身体不适请及时就医。”
- 胸痛、呼吸困难、意识障碍、大出血等红旗症状必须优先提示立即就医；自伤风险必须展示危机干预。
- 医学建议必须带可点击、可追踪来源；无证据时 fail closed。
- 不记录隐藏 Chain-of-Thought；仅记录简短 reasoning summary、工具状态和 PHI-free Trace metadata。

## 贡献流程

从 `docs/exec-plans/active/` 中编号最小的计划开始。每个变更集只做一个里程碑，更新规格与矩阵，实际运行必要测试，使用 conventional commit，并由独立审阅者复现后才能归档。
