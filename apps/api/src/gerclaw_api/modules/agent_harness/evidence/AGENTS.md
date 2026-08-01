# Evidence Instructions

Owns normalized evidence metadata and citation admission. It does not retrieve, rank, parse,
or store source documents; RAG, Search, and Document remain their sole capability owners.

Every emitted medical citation must resolve to adopted text and a locator from a validated
source. Never invent title, institution, year, version, locator, or quotation. Unavailable
evidence must remain unavailable and force a truthful downgrade.

Evidence is a claim-to-source relationship, not a turn-level boolean. A citation only supports
the clinical claim in the same public segment. Normalize model markers before SSE emission,
keep public positions stable through the terminal response, and remove reserved, missing, or
out-of-range model markers without inventing a source. Before promotion, one private repair may
replace a claim whose marker is missing; if the replacement is still unbound, delete only that
claim segment and preserve the rest of the answer.
Server-owned public-marker corruption still fails closed.

Run Harness safety, RAG, Search, document isolation, and citation contract tests after changes.
