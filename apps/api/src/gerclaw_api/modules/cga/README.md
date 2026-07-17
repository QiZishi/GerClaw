# CGA screening module

This module supplies versioned, deterministic geriatric screening scale definitions.  It does not diagnose, prescribe, or generate LLM interpretation.

## Supported server workflows

| Scale | Definition | Server scoring | Safety behavior |
| --- | --- | --- | --- |
| PHQ-9 | `phq9.py` | 0–27 total and PHQ-9 severity bands | A non-zero item 9 answer immediately asks for safety assessment; total ≥20 requests prompt clinical follow-up. |
| SAS | `sas.py` | 20 items, five reverse-scored items, raw score × 1.25 with half-up rounding | Standard score ≥60 requests prompt clinical follow-up; it is not an immediate self-harm signal. |
| PSQI | `psqi.py` | 19 self-report items, seven component scores and a 0–21 total | Item 5J may retain an optional encrypted explanation outside scoring; high scores request clinical follow-up. |
| Mini-Cog | `minicog.py` | three-word recall plus the participant's reported paper-clock completion, 0–5 total | Positive screens request professional confirmation. The application does not analyse a drawing or claim clinician observation. |
| MMSE | `mmse.py` | education selection plus 30 reported standard items, 0–30 total | The education-adjusted source threshold is shown with the result; positive screens request professional confirmation. The application does not verify actions, handwriting, or drawings. |

The state machine is implemented by `services/cga_service.py`, with encrypted answers and reports in `cga_assessments`.  It enforces owner/tenant scope, sequential server-selected questions, revision checks, idempotent same-answer retries, and completion only after every item has an allowed value.

Start, answer and complete operations atomically create a PHI-free Runtime Trace. It contains only scale, definition version, operation, answer count and outcome; it never stores question IDs, scores, risk flags, notes, assessment IDs or request bodies.

## Version-bound audio release assets

The screening module remains network-free: it never calls TTS at request time.
apps/mvp/scripts/generate_cga_audio_assets.py is a release-time command that
reads these immutable public definitions and, after an explicit confirmation,
uses the configured TTS provider to create WAV files under
apps/mvp/public/audio/cga/. It emits a SHA-256 manifest and the generated
client manifest. The patient UI plays a file only if scale_id,
definition_version, and question_id all match the server response; a missing
matching asset falls back to the separately controlled live TTS accessibility
path. The generation command sends no patient data.

## API contract

Authenticated callers use `GET /api/v1/cga/scales`, then start, read, answer, complete, and fetch a report under `/api/v1/cga/assessments`. `GET /assessments/{id}/comparison` returns only the caller's immediately preceding completed result for the same scale, and calculates a delta only when both definition versions match. API Pydantic schemas live in `models.py`; the Next.js BFF validates the corresponding response/request shapes with Zod. A report always includes a disclaimer and `score_max`; the PHQ-9 legacy default is retained so encrypted reports written before multi-scale support remain readable.

## Scope and limitations

The patient UI reads the server scale directory and supports five separately recoverable flows; it never renders legacy static scale data as a source of truth. Mini-Cog and MMSE results explicitly state that they are based on the participant's responses, not automated drawing/action verification. PSQI item 5J's optional free-text detail is encrypted separately from numeric answers; it is never scored, listed in history, returned in the public report, or exported. Completed reports can be exported in Markdown, PDF, or editable DOCX from the same validated server report; all formats include an explicit medical disclaimer and omit raw answers. The caller can open their own bounded report history. Historical comparison is descriptive only: it never infers symptom improvement, diagnosis, or treatment need, and refuses a cross-version score comparison. Clinician-authorized cross-account viewing and fatigue pause remain unimplemented. All results are screening information and cannot replace clinical diagnosis or emergency care.
