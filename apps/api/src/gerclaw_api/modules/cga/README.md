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

The patient UI reads the server scale directory and supports five separately recoverable flows; it never renders legacy static scale data as a source of truth. Mini-Cog and MMSE results explicitly state that they are based on the participant's responses, not automated drawing/action verification. PSQI item 5J's optional free-text detail is encrypted separately from numeric answers; it is never scored, listed in history, returned in the public report, or exported. Completed reports can be exported in Markdown, PDF, or editable DOCX from the same validated server report; all formats include an explicit medical disclaimer and omit raw answers. The caller can open their own bounded report history. Historical comparison is descriptive only: it never infers symptom improvement, diagnosis, or treatment need, and refuses a cross-version score comparison. A patient may authorize a doctor to read completed CGA report summaries; that grant does not expose raw answers, active assessments, conversations, files, or other patient data. Professional observation verification and a complete clinician workspace remain unimplemented. All results are screening information and cannot replace clinical diagnosis or emergency care.

## 维护与演进

**可安全改进。** 新量表必须以新的不可变定义版本加入，并补齐 server scoring、允许答案、报告、音频 manifest、API/Zod 契约和迁移回归；可改善题目导航、导出和专业观察工作流，但观察证据须有明确角色和审计策略。

**不可破坏的契约。** 已完成评估的定义版本、加密答案、顺序服务端选题和 revision 幂等语义不可原地改写；不得把 Mini-Cog/MMSE 自报答案伪称为图像/动作核验，也不得把 PSQI 5J 自由文本加入分数、历史、公共报告或导出。CGA 不启用联网搜索，医生读取只能是已完成摘要且受有效授权约束。

**性能与回归验收。** 每个量表应有逐题、重复提交、越权、完成、版本差异比较和报告导出回归；音频发布须校验 manifest SHA-256 与题目/版本一一对应。10 个并发独立 assessment 不得串答、重复完成或泄露答案；报告读取 p95 与导出耗时分别记录。
