# Companion

`companion` supplies the policy for the `workflow=companion` Chat mode. The
mode reuses the production Chat transaction, SSE, tenant/actor/session
isolation and deterministic red-flag safety checks, while removing long-term
health Memory, RAG, web search, Skills and uploaded documents from the model
context.

It is deliberately a limited backend baseline: a supportive AI may listen and
respond respectfully, but cannot present itself as human, promise to remain or
contact someone, create dependency, make clinical conclusions or substitute
for professional or emergency support. The existing red-flag short-circuit
remains authoritative. A user-configurable companion-memory preference,
human escalation and doctor authorization are not implemented.

## Patient entry

The patient welcome page exposes **暖心陪伴**. Entering it starts a fresh local
conversation and sends `workflow=companion` with empty Skill and document
lists. The UI hides image, document and Skill controls and explains that only
the current conversation is used. This is defense in depth; the API contract
still rejects non-empty Skill or upload context.

## 维护与演进

**可安全改进。** 可优化陪伴提示语、增加用户可选择的会话内偏好和人工求助入口；新增能力应先明确是否保存、是否可见、是否由人工接管，并用独立 workflow version 和 profile 声明。

**不可破坏的契约。** `companion` 必须保持无长期健康 Memory、RAG、联网搜索、Skill 和上传资料的上下文；红旗短路不能被陪伴语气或模型 fallback 覆盖。不得把陪伴实现为依赖性诱导、承诺联系、冒充人类或医疗诊断。

**性能与回归验收。** 回归须断言新会话的 workflow、Skill/document 列表和长期记忆上下文均为空，并覆盖红旗短路与 provider 失败的稳定用户态。10 并发陪伴会话必须无跨会话文本、历史或 Trace 复用；模型回复和安全短路延迟分开统计。
