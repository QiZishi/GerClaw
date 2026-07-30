# Artifact manifest

## Submission deliverables

| Artifact | Purpose |
|---|---|
| `paper/main.pdf` | Current anonymous workshop PDF |
| `paper/main.tex` | LaTeX entry point |
| `paper/sections/01_introduction.tex` | Introduction and contributions |
| `paper/sections/02_related_work.tex` | Related work and verification gap |
| `paper/sections/03_verification_model.tex` | Three-boundary design contracts |
| `paper/sections/04_architecture.tex` | GerClaw architecture and figure integration |
| `paper/sections/05_engineering_evidence.tex` | Deterministic engineering evidence |
| `paper/sections/06_limitations_ethics.tex` | Limitations, ethics, and future evaluation |
| `paper/sections/07_conclusion.tex` | Conclusion |
| `paper/references.bib` | Audited bibliography |
| `paper/checklist_answers.tex` | Required NeurIPS checklist |
| `paper/neurips_2026.sty` | Official NeurIPS 2026 style |

## Figures

| Artifact | Purpose |
|---|---|
| `figures/fig1_system_overview.png` | System overview and three verification boundaries |
| `figures/fig2_claim_evidence.png` | Emergency branch, marker audit, and bounded diagnosis rewrite |
| `figures/fig3_transactional_run.png` | Lease, fencing, and terminal commit |
| `figures/fig4_offline_evolution.png` | Candidate isolation, routing-only evaluation, release contracts, and required authorities |
| `figures/prompts/*.txt` | Final image-generation prompts |

`figures/fig1_system_overview_draft.png` is a rejected draft retained only for
provenance; it is not referenced by the paper.

## Planning and evidence

| Artifact | Purpose |
|---|---|
| `NARRATIVE_REPORT.md` | Thesis and narrative arc |
| `PAPER_PLAN.md` | Contributions, sections, and scope |
| `PAPER_ACCEPTANCE_CONTRACT.md` | Claim and review gate |
| `SOURCE_EVIDENCE.md` | Internal claim-to-source map |
| `evidence/engineering_audit.json` | Machine-readable 40-case audit |
| `CITATION_AUDIT.md` | Bibliography existence and context audit |
| `PAPER_CLAIM_AUDIT.json` | Claim-to-evidence audit |
| `PROOF_AUDIT.json` | Not-applicable proof audit |
| `ANONYMITY_AUDIT.md` | Double-blind artifact audit |
| `ARIS_EXCEPTIONS.md` | User-requested reviewer and forensics adaptations |
| `reviews/` | Independent review and disposition |

Rendered page PNGs under `evidence/rendered-*` are local visual-inspection
artifacts and are not submission files.
