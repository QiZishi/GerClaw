# Source–evidence map

This file is an internal authoring aid and is not part of the anonymous
submission.

| Paper claim | Primary source evidence | Qualification |
|---|---|---|
| GerClaw is a Web platform for older patients and geriatric clinicians | `docs/references/gerclaw设计要求.md:5-31` | Product requirement, not deployment evidence |
| Browser traffic crosses a server-only BFF before FastAPI/AgentScope | `ARCHITECTURE.md:18-45` | Current architecture description |
| A turn binds trace, lease, fencing, evidence, and an atomic terminal commit | `ARCHITECTURE.md:61-74`, `ARCHITECTURE.md:166-171`; `apps/api/src/gerclaw_api/modules/agent_harness/README.md:23-32` | Implemented runtime contract |
| The output path audits in-range current-turn markers and records bound/unbound medical segments | `apps/api/src/gerclaw_api/modules/agent_harness/evidence/markers.py:32-104`, `markers.py:125-161` | Structural marker binding only; no entailment |
| Unbound deterministic diagnosis assertions are rewritten | `apps/api/src/gerclaw_api/modules/agent_harness/safety.py:52-88`, `safety.py:156-204` | Narrow regex-defined class; general unbound clinical statements do not all fail closed |
| Red-flag inputs can bypass the model | `apps/api/src/gerclaw_api/modules/agent_harness/safety.py:90-125`; `apps/api/src/gerclaw_api/modules/agent_harness/README.md:25-32` | Six pattern codes; pattern-bounded, not comprehensive triage |
| Stale workers cannot commit a terminal state after lease takeover | `apps/api/src/gerclaw_api/modules/agent_harness/README.md:51-56`; `ARCHITECTURE.md:175-186` | Software invariant under documented datastore assumptions |
| Candidate code executes from a frozen bundle in a restricted container | `apps/evolution/README.md:15-34`; `apps/evolution/AGENTS.md:8-27` | Deployment identities and host controls remain operator responsibilities |
| The concrete paired runner evaluates only `routing.strategy` with four deterministic cases | `apps/evolution/src/gerclaw_evolution/runner.py:25-80`, `runner.py:126-219` | One case per normal/complex/high-risk/elderly slice; not a general medical-agent evaluation |
| Signed attestation and approval envelopes bind declared facts and exact artifacts | `apps/evolution/src/gerclaw_evolution/attestation.py:26-228`; `apps/evolution/src/gerclaw_evolution/approval.py:146-335` | Contracts/classes only; no hidden-case runner and no deployed independent approval service |
| Promotion and rollback use signed records and atomic Git reference updates | `apps/evolution/src/gerclaw_evolution/git_repository.py:21-174`; `apps/evolution/src/gerclaw_evolution/release.py:259-469` | Library contract; external audit mirror may require repair |
| Existing deterministic evaluation has 40 cases in seven adjacent policy families | `apps/api/src/gerclaw_api/modules/evals/cli.py`; `evidence/engineering_audit.json` | Does not cover run/update boundaries; external-model field is suite metadata |
| CGA, voice, and governed prescription flows are not yet unified under the Harness | `apps/api/src/gerclaw_api/modules/agent_harness/README.md:58-64` | Disclosed limitation |
| Overall system is not release complete | `docs/exec-plans/active/0035-Agent-Harness与对话工作台分阶段优化.md:29-40` | Active development |
