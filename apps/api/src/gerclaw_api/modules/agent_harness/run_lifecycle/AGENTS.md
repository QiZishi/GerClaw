# Run Lifecycle Instructions

Owns typed Harness failures and public-stream normalization. It does not own database
transactions, leases, traces, conversations, or SSE transport.

Trust boundary: accept only already validated text and evidence-presence callbacks.
Never expose provider payloads, credentials, private reasoning, or partial unsafe medical
sentences. Preserve a single public terminal outcome and cancellation idempotency.

Inputs are bounded text deltas and validated lifecycle commands; outputs are safe public
text fragments or stable typed errors. Do not import concrete Runtime, Memory, RAG, Search,
Skill, Workflow, or persistence implementations.

Run `tests/test_agent_harness.py`, `tests/test_agent_harness_safety.py`, and
`tests/test_chat_cancellation.py` after changes.
