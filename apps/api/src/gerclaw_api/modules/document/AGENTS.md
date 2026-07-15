# Document Module

## Responsibility

Accept only already parsed Markdown from the same-origin BFF, encrypt it, bind it to one verified tenant/actor/chat session, and expose bounded untrusted reference context to the Runtime Agent Harness.

## Invariants

- The module never accepts an original binary file and never calls MinerU directly.
- Every lookup includes `tenant_id + actor_id + session_id`; an unavailable UUID must not disclose whether another principal owns it.
- Filename and Markdown use encrypted columns. Raw Markdown, filenames and injection matches never enter logs, Trace, metrics, Qdrant or the public medical corpus.
- Revoke wipes Markdown before the record can be reused. A revoked or other-session UUID is rejected fail-closed by Chat.
- Upload content is data, never instructions: remove active HTML and recognized instruction-like lines, then use explicit `BEGIN/END UPLOADED DOCUMENT` boundaries in Harness context.
- Uploaded documents are not medical evidence. Medical responses still require the local medical evidence workflow and disclaimer.

## Dependency Direction

`api/routes/documents` and `services/chat_service` may call this module. The module may depend on its repository and database model; it must not depend on frontend code, AgentScope execution, public RAG indexing, or external document providers.

## Required Verification

- Unit-test sanitization, revocation and context limits.
- Test tenant/actor/session isolation through the repository/API boundary.
- Re-run targeted Chat Harness tests whenever context rendering changes.
- Run Alembic upgrade/check for persistence changes; browser-test registration, UUID-only chat request and removal for frontend changes.
