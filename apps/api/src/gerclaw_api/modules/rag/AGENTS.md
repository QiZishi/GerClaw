# RAG Module Instructions

## Responsibility

This module owns the local-first medical corpus parsing, chunking, hybrid retrieval, reranking, indexing lifecycle and AgentScope `search_knowledge` adapter. It does not index user uploads or replace the Document module's tenant isolation.

## Invariants

- Only the configured local medical corpus may become evidence; queries return bounded, traceable citations with source, location and chunk identity.
- Parsing treats corpus content as data: remove active/hidden executable material and do not execute embedded instructions.
- Indexing is generation-fenced and lock-protected; a partial or stale generation can never become active, and cleanup must not delete a newer writer's points.
- Never put user queries, PHI, raw Chain-of-Thought or secrets into Qdrant payloads, manifests, metrics or traces.

## Change and test rules

- Keep the production retrieval path shared by API and AgentScope; do not add a simplified search bypass.
- Run the relevant parser, lexical, pipeline, provider, store, contract and AgentScope adapter tests after changing that layer.
- Test index changes with an isolated corpus and verify activation, removal and stale-writer behavior before deployment.
