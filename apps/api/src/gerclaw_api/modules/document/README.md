# Session-scoped document context

The Document module turns an already parsed Markdown result into a revocable, encrypted reference for one chat session. It deliberately does not implement a private vector database or an uploaded-document evidence corpus.

## Flow

1. The browser sends a file only to the Next.js MinerU BFF. Before the external MinerU submit call, that BFF resolves the same HttpOnly principal used by the GerClaw BFF and creates an owner-bound `external_document_parse` `prepared` audit decision. The API issues that decision only when the deployment explicitly declares `mineru-capabilities-v1` async parsing and Markdown export support; otherwise it returns 503 before provider egress. The PHI-free audit binds the declared capability version, never a filename, Markdown, size or page count, and is completed as `succeeded` or `failed` after the provider outcome. The BFF replaces the original filename with an opaque UUID-based name; the document bytes remain necessary parsing input.
2. The browser registers returned Markdown with `POST /api/v1/documents` through the GerClaw BFF.
3. FastAPI verifies the caller owns the target session, encrypts content and filename, and returns only a document UUID plus metadata.
4. Chat accepts that UUID only if its tenant, actor and session all match. The Harness renders the bounded body as JSON-encoded patient material, preserves its clinical text, and ignores only text that tries to change the task, permissions or tool execution.
5. Removing the attachment calls the revoke endpoint, which wipes the encrypted body and makes future chat use fail closed.

`resolve_context` makes truncation an explicit server-owned choice. Ordinary
chat may request a bounded excerpt; the five-prescription input assembler
passes `allow_truncation=False`, so a report, PDF or other extracted input can
never be silently treated as complete after clipping. This remains uploaded
patient evidence/provenance, distinct from (but usable alongside)
local-knowledge-base and governed-web evidence.

## Limits and non-goals

- Markdown registration is limited to 1,000,000 characters. The server-owned aggregate context budget is 273,000 characters; ordinary chat may use an explicitly bounded excerpt, while five-prescription input rejects any selected material that would not fit in full.
- No original binary is stored.
- No body or filename is persisted in browser storage, logs, Trace, Qdrant or the public local medical knowledge base.
- No cross-session library, physician access, vector retrieval, long-document retrieval, export, retention scheduler or malware scan exists yet.

The source of truth for delivered behavior and residual risk is [0024 MinerU 文档信任链](../../../../../../docs/exec-plans/completed/0024-MinerU文档信任链.md).

## 维护与演进

**可安全改进。** 可增加受控 MIME/恶意文件扫描、私有长文档检索、跨会话保留或医生授权；每项先定义数据所有者、删除/撤销语义、证据投影和独立索引边界。更换 MinerU adapter 时保留同源 BFF、owner-bound egress audit 与 UUID 注册契约。

**不可破坏的契约。** 上传资料是当前会话的患者输入和 evidence，不是公共知识库；tenant/actor/session 三重匹配、加密存储、撤销擦除和五大处方不可静默截断不能放宽。不得把原文件、文件名、Markdown 正文或图片字节写入日志、Trace、Qdrant 或浏览器持久化。

**性能与回归验收。** 必测 MinerU 成功/轮询失败、同会话解析登记、撤销后解析拒绝、跨主体拒绝和 273k/1M 字符边界；用既有病例 PDF 做真实解析烟测并记录 provider 耗时、字符数和失败码。长文档优化必须分别测 full-content five-prescription 输入和普通截断 chat 的 p95 与内存上限。
