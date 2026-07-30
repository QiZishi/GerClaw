# Evidence Instructions

Owns normalized evidence metadata and citation admission. It does not retrieve, rank, parse,
or store source documents; RAG, Search, and Document remain their sole capability owners.

Every emitted medical citation must resolve to adopted text and a locator from a validated
source. Never invent title, institution, year, version, locator, or quotation. Unavailable
evidence must remain unavailable and force a truthful downgrade.

Evidence is a claim-to-source relationship, not a turn-level boolean. A citation only supports
the clinical claim in the same public segment. Normalize model markers before SSE emission,
keep public positions stable through the terminal response, and fail closed on reserved,
missing, or out-of-range markers.

Run Harness safety, RAG, Search, document isolation, and citation contract tests after changes.
