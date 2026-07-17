# 005 — 将录音波形改为合成层动画

- **Status**: DONE
- **Commit**: 36ef85b
- **Severity**: HIGH
- **Category**: Performance
- **Estimated scope**: 1 file, small focused change

## Problem

`apps/mvp/src/components/chat/ChatInput.tsx:90-114` renders 28 bars on every
audio-level update. Each bar currently changes its layout height and applies a
broad transition:

```tsx
// apps/mvp/src/components/chat/ChatInput.tsx:101-109 — current
<div
  key={i}
  className={cn(
    "w-[3px] rounded-full transition-all duration-100",
    isActive ? "bg-gray-800 dark:bg-gray-200" : "bg-gray-300 dark:bg-gray-600"
  )}
  style={{ height: `${height}px` }}
/>
```

This recording-only interaction can update many times per second. `height`
requires layout and `transition-all` also makes unrelated style changes
eligible for animation. On a constrained mobile device this competes with
recording UI responsiveness, making an important accessibility interaction
feel unstable.

## Target

Keep each bar at a stable maximum height and express amplitude with a
compositor-friendly transform. Only `transform` and background color may
transition; use the shared 100ms press-response timing with strong ease-out.
At `prefers-reduced-motion: reduce`, show the current, static amplitude and
color without a transform transition.

```tsx
// target shape; derive scaleY from the existing clamped height / 28 value
className={cn(
  "h-7 w-[3px] origin-center rounded-full transition-[transform,background-color] duration-100 ease-[var(--motion-ease-out)] motion-reduce:transition-[background-color]",
  isActive ? "bg-gray-800 dark:bg-gray-200" : "bg-gray-300 dark:bg-gray-600"
)}
style={{ transform: `scaleY(${scaleY})` }}
```

## Repo conventions to follow

- Motion tokens are defined in `apps/mvp/src/app/globals.css:104-110`.
- `apps/mvp/src/components/ui/progress.tsx:49` is the existing transform-only
  progress precedent, including `motion-reduce:transition-none`.
- Do not introduce a JavaScript animation loop or a new motion dependency.

## Steps

1. In `apps/mvp/src/components/chat/ChatInput.tsx`, calculate a `scaleY`
   value from the existing `height` result, clamped to a small visible minimum
   and at most `1`; retain the existing audio-level calculation and bar count.
2. Replace the inline `height` style with `transform: scaleY(...)`, give every
   bar one stable `h-7` layout box, and replace `transition-all` with exactly
   `transition-[transform,background-color] duration-100
   ease-[var(--motion-ease-out)]`.
3. Add the explicit `motion-reduce` transition override described above. Do
   not remove the active/inactive color distinction, which is useful feedback.
4. Add or extend the focused front-end test only if the current test setup can
   assert the generated class/style deterministically; otherwise leave a
   browser feel check as the behavioral proof.

## Boundaries

- Do NOT change recording permissions, ASR requests, timers, or send/cancel
  semantics.
- Do NOT add a looping decorative animation.
- Do NOT alter the number, color, or accessible controls of waveform bars.

## Verification

- **Mechanical**: run `npm run lint` and `npm run build` in `apps/mvp`; both
  must pass.
- **Feel check**: start recording on a physical or headed browser. Speak and
  confirm all bars react immediately without horizontal reflow; repeatedly
  start/stop and confirm no stale visual transition appears.
- **Reduced motion**: emulate `prefers-reduced-motion: reduce`; amplitude and
  color must remain understandable but must not glide between values.
- **Done when**: `WaveformBars` has no `transition-all` and no per-update
  `height` style, while recording remains visibly responsive.

## Execution record

- Implemented at commit pending: each bar now has a stable `h-7` layout box and
  its existing calculated amplitude is represented as `scaleY`; the only
  transitions are transform/background color, and reduced motion is static.
- `npm run lint` and `npm run build` passed. A real guest patient browser
  session entered through the login page and toggled senior mode twice without
  console errors; microphone permission/real audio input was intentionally not
  requested during this UI-only regression.
