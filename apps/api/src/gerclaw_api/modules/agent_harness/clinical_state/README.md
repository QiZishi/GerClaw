# Clinical State

This package currently defines versioned `ClinicalState`, `ClinicalFact`, and provenance
contracts. It is not yet injected into the production Harness, so current behavior is
unchanged.

Validation rejects untrusted provenance types and unbounded collections. Stage 3 adds the
general geriatric reducer and treatment gates. Measure improvement with unknown/negative
separation, conflict preservation, provenance completeness, and zero model-derived confirmed
facts.

Consumer: the future router/planner and treatment gate. Configuration: reducer limits and
allowlists will be injected. Known limit: no reducer is active, so this contract is not yet a
clinical fact source. Acceptance: provenance-complete fixtures, preserved conflicts, and
explicit unknowns.
