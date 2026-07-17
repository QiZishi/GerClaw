# 0026 — 反馈、Bad Case 与回归闭环

> 创建：2026-07-16 | 优先级：P0 | 状态：待独立审阅 | 前置：0014 Trace、0016 SSE、0021 Runtime Harness

## 目标

让用户对真实聊天执行提交的正/负反馈可靠进入服务端 Trace 链路；负反馈和执行失败自动产生 tenant-scoped Bad Case。前端不得把 localStorage 图标状态冒充已提交反馈，反馈不得包含未经校验的 PHI 或模型隐藏推理。

## 阶段 A：真实反馈纵切面

- 将服务端 SSE `trace_id` 绑定到完成的前端 assistant 消息。
- 以 Zod 验证的 `POST /feedback` 提交含稳定 idempotency key 的正/负反馈；网络失败保留原 key 供用户安全重试。
- 没有真实 trace 的历史/mock 消息不显示反馈入口；提交后明确终态，不重复伪造本地成功。
- 验证 actor/tenant 所有权、幂等、负反馈 Bad Case、PHI 脱敏和前端浏览器路径。

## 后续范围

- 管理员已可经服务端 `account:admin` scope 读取最多 100 条同 tenant 的 PHI-free Bad Case 元数据并把状态更新为 open/triaged/resolved/dismissed；API 与管理员前端队列均不返回加密 snapshot、用户评论或原始输入。2026-07-18 已在 Compose 真实浏览器会话中验证队列加载与状态更新。受控 snapshot 查看和人工去标识化为 golden case 仍待接入。
- 评测集版本、回放预算、模型/提示词/知识索引版本比较与安全 red-team 根据 Runtime Harness 版本绑定实现，不能把用户原文直接复制为 golden case。

## 阶段 B：可重复的 ≤10 并发性能证据

- 在健康的 Docker Compose API、PostgreSQL、Redis、Qdrant 上，以最多 10 个并发会话执行受控、无外部模型成本的安全短路 SSE 路径；每个会话必须独立创建、写入并完成 Trace。
- 报告请求总延迟 p50/p95、失败率、HTTP/SSE 终态、Trace 唯一性、会话消息写入与跨会话隔离。不得把该安全短路工作负载表述为真实 LLM/RAG 吞吐或千级容量证明。
- 复用的性能脚本必须有硬性并发上限 10、超时、结构化 JSON 输出和失败非零退出；任何外部模型/RAG 基准另设 opt-in 运行方式，避免意外成本和不稳定结果。

## 验收

- [x] 完成聊天消息关联真实 trace，前端反馈只对该消息提交；没有 trace 或未完成的消息不显示入口。
- [x] 请求和响应严格校验；提交前持久化 idempotency key，网络错误不显示成功且可使用同一 key 重试。
- [x] 负反馈真实进入 Bad Case，且不向浏览器披露其他主体的 Trace/snapshot。
- [ ] 定向测试、前端 build、真实 Compose 浏览器路径和独立审阅通过（缺独立审阅）。
- [x] 在真实 Compose 依赖上保留可重复的 ≤10 并发性能报告；该报告只覆盖已声明工作负载，不能代替临床 workflow、外部模型或千级容量验收。

## 实现与验证记录（2026-07-16）

- SSE `done` 的服务端 `trace_id` 只写入完成态 assistant message；错误、取消与旧消息均不会获得反馈按钮。
- 前端通过 BFF 的 `POST /api/gerclaw/feedback` 提交 Zod 校验的 payload；响应也严格校验。按钮在请求中和成功后均不可重复操作，失败只显示可重试提示。
- 前端定向测试：`npm run test:feedback`（2 passed）；`npm run lint`、`npm run build`、`npm run test:audio`（6 passed）、`npm run test:document`（5 passed）、`npm run test:search`（4 passed）均通过。
- 后端真实依赖测试：在 Compose 网络的一次性容器中运行 `test_real_trace_feedback_bad_case_encryption_and_readiness_flow`，结果 `1 passed`；验证了负反馈幂等入库、Bad Case、租户隔离与加密快照。容器退出已自动删除。
- 2026-07-18：管理员队列查询与状态更新均显式延迟数据库 `snapshot` 列，防止历史加密快照在密钥轮换后不可读时使 PHI-free 队列 500；隔离 Compose 测试以不可读的合成密文验证仍可读取并更新，结果 `1 passed`。随后在实际 Compose 浏览器会话中登录临时管理员，队列加载成功并将一条项目由 `open` 更新为 `triaged`（BFF PATCH 200）；测试账号与会话已精确清理。
- 浏览器在 `http://127.0.0.1:3048` 验证了失败响应不显示反馈入口；另以 transport mock 模拟一个合规的已完成 SSE，验证 trace 门槛、点踩弹窗、提交状态、禁用重复提交和请求 payload。模拟 `503` 时弹窗保留、按钮仍可用且仅显示可重试提示。该 mock 仅验证前端交互，不替代上述真实后端证据。
- 2026-07-17：新增受版本绑定的合成 RAG 检索用例 `apps/api/evals/rag-retrieval-reviewed-v1.json`。默认 Eval 仍不会调用外部服务；仅以 `--allow-external-rag` 明确 opt-in 后，才使用当前 immutable index `markdown-heading-v1:lexical-cjk-ngram-v1:BAAI/bge-m3:1024` 执行 embedding 与 rerank。Compose 真实运行 1 个公共、合成多重用药安全问题，top-3 中预期文献命中 1/1；机器报告不回显 query、正文或检索来源。该结果只证明这条检索回归契约，不代表医学正确性、模型质量、临床 workflow 或性能容量。
- 2026-07-17：用 `apps/api/scripts/perf_sse_safety_short_circuit.py` 在当前 Compose API 重跑 10 并发确定性安全短路。10/10 HTTP 200 与 SSE `done`，失败率 0，p50 114ms、p95 115ms；每个会话的 completed Trace、持久化 assistant 消息和跨访客 404 都由脚本复核。原始 PHI-free JSON 已保存至 `docs/evidence/perf-sse-safety-short-circuit-compose-2026-07-17.json`。这不是模型、RAG、临床 workflow 或千级容量基准。
- 2026-07-18：新增 `docs/design-docs/容量与扩展计划.md`，将 1,000 活跃会话的目标落实为无状态 BFF/API、Redis owner lease、有界 SSE 队列、分 lane 资源预算、Provider/数据层背压和 10→1,000 的阶梯压测/故障注入门槛。它明确保留目前仅有 10 并发安全短路的真实证据，未将设计或 Docker Compose 误表述为千级压测通过。
