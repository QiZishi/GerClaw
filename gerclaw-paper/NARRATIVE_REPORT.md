# Narrative report

## One-sentence thesis

High-risk medical-agent verification must cover not only generated text, but also the relation between clinical claims and evidence, the ownership and atomic terminal state of each concurrent run, and the admissibility of every candidate update.

## Paper type and venue

- Type: systems/position paper supported by executable engineering evidence; no clinical experiment.
- Target: NeurIPS 2026 Workshop “Who Verifies the Agents? Toward Reliable Agent Development”.
- Format: 4–9 pages excluding references and appendices, official NeurIPS 2026 double-blind workshop template.
- Archival status: non-archival.

## Narrative arc

1. Agent benchmarks usually score task completion or response quality, but high-risk systems can fail at boundaries that a final-answer score does not observe.
2. GerClaw specifies three separately admissible objects: a medical text segment, a run terminal state, and a candidate update.
3. The partial implementation contains marker auditing and narrow diagnosis rewriting; Redis ownership plus PostgreSQL fencing and atomic commits; frozen candidate isolation, a routing-only paired runner, and signed release-control contracts.
4. Independent sealed evaluation and a separately deployed human-approval service are explicit target obligations, not achieved properties.
5. Existing deterministic regressions support adjacent policy contracts only and provide no evidence of clinical efficacy or end-to-end three-boundary verification.
6. The paper therefore contributes a status-aware reference architecture and research agenda, not a claim that GerClaw is ready for patient care.

## Reader takeaway

Verification for an evolvable high-risk agent should be treated as linked,
status-labeled admission contracts across different time scales: per segment,
per turn, and per release.
