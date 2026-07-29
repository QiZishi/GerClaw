# Clinical State

This package defines versioned `ClinicalState`, `ClinicalFact`, provenance contracts, and
the independently constructible `DeterministicClinicalStateReducer`. Production Chat restores
the latest actor-owned state from the encrypted `AgentRun.context_snapshot`, projects the
persisted current user message and code-owned red-flag matches as `reported` observations,
reduces them, and persists the resulting state on the new Run. Regeneration recognizes the
same input-message fact ID and does not duplicate it.

Validation rejects untrusted provenance types and unbounded collections. The reducer accepts
only already-validated user or trusted-tool observations. Equal observations merge provenance;
different values under one semantic `fact_id` remain as separate `conflicted` candidates.
Neither user nor tool input silently resolves a conflict. Callers may add or explicitly resolve
unknown labels, but an unknown is never converted into `negative_evidence`.

The Harness receives the validated state through `AgentContext` as explicitly untrusted
private model context; its serialized size is included in model preflight. Model output is
never fed back into this reducer. Trusted tool-result projection is the remaining producer
extension point and must use the same reducer boundary.

Consumers: production Chat/Harness, planner, and treatment gate. Configuration: collection bounds are
owned by the Pydantic contract; the reducer reads no environment or provider configuration.
Failure semantics: Pydantic rejects malformed or corrupt persisted facts at the trust boundary and reducer-wide
collection/provenance overflow raises a stable `ClinicalStateError`. Known limit: free text is
not parsed into facts here; a caller must construct facts only from explicit user input or a
validated tool result. Acceptance: provenance-complete fixtures, preserved conflicts, explicit
unknowns, and zero model-derived confirmed facts.

`DifferentialAssessment` is the GerClaw adaptation of C3: it does not import a disease catalog
from another product and does not force a candidate count. Each non-diagnostic direction keeps
supporting, opposing, missing, and residual facts. `C3DifferentialValidator` rejects unknown
fact references and refuses to use a conflicted fact as positive support.

`TreatmentContext` and `STEPTreatmentGate` implement the code-owned STEP boundary. Treatment
receives source-linked age, allergy, current-medication, comorbidity and test fact IDs plus
explicit uncertainty, monitoring, and follow-up conditions. Red flags block treatment;
missing/conflicted prerequisites keep output review-only and prohibit actionable medication
changes. The five-prescription generator serializes this context into its private model input
and falls back to the existing evidence-bound review baseline when a provider proposes a
medication change before prerequisites are complete. It does not expose the private context in
the API response.
