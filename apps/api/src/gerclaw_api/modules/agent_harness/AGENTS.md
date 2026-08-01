# Agent Harness Module Instructions

## Responsibility

This module owns the production, one-turn AgentScope ReAct orchestration and safe SSE projection. It coordinates already-governed memory, RAG, search, Skill and document inputs; it is not a second source of truth for their data or authorization.

## Invariants

- A turn is tenant/actor/session/trace scoped, fenced by the session lease, and commits its terminal message and trace atomically.
- 医疗结论、风险判断和用药调整优先绑定本地知识、受治理联网搜索或当前用户上传资料的可追溯证据。证据入口不可用时仍必须继续生成可用回答，不得伪造 citation；应由模型结合当前上下文表达不确定性，并保留统一免责声明。没有 Runtime 标记的 citation 时，确定性诊断措辞必须改写；有证据时可保留结论，并在患者端整段末尾仅追加一次风险复核提示，医生端不作机械改写。红旗输入仍短路为紧急指引，统一免责声明始终生效。
- Never expose raw Chain-of-Thought, provider endpoints, credentials, or untrusted tool/document instructions. The public terminal contract may expose only the server-owned Provider adapter label, selected model display name and primary/backup slot; it must never expose URLs, keys, request headers or raw Provider payloads.
- Daily conversation prompts must not impose answer length, fixed presentation, or repeated self-review. Safety is enforced by evidence, policy and deterministic guards; default ReAct and retrieval limits prevent loops.
- `workflow=companion` is a policy-owned exception to medical retrieval: it has
  no long-term Memory, RAG, web search, Skill or uploaded-document context, but
  still runs deterministic high-risk short-circuiting before any model call.
- The concrete geriatric and companion Agent implementations must pass the
  server-owned `security_evaluation` profile gate before construction. Do not
  move this admission decision into prompts, browser code, or model output.

## Change and test rules

- Keep all external calls behind the Runtime governed toolkit and preserve fail-closed SSE terminal states.
- Root `harness.py` is a compatibility facade/composition entry. New route, plan, clinical
  state, snapshot, lifecycle, evidence, capability, or evolution logic belongs in its named
  component package and depends on Protocol/public contracts rather than concrete owners.
- Thresholds, limits, timeouts, retries, and candidate counts must enter through
  `Settings` → `ResolvedHarnessConfig`; component packages may not read environment variables.
- Prompt changes must retain evidence, emergency, privacy and injection boundaries; run `tests/test_agent_harness.py` and `tests/test_agent_harness_safety.py`.
- Re-run chat/session cancellation and contract tests for changes to lease, events, persistence or client-visible payloads.
