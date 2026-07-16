# Built-in Skills Instructions

## Responsibility

This directory owns the reviewed, declarative Skill assets bundled with GerClaw. Each child directory represents one user-facing workflow and contains one versioned `SKILL.md`.

## Invariants

- Built-ins are Markdown/YAML data only: no executable scripts, shell commands, network endpoints, credentials or hidden prompts.
- Each asset declares only supported parameter types and allowlisted tools; medical facts, diagnosis and medication changes require the normal evidence and safety flow.
- Workflow instructions remain concise and action-oriented without forcing answer length, fixed display format or repeated model self-review for ordinary conversation.
- A built-in Skill cannot override Runtime permissions, document/memory trust boundaries, emergency handling or unified disclaimers.

## Change and test rules

- Change `id`, version and the asset-specific `AGENTS.md` deliberately; validate the complete file through the Skill loader and relevant Skill API tests.
- Keep patient-facing wording accessible, but let the caller choose sufficient answer detail rather than imposing arbitrary word limits.
