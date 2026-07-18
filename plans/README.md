# Motion improvement plans

Initial plans were generated from the 2026-07-17 motion audit at commit `6eeefd4`.
The follow-up audit at commit `36ef85b` retained the calm Codex-style activity
indicator and identified three scoped regressions in recording feedback,
reduced-motion coverage, and a shared high-frequency control. The audit used
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
| 005 | 将录音波形改为合成层动画 | HIGH | DONE |
| 006 | 为通用弹层补齐 reduced-motion 退化 | MEDIUM | DONE |
| 007 | 限定开关的过渡属性 | MEDIUM | DONE |
| 008 | 降低抽屉与高频控件的无障碍运动负担 | MEDIUM | DONE |
| 009 | 使五大处方生成可感知且可安全停止 | HIGH | DONE |
| 010 | 统一非对话加载反馈，避免旋转图标和状态闪烁 | MEDIUM | DONE |

Executed in order 001 → 002 → 003 → 004. Plans 002 and 003 use the motion
tokens and reduced-motion policy introduced by 001; plan 004 uses the shared
ease-out token. Browser review covered the patient entry and settings panel;
the CLI's media-emulation snippet is not supported by this runner, so
reduced-motion behavior is additionally covered by the component branches and
production build.

Plan 005, plan 006, plan 007, and plan 008 are complete. They reuse existing
motion tokens and do not change product behavior.

Plan 008 records the follow-up browser review of the mandatory login and guest
patient entry. It is intentionally separate from plan 006: Drawer gesture
motion and high-frequency press feedback need different verification from
anchored popovers and status notices.

Plan 009 is complete. It reuses the existing low-frequency Codex activity
indicator instead of introducing new decorative motion; browser and database
evidence confirm a user cancellation reaches a terminal cancelled Trace.

The 2026-07-18 follow-up audit at `c5afd5b` found that the primary model and
five-prescription flows remain aligned with this policy, but several passive
ledger fetch states still use generic continuous spinners. Plan 010 is queued
without altering model execution, medical results or cancellation semantics.

Plan 010 is complete in `9283e00`. A subsequent source and interaction audit
at `038d60b` rechecked the patient CGA voice controls, model-running status,
passive fetch states, and reduced-motion fallback. It found no new motion
change worth adding: the voice surface keeps preparation-cancel, pause/resume,
stop and progress; question changes stop stale playback; and all passive
fetches use the shared low-frequency indicator rather than a continuous
spinner. This is intentionally a no-new-plan result rather than churn.
