# Evolution Signals

Current implementation defines a strict, content-free `EvolutionSignal` contract. No online
collector or optimizer has been activated, and production images do not gain training
dependencies.

Unknown fields fail validation to prevent accidental content leakage. Stage 6 adds the
isolated exporter and official-optimizer evaluation workflow. Measure success with privacy
allowlist tests, revision-correct feedback, complete lineage, and zero production mutations.
“Zero production mutations” applies to this signal pipeline, not to ordinary actor-owned
Memory CRUD or separately governed low-risk Skill content versions.

Consumer: the future metadata-only signal collector. Configuration: export allowlists and
destinations will be sealed and injected; this package reads no environment. Known limit:
there is no collector/exporter/optimizer in the request path. Acceptance: content-field
negative tests, one-way fingerprints, reconciled feedback revisions, and no online mutation.
