# Round-1 review disposition

| Reviewer finding | Disposition |
|---|---|
| ClaimCheck overstated universal enforcement | Corrected in abstract, Sections 3–4, limitations, conclusion, Figure 2 prompt, and claim audit. The paper now states marker audit + narrow diagnosis rewrite and explicitly disclaims entailment/universal blocking. |
| UpdateGate overstated independent evaluator and approval service | Corrected throughout. The routing-only runner and envelope/promotion libraries are separated from required but unimplemented/deployed authorities. |
| 40/40 presented too close to core three-boundary evidence | Corrected. Section 5 calls it adjacent policy evidence and enumerates run/update mechanisms it does not test. |
| Audit provenance and `external_model_or_rag=false` too strong | Corrected. The paper labels the field as suite metadata and discloses missing source release, environment capture, and raw-output hash; checklist reproducibility is now “No.” |
| Missing threat model | Corrected with an explicit threat model and trusted computing base in Section 3. |
| Related work missing transactions, attestation, assurance cases, and ML readiness | Corrected with Gray–Reuter, in-toto, ML Test Score, and GSN; novelty is narrowed to the boundary decomposition. |
| Figures 1, 2, and 4 overstate seriality/safety/deployment status | All three figures were regenerated after textual correction. Figure 4 explicitly distinguishes solid implemented contracts from dashed deployment-required authorities. |
| “Five patterns” count inaccurate | Corrected to five positive cases exercising six red-flag codes. |

## Final re-review addendum

The same independent reviewer returned **Weak Accept** after revision.  It
identified one remaining camera-ready issue: Figure 1 showed public SSE before
the atomic terminal commit.  Figure 1 was then edited to show the exact order
`Output policy + private buffer → Atomic terminal commit → Public SSE done /
replay`, with no public bypass.

No finding was dismissed.  The original recommendation remains preserved in
`independent_review_round1.md`; this file records author actions, not a second
review verdict.
