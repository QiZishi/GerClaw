# Citation audit

Audit date: 2026-07-30

Method: every bibliography entry was matched to a primary publication page,
publisher DOI record, official proceedings page, ACL Anthology, DBLP, or arXiv
record.  All 15 bibliography keys are cited in the paper, and every citation
key used by the paper exists in `references.bib`.

| Key | Verdict | Canonical verification | Context check |
|---|---|---|---|
| `yao2023react` | KEEP | ICLR/OpenReview `WE_vluYUL-X` | Supports interleaved reasoning and acting |
| `gao2024agentscope` | KEEP | arXiv `2402.14034`, arXiv DOI | Supports AgentScope platform description |
| `liu2024agentbench` | KEEP | Official ICLR 2024 proceedings | Supports interactive agent benchmarking |
| `ruan2024toolemu` | KEEP | DBLP `conf/iclr/RuanDWPZBDMH24`; ICLR 2024 | Supports LM-emulated sandbox risk testing |
| `debenedetti2024agentdojo` | KEEP | NeurIPS 2024 Datasets and Benchmarks/OpenReview `m1YYAQjO3w` | Supports utility/security evaluation over tool-mediated tasks |
| `lewis2020rag` | KEEP | Official NeurIPS 2020 proceedings | Supports retrieval-augmented generation |
| `gao2023alce` | KEEP | ACL Anthology `2023.emnlp-main.398`, DOI verified | Supports citation correctness/completeness as distinct dimensions |
| `jiang2025medagentbench` | KEEP | NEJM AI DOI `10.1056/AIdbp2500144` | Supports virtual-EHR medical-agent benchmarking |
| `vasey2022decide` | KEEP | Nature Medicine DOI `10.1038/s41591-022-01772-9` | Supports early-stage clinical evaluation and human-factors reporting |
| `liu2020consortai` | KEEP | Nature Medicine DOI `10.1038/s41591-020-1034-x` | Supports AI-intervention trial reporting, versions, inputs/outputs, and error analysis |
| `lekadir2025futureai` | KEEP | BMJ DOI `10.1136/bmj-2024-081554` | Supports lifecycle traceability, stakeholder engagement, privacy, and trustworthy deployment guidance |
| `gray1992transaction` | KEEP | Morgan Kaufmann book, ISBN `9781558601901` | Supports transaction-processing provenance; no novelty claim is assigned to atomic commit |
| `torresarias2019intoto` | KEEP | Official USENIX Security 2019 proceedings | Supports signed software supply-chain attestations |
| `breck2017mltestscore` | KEEP | IEEE Big Data 2017 DOI `10.1109/BigData.2017.8258038` | Supports ML production-readiness testing beyond predictive quality |
| `spriggs2012gsn` | KEEP | Springer DOI `10.1007/978-1-4471-2312-5` | Supports structured assurance claims, arguments, and evidence |

## Outcome

- Missing bibliography keys: 0
- Unused bibliography entries: 0
- Unresolved citations after BibTeX: 0
- Retracted or unverifiable sources found: 0
- Citation-context mismatches found: 0
- Final verdict: PASS
