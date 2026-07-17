# Workflows

`workflows` is the Runtime-facing registry for the workflows that production
Chat can execute. It is deliberately a registry, not a second workflow engine:
conversation persistence, leases, Trace and checkpoints remain owned by their
existing Runtime, service and repository layers.

## Registered workflows

| ID | Version | Owner | Context boundary |
|---|---:|---|---|
| `standard` | `1.0.0` | `agent_harness` | Skills and session documents allowed; governed search can be enabled |
| `cga` | `1.0.0` | `cga` | CGA assistance only; deterministic scoring stays in `cga` |
| `companion` | `1.0.0` | `companion` | No Skills, uploaded documents or search; no long-term health memory |

Every definition resolves through a matching active `security_evaluation`
workflow profile. A missing, blocked or mismatched profile fails closed before
Chat creates a Runtime execution.

## Limits

This registry does not make a clinical workflow executable by itself. Five
prescription, medication review and clinician approval workflows remain gated
on reviewed rules, patient authorization and medical governance.
