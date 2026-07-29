# Clinical State Instructions

Owns source-aware clinical fact contracts and, in stage 3, the deterministic reducer.
Only explicit user input and validated trusted-tool results may add facts. Model output,
Memory suggestions, retrieval text, and planner hypotheses cannot become confirmed facts.

Unknown is not negative evidence. Conflicts must remain visible until an authorized source
resolves them. Every fact requires provenance; never log unrestricted state or expose PHI
outside the scoped run.

Run ClinicalState, red-flag, medical safety, Memory conflict, and Harness tests after changes.
