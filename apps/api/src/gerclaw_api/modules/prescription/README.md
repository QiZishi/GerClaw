# Five-prescription intake

This is a fail-closed intake module for the future governed five-prescription workflow. It stores only caller-provided, minimum discussion context in an encrypted record. Medication-review collection is independently owned by `modules/medication_review/`. Neither module calls an LLM, RAG, web search, rules engine or clinical tool.

For the five-prescription intake, the caller may attach up to five already parsed, active documents from the same conversation. The intake stores only encrypted document IDs; the MinerU-extracted text remains in the private document store. A later medically governed report may resolve those IDs into its input template and display them as “上传资料依据” for traceability. They are never indexed into the public/local knowledge base and never satisfy the medical-evidence requirement on their own.

## State

- `collecting`: required server-defined fields are still absent.
- `information_complete_pending_governance`: required fields are present, but medical rules, patient authorization and physician-review workflow are not enabled. No clinical output exists in this state.

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
