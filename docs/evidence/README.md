# 运行证据

## 2026-07-16：Compose API 的 10 并发安全短路 SSE

证据文件：perf-sse-safety-short-circuit-compose-2026-07-16.json

运行对象是当前 Docker Compose 中健康的 API、PostgreSQL、Redis 与
Qdrant；API 镜像由本仓库当前 apps/api 源码构建，迁移容器成功完成后才
启动 API。负载脚本为 apps/api/scripts/perf_sse_safety_short_circuit.py，
并发参数固定为 10，脚本本身拒绝大于 10 的参数。

每个并发访客独立获取身份、创建会话、提交同一条确定性高风险文本并消费
完整 SSE。该文本在 Agent Harness 的安全短路分支结束，因此不会调用外部
LLM、RAG 或搜索。脚本验证每条请求的 done 终态、唯一且完成的 Trace、同一
会话内持久化 assistant 消息，以及另一访客读取该会话返回 404。该行为是当时的
历史结果；当前产品已将访客会话历史整体改为不可读，最新证据见下节。

结果为 10/10 HTTP 200 与 SSE done，失败率 0，端到端延迟 p50 为 153ms、
p95 为 154ms。这是安全短路的容器链路基线，不代表外部模型/RAG 吞吐、完整
临床 workflow 性能或千级并发能力。

## 2026-07-17：当前镜像复验

证据文件：perf-sse-safety-short-circuit-compose-2026-07-17.json

在包含最新 Voice SSE 修复的当前 Compose API 镜像上，用相同脚本和相同硬上限
10 重新执行。10/10 HTTP 200 与 SSE `done`，失败率 0；p50 为 114ms，p95 为
115ms。每条请求均有唯一 completed Trace、同会话持久化 assistant 消息，另一
访客读取仍为 404。该重跑仍只覆盖无外部模型、无 RAG 的确定性高风险安全短路，
不能被解读为完整临床 workflow、外部 provider 或千级并发的性能承诺。

## 2026-07-18：访客历史保护后的当前镜像复验

证据文件：perf-sse-safety-short-circuit-compose-2026-07-18.json

当前版本明确规定访客数据保留为服务端 Trace/质量分析输入，但不能由访客会话历史
端点重放。因此脚本升级为 `v2`：除 10 个独立访客的 HTTP/SSE 完成、唯一 completed
Trace 和延迟外，还要求每个访客的 history 读取为 `403 GUEST_SESSION_HISTORY_DISABLED`，
并要求一个访客读取另一访客 Trace 为 404。

实际结果为 10/10 HTTP 200、10/10 SSE `done`、失败率 0、p50 99ms、p95 100ms、10 个
唯一 completed Trace、10/10 history 拒绝 403、跨访客 Trace 读取 404。仍只覆盖无外部
模型、无 RAG 的确定性高风险安全短路；不是临床 workflow、模型吞吐或千级容量结论。

## 2026-07-18：当前镜像的 10 并发用药审查工作流

证据文件：perf-medication-review-workflow-compose-2026-07-18.json

`apps/api/scripts/perf_medication_review_workflow.py` 在当前 Compose API 中为 10 个独立
访客创建独立身份、会话和已填充的合成用药审查 intake，然后仅并发计时
`medication-review-draft` 请求。脚本要求每次返回版本化 `medication-rules-v3`、至少一条
finding 和至少一个来源；还验证每条 Trace 为 completed，以及跨访客读取 intake 与 Trace
都为 404。机器报告不回显合成药物文本、会话 ID 或 Trace ID。

实际结果为 10/10 HTTP 200、失败率 0、p50 50ms、p95 53ms、10 个唯一 completed Trace；
10/10 均返回规则 finding 与来源。这只证明已安装、来源可追溯的确定性规则工作流在这条
有限路径上的并发、所有权和 Trace 行为；不构成临床正确性验证，也不代表 LLM/RAG、MinerU、
完整五大处方或千级容量结论。

## 2026-07-18：最新 Compose 源码重建后的复验

证据文件：perf-sse-safety-short-circuit-compose-2026-07-18-current.json、
perf-medication-review-workflow-compose-2026-07-18-current.json

在包含当前 Chat Turn Coordinator 的 Compose API 重新构建、迁移并通过 Docker
healthcheck 后，分别以最多 10 个独立访客重跑安全短路 SSE 与用药审查工作流。两份
报告均只含聚合指标，不含会话、Trace、身份或患者资料。

安全短路路径为 10/10 HTTP 200、10/10 SSE `done`、10 个唯一 completed Trace、失败率
0、p50 238ms、p95 240ms；10/10 访客 history 读取稳定返回 `403
GUEST_SESSION_HISTORY_DISABLED`，跨访客 Trace 读取为 404。用药审查路径为 10/10 HTTP
200、失败率 0、p50 46ms、p95 49ms；全部返回 `medication-rules-v3` 的 finding 与来源，
且跨访客 intake/Trace 均为 404。两项均为合成、确定性、无外部模型/RAG 的有限集成验证，
不构成临床正确性、MinerU/模型吞吐、完整五大处方或千级容量结论。
