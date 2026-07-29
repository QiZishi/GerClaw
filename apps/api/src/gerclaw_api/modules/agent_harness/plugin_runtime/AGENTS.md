# Plugin Runtime Instructions

Owns governed capability manifests, selection boundaries, and reusable result references.
It never reimplements CGA, medication review, prescription, report, Runtime, RAG, or Skill.

Only allowlisted manifests may execute. Validate input/output at the boundary, respect
Runtime permissions and risk levels, and reuse actor/session-scoped results. Never load
arbitrary Python, remote code, prompts, or sibling-project paths.

Run capability manifest, Runtime permission, workflow registry, and shared-result tests.
