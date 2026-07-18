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
| `prescription` | `1.0.0` | `prescription` | Evidence-bound five-prescription draft; session documents allowed, Skills disallowed, clinician review required |

Every definition resolves through a matching active `security_evaluation`
workflow profile. A missing, blocked, mismatched or control-incomplete profile
fails closed before Chat creates a Runtime execution. Every workflow requires
schema, output-boundary, budget and untrusted-data controls; PHI workflows
also require patient ownership, external workflows require egress redaction,
and search-enabled workflows require evidence provenance.

## Limits

This registry does not make a clinical workflow executable by itself. The
registered five-prescription workflow can create only an evidence-bound,
clinician-review draft; it cannot create an executable prescription. Medication
review publication and clinician approval remain gated on reviewed rules,
patient authorization and medical governance.

## 维护与演进

**可安全改进。** 可注册新的 server-owned workflow 或升级现有版本；每个定义必须列明 owner、上下文允许项、风险 profile、预算和回退行为，并由对应 feature module 实现领域逻辑。持久化恢复/补偿应在 Runtime executor 完整后接入，而非在 registry 中临时实现。

**不可破坏的契约。** registry 不能成为第二个 workflow engine；缺失、blocked、版本/owner/风险/控制不匹配的 profile 必须在 Chat 创建前拒绝。不得将 `prescription` 或 `medication_review` 定义为可执行处方/自动临床批准，也不得让 companion 接收被禁用的上下文。

**性能与回归验收。** 每条 workflow 必测 profile admission、allowed/disallowed context、Trace version 绑定、预算和跨主体隔离；新增 workflow 要有 API/Harness 消费方回归。10 并发混合 workflow 不得共享 Toolkit、profile 或上下文；分别报告 admission 和执行 p95。
