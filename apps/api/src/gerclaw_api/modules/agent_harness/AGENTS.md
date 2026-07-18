# Agent Harness Module Instructions

## Responsibility

This module owns the production, one-turn AgentScope ReAct orchestration and safe SSE projection. It coordinates already-governed memory, RAG, search, Skill and document inputs; it is not a second source of truth for their data or authorization.

## Invariants

- A turn is tenant/actor/session/trace scoped, fenced by the session lease, and commits its terminal message and trace atomically.
- 医疗结论、风险判断和用药调整必须绑定本地知识、受治理联网搜索或当前用户上传资料的可追溯证据。若所有证据入口均不可用，必须返回不调用模型的补充信息提示，不得伪造 citation、诊断或用药指令。没有 Runtime 标记的 citation 时，直接临床结论必须改写；有证据时可保留结论，并在患者端整段末尾仅追加一次风险复核提示，医生端不作机械改写。红旗输入仍短路为紧急指引，统一免责声明始终生效。
- Never expose raw Chain-of-Thought, provider details, credentials, or untrusted tool/document instructions.
- Daily conversation prompts must not impose answer length, fixed presentation, or repeated self-review. Safety is enforced by evidence, policy and deterministic guards; default ReAct and retrieval limits prevent loops.
- `workflow=companion` is a policy-owned exception to medical retrieval: it has
  no long-term Memory, RAG, web search, Skill or uploaded-document context, but
  still runs deterministic high-risk short-circuiting before any model call.
- The concrete geriatric and companion Agent implementations must pass the
  server-owned `security_evaluation` profile gate before construction. Do not
  move this admission decision into prompts, browser code, or model output.

## Change and test rules

- Keep all external calls behind the Runtime governed toolkit and preserve fail-closed SSE terminal states.
- Prompt changes must retain evidence, emergency, privacy and injection boundaries; run `tests/test_agent_harness.py` and `tests/test_agent_harness_safety.py`.
- Re-run chat/session cancellation and contract tests for changes to lease, events, persistence or client-visible payloads.
