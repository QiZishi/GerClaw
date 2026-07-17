# 009 — Make five-prescription generation visibly active and safely stoppable

- **Status**: DONE
- **Commit**: 8948195
- **Severity**: HIGH
- **Category**: Purpose & frequency / interruptibility / accessibility
- **Estimated scope**: 6 files, roughly 180 lines

## Problem

The chat-native five-prescription flow can legitimately run for several
minutes, but it presents a static text-only status and has no user action to
stop a generation. Its current implementation at
`apps/mvp/src/components/prescription/PrescriptionConversation.tsx:205` is:

```tsx
{generating && (
  <div ... role="status">
    正在整理资料并生成草案 · 已执行 {String(Math.floor(elapsedSeconds / 60)).padStart(2, "0")}:{String(elapsedSeconds % 60).padStart(2, "0")}
  </div>
)}
```

The shared `codex-activity-dots` indicator already gives low-frequency,
reduced-motion-safe feedback in `apps/mvp/src/app/globals.css:386`, but this
entry point does not use it. More importantly, aborting only the browser
request would leave the server model execution and Trace ambiguous. The chat
route already has a Redis-coordinated, identity-scoped cancellation registry;
the prescription flow needs the equivalent durable terminal behavior.

## Target

Use the existing three-dot Codex activity indicator next to an exact,
tabular elapsed time. Add a visible `停止生成` action while the request is
active. It must immediately acknowledge the press, send an owner-scoped
cancellation request tied to the client-provided Trace ID, and only settle
the local UI after the server has recorded the Trace as `cancelled` or has
returned a stable cancellation failure. Do not use fake percentage progress,
repeating brightness flashes, or layout-changing animation.

```tsx
<div role="status" aria-live="polite" className="...">
  <span className="codex-activity-dots" aria-hidden="true">...</span>
  <span>正在整理资料并生成草案</span>
  <span className="tabular-nums">已执行 {elapsed}</span>
  <Button variant="outline" onClick={stopGeneration}>停止生成</Button>
</div>
```

The indicator keeps the existing `1.35s ease-in-out` transform/opacity loop;
`prefers-reduced-motion: reduce` continues to make the dots static. The
button inherits the project's `160ms var(--motion-ease-out)` press feedback,
with no additional animation.

## Repo conventions to follow

- `apps/mvp/src/components/chat/MessageBubble.tsx:295` uses the exact shared
  three-dot activity markup plus elapsed time.
- `apps/mvp/src/services/gerclaw/chat.ts:135` creates a trace identifier
  before transport and sends an explicit cancellation request on abort.
- `apps/api/src/gerclaw_api/services/chat_cancellation.py:26` provides durable
  Redis cancellation and identity-scoped task ownership; retain its
  fail-closed behavior rather than treating client disconnection as a cancel.

## Steps

1. Add a versioned, owner-scoped cancellation endpoint for a running
   five-prescription Trace in `apps/api/src/gerclaw_api/api/routes/clinical_intakes.py`.
   It must use the existing cancellation registry, rate limit, and return a
   bounded acknowledgement; no clinical content may be present in either
   request or response.
2. Register the prescription generation task before model execution, fence
   persistence with `is_cancel_requested`, and on `asyncio.CancelledError`
   finalize the already-started Trace with `TraceStatus.CANCELLED` and one
   PHI-free clinical-intake event. Always unregister the exact task in
   `finally`; never persist a draft after cancellation wins.
3. Add strict backend contract/negative tests for owner-only cancellation,
   cancellation during generation, terminal Trace status, and the no-draft
   persistence fence.
4. Extend the controlled BFF allowlist and its unit test only for that exact
   UUID + trace-ID cancellation URL. Do not create a wildcard runtime proxy.
5. In `apps/mvp/src/services/gerclaw/clinical-intakes.ts`, accept an
   `AbortSignal`, create/send a bounded Trace ID, and on abort call the
   cancellation endpoint before aborting transport. Return a stable
   `PRESCRIPTION_GENERATION_CANCELLED` error only after the API confirms it.
6. In `PrescriptionConversation.tsx`, use the shared dot markup, exact
   elapsed time in `tabular-nums`, an `aria-live="polite"` status, and a
   `停止生成` action that is disabled only while cancellation confirmation is
   pending. Keep the composer unavailable during an active generation, but
   restore it after cancellation so the user may edit inputs or retry.

## Boundaries

- Do NOT alter clinical generation prompts, medical rule results, evidence
  binding, patient data, or approval policy.
- Do NOT silently turn an HTTP disconnect into a successful cancellation.
- Do NOT make a user-visible claim that an in-flight model was stopped until
  the server records that terminal Trace state.
- Do NOT add a separate spinner, progress bar, timer loop, or motion library.

## Verification

- **Mechanical**: run the focused FastAPI cancellation tests, then from
  `apps/mvp` run `npm run test:gerclaw-proxy`, `npm run lint`, and
  `npm run build`.
- **Integration**: against Compose, start a controlled delayed model draft,
  press `停止生成`, verify the API returns the acknowledgement, the Trace is
  `cancelled`, and no `PrescriptionDraft` row is written. Verify a different
  principal receives 404 and cannot cancel it.
- **Feel check**: open the patient five-prescription flow. On generation, the
  dots move calmly once per cycle beside a steadily increasing exact elapsed
  time; there is no container jump or brightness flash. Toggle reduced motion:
  dots become static while elapsed text and stop control remain usable.
- **Done when**: generation is visibly active, can be safely stopped from the
  same page, and cancellation cannot leave a completed draft or running Trace.

## Execution result

- 2026-07-18: FastAPI route/unit contracts, BFF allowlist, MVP lint/build and
  the full API suite passed (`675 passed, 36 skipped`, coverage `80.12%`).
- Browser: mandatory login → guest patient entry → five-prescription chat →
  generation status → `停止生成` completed against the rebuilt Compose API.
  The UI returned to a retryable state and the newest database Trace was
  `cancelled` with `prescription_generation_cancelled`; no draft was saved.
