# Eval baseline module

This module starts the safe, deterministic portion of GerClaw's Eval Harness.
It executes reviewed synthetic safety cases against the same red-flag detector,
safety-decision contract, emergency public-output invariant, and deterministic
medical-output rewrite used by the Agent Harness. It has no database, model,
RAG, search, or provider dependency. The CLI emits only IDs and outcomes, never
the reviewed synthetic input or expected public text.

The same command also runs committed `privacy-redaction-case-v1` canaries for
the server-owned `1.1.0` external-search/TTS policies and the separate `1.0.0`
external-model-prompt projection. Their output contains only a case ID, purpose,
policy version and PHI-free category counts; it never contains source text,
expected redacted text, matching spans or credentials. They are deterministic
text-policy regression checks only. They do not measure OCR, ASR, free-form
structured fields, model-based detection, false-positive or false-negative
production rates, and therefore do not prove full PHI coverage.

`medication-rule-case-v1` adds six reviewed, synthetic cases that bind
`medication-rules-v4` findings to exact rule IDs and local source IDs. The
result never emits a medication list, patient attribute, rule text or source
content. It guards deterministic wiring and provenance only; it is not a
complete DDI/Beers/dose evaluation or clinical-validity evidence.

`skill-draft-case-v1` adds three reviewed, synthetic checks for the same
`skill-draft-quality-v1` checklist used to label generated and evolution
drafts for manual review. The CLI emits only a case ID, expected/actual
checklist codes and the quality version; it never emits instructions, user
requests or model output. Passing it does not assess medical validity or
publish a Skill.

`memory-extraction-case-v1` adds four reviewed, synthetic regressions for the
production `RealMemoryExtractor`: explicit self-report confirmation, negated
fact deactivation, other-subject rejection and unbound-entity rejection. It
uses an in-memory synthetic structured response and never calls a provider.
The CLI emits only a case ID plus category/status/action outcomes and the
guard version; it never emits input, entity, statement, evidence span or model
content. Passing it verifies these deterministic evidence guards only, not
clinical correctness or extraction-model quality.

`runtime-security-profile-case-v1` adds twelve content-free admission checks
for the production Agent, encrypted Memory and local RAG-source profile gates:
the reviewed profile admits, while version drift and removal of the execution
budget control reject. The CLI emits only an asset kind, case ID and allowed
outcome; it never emits profile controls, residual-risk wording, request data,
or user content. Passing it proves only this deterministic pre-enable gate, not
clinical validity, privacy completeness or model quality.

Run:

```bash
cd apps/api
uv run python -m gerclaw_api.modules.evals.cli
```

Bad Case records remain encrypted and tenant-scoped. They are not replayed
directly. A future authorised reviewer must create a new de-identified,
synthetic canonical case before it may be added here. This baseline therefore
does not expose user data or claim to evaluate LLM quality, medical validity,
retrieval quality, or capacity.

`run_opt_in_rag_retrieval_evaluation` is a separate, asynchronous path for a
reviewed synthetic RAG case set. The committed
`evals/rag-retrieval-reviewed-v1.json` currently contains five version-bound,
source-checked positive retrieval baselines spanning polypharmacy, falls,
frailty, cognition and stable coronary medication management, plus one
no-evidence baseline. It contains no patient or provider content. A reviewer
must still bind every new synthetic query to its expected local-corpus document
IDs (or explicitly require no evidence) and one index version; duplicate case
IDs are rejected. A positive case also rejects every returned result whose
citation provenance cannot locate its chunk (document ID, chunk ID, title,
chapter, category, source type and bounded chunk position); a reviewed case
may further require specific source types. The caller must pass
`allow_external_rag=True`, an index version, a top-k value and a maximum case
budget. Its report contains IDs, counts and outcomes only; it never emits
queries, retrieved text, source paths or model content. It is an
evidence-retrieval regression check, not a medical-validity or model-quality
claim.

For a real, cost-bearing run use the separate CLI, which refuses to execute
without an explicit opt-in:

```bash
cd apps/api
uv run gerclaw-eval-rag \
  --allow-external-rag \
  --cases evals/rag-retrieval-reviewed-v1.json \
  --index-version markdown-heading-v1:lexical-cjk-ngram-v2:BAAI/bge-m3:1024 \
  --top-k 5 --max-cases 8
```

The case file must be a `rag-retrieval-case-set-v1` JSON object with only
reviewed synthetic `RAGRetrievalEvalCase` entries. New corpus-specific expected
document IDs still require a reviewer to confirm the intended source and index
version first.

## 维护与演进

