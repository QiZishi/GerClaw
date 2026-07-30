# GerClaw NeurIPS 2026 Workshop Paper

Target: **Who Verifies the Agents? Toward Reliable Agent Development**,
NeurIPS 2026 Workshop.

- Submission type: 9-page systems/position paper (references begin on page 9)
  plus checklist
- Review: double blind
- Archival status: non-archival
- Official deadline: 2026-08-29 AoE
- Paper language: English
- Clinical status: pre-deployment research prototype; no clinical experiment

## Build

```bash
cd gerclaw-paper/paper
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

The compiled submission artifact is `paper/main.pdf`.  The LaTeX source uses
the official NeurIPS 2026 `dblblindworkshop` style and includes the required
checklist after references.

## Before submission

1. Replace the anonymous author block only after the double-blind review stage.
2. Obtain a human medical-language read and an engineering source audit.
3. Resolve repository licensing before promising an anonymized code release.
4. Upload the PDF only; internal source maps, prompts, review reports, and ARIS
   audit records are not anonymous supplemental material by default.
5. Recheck the workshop page and OpenReview form immediately before upload.

## Evidence boundary

The reported 40/40 result is an existing deterministic adjacent-policy
regression run.  It does not cover run finality or update admissibility.  It is
not a clinical experiment, has no sampled population, and does not measure
diagnostic accuracy, clinical safety, effectiveness, or clinician utility.
