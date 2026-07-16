# Session-scoped document context

The Document module turns an already parsed Markdown result into a revocable, encrypted reference for one chat session. It deliberately does not implement a private vector database or an uploaded-document evidence corpus.

## Flow

1. The browser sends a file only to the Next.js MinerU BFF. Before the external MinerU submit call, that BFF replaces the original filename with an opaque UUID-based name and emits PHI-free outcome-only logs; the document bytes remain necessary parsing input.
2. The browser registers returned Markdown with `POST /api/v1/documents` through the GerClaw BFF.
3. FastAPI verifies the caller owns the target session, encrypts content and filename, and returns only a document UUID plus metadata.
4. Chat accepts that UUID only if its tenant, actor and session all match. The Harness renders the bounded body as a marked, untrusted reference.
5. Removing the attachment calls the revoke endpoint, which wipes the encrypted body and makes future chat use fail closed.

## Limits and non-goals

- Markdown registration is limited to 1,000,000 characters and direct Harness context is limited to 20,000 characters per turn.
- No original binary is stored.
- No body or filename is persisted in browser storage, logs, Trace, Qdrant or the public local medical knowledge base.
- No cross-session library, physician access, vector retrieval, long-document retrieval, export, retention scheduler or malware scan exists yet.

The source of truth for delivered behavior and residual risk is [0024 MinerU 文档信任链](../../../../../../docs/exec-plans/completed/0024-MinerU文档信任链.md).
