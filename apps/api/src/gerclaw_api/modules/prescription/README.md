# Five-prescription intake

This module stores caller-provided minimum discussion context in an encrypted record and can generate one evidence-bound, clinician-review-only five-prescription draft. Medication-review collection is independently owned by `modules/medication_review/`.

For the five-prescription intake, the caller may attach up to ten already parsed, active documents from the same conversation. The intake stores only encrypted document IDs; the MinerU-extracted text remains in the private document store. The review-draft workflow resolves those IDs into its input template within the configured 273,000-character aggregate budget and displays their count as “上传资料依据” for traceability. Each resolved document is a same-session patient-material evidence source with its own evidence ID. It is never indexed into the public/local knowledge base or mislabeled as a local medical source; the model reads its clinical facts normally and ignores only text attempting to alter the task or execute an operation.

`ClinicalIntakeService.prepare_prescription_input` is the shared, private
`five-prescription-input-v1` assembly boundary. It resolves a completed
prescription intake's answers and selected documents again under the same
tenant/actor/session boundary. Documents must fit in the configured server-side
input ceiling **without truncation**; revoked, cross-session or oversized
material rejects the preparation. The owner-facing
`GET /clinical-intakes/{id}/prescription-input` route invokes this check but
returns only counts and the governance notice, never answer text, filenames,
document IDs or extracted bodies. It is not report generation and performs no
model, RAG, search or rule-engine call.

## Draft generation

`POST /api/v1/clinical-intakes/{intake_id}/prescription-draft` resolves the same
owner/session-scoped `five-prescription-input-v1`, rejects red-flag input,
retrieves local medical evidence, uses validated online-search results when
available, and binds same-session uploaded materials as patient evidence. It
then requests `GeneratedPrescriptionContent` from the configured structured
model and writes `evidence_sources` itself from those provenance records. The
model cannot supply source title, locator or document provenance. Local, web
and patient-material sources remain distinguishable in the output; an online
outage produces no invented web source. The result is always
`needs_clinician_review` and contains the fixed medical disclaimer.

The model projection is independently versioned as
`five-prescription-model-output-v1` and retained in the owner-visible report,
separate from `five-prescription-report-v1`. The chat-native intake extractor
requires `prescription-intake-model-output-v1`. Structured and plain-JSON
fallbacks both reject missing, stale, malformed or extra output fields through
the same strict contract; a generation formatting failure takes the existing
evidence-bound review baseline instead of blending unversioned provider data
into a report.

Each successful generation is retained as an encrypted draft revision, separate
from the PHI-free Runtime Trace. `GET
/api/v1/clinical-intakes/{intake_id}/prescription-drafts` returns at most the
twenty newest revisions, and its SQL boundary requires the same tenant and
actor that own the prescription intake. The browser restores only that caller's
newest draft into the report panel after the intake is reopened.

The authenticated generic session list exposes only the owner-scoped boolean
`has_prescription_draft`. This lets the web client re-open the corresponding
chat-native intake after a new login, while all report content, intake answers,
patient materials and clinician feedback remain available solely through the
existing owner-scoped prescription routes.

Before execution the route resolves the versioned Runtime workflow
`prescription@1.0.0` and its `security.workflow.prescription` profile. The
workflow allows its bounded, owner-scoped uploaded input but rejects Skills;
it has a 600-second configurable end-to-end budget while each model candidate
retains its independent 180-second deadline. A budget failure is a safe draft
failure, never an incomplete report.

Uploaded MinerU text is passed as bounded, untrusted patient input and appears
only as owner-visible uploaded-document provenance. It never becomes a local
knowledge-base citation. If RAG has no evidence, the endpoint fails closed.

When the caller provides a current medication list, the server attaches the
separate, deterministic `medication-rules-v4` result after model generation.
It has limited source-traceable DDI/dose/duplicate/polypharmacy coverage and a
narrowly qualified Beers-related signal; it remains pending clinical governance
and cannot be presented as a complete medication review. The model may record
a user-provided dose and propose a start, stop, replacement or dose change only
in a cited recommendation. If a model projection references an unknown evidence
ID or places an affirmative medication action in an uncited free-text field, the
server discards that projection and returns an explicit evidence-bound,
review-only baseline instead of returning a late 503. Negative safety wording
such as “涉及停用或减量时，请结合相应证据和完整病史复核” remains visible and is not
misclassified as a proposal.
Both roles receive the complete cited candidate; the report ends with one unified
risk notice. The model cannot create, override or explain deterministic rule findings.

## State

- `collecting`: required server-defined fields are still absent.
- `information_complete_pending_governance`: required fields are present. A source-bound `needs_clinician_review` draft can be generated, but it is not a physician-approved or executable clinical output.

## Boundaries

The module depends on its repository and encrypted database model only. Routes verify identity, session ownership and rate limits. The Runtime Harness and later approved clinical workflow may consume a validated snapshot only after the missing medical governance requirements are implemented.

Write operations also emit an atomic, PHI-free Runtime Trace. The trace contains only the intake kind, definition version, answer/document counts, operation and result status; it never stores answer text, filenames or uploaded-document identifiers.

## 通用报告契约

`models.FivePrescriptionDraft` 是 `five-prescription-report-v1` 的严格、仅供
审核的报告结构：药物、运动、营养、心理、康复五章均为必填；每项建议和章节必须
引用同一报告中的可解析循证 ID，康复章强制包含康复类型、功能评估、训练计划、
辅助器具与安全注意事项。报告固定附带医疗免责声明，药物与心理章节固定要求临床
复核。

该契约只固化 `docs/references/五大处方报告模板.md` 的**通用结构**。其中的原始
心脏康复案例、药名、剂量和数值从不作为默认值、生成示例或规则来源。没有经审核的
医学规则、证据、授权和医生审核流程时，任何草案只能是 `needs_medical_governance`
或 `needs_clinician_review`，不能向患者发布、更不能视为可执行处方。

`needs_medical_governance` 的通用草案不得携带 `uploaded_document_ids`：该状态尚未
经过 owner/session-bound 的文档再次解析，不能用任意 UUID 声称患者资料 provenance。
只有服务端从完整私有输入构建的 `needs_clinician_review` 草案才能绑定同会话上传资料
及其独立 evidence ID。
