# 002 — Restrict chat and panel motion to composited properties

- **Status**: DONE
- **Commit**: 6eeefd4
- **Severity**: HIGH
- **Category**: Performance / purpose & frequency
- **Estimated scope**: 3 files, roughly 60 lines

## Problem

New chat messages and the right-side working panel are high-visibility paths.
They currently animate broad or layout-affecting property sets:

```tsx
/* apps/mvp/src/components/chat/MessageBubble.tsx:455 — current */
const messageAnimation = cn(
  "transition-all duration-200 ease-out",
  appeared ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2"
);

/* apps/mvp/src/components/layout/RightPanel.tsx:150 — current */
const desktopTransition = reducedMotion ? "" : "transition-all duration-250 ease-out";
```

`transition-all` can animate unrelated paint/layout changes. The desktop panel
also animates its changing width, so resizing or opening can trigger repeated
layout work while the user is reading or interacting.

## Target

Use only `transform` and `opacity` for visible entry feedback. Use the shared
tokens from plan 001:

```tsx
const messageAnimation = cn(
  "transition-[transform,opacity] duration-[var(--motion-popover)] ease-[var(--motion-ease-out)]",
  appeared ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2"
);
```

Desktop panel width changes should be immediate, not animated; only its content
may cross-fade at `opacity 180ms var(--motion-ease-out)`. Mobile retains a
directional `transform` enter/exit at `250ms var(--motion-ease-drawer)`.

## Repo conventions to follow

- `apps/mvp/src/components/chat/blocks/ToolCallBlock.tsx:159` scopes expansion
  to `transition-[grid-template-rows]` and branches for `useReducedMotion`.
- `apps/mvp/src/components/layout/RightPanel.tsx:149` already separates mobile
  and desktop class assembly; keep that structure.

## Steps

1. In `apps/mvp/src/components/chat/MessageBubble.tsx`, replace its
   `transition-all` with `transition-[transform,opacity]`; retain the existing
   200ms entry distance, and make reduced motion omit `translate-y-*` while
   retaining an opacity transition.
2. In `apps/mvp/src/components/layout/RightPanel.tsx`, remove
   `transition-all` from the desktop branch. Do not animate `width`,
   `minWidth`, `borderLeftWidth` or resize updates. Add an opacity-only content
   transition at 180ms on the desktop branch.
3. In `apps/mvp/src/components/chat/WelcomePage.tsx`, replace the visitor card
   `transition-all` with a restricted background/border/color transition and
   `transform 160ms ease`; add `active:scale-[0.97]` only where it does not
   change the 48px senior touch target.

## Boundaries

- Do NOT change message persistence, streaming, loading, right-panel state or
  desktop panel width bounds.
- Do NOT animate an action on keyboard navigation; keep focus changes visual
  but instantaneous.
- Do NOT add Framer Motion, WAAPI libraries or JavaScript animation loops.

## Verification

- **Mechanical**: from `apps/mvp`, run `npm run lint` and `npm run build`.
- **Feel check**: send a response and open/close the right panel repeatedly.
  The message enters once without a layout wobble; the desktop panel never
  lags behind its width; mobile sheet/panel always returns along the right edge.
  In DevTools Animations at 10% speed, only opacity and transform change for
  message entry.
- **Done when**: these components contain no `transition-all`; their frequent
  interactions remain immediately interruptible and readable.
