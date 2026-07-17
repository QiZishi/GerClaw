# 001 — Preserve feedback in reduced-motion mode

- **Status**: DONE
- **Commit**: 6eeefd4
- **Severity**: HIGH
- **Category**: Accessibility / cohesion & tokens
- **Estimated scope**: 2 files, roughly 70 lines

## Problem

`apps/mvp/src/app/globals.css:351` globally forces every animation and
transition to `0.01ms` for `prefers-reduced-motion`. This removes both
positional motion and useful state feedback (focus, color, opacity, error and
completion changes), which leaves an older user with abrupt UI state changes.
The nearby `.senior-mode` rule also makes every animation 30% faster:

```css
/* apps/mvp/src/app/globals.css:272 — current */
.senior-mode *,
.senior-mode *::before,
.senior-mode *::after {
  animation-duration: calc(var(--animation-duration, 200ms) * 0.7) !important;
  transition-duration: calc(var(--animation-duration, 200ms) * 0.7) !important;
}
```

The screen reader-friendly `useReducedMotion` hook already exists in
`apps/mvp/src/hooks/useReducedMotion.ts:10`; it is the precedent for component
code that needs to drop transform motion.

## Target

Keep color, opacity, border and focus feedback. For reduced motion, suppress
movement and use a short `opacity 200ms ease` cross-fade. Add one shared token
set in `:root`:

```css
--motion-ease-out: cubic-bezier(0.23, 1, 0.32, 1);
--motion-ease-in-out: cubic-bezier(0.77, 0, 0.175, 1);
--motion-ease-drawer: cubic-bezier(0.32, 0.72, 0, 1);
--motion-press: 160ms;
--motion-popover: 180ms;
--motion-panel: 250ms;
```

Under `prefers-reduced-motion: reduce`, remove transform/filter movement and
continuous animation, but retain `opacity 200ms ease`, color and background
feedback. Do not make senior mode faster; it should inherit the same restrained
motion and leave motion reduction to the user preference.

## Repo conventions to follow

- `apps/mvp/src/hooks/useReducedMotion.ts:10` subscribes to the browser media
  query and is used by `RightPanel`, `ThinkingBlock` and `ToolCallBlock`.
- `apps/mvp/src/app/globals.css:395` already gives the Codex activity dots a
  static reduced-motion fallback; preserve that behavior.

## Steps

1. In `apps/mvp/src/app/globals.css`, add the six custom properties above to
   `:root`, without adding a motion dependency.
2. Delete the universal `.senior-mode *` duration override. Do not change
   senior text, size, contrast or hit-area rules.
3. Replace the universal reduced-motion duration reset with rules that set
   `animation: none` only for continuous/decorative animation classes and make
   transform-based transitions use `transform: none` plus `opacity 200ms ease`.
   Leave color/background/border/focus feedback available.
4. Update `apps/mvp/src/hooks/useReducedMotion.ts` only if a small exported
   helper is needed to make the same distinction in React. Do not add a second
   media-query listener API or a new dependency.

## Boundaries

- Do NOT remove the Codex running dots or the real elapsed clock.
- Do NOT introduce looping decorative motion or a global `transition: all`.
- Do NOT alter API calls, loading-state semantics, text, accessibility roles,
  senior-mode sizing or product navigation.
- If the existing `tw-animate-css` classes cannot be safely overridden with
  explicit selectors, stop and report instead of broadly disabling animation.

## Verification

- **Mechanical**: from `apps/mvp`, run `npm run lint` and `npm run build`.
- **Feel check**: in a real browser, open a right panel and an assistant
  response. With normal preference, feedback is immediate and motion is calm.
  In DevTools Rendering, emulate `prefers-reduced-motion: reduce`: panel
  content cross-fades without translating, loading dots are static, and button
  hover/focus colors remain perceptible.
- **Done when**: no global rule reduces every transition to `0.01ms`; reduced
  motion still communicates state without positional or looping motion.
