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
会话内持久化 assistant 消息，以及另一访客读取该会话返回 404。

结果为 10/10 HTTP 200 与 SSE done，失败率 0，端到端延迟 p50 为 153ms、
p95 为 154ms。这是安全短路的容器链路基线，不代表外部模型/RAG 吞吐、完整
临床 workflow 性能或千级并发能力。
