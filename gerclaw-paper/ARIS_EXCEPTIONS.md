# ARIS execution exceptions

## Reviewer substitution

The user explicitly prohibited Claude review and requested one independent
child agent.  The paper therefore uses one fresh-context Codex child-agent
review instead of the default Claude reviewer.  No author summary, fix list,
or prior review is supplied to that reviewer.

## Integrity forensics

The ARIS `integrity-forensics` full sweep depends on a Claude Code execution
contract.  Its own Codex-native note permits only a deterministic incomplete
mode that can never issue a clean verdict.  Because the user prohibited Claude
review, the full sweep is not run and no `CLEAN_GIVEN_EVIDENCE` or equivalent
claim is made.

## Kill-argument exercise

The canonical exercise requires two additional fresh reviewers.  The user
asked for one independent child reviewer, so the final review is instructed to
state the strongest rejection argument within its single report.  This is a
documented adaptation, not a claim of protocol-equivalent execution.