**可安全改进。** 只可将经审核、去标识化的合成 case 加入版本化 case set；可扩展到模型、OCR/ASR、规则和 RAG 评测，但先定义允许的输出字段、基线、reviewer 与失败处置。真实 Bad Case 必须先走授权的去标识化晋升，不能直接回放。

**不可破坏的契约。** CLI 输出不得包含原始输入、期望文本、PHI、prompt、规则正文或 provider 凭据；case ID 不是患者或 Trace ID。不得把 deterministic canary 通过表述为临床有效性、全量隐私覆盖或模型质量通过。

**性能与回归验收。** 新 case 集必须离线、确定、可重复，且固定版本/预期；CI 应在无数据库、无网络、无模型下完成。每次变更记录 case 总数、通过率和运行时；任何既有安全 case 回归失败必须阻断相关发布而不是更新期望值掩盖。

---

## 多维度评测框架（2026-08-17 新增）

### 概述

新增多维度评测框架，支持 5 个独立评分器，覆盖规则、证据、医学、性能、对话维度。

### 评分器

| 评分器 | 类型 | 职责 |
|--------|------|------|
| 规则评分器 | rule | 红旗短路、拒答/过度转诊、结构化输出 schema、用药规则 |
| 证据评分器 | evidence | 引用存在性、claim-证据匹配、无依据结论检测 |
| 医学评分器 | medical | 处方合理性抽检、药物相互作用、禁忌症 |
| 性能评分器 | performance | 延迟、token 成本、SSE 心跳与超时 |
| 对话评分器 | dialogue | 多轮一致性、追问完整性 |

### 数据隔离（审查报告 §6.2）

**硬性要求**：评测数据不与生产 Trace/PHI 混用。

- 所有测试用例从 `fixtures/*.json` 加载
- 绝对禁止在代码中直接连接生产数据库
- 所有测试数据为合成数据，不包含真实患者信息
- 环境隔离：运行时必须设置 `EVAL_MODE=true`

### fixtures 目录结构

```
evals/fixtures/
├── rule_cases.json          # 规则评分器用例
├── evidence_cases.json      # 证据评分器用例
├── medical_cases.json       # 医学评分器用例
├── performance_cases.json   # 性能评分器用例
├── dialogue_cases.json      # 对话评分器用例
├── memory_cases.json        # 记忆提取用例
└── rag_cases.json           # RAG检索用例
```

### CLI 一键运行

```bash
# 设置环境变量并运行
EVAL_MODE=true python -m gerclaw_api.modules.evals.run_eval

# 指定评分器
EVAL_MODE=true python run_eval.py --grader rule evidence

# 指定输出目录
EVAL_MODE=true python run_eval.py --output ./reports

# 跳过环境检查（仅用于测试）
python run_eval.py --skip-env-check
```

### 报告生成

运行后自动生成 JSON 和 Markdown 格式报告，存放于 `evals/reports/` 目录：

- `eval_report_YYYYMMDD_HHMMSS.json` - JSON 格式报告
- `eval_report_YYYYMMDD_HHMMSS.md` - Markdown 格式报告

报告内容包括：
- 总体通过率（加权或平均）
- 每个 Grader 的通过率
- 失败用例清单（含失败原因）

### 评测结果示例

| 评分器 | 通过率 | 平均分 |
|--------|--------|--------|
| 规则评分器 | 90.38% | 0.9712 |
| 证据评分器 | 26.92% | 0.6365 |
| 医学评分器 | 100.00% | 1.0000 |
| 性能评分器 | 100.00% | 1.0000 |
| 对话评分器 | 100.00% | 0.9077 |

### 审计检查清单

- [x] 数据源：所有测试用例从 `fixtures/*.json` 加载
- [x] PHI 脱敏：不包含真实患者信息
- [x] 环境隔离：`EVAL_MODE=TRUE` 检查
- [x] CLI 可重复：多次运行结果一致
- [x] 输出报告：包含 5 个 Grader 评分

---

## 文件清单

| 文件 | 说明 |
|------|------|
| `base_grader.py` | 评分器基类和数据结构 |
| `rule_grader.py` | 规则评分器 |
| `evidence_grader.py` | 证据评分器 |
| `medical_grader.py` | 医学评分器 |
| `performance_grader.py` | 性能评分器 |
| `dialogue_grader.py` | 对话评分器 |
| `evaluation_framework.py` | 评测框架主类 |
| `run_eval.py` | CLI 入口 |
| `fixtures/*.json` | 测试用例 |
| `reports/*.json` | 评测报告 |
| `AUDIT_CHECKLIST.md` | 审计检查清单 |
