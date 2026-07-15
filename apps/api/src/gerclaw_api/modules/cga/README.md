# CGA screening module

This module supplies versioned, deterministic geriatric screening scale definitions.  It does not diagnose, prescribe, or generate LLM interpretation.

## Supported server workflows

| Scale | Definition | Server scoring | Safety behavior |
| --- | --- | --- | --- |
| PHQ-9 | `phq9.py` | 0–27 total and PHQ-9 severity bands | A non-zero item 9 answer immediately asks for safety assessment; total ≥20 requests prompt clinical follow-up. |
| SAS | `sas.py` | 20 items, five reverse-scored items, raw score × 1.25 with half-up rounding | Standard score ≥60 requests prompt clinical follow-up; it is not an immediate self-harm signal. |

The state machine is implemented by `services/cga_service.py`, with encrypted answers and reports in `cga_assessments`.  It enforces owner/tenant scope, sequential server-selected questions, revision checks, idempotent same-answer retries, and completion only after every item has an allowed value.

## API contract

Authenticated callers use `GET /api/v1/cga/scales`, then start, read, answer, complete, and fetch a report under `/api/v1/cga/assessments`.  API Pydantic schemas live in `models.py`; the Next.js BFF validates the corresponding response/request shapes with Zod.  A report always includes a disclaimer and `score_max`; the PHQ-9 legacy default is retained so encrypted reports written before multi-scale support remain readable.

## Scope and limitations

The patient UI reads the server scale directory and supports separately recoverable PHQ-9 and SAS flows; it never renders the legacy static scale data as a source of truth.  PSQI, Mini-Cog, MMSE, clinician-authorized viewing, fatigue pause, historical comparison, and report export remain unimplemented.  All results are screening information and cannot replace clinical diagnosis or emergency care.
