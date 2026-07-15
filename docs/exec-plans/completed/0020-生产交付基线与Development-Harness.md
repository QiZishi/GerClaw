# 0020 — 生产交付基线与 Development Harness

> 创建：2026-07-15 | 完成：2026-07-15 22:41 CST | 优先级：P0 | 状态：已完成

## 1. 目标

把最高权威设计要求转换成真实、可追踪的生产 PRD 与验收矩阵；清理过时的“已完成/mock”叙述；建立统一 Development Harness，使后续每个 Runtime/临床模块都以同一套门禁和证据合同交付。

## 2. 范围

1. 重写 `docs/PRD.md` 为生产版，覆盖访客/患者/医生、Development Harness、Runtime Agent Harness、临床模块、安全、数据、可观测和 Docker。
2. 新建 `docs/REQUIREMENTS_MATRIX.md`，逐项记录责任模块、验收和真实状态。
3. 修正 `README.md`、`docs/PLANS.md`、`docs/长期规划.md` 的当前事实，不再把 mock 或前端占位描述为生产完成。
4. 新增统一门禁脚本：默认 quick 串联 docs、Ruff、mypy、pytest/coverage、单 migration head、MVP lint/build；真实 integration 在专用测试库执行 Alembic upgrade/check；external、Docker 与浏览器门禁保持显式 opt-in。
5. 为门禁本身增加负向测试/自检：覆盖率不足、文档 placeholder、缺失迁移或 build 失败时必须非零退出。
6. 输出后续最小 exec-plan 顺序：Runtime 权限/HITL/工具 → Voice/Privacy/Document → CGA → 处方/用药 → 账号/RBAC → feedback/eval/Bad Case → 前端全接入 → 并发/Docker。

## 3. 验收标准

- [x] 生产 PRD 覆盖权威文档核心需求且不再以 MVP 阶段作为最终范围。
- [x] 需求矩阵覆盖所有生产模块，当前 mock/缺口明确标为 `🚧/❌`。
- [x] README、PLANS、长期规划与矩阵一致，无虚假完成声明。
- [x] 一条默认命令可运行 docs + backend + frontend 的必要门禁并保留退出码。
- [x] quick/full/external/e2e/docker 模式、环境前置条件和故障语义有文档与自检。
- [x] 全套门禁实际通过，独立审阅者 PASS，提交 conventional commit 并归档。

## 4. 后续里程碑顺序

1. 0021 Runtime PermissionEngine、HITL、统一 Tool Registry 与多智能体复核。
2. 0022 Voice、Privacy、MinerU Document 与多模态文件上下文。
3. 0023 CGA、风险预警、慢病管理、情感陪伴的后端状态机、确定性规则、安全边界和双端工作区。
4. 0024 五大处方结构化生成、四重校验、用药规则与审批。
5. 0025 账号、角色、RBAC、患者授权与临床数据加密持久化。
6. 0026 Feedback、Bad Case、Eval、指标、≤10 并发和性能报告。
7. 0027 前端全功能接入、全站适老化/响应式/无障碍 E2E。
8. 0028 Docker 空卷部署、全量真实外部回归与最终独立验收。

## 5. 验证证据

- `scripts/quality-gate.sh docs`：文档合同无错误/无警告；verifier `4 tests OK`，动态核对 53 个 PRD/矩阵 ID、README 章节、相对链接与状态。
- `quick`：Ruff format/check、strict mypy、单一 Alembic head、默认 pytest `349 passed, 31 skipped`、branch coverage 80.02%、MVP ESLint 与 production build 全部通过。
- 负向自检：未知 mode、缺失/业务 migration URL、业务 integration URL、99% coverage 阈值与伪 npm build 均真实非零退出。
- `security`：Bandit 通过；`uv export --locked --all-extras --no-emit-project` 后 pip-audit 审计当前平台完整适用依赖集，`No known vulnerabilities found`。
- `migration`：专用 PostgreSQL `_test` 库执行 `upgrade head` 与 `alembic check`，`No new upgrade operations detected`。
- `integration`：先执行 migration 门禁，再完成真实 PostgreSQL/Redis/Qdrant `370 passed, 10 deselected`，coverage 87.06%。
- `docker`：Compose config 通过；第一次拉取 Python base image 因 Docker Hub OAuth 连接超时真实失败，显式 `docker pull python:3.12-slim` 成功后重跑，`gerclaw-api` image build 明确以 exit 0 完成。
- CI workflow YAML 已由 PyYAML 解析并检查 `jobs.quick`；CI 本身须在 GitHub push 后以平台结果为准，本地不伪造远端执行。
- `e2e` 初测发现 Playwright CLI 对 `ERR_CONNECTION_REFUSED` 自身返回 0；Harness 已改为检查 `### Error` 和 `location.origin`。服务未启动时现明确返回 1，启动真实 Next dev 后 snapshot/title/origin 通过并返回 0；远程 URL 被入口策略拒绝。
- 独立审阅者最终复验 59/59 PRD↔matrix、quick/security/migration、Harness 负向测试、CI YAML 和 `git diff --check`，2026-07-15 22:41 CST 给出无 P0/P1 阻断的 PASS。
