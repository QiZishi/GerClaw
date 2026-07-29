# Context Snapshot Instructions

Owns the immutable, bounded input contract for one Agent turn. It does not fetch Memory,
documents, conversation rows, or profiles.

Every field crossing into the Harness must be actor/tenant scoped and validated before
construction. Never add raw credentials, provider payloads, unrestricted PHI, private
reasoning, or unbounded history. Unknown and absent data must remain distinguishable.

Consumers may depend on these models; this package must depend only on public domain
contracts. Run Harness and context contract tests after changes.
