# Motion improvement plans

Generated from the 2026-07-17 motion audit at commit `6eeefd4`. The audit used
the running MVP at `http://127.0.0.1:3052`, source inspection, and the project
reduced-motion implementation. The Codex-style single activity indicator with
real elapsed time was intentionally retained: it gives useful status without a
loader wall or fake progress.

| Plan | Title | Severity | Status |
| --- | --- | --- | --- |
| 001 | Preserve feedback in reduced-motion mode | HIGH | DONE |
| 002 | Restrict chat and panel motion to composited properties | HIGH | DONE |
| 003 | Make sheets and dialogs enter from their spatial origin | MEDIUM | DONE |
| 004 | Animate progress with transforms, not layout width | MEDIUM | DONE |

Executed in order 001 → 002 → 003 → 004. Plans 002 and 003 use the motion
tokens and reduced-motion policy introduced by 001; plan 004 uses the shared
ease-out token. Browser review covered the patient entry and settings panel;
the CLI's media-emulation snippet is not supported by this runner, so
reduced-motion behavior is additionally covered by the component branches and
production build.
