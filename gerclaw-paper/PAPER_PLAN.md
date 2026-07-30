# Paper plan

## Working title

**GerClaw: Three-Boundary Verification Contracts for Evolvable Medical Agents**

## Contributions

1. A three-boundary verification model spanning clinical claims, concurrent agent runs, and offline candidate updates.
2. A source-grounded status report: marker auditing and bounded diagnosis rewriting, lease-plus-fencing terminal commits, frozen sandbox execution, a routing-only paired runner, and signed release-control contracts.
3. A coverage-gap analysis of 40 passing adjacent policy cases, explicitly excluding run/update verification and all clinical inference.

## Planned sections

1. Introduction
2. Related Work and Verification Gap
3. Three-Boundary Verification Model
4. GerClaw Architecture
5. Executable Engineering Evidence and Coverage Gaps
6. Limitations, Ethics, and Research Agenda
7. Conclusion

## Planned figures

1. System overview and the three verification boundaries.
2. Pattern-bounded claim enforcement, marker auditing, and emergency short-circuit.
3. Concurrent run lifecycle, fencing, and atomic terminal commit.
4. Offline candidate freeze, sandbox, routing-only paired evaluation, release contracts, and deployment-required authorities.

## Planned tables

1. Verification objects, failure modes, mechanisms, and machine-checkable obligations.
2. Deterministic regression suite composition.

## Scope exclusions

- No diagnostic-accuracy, clinical-effectiveness, clinician-time, patient-satisfaction, or deployment claim.
- No superiority claim over another medical agent.
- No claim that passing deterministic regressions establishes general safety.
- No claim that the prototype is a medical device or is ready for clinical use.
- No claim that current CGA, voice, and prescription modules all execute through the unified Harness.
- No claim that marker presence establishes semantic entailment.
- No claim that sealed evaluation or a separately authenticated approval service is implemented or deployed.
