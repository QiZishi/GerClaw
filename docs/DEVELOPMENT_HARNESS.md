# GerClaw Development Harness

Development Harness 将文档合同、静态检查、测试、构建、安全扫描、真实依赖和 Docker 检查统一为一个稳定入口：

```bash
scripts/quality-gate.sh <mode>
```

脚本以仓库位置解析绝对路径，不依赖调用者当前目录；使用 `set -euo pipefail`，任一步失败立即保留非零退出码。

## 模式

| 模式 | 内容 | 是否调用外部/容器 |
|---|---|---|
| `docs` | 文档结构、placeholder、需求 ID 覆盖、核心模块 AGENTS/README 自检 | 否 |
| `backend` | Ruff format/check、strict mypy、单一 Alembic head、pytest+coverage | 否；integration/external 自动跳过 |
| `frontend` | ESLint、Next production build | 否 |
| `quick` | docs + backend + frontend + 门禁负向自检；默认 PR/本地门禁 | 否 |
| `security` | Bandit、对 `uv.lock` 导出的完整依赖集执行 pip-audit、对 production npm 依赖执行 high/critical `npm audit`、从 production API image 生成 Python runtime CycloneDX SBOM | 需要包索引网络与 Docker |
| `migration` | 对专用测试库执行 Alembic upgrade/check | 是 |
| `integration` | 真实 PostgreSQL/Redis/Qdrant，全套 `not external` | 是 |
| `external` | 根 `.env` 配置的真实 Provider 测试 | 是，可能计费 |
| `e2e` | 对已运行的本地前端执行 Playwright browser smoke | 是 |
| `docker` | Compose config 与 API image build | 是 |
| `full` | quick + security | 需要包索引网络 |

`e2e` 只证明真实浏览器能打开指定本地 origin 并生成可访问性快照。患者/医生核心旅程仍由对应 exec-plan 使用 Playwright CLI 执行，因为它依赖当次测试数据；最终 Docker 运行验收在 0028 执行，不能用 `docker config` 或单镜像 build 冒充。

## 环境前置条件

首次运行：

```bash
cd apps/api && uv sync --all-extras --dev
cd ../mvp && npm ci
```

`migration` 和 `integration` 必须显式设置：

- `GERCLAW_TEST_DATABASE_URL`：库名以 `_test` 结尾；shell 在启动 Alembic/pytest 前校验，fixture 再次校验。
- `GERCLAW_TEST_REDIS_URL`：专用 Redis DB。
- `GERCLAW_TEST_QDRANT_URL` 与 `GERCLAW_TEST_QDRANT_API_KEY`。
- `GERCLAW_TEST_KNOWLEDGE_BASE_PATH`：真实 Markdown 语料绝对路径。

`external` 只有 `GERCLAW_RUN_EXTERNAL=1` 时执行，并要求与 `integration` 相同的隔离资源变量，以便真实 Chat/RAG/Memory/Skill 用例不会因缺少 integration fixture 而跳过。Provider URL、Key、模型名仍从仓库根 `.env` 的 server-only 配置读取；命令不得打印密钥。

`e2e` 必须设置 `GERCLAW_E2E_BASE_URL`，且只接受显式的 `http://127.0.0.1:<port>` 或 `http://localhost:<port>`，避免门禁意外操作外部站点。

`docker` 与 `security` 的 SBOM 步骤需要 Docker daemon，并读取 `.env` 或 `.env.example` 对应变量。生产镜像验收不得使用 development placeholder。SBOM 的组件范围、许可证未知项和发布复审规则见 [SUPPLY_CHAIN](SUPPLY_CHAIN.md)。

若宿主机未发布数据服务端口，或需要验证容器网络中的完整真实依赖路径，可运行 `docker compose --profile test up --build --abort-on-container-exit --exit-code-from test-api test-api`。该 profile 只创建/使用 `*_test` PostgreSQL 库和 Redis DB 15，测试镜像与 production API image 分离，且默认排除 `external` Provider 调用。

CI 使用 `uv sync --locked` 构造项目 `.venv`；`security` 同时用 `uv export --locked --all-extras --no-emit-project` 生成带 hash 的临时 requirements，再交给 pip-audit 严格审计完整传递依赖。仓库自身的 `gerclaw-api` 源码由 Bandit 检查。禁止无参数运行 pip-audit，因为那只会审计 `uvx` 自身的隔离工具环境。

## 失败语义

- 未知 mode 返回 2。
- 缺少真实依赖变量或外部调用授权立即非零退出，不自动选择业务数据库或模拟 Provider。
- 文档缺章节、遗留 placeholder、需求矩阵漏 ID/重复 ID，或任一含实现源码的核心
  Python 模块缺少 AGENTS.md/README.md，均返回 1。
- coverage 使用两位小数；低于 80.00% 返回 1，不能因整数舍入放行。
- backend 必须恰有一个 Alembic head；integration 在 pytest 前对隔离库执行 `upgrade head` 和 `alembic check`。
- 任一 lint、type、test、build、scan 或 Docker 命令失败，整个 mode 失败。

`quick` 末尾还会真实制造并捕获四类失败：未知 mode、缺失/不安全 migration URL、99% coverage 阈值和伪造 npm build 非零退出。自检只使用已有 coverage 数据与临时 PATH，不修改产品源文件或测试数据库。

门禁不会自动修复、自动重写或吞掉输出；开发者必须保留实际错误并在当前 exec-plan 记录复现命令。

## 证据合同

每个完成里程碑必须记录：

1. commit SHA、系统时间和关键依赖版本。
2. 实际执行的 quality mode、测试数量、coverage 和退出码。
3. integration/external 使用的隔离资源类型，不记录 Key、PHI 或完整连接凭证。
4. 前端改动的浏览器路径、computed style/ARIA/console 和必要截图。
5. 医疗/权限/上传/外部响应的负向边界与 fail-closed 结果。
6. 独立审阅者的 PASS/FAIL；FAIL 不得归档。

已选取的非敏感浏览器证据放入 `output/playwright/`；CLI 临时快照目录 `.playwright-cli/` 不属于交付证据。
