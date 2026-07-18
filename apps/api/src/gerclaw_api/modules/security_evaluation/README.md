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

Every enabled Skill is also admitted immediately before AgentScope activation.
The server derives its exact profile from the already validated Skill ID,
SemVer and declared allowlisted tools; it rejects a profile/control mismatch
before the Skill viewer can be created. A `0.x.y` Skill SemVer is accepted as
an asset version without weakening the stricter released Runtime-policy
version contract.

This module still does not claim a completed application-wide threat model,
full red-team suite, clinical safety validation, or privacy/data-retention
lifecycle.

Run the focused checks from `apps/api`:

```bash
uv run pytest --no-cov -q tests/test_security_evaluation.py tests/test_runtime_registry.py
uv run ruff check src/gerclaw_api/modules/security_evaluation tests/test_security_evaluation.py
uv run mypy src/gerclaw_api/modules/security_evaluation
```

## 维护与演进

**可安全改进。** 核心功能稳定后可扩展受审查的 asset/profile、red-team case 和发布 gate；每个新控制项应能被运行时判定，不能只是说明文字。profile 版本升级须有兼容性、owner 和审阅记录。

**不可破坏的契约。** registry/profile 只能由服务端代码构造；浏览器、模型、Skill 和检索文本不得降低 risk、network、data class 或 control。此模块仅 admission gate，不得被误称为完整威胁建模、临床安全验证或隐私生命周期。

**性能与回归验收。** 运行 security-evaluation 与 runtime-registry 定向测试及 Ruff/Mypy；每个 profile 必测缺失、版本漂移、控制遗漏和合法接入。admission 应为无 I/O 的确定性快速路径；在 10 并发 toolkit/workflow 创建下无 profile 串用或非预期放行。
