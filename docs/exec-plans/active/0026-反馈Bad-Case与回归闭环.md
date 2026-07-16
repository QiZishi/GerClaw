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

- 审核/运维专属的 Bad Case 队列、分诊、解决状态、受控 snapshot 查看和回归 golden case 需要 0025 的真实账号/RBAC；在此之前不暴露任何跨主体审计内容。
- 评测集版本、回放预算、模型/提示词/知识索引版本比较与安全 red-team 根据 Runtime Harness 版本绑定实现，不能把用户原文直接复制为 golden case。

## 验收

- [x] 完成聊天消息关联真实 trace，前端反馈只对该消息提交；没有 trace 或未完成的消息不显示入口。
- [x] 请求和响应严格校验；提交前持久化 idempotency key，网络错误不显示成功且可使用同一 key 重试。
- [x] 负反馈真实进入 Bad Case，且不向浏览器披露其他主体的 Trace/snapshot。
- [ ] 定向测试、前端 build、真实 Compose 浏览器路径和独立审阅通过（缺独立审阅）。

## 实现与验证记录（2026-07-16）

- SSE `done` 的服务端 `trace_id` 只写入完成态 assistant message；错误、取消与旧消息均不会获得反馈按钮。
- 前端通过 BFF 的 `POST /api/gerclaw/feedback` 提交 Zod 校验的 payload；响应也严格校验。按钮在请求中和成功后均不可重复操作，失败只显示可重试提示。
- 前端定向测试：`npm run test:feedback`（2 passed）；`npm run lint`、`npm run build`、`npm run test:audio`（6 passed）、`npm run test:document`（5 passed）、`npm run test:search`（4 passed）均通过。
- 后端真实依赖测试：在 Compose 网络的一次性容器中运行 `test_real_trace_feedback_bad_case_encryption_and_readiness_flow`，结果 `1 passed`；验证了负反馈幂等入库、Bad Case、租户隔离与加密快照。容器退出已自动删除。
- 浏览器在 `http://127.0.0.1:3048` 验证了失败响应不显示反馈入口；另以 transport mock 模拟一个合规的已完成 SSE，验证 trace 门槛、点踩弹窗、提交状态、禁用重复提交和请求 payload。该 mock 仅验证前端交互，不替代上述真实后端证据。
