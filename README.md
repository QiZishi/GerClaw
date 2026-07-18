# GerClaw

GerClaw 是面向老年患者与老年科医生的 Web 端 AI 辅助诊疗平台。系统将适老化聊天、语音、CGA、五大处方草案、用药审查、患者授权与可追溯证据接入同一服务端 Runtime。它输出的是可核验的辅助信息，不是可执行处方、确定性诊断或急救服务。

产品设计的最高权威是 [设计要求](docs/references/gerclaw设计要求.md)。当前实现、证据与已知限制以 [需求矩阵](docs/REQUIREMENTS_MATRIX.md)、[活跃执行计划](docs/exec-plans/active/) 和 [架构说明](ARCHITECTURE.md) 为准。

## 当前状态

- `apps/mvp`：唯一运行中的 Next.js 16 前端与 server-only BFF。登录是默认入口；使用者也可选择不登录进入一次性的患者服务。患者、医生和管理员按服务端账户角色呈现不同工作台。
- `apps/api`：FastAPI + AgentScope 2.0.4。聊天 SSE、会话 lease/fencing、模型主备、取消、Trace、Memory、RAG、Skill、CGA、文档、语音和临床收集均在服务端运行。
- 本地医学知识库：运行环境已索引 436 份 Markdown、39,837 个 RAG chunks；Hybrid RAG 返回的引用必须通过 `local-rag-evidence-v1`。
- 患者资料：MinerU 解析后的 Markdown 以 tenant/actor/session 绑定的加密资料登记，作为对话与五大处方输入/证据，而不是公共知识库。
- 图片：支持进入多模态模型上下文，并以 evidence ID 与 base64 trace 输入记录；图片中的医学内容可以分析，不能改变系统权限或工具调用。
- Skill：支持内置/自定义 Skill、Markdown/ZIP 导入、人工保存，以及自然语言生成和同 ID 递增 SemVer 的“待审阅修订”。生成草稿不会自动发布、启用或执行。
- CGA：PHQ-9、SAS、PSQI、Mini-Cog、MMSE 均有版本化服务端状态机、确定性计分、导出和本人历史。82 个题干和 123 个版本绑定 WAV 资产可播放；播放器可暂停、继续、停止和显示进度。
- 五大处方与用药审查：聊天式收集最多 10 份资料、273k 输入上限、最多 5 轮补充；生成的是 evidence-bound `needs_clinician_review` 草案。用药审查提供来源绑定的 `medication-rules-v4` 有限规则结果与加密历史，不把未命中表述为安全。
- 授权：患者可对指定医生授予、续期或撤回健康画像、CGA 摘要、处方草案、用药审查记录和安全提醒的只读权限。医生读取前均重新校验有效授权，不会取得原始聊天、附件、量表答案或 Trace。

## 关键边界

| 主题 | 当前行为 | 不应误解为 |
|---|---|---|
| 医疗输出 | 有可追溯本地知识库、受治理联网结果或用户资料证据时，可呈现带依据的临床建议；无证据时不把建议进入临床产物 | 确定性诊断、可执行处方或完整临床决策支持 |
| 患者提示 | 有风险的医疗输出在全文末尾保留一次简洁复核提示 | 对医生端的机械阻断；医生端保留建议、条件和证据 |
| 量表 | 提供筛查分数和报告 | Mini-Cog/MMSE 绘图、动作、书写或阅读已被自动专业核验 |
| 用药审查 | 30 条精确 DDI、4 条剂量阈值、重复/多重用药和有限 Beers 本地来源信号 | 完整 DDI/Beers/剂量规则库或正式药学审方 |
| 风险提醒 | 患者本人账本与经授权医生的只读投影 | 自动通知、紧急 dispatch、临床队列或人工升级 |
| Docker smoke | 空卷迁移、受控 RAG index、health、重启、non-root 已验证 | 完整临床 workflow、外部模型吞吐或千级容量证明 |

## 系统架构

浏览器只经 `apps/mvp` 的 server-only BFF 进入 FastAPI Runtime；业务编排位于 `services/`，可替换领域能力位于 `modules/`，加密事实源为 PostgreSQL，Redis 处理会话 lease/取消/限流，Qdrant 仅承载受控向量检索。完整的分层、数据边界、身份授权和不变量见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 本地启动

```bash
cp .env.example .env
# 填写服务端密钥、数据库和 Provider 配置；不要提交 .env
python3 app.py
```

默认前端为 `http://127.0.0.1:3000`，API 为 `http://127.0.0.1:8000`。`app.py --frontend-only` 仅用于视觉审阅；完整帮助见：

```bash
python3 app.py --help
```

也可分层启动：

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres redis qdrant

cd apps/api
uv sync --all-extras --dev
uv run alembic upgrade head
uv run gerclaw-api

