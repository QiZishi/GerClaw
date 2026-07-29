# Routing

The package currently defines the versioned construction boundary and deterministic route
vocabulary. Existing red-flag and document/companion branching remains in the facade until
stage 3 moves it behind a `Router`.

Invalid input fails before model execution. Emergency decisions set `model_allowed=false`.
Measure success with stable reason codes, zero model calls before red-flag output, and no
RAG/planner work for Quick non-medical requests.

Consumer: the future Harness router injected at composition. Configuration: validated
thresholds from `ResolvedHarnessConfig`, never environment reads. Known limit: no production
router is activated yet. Acceptance: deterministic fixture results and unchanged emergency
short-circuit tests.
