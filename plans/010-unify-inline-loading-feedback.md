# 010 — 统一非对话加载反馈，避免旋转图标和状态闪烁

- **Status**: TODO
- **Commit**: c5afd5b
- **Severity**: MEDIUM
- **Category**: Purpose & frequency / accessibility / cohesion
- **Estimated scope**: 5 files, focused state-presentation changes

## Problem

对话主路径已有低频 Codex 三点指示和真实耗时，且不会用伪百分比。但其它高频、
短暂的读取状态仍直接使用持续旋转的 `animate-spin` 图标。它们与产品已确立的平静
状态语言不一致；如果网络慢，用户看不到这项请求是否仍在推进、能否重试，老年用户
也容易把持续旋转理解为故障。

```tsx
// apps/mvp/src/components/chronic/ChronicCareLedger.tsx:224 — current
<RefreshCw className="size-5 animate-spin" aria-hidden="true" /> 正在读取您的记录…

// apps/mvp/src/components/risk-alert/RiskAlertLedger.tsx:79 — current
<RefreshCw className="size-5 animate-spin" aria-hidden="true" />正在读取安全提醒…
```

`apps/mvp/src/components/account/AdminDashboard.tsx:25` also uses a spinning
refresh icon for the management queue. These are not continuous measurements;
they are fetch states. A high-speed loop provides no extra information and
competes with the single, intentionally restrained running indicator.

## Target

Create one tiny presentational `InlineLoadingState` component for bounded
read/refresh states. It uses the existing `codex-activity-dots` markup,
short direct text and optional `aria-live="polite"`; it never manufactures
progress or elapsed time for requests that do not report a server execution.

```tsx
// target shape
<div role="status" aria-live="polite" className="flex min-h-12 items-center gap-3 text-muted-foreground">
  <span className="codex-activity-dots" aria-hidden="true">
    <span className="codex-activity-dot" />
    <span className="codex-activity-dot" />
    <span className="codex-activity-dot" />
  </span>
  <span>正在读取安全提醒</span>
</div>
```

The existing `@media (prefers-reduced-motion: reduce)` fallback in
`apps/mvp/src/app/globals.css:409-411` makes the dots static, preserving the
state message without persistent movement. Keep `RefreshCw` static on manual
refresh buttons so the pressed state remains clear, but do not use
`animate-spin` for passive fetch content.

## Repo conventions to follow

- `apps/mvp/src/components/chat/MessageBubble.tsx` already owns the real
  model-execution elapsed clock. This plan must not duplicate it elsewhere.
- `apps/mvp/src/app/globals.css:385-411` is the shared Codex activity-indicator
  implementation and reduced-motion policy; do not add a second keyframe.
- Patient senior mode requires an at-least-48px actionable control, but a
  passive status may remain compact while retaining readable text.

## Steps

1. Add `apps/mvp/src/components/ui/inline-loading-state.tsx` as a purely
   presentational component with strict props for its short message, optional
   `className`, `role="status"`, and `aria-live="polite"`. Reuse the existing
   three-dot CSS class names exactly. Do not add a timer, request state, or
   dependency.
2. Replace passive content loading in
   `components/chronic/ChronicCareLedger.tsx` and
   `components/risk-alert/RiskAlertLedger.tsx` with that component. Preserve
   each component's existing empty, error, retry and success branches.
3. Split the admin dashboard's manual refresh feedback from its passive
   loading content. The button may become disabled and say `正在刷新`; its
   icon must not rotate indefinitely. Reuse the shared loading state only in
   the content region, without changing account/bad-case API behavior.
4. Search the MVP for remaining passive `animate-spin` instances. Convert
   only states that lack task progress or an action-specific reason for
   rotation; document any retained exception in this plan's execution record.
5. Add a focused render/contract test if the existing Node setup can reliably
   assert the status markup. Otherwise verify using the browser on a delayed
   API response; do not introduce a test-only fake progress timer.

## Boundaries

- Do NOT remove the main Chat or five-prescription elapsed clocks, stop
  actions, cancellation behavior, status text, or error recovery.
- Do NOT add fake percentages, looping shimmer, a new animation library, or
  global `animation: none` overrides.
- Do NOT turn a passive status into an interactive control or change medical
  result/alert semantics.

## Verification

- **Mechanical**: from `apps/mvp`, run `npm run lint`, `npm test`, and
  `npm run build`.
- **Feel check**: throttle one ledger request. The status appears once,
  remains visually stable while the request is pending, and disappears cleanly
  on success or error. It must not flash or restart after unrelated renders.
- **Reduced motion**: emulate `prefers-reduced-motion: reduce`; dots become
  static while the status text still announces the pending request.
- **Done when**: passive read states use the same calm indicator as the
  product's model-running surface; no remaining `animate-spin` represents a
  generic fetch wait without a documented exception.
