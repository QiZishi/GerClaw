# Independent re-review — round 2

Reviewer: same fresh-context Codex child reviewer used in round 1
Recommendation before final figure correction: **Weak Accept**

## Closed findings

- ClaimCheck is now accurately limited to marker audit, narrow deterministic
  diagnosis rewriting, and audit-only handling for other unbound statements.
- UpdateGate now distinguishes the routing-only paired runner and library
  contracts from unimplemented/deployment-required evaluator and approval
  authorities.
- The 40/40 result is explicitly adjacent policy evidence and does not claim
  run/update coverage.
- `external_model_or_rag=false` is labeled suite metadata, not intercepted
  egress evidence.
- A centralized threat model and trusted computing base are present.
- Related work now covers transaction processing, in-toto, ML Test Score, and
  GSN while narrowing novelty to boundary decomposition.
- Figures 2 and 4, as well as the reproducibility checklist answer, accurately
  reflect the implementation limits.

## Camera-ready correction requested

The reviewer observed that Figure 1 showed
`Policy-gated SSE → Atomic terminal commit`, contrary to the central run
invariant.  The final figure was corrected with image generation to:

`Output policy + private buffer → Atomic terminal commit → Public SSE done /
replay`.

The public SSE node is now final and has no bypass around the commit.  No
textual blocker remained after the re-review.
