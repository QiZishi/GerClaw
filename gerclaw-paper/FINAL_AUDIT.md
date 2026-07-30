# Final submission audit

Audit date: 2026-07-30

## Build

- Command: `latexmk -g -pdf -interaction=nonstopmode -halt-on-error main.tex`
- Result: PASS
- Total PDF pages: 13
- Main-paper span: pages 1–9; references begin on page 9
- Checklist begins on page 10
- Undefined citations/references: 0
- Overfull boxes: 0
- Duplicate PDF destinations: 0

## Bibliography and claims

- Bibliography entries: 15
- Unique cited keys: 15
- Claim audit verdict: `PASS_AFTER_SCOPE_NARROWING`
- Proof audit: `NOT_APPLICABLE`
- Clinical experiment: none
- 40/40 interpretation: adjacent deterministic policy checks only; not run,
  update, or clinical evidence

## Anonymous artifact

- Author metadata: empty
- Identifying name, email, repository URL, and local path scan: no match
- Fonts: all embedded
- Encryption: none
- Final artifact:
  `GerClaw_NeurIPS2026_Workshop_Anonymous.pdf`
- SHA-256:
  `fbd2e97dab5015852e088a7a3a45f1ffa2729d7167851602585046f4259f4970`

## Figure provenance

All four embedded figures are image-generation outputs.  Final prompt files
are retained under `figures/prompts/`; the source generator originals remain
in the local Codex generated-images store.  Figures 1, 2, and 4 were regenerated
after independent review to remove serial-pipeline, clinical-safety, and
deployed-authority implications.

## Process exception

Per user instruction, no Claude reviewer or Claude-dependent integrity
forensics was used.  One independent Codex child reviewer performed the
substantive review and final re-review.  Its original Reject, author
disposition, final Weak Accept, and the last figure correction are preserved
under `reviews/`.
