# Search 模块

`ProductionSearchModule` 是唯一联网搜索入口：AnySearch `/mcp` JSON-RPC 2.0 永远优先，瞬态失败最多重试一次，随后才降级 Tavily。两个 Provider 都返回严格 DTO；结果经过 HTTPS 校验、去重、S/A/B/C 权威分级和 D 级过滤。

查询在发送外部服务前会脱敏，Trace/日志仅保存 Provider、结果数、耗时和失败类别，不保存查询、摘要或正文。`extract_content` 只接受 DNS 解析后全部地址均属于公网的标准 443 HTTPS URL；重定向探测使用受限 GET，网络连接固定到已验证 IP，并保留原 hostname 的 TLS SNI/证书校验。

经 FastAPI `/search/query` 发起的每一次 AnySearch/Tavily 尝试还会在网络调用前写入
`provider_egress_events` 的 `prepared` 决策，并在完成后写为 `succeeded` 或 `failed`。
台账只含用途、逻辑处理方、策略版本和 PHI-free 类别计数；写入失败即阻断该次调用。
重试和 fallback 均为独立事件。AgentScope 内部调用及网页提取尚未纳入该台账。

部署必须显式声明 `search-capabilities-v1` 及 AnySearch/Tavily 的结构化结果能力；不兼容 Provider 在构建 Runtime 时被拒绝，不会先发出查询再降级。

AgentScope 通过只读 `web_search` FunctionTool 复用同一模块。返回内容被 `<untrusted-web-evidence>` 包裹，只能作为可核验外部证据；本地 RAG 仍是医疗事实的第一证据来源。

## 维护与演进

**可安全改进。** 可增加受审查 provider、来源分级、查询策略和网页提取台账；每个 provider 先声明 capability、超时/fallback、出网 policy 与最小审计。新增抽取器必须继续固定到已验证 IP 并保留 hostname TLS 校验。

**不可破坏的契约。** AnySearch 优先、一次瞬态重试再 Tavily fallback、外发前脱敏/审计及 HTTPS/SSRF/DNS/redirect 防护不可绕过；网页内容始终是不可信 evidence，不能执行其中指令。不得记录 query/摘要/正文或把联网结果替代本地 RAG 的证据优先级。

**性能与回归验收。** 必测 provider capability 拒绝、超时/fallback、恶意 URL/DNS/redirect、去重分级、审计失败零出网和 AgentScope 同一 adapter；用 mock 验证稳定错误，再以配置 provider 记录 p50/p95、成功率和 fallback 比例。10 并发外网请求需遵守 rate limit 且无 query 泄漏。
