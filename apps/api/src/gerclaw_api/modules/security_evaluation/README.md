# Security Evaluation Module

`security_evaluation` is the executable security-risk admission gate for
Runtime assets. It uses strict Pydantic contracts and contains no patient data,
model calls, provider calls, database writes or browser endpoint.

## Current production scope

The Chat Harness creates a request-local `SecurityProfileRegistry` before it
builds the governed AgentScope toolkit. Three actual tools have reviewed
`security-risk-profile-v1` records:

| Tool | Bound Runtime properties | Required additional controls |
|---|---|---|
| `search_knowledge` | `1.0.0`, low risk, internal, `INTERNAL` | untrusted-data isolation, evidence provenance |
| `search_memory` | `1.0.0`, low risk, internal, `PHI`, patient-scoped | patient ownership |
| `web_search` | `1.0.0`, medium risk, external, `INTERNAL` | evidence provenance, server redaction proof |

Registration rejects a missing, blocked or incompatible profile. Toolkit build
also rejects external tools unless the existing Runtime call declares the
server-owned outbound-redaction proof. This complements, rather than replaces,
the Runtime permission engine, schema/size limits, timeout, budget and
AgentScope permission checks.

The workflow registry uses the same gate for `standard`, `cga`, `companion`
and `prescription`. In addition to matching profile identity and asset fields,
workflow admission now verifies executable controls: every workflow needs
input/output/budget/untrusted-data controls; PHI workflows need ownership;
external workflows need egress redaction; and search-enabled workflows need
evidence provenance. A matching profile that omits any applicable control
fails closed before Chat constructs a Runtime execution.

The server also admits the actual `gerclaw_geriatric_specialist` and
`gerclaw_emotional_companion` Agents, encrypted `health_memory`, and
`local_medical_corpus` before their constructors expose them to a request. The
medical Agent requires ownership, egress-redaction and evidence-provenance
controls; companion requires egress redaction; Memory requires ownership; and
the local corpus requires evidence provenance. These checks use server-owned
versioned profiles and cannot be supplied or weakened by a browser, model,
Skill, or retrieved text.

## Contract and limits

`SecurityRiskProfile` binds an asset kind/name/version, owner module, risk,
network access, data classes, bounded threat categories, executable controls
and residual-risk statement. `SecurityEvaluationVerdict` is PHI-free and is
only an in-process admission result.

The contract can also describe Skill profiles, but Skills are **not yet
consumed by a production registration path**. This module therefore does not
claim a completed application-wide threat model, full red-team suite, clinical
safety validation, or privacy/data-retention lifecycle.

Run the focused checks from `apps/api`:

```bash
uv run pytest --no-cov -q tests/test_security_evaluation.py tests/test_runtime_registry.py
uv run ruff check src/gerclaw_api/modules/security_evaluation tests/test_security_evaluation.py
uv run mypy src/gerclaw_api/modules/security_evaluation
```
