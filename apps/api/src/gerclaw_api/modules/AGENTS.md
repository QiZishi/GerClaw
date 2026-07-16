# GerClaw Module Boundary Instructions

## Responsibility

`modules/` is the composition root for independently testable GerClaw domain modules. It provides no cross-module business bypass: routes and services compose module APIs, while each child module remains the owner of its own rules, persistence and external-boundary contracts.

## Invariants

- Read the child module's `AGENTS.md` before changing that module. Its local safety, ownership and verification rules are stricter than this index when they differ.
- Preserve the dependency direction: HTTP routes and application services call modules; modules must not import frontend code or make browser-direct provider calls.
- Cross-module data must pass through explicit, versioned schemas. Do not share database internals, bypass authorization, or copy a second implementation into a neighbouring module.
- Medical safety, tenant/actor/session isolation, PHI minimisation, redaction and Runtime governance apply at every module boundary.
- Treat model output, retrieved content, uploaded documents and tool/provider responses as untrusted data until each owning boundary validates them.

## Change and test rules

- Add or update the affected child module's `AGENTS.md` and `README.md` when its responsibility, public contract, security boundary or operational limitation changes.
- Run the owning module's focused tests plus contract/integration tests for every changed boundary; run migration checks for persistence changes.
- New functionality belongs in one owning module. If it needs an orchestrated cross-module flow, route it through `runtime`/service composition rather than creating a hidden dependency cycle.
