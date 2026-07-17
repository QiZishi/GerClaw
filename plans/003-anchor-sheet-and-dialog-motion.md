# 003 — Make sheets and dialogs enter from their spatial origin

- **Status**: DONE
- **Commit**: 6eeefd4
- **Severity**: MEDIUM
- **Category**: Physicality & origin / easing & duration
- **Estimated scope**: 2 files, roughly 40 lines

## Problem

The Base UI sheet uses a generic `ease-in-out` transition and fixed 2.5rem
closed offsets regardless of the sheet dimension:

```tsx
/* apps/mvp/src/components/ui/sheet.tsx:56 — current */
"... shadow-lg transition duration-200 ease-in-out ...\
data-[side=bottom]:data-ending-style:translate-y-[2.5rem] ...\
data-[side=right]:data-ending-style:translate-x-[2.5rem] ..."
```

An edge sheet should use the same edge on entry and exit, beginning quickly
with an iOS-like drawer curve. A fixed 2.5rem offset makes a full-height sheet
appear to fade rather than arrive from its edge.

## Target

For directional sheets, use `250ms` and
`cubic-bezier(0.32, 0.72, 0, 1)` through `--motion-ease-drawer`; close and open
from the matching full dimension: `translate-y-full` for bottom/top sheets and
`translate-x-full`/`-translate-x-full` for right/left sheets. Center dialogs
remain centered and use `opacity` plus `scale(0.95)`, never `scale(0)`.

Under reduced motion, sheets and dialogs cross-fade (`opacity 200ms ease`) and
do not translate or zoom.

## Repo conventions to follow

- `apps/mvp/src/components/ui/drawer.tsx:125` already uses a constrained
  transform transition and `will-change-transform` for swipeable drawers.
- `apps/mvp/src/components/ui/dialog.tsx:56` correctly uses `zoom-in-95`, not
  `scale(0)`; preserve its centered origin.

## Steps

1. Update `apps/mvp/src/components/ui/sheet.tsx` to use only
   `transition-[transform,opacity] duration-[var(--motion-panel)]
   ease-[var(--motion-ease-drawer)]` on the popup and `opacity` on the
   backdrop. Replace each 2.5rem directional starting/ending transform with
   the corresponding full-dimension translate utility.
2. Add reduced-motion utility classes/conditionals in `sheet.tsx` so its
   directional transforms are not applied when the preference is reduce.
3. Update `apps/mvp/src/components/ui/dialog.tsx` only to consume the shared
   180ms ease-out token for its existing opacity/zoom-95 behavior and to add
   an explicit reduced-motion opacity-only state.

## Boundaries

- Do NOT alter dialog focus management, escape handling, portal structure,
  backdrop click behavior or Base UI state attributes.
- Do NOT change the swipeable drawer implementation in this plan.
- Do NOT add bounce to menus, dialogs or sheets; these are not momentum-driven
  direct-manipulation interactions.

## Verification

- **Mechanical**: from `apps/mvp`, run `npm run lint` and `npm run build`.
- **Feel check**: open and dismiss each side of a sheet. At 10% animation
  speed, it enters and exits on exactly the same edge; the backdrop does not
  flash; a dialog materializes from 95% scale rather than nowhere. Emulate
  reduced motion and confirm only opacity changes.
- **Done when**: no sheet relies on `ease-in-out` or a fixed 2.5rem closed
  offset, and all panels preserve their spatial path.
