# Search 模块

`ProductionSearchModule` 是唯一联网搜索入口：AnySearch `/mcp` JSON-RPC 2.0 永远优先，瞬态失败最多重试一次，随后才降级 Tavily。两个 Provider 都返回严格 DTO；结果经过 HTTPS 校验、去重、S/A/B/C 权威分级和 D 级过滤。

查询在发送外部服务前会脱敏，Trace/日志仅保存 Provider、结果数、耗时和失败类别，不保存查询、摘要或正文。`extract_content` 只接受 DNS 解析后全部地址均属于公网的标准 443 HTTPS URL。

AgentScope 通过只读 `web_search` FunctionTool 复用同一模块。返回内容被 `<untrusted-web-evidence>` 包裹，只能作为可核验外部证据；本地 RAG 仍是医疗事实的第一证据来源。