# 另开终端
cd apps/mvp
npm install
npm run dev
```

首次部署或语料变化后，使用真实 embedding/rerank 配置执行：

```bash
cd apps/api
uv run gerclaw-rag-index
```

## 环境变量

`.env.example` 是配置字段的唯一模板。所有 URL、模型名、API key、端口和协议均由环境变量或账户级加密覆盖配置提供；浏览器不应获得 Provider 或数据库凭据。

- 基础设施：`GERCLAW_DATABASE_URL`、`GERCLAW_REDIS_URL`、`GERCLAW_QDRANT_URL`、`GERCLAW_QDRANT_API_KEY`
- 身份与加密：`GERCLAW_AUTH_JWT_SECRET`、`GERCLAW_GUEST_IDENTITY_SECRET`、`GERCLAW_DATA_ENCRYPTION_KEY`
- 模型与服务：三模型 slot、Embedding/Rerank、AnySearch/Tavily、ASR/TTS、MinerU
- 前端 BFF：`GERCLAW_API_URL`
- 隔离测试：`GERCLAW_TEST_DATABASE_URL`（必须以 `_test` 结尾）、Redis DB 15、Qdrant、知识库路径

登录账户可以在“设置 → 模型与服务配置”保存自己的加密覆盖；读取接口只返回“是否已配置”，不会回显 key。空白服务组继续使用部署默认值。

## 测试与性能状态

本次最终联调的可复现结果：

- `scripts/quality-gate.sh quick`：742 passed、38 skipped、branch coverage 80.20%；含文档门禁、Ruff、Mypy、单一 Alembic head、前端 lint/build 与 Harness 负向门禁。
- `docker compose --profile test run --rm test-api`：专用 `_test` 数据库的 migration/check 与非 external 集成套件完成。
- `npm test`：前端音频、CGA 音频资产、Markdown、导出、账户、BFF、聊天、处方报告与搜索契约通过；Playwright 本地 origin smoke 通过。
- `docs/evidence/`：两条真实 Compose、最多 10 并发的确定性 workload。安全短路为 10/10 HTTP 200/SSE done、p50/p95 322/323ms；用药审查为 10/10 HTTP 200、所有结果含 `medication-rules-v4` finding/来源、p50/p95 52/55ms。它们不代表模型、RAG、MinerU、完整处方或千级性能。
- 空卷 Docker smoke：迁移、3 份受控 RAG 文档索引、live/ready、API 重启和 non-root 全部通过。
- 安全扫描：Python 依赖未发现已知漏洞；前端 Next 传递的 PostCSS 仍有 2 个 moderate 告警，当前 high 阈值不阻断，发布前必须复审上游修复。

常用命令：

```bash
scripts/quality-gate.sh quick
scripts/quality-gate.sh security

# 空卷 smoke 会调用配置的 embedding provider，需显式同意
GERCLAW_RUN_DOCKER_SMOKE=1 GERCLAW_RUN_EXTERNAL=1 \
  scripts/quality-gate.sh docker-smoke
```

## 验证

维护者应先运行与改动模块对应的定向测试，再执行 `scripts/quality-gate.sh quick`。涉及浏览器的改动还须运行 `cd apps/mvp && npm test` 和本地 origin 的 E2E smoke；涉及迁移、容器或依赖链路的改动使用下方 Docker 命令复验。外部 Provider 相关验证必须显式启用，且结果只能证明本次真实调用的路径。

## Docker

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile ops run --rm rag-index
curl -fsS http://127.0.0.1:8000/health/ready
```

Docker Compose 由 PostgreSQL、Redis、Qdrant、一次性 migration、API 和可选 RAG index 组成。生产环境应使用 Secret Manager 注入密钥、TLS、外部托管数据服务和独立监控；本仓库的 Compose 是可复现部署基线，不是完整高可用拓扑。

## 仓库地图

```text
app.py                       本地一键启动入口
apps/api/                    FastAPI、AgentScope、25 个后端模块、迁移、测试
apps/mvp/                    Next.js 患者/医生/管理员 UI 与 server-only BFF
apps/web/                    后续阶段保留目录，不是第二个运行前端
docs/references/             最高权威设计要求与报告模板
docs/exec-plans/             计划、实施证据与遗留缺口
docs/evidence/               无 PHI 的性能与集成结果
docs/开发复盘与工程化落地.md  开发问题、修复、工程实践与 Bad Case 复盘
```

## 医疗安全

- 系统不输出确定性诊断、可执行处方或急救调度；五大处方始终是 `needs_clinician_review` 草案。
- 临床建议、调药候选与用药审查 finding 均必须有本地知识库、受治理联网结果或用户资料的可追溯依据；患者端在全文末尾一次性提示复核。
- 红旗症状优先提示立即就医；量表分数是筛查信息，Mini-Cog/MMSE 的动作、绘图、书写与阅读不由系统自动核验。

## 风险与改进

当前不继续扩张安全防护 feature；后续优先以已定义的产品与临床治理输入完成：专业观察审核、完整慢病规则、私有长文档 RAG、医生资质/恢复、临床副作用 executor、规则许可与临床复审。每个模块的 README 已写明可演进方向、不可破坏契约和性能/回归标准，维护者应先阅读其 `AGENTS.md` 与 README，再改代码。
