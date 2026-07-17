# 006 — 为通用弹层补齐 reduced-motion 退化

- **Status**: TODO
- **Commit**: 36ef85b
- **Severity**: MEDIUM
- **Category**: Accessibility
- **Estimated scope**: 3 files, focused utility-class changes

## Problem

The main dialog and sheet branches already use `useReducedMotion`, but the
frequently used dropdown, tooltip, and toast primitives retain positional
`animate-in`/`animate-out` classes without a reduced-motion override:

```tsx
// apps/mvp/src/components/ui/dropdown-menu.tsx:42-45 — current
className={cn("... origin-(--transform-origin) ... data-[side=bottom]:slide-in-from-top-2 ... data-open:animate-in data-open:fade-in-0 data-open:zoom-in-95 data-closed:animate-out ... data-closed:zoom-out-95", className)}

// apps/mvp/src/components/ui/tooltip.tsx:53 — current pattern
"... data-[side=bottom]:slide-in-from-top-2 ... data-open:animate-in ... data-open:zoom-in-95 ..."

// apps/mvp/src/components/ui/toast.tsx:102 — current
"... animate-in fade-in slide-in-from-bottom-2 duration-200 ..."
```

For a user who explicitly requests less motion, directional slides and zooms
should become a short opacity cross-fade. Menus and status notices are used
throughout the product, including the senior patient interface.

## Target

Keep normal motion anchored to the trigger and under 200ms. Under
`prefers-reduced-motion`, remove slide/zoom transforms while retaining a
short opacity transition so state feedback is not lost. Use Tailwind
`motion-reduce:*` variants rather than a second global reset.

```tsx
// target pattern for dropdown/tooltip
"... duration-[var(--motion-popover)] ease-[var(--motion-ease-out)]
 motion-reduce:data-[side=bottom]:translate-y-0
 motion-reduce:data-[side=top]:translate-y-0
 motion-reduce:data-[side=left]:translate-x-0
 motion-reduce:data-[side=right]:translate-x-0
 motion-reduce:data-open:zoom-in-100 motion-reduce:data-closed:zoom-out-100"

// target toast pattern
"... duration-200 ease-[var(--motion-ease-out)]
 motion-reduce:slide-in-from-bottom-0"
```

## Repo conventions to follow

- `apps/mvp/src/components/ui/dialog.tsx:51-54` and
  `apps/mvp/src/components/ui/sheet.tsx:62` are the existing opacity-only
  reduced-motion precedent.
- Shared duration/easing variables live in `apps/mvp/src/app/globals.css:104-110`.
- Trigger-origin handling already exists through
  `origin-(--transform-origin)` in dropdown and tooltip; retain it.

## Steps

1. In `apps/mvp/src/components/ui/dropdown-menu.tsx`, add exact
   `motion-reduce` overrides to both main and submenu content classes so
   side-specific translate and zoom utility transforms resolve to zero/100.
   Preserve `origin-(--transform-origin)` and all focus behavior.
2. Apply the same transform-neutral reduced-motion pattern to
   `apps/mvp/src/components/ui/tooltip.tsx`.
3. In `apps/mvp/src/components/ui/toast.tsx`, retain the 200ms fade but remove
   the bottom slide in reduced motion. Do not change the single-toast
   replacement behavior or its `aria-live` semantics.
4. If Tailwind variant composition cannot safely override a generated
   `tw-animate-css` transform, use the smallest component-local CSS utility in
   `apps/mvp/src/app/globals.css`; do not add a global rule that changes all
   animations.

## Boundaries

- Do NOT disable opacity/color feedback in reduced motion.
- Do NOT change popup placement, keyboard focus, portal behavior, or close
  timing.
- Do NOT add a new animation library.

## Verification

- **Mechanical**: run `npm run lint` and `npm run build` in `apps/mvp`.
- **Feel check**: open the user menu, tooltip, and a toast at normal preference;
  each should originate near its trigger or status location and settle within
  200ms.
- **Reduced motion**: emulate `prefers-reduced-motion: reduce`; each must fade
  without directional translation or scale, while remaining visibly announced.
- **Done when**: every cited primitive has an explicit component-level reduced
  motion path and existing keyboard interaction continues to work.
