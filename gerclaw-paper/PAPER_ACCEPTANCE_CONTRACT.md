# Paper acceptance contract

## Venue fit

The paper must directly address runtime verification, heterogeneous verification signals, human-in-the-loop verification, and stable evolution of agent systems.

## Required claims

- The paper defines three verification boundaries: claim, run, and update.
- Every implementation statement is supported by a named source module, contract, or test.
- The 40/40 result is described only as a deterministic engineering regression result.
- The abstract, introduction, limitations, and conclusion explicitly state that no clinical evaluation was performed.
- The current integration gaps for CGA, voice, and governed prescriptions are disclosed.
- The claim path is described as marker auditing plus narrow diagnosis-pattern rewriting, not a universal fail-closed claim checker.
- Update controls distinguish concrete routing execution, library contracts, and deployment-required authorities.

## Forbidden claims

- “clinically safe”, “clinically validated”, “improves outcomes”, “reduces errors”, “saves clinician time”, or equivalent.
- “guarantees safety” without limiting the guarantee to a precise software invariant.
- “first”, “state of the art”, or “outperforms”.
- Any claim that the repository is publicly reproducible before licensing and anonymized release are resolved.
- Any claim that 40/40 covers run finality or update admissibility.

## Evidence requirements

- A machine-readable engineering-audit record stores the command, date, case count, pass count, policy families, and suite metadata; the paper must not describe `external_model_or_rag=false` as egress-interception evidence.
- A source-evidence map links headline claims to exact repository paths and line ranges.
- Citations must resolve to primary publication pages or official metadata.
- Figures must not introduce claims absent from the text or source.

## Presentation requirements

- Official NeurIPS 2026 `dblblindworkshop` format.
- Anonymous authors and no identifying repository URL.
- Main text between 4 and 9 pages, excluding references and checklist.
- All four figures readable in the compiled PDF at normal zoom.
- No unresolved LaTeX references or citations.

## Review requirements

- One independent, fresh-context child agent reads the raw source and compiled PDF without receiving author summaries or previous fix lists.
- All critical and major review findings are either corrected or recorded as unresolved submission blockers.
- Because the user prohibited Claude review, the ARIS Claude-dependent integrity-forensics sweep is not used; the final readiness statement must disclose this exception.
