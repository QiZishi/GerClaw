# Routing Instructions

Owns Quick, Standard, Deep, and Emergency decisions before model execution. Emergency
short-circuit always wins; a model may not downgrade it.

Inputs must be validated and content-bounded. Outputs expose stable reason codes, never
private reasoning. Do not call models, RAG, Memory, Search, Skill, or persistence here.
All thresholds must arrive through resolved configuration.

Run routing, red-flag, Harness safety, and budget tests after changes.
