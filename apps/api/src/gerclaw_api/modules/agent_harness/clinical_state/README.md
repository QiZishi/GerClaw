# Clinical State

This package defines versioned `ClinicalState`, `ClinicalFact`, provenance contracts, and
the independently constructible `DeterministicClinicalStateReducer`. It is not yet injected
into the production Harness, so current chat behavior is unchanged.

Validation rejects untrusted provenance types and unbounded collections. The reducer accepts
only already-validated user or trusted-tool observations. Equal observations merge provenance;
different values under one semantic `fact_id` remain as separate `conflicted` candidates.
Neither user nor tool input silently resolves a conflict. Callers may add or explicitly resolve
unknown labels, but an unknown is never converted into `negative_evidence`.

Consumer: the future router/planner and treatment gate. Configuration: collection bounds are
owned by the Pydantic contract; the reducer reads no environment or provider configuration.
Failure semantics: Pydantic rejects malformed facts at the trust boundary and reducer-wide
collection/provenance overflow raises a stable `ClinicalStateError`. Known limit: free text is
not parsed into facts here; a caller must construct facts only from explicit user input or a
validated tool result. Acceptance: provenance-complete fixtures, preserved conflicts, explicit
unknowns, and zero model-derived confirmed facts.
