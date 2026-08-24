# GerClaw

English | [中文](README.zh.md)

GerClaw is a private, account-isolated health workspace built on DeepSeek Harness. It combines conversational health assistance, five-part care-plan drafting, deterministic CGA scoring, medication review, chronic-condition tracking, local medical RAG, document parsing, and downloadable reports in one patient- and clinician-friendly interface.

> GerClaw supports health information organization and clinical review. It does not replace diagnosis, treatment, prescriptions, emergency services, or professional judgment.

## Run

Requirements: Node.js 24+, pnpm 10+, and a populated root `.env`.

## Run from source

```bash
pnpm install
pnpm build:lib:host
pnpm gerclaw
```

Open <http://127.0.0.1:3000>. The launcher reads only the repository-root `.env`; it reports missing variable names without printing values.

Use `pnpm gerclaw:dump-config` to verify the real Loader composition. For non-localhost microphone access, place the service behind a trusted HTTPS reverse proxy.

## Product features

- Account registration, login, recovery, guest sessions, and per-account DSH Hosts.
- Native DSH sessions, workspace, files, artifacts, Memory, tools, Plan, and Goal.
- GerClaw system prompt and four callable skills: follow-up questionnaire, risk assessment, health education, and medication reminder.
- Five-part prescription reports: medication, exercise, nutrition, psychological, and rehabilitation guidance.
- Deterministic PHQ-9, SAS, PSQI, Mini-Cog, and MMSE scoring.
- Source-traceable medication rules, structured health profiles, chronic measurements, risk alerts, and companion conversations.
- Qianwen realtime ASR and streaming TTS inside the chat composer; raw audio is never persisted.
- The copied `knowledge-base/` corpus, SiliconFlow embedding/rerank, `dsh-library`, MinerU document parsing, PubMed, openFDA, and MedlinePlus.
- Markdown, HTML, DOCX, PDF, PNG, JPG, and JSON exports.

## Architecture

`@gerclaw/launcher` starts the account gateway through the real DSH Web Loader. The gateway creates one loopback child Host per account or guest. Each child Host loads `packages/gerclaw/profile-bundle/cordis.patch.yml`, which disables the default system prompt and developer-facing Web UI, mounts GerClaw plugins, and retains native runtime services.

Every registered account owns a separate `DSH_HOME`, workspace, session log, SQLite storage, Memorix directory, uploaded files, local indexes, and artifacts. The gateway authenticates and proxies requests but does not read medical content. Doctor and patient preferences change wording only; all capabilities are identical.

## Configuration

Copy variable names from `.env.example` into the existing root `.env`.

| Area | Variables |
| --- | --- |
| Primary model | `AGENT_PRIMARY_API_KEY`, `AGENT_PRIMARY_URL`, `AGENT_PRIMARY_MODEL` |
| Qianwen ASR | `MODEL_ASR_KEY`, `MODEL_ASR_URL`, `ASR_MODEL` |
| Qianwen TTS | `MODEL_TTS_KEY`, `MODEL_TTS_URL`, `TTS_MODEL` |
| Local RAG | `SILICONFLOW_API_KEY`, `SILICONFLOW_URL`, `EMBEDDING_MODEL`, `RERANK_MODEL` |
| MinerU | `MINERU_API_KEY`, `MINERU_URL` |

`ASR_MODEL` is `qwen3-asr-flash-realtime`; `TTS_MODEL` is `qwen3-tts-instruct-flash-realtime`. SiliconFlow variables are used only for embedding and rerank, never for speech.

## Medical knowledge base

`knowledge-base/` is the verified copy of `gerclaw-main-codex/knowledge-base`. On account startup the gateway copies only missing files to the account data directory and rejects conflicting content. `@gerclaw/local-rag` indexes every Markdown/text source with source-preserving shards, SiliconFlow embeddings, and rerank. Search results retain the original relative file path and chunk number.

To update the corpus, add or replace source files in `knowledge-base/` intentionally, then start a fresh account index or change the configured library version after reviewing the source diff. Do not edit an account's generated index directly.

## GerClaw plugins

| Plugin | Location | Responsibility |
| --- | --- | --- |
| Business app | `packages/gerclaw/client` | Typed business API, task/session events, exports |
| Product client | `packages/gerclaw/client-ui` | Native chat theme, medical entries, task cards, artifact sidebar |
| CGA | `packages/gerclaw/cga` | Five deterministic assessments |
| Chronic care | `packages/gerclaw/chronic-care` | Measurements and trends |
| Companion | `packages/gerclaw/companion` | Supportive mode and urgent-signal detection |
| Health profile | `packages/gerclaw/health-profile` | Structured authoritative health profile |
| Local RAG | `packages/gerclaw/local-rag` | Copied corpus and personal-document retrieval |
| Medical evidence | `packages/gerclaw/medical-evidence` | PubMed, openFDA, MedlinePlus providers |
| Medication review | `packages/gerclaw/medication-review` | DDI, dose, duplicate, polypharmacy, Beers signals |
| Prescription | `packages/gerclaw/prescription` | Evidence-bound five-part report |
| Risk alert | `packages/gerclaw/risk-alert` | Unified deterministic alerts |
| Skills | `packages/gerclaw/skills` | Four GerClaw DSH skills |
| System prompt | `packages/gerclaw/system-prompt` | GerClaw-only model instructions |
| Voice | `packages/gerclaw/voice` | Chat ASR/TTS bridge |
| Profile bundle | `packages/gerclaw/profile-bundle` | Real Cordis Loader composition |
| Tenant gateway | `packages/gerclaw/tenant-gateway` | Authentication, isolation, child Hosts |
| Launcher | `packages/gerclaw/launcher` | Environment validation and startup |

Each directory contains a developer README describing services, events, persistence, lifecycle, extension points, and tests.

## Verification

```bash
pnpm gerclaw:dump-config
pnpm test
pnpm typecheck
pnpm lint
pnpm build
pnpm docs:check
pnpm check:all
```

Final user acceptance must be performed through the GerClaw browser surface, including Qianwen speech, the primary model, local RAG, MinerU, all CGA forms, exports, account isolation, responsive layouts, and teardown.

## Repository layout

```text
knowledge-base/
packages/gerclaw/
apps/cli/
packages/
.env.example
icon.png
```

## Medical use boundary

GerClaw's prescription, assessment, medication-review, risk, and companion outputs remain decision-support material. Severe signals prompt immediate help, but do not add clinician/patient role gates, approval chains, or feature restrictions. Starting, stopping, or changing medication requires professional review using the complete clinical context.

## License and third-party notices

The DSH baseline retains its original license. Derived voice code records its `dsh-talk@0.1.3` and `dsh-speech-plugin` origins in `packages/gerclaw/voice/NOTICE` and `LICENSES/`. Community packages retain their upstream licenses and locked versions.
