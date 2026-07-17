# 008 — 降低抽屉与高频控件的无障碍运动负担

- **Status**: DONE
- **Severity**: MEDIUM
- **Category**: Accessibility / interaction feedback
- **Estimated scope**: 2 files, focused utility and token changes

## Problem

Browser review of the patient entry at `http://127.0.0.1:3052` confirmed that
the navigation drawer is responsive at desktop and 390px widths. Its primitive,
however, retains a 450ms transform/height/filter transition when the operating
system requests reduced motion. This differs from the existing Sheet and Dialog
components, which already use an opacity-only fallback.

The global feedback rule for buttons, links, and button roles also uses a 220ms
generic `ease-out` transition. It is perceptibly slow for a high-frequency
control response, particularly alongside the component-level 160ms press token.

## Target

Keep direct-manipulation drawer dragging intact, but when
`prefers-reduced-motion: reduce` is enabled, do not interpolate the drawer's
transform, size, or filter during open/close. Retain a brief opacity transition
so the state change remains legible. Make the shared non-gesture control
feedback use `--motion-press` and `--motion-ease-out`.

## Steps

1. In `apps/mvp/src/components/ui/drawer.tsx`, add component-local
   `motion-reduce` transition-property and duration overrides for the backdrop
   and popup. Keep Base UI's transform values for placement and drag tracking,
   but transition only opacity for reduced-motion users. Do not alter focus,
   portal, snap-point, or swipe behavior.
2. In `apps/mvp/src/app/globals.css`, replace the duplicated 220ms generic
   button transition timing with `var(--motion-press)` and
   `var(--motion-ease-out)`. Preserve the existing set of transitioned visual
   properties and active-state behavior.
3. Update this plan and `plans/README.md` only after mechanical and browser
   verification passes.

## Verification

- `npm run lint` and `npm run build` pass in `apps/mvp`.
- At normal preference, opening and closing the patient menu remains smooth and
  drawer dragging stays direct.
- With `prefers-reduced-motion: reduce`, opening/closing the drawer uses no
  interpolated positional, height, or filter movement; the overlay and content
  remain visibly announced through a short fade.
- At 390px, the menu trigger and close action remain visible, keyboard usable,
  and unobscured.

## Boundaries

- Do not remove all feedback or disable direct user-driven dragging.
- Do not add an animation library or a global reduced-motion reset.
- Do not change product copy, navigation structure, or account access behavior.

## Result

- Implemented opacity-only reduced-motion transition overrides for the Drawer
  backdrop and popup. Base UI transform values remain available for placement
  and direct dragging, but are no longer interpolated under reduced motion.
- The shared button/link feedback now uses the existing 160ms press token and
  shared ease-out curve instead of a separate 220ms timing value.
- Browser review confirmed the mandatory login → guest patient → navigation
  menu path under `prefers-reduced-motion: reduce`, with no browser console
  errors. The visible patient navigation uses the existing Sheet primitive;
  its already-present reduced-motion branch remained functional.
- `npm run lint`, `npm run build`, and `npm test` passed.
