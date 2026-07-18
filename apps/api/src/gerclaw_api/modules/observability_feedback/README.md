# Observability feedback

`BadCaseSummary` is the operational feedback projection for the administrator
console. It receives only database-grouped source, severity, status and count
metadata, and returns queue totals such as open, high-priority and
negative-feedback counts.

`BadCaseTrend` adds a fixed seven-day series. PostgreSQL groups only calendar
day, source and count; missing days are emitted as zero. The administrator UI
therefore receives neither case IDs nor trace, feedback, snapshot or account
data when rendering the trend.

It never decrypts or exposes Bad Case snapshots, feedback text, image input,
trace input, document content or account identifiers. It does not replay real
cases or automatically promote them into Eval data.

## 维护与演进

**可安全改进。** 可增加经审查的聚合维度、趋势窗口和管理员处置指标；先确认每个字段是 PHI-free aggregate，且 BFF/UI 不会为方便展示回查 case 明细。Bad Case 晋升必须另走授权、去标识化与合成化流程。

**不可破坏的契约。** 本模块只消费 SQL 聚合，绝不解密 snapshot、读取反馈正文、图片、Trace、文档或账户标识；管理员状态更新不能重置其他查询状态或泄漏 case。不得将运营计数解释为临床质量或隐私合规通过。

**性能与回归验收。** 聚合查询需覆盖空集、连续七日补零、tenant 隔离、状态变更和严格响应字段；在大量 Bad Case 下用 EXPLAIN/索引与 p95 验证。管理员未认证访问必须稳定拒绝，10 并发读取不能触发明细加载或 N+1 查询。
