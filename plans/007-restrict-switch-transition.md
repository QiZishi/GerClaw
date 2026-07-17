# 007 — 限定开关的过渡属性

- **Status**: TODO
- **Commit**: 36ef85b
- **Severity**: MEDIUM
- **Category**: Performance / cohesion
- **Estimated scope**: 1 file, small utility-class change

## Problem

The shared switch is used for settings such as senior mode. Its root currently
uses `transition-all`, so changes to any animatable property can be scheduled:

```tsx
// apps/mvp/src/components/ui/switch.tsx:18-26 — current
"... rounded-full border border-transparent transition-all outline-none ...
 data-checked:bg-primary data-unchecked:bg-input ..."
...
className="... rounded-full bg-background ring-0 transition-transform ..."
```

The component has a clear, narrow visual contract: the track color changes and
the thumb translates. A broad transition is unnecessary and can animate
unrelated style changes as the component evolves.

## Target

Animate only track background/border/color/opacity feedback with the shared
160ms strong ease-out. Keep the thumb transform transition explicit, use the
same timing, and retain static state changes under reduced motion.

```tsx
// target root fragment
"... transition-[background-color,border-color,color,opacity]
 duration-[var(--motion-press)] ease-[var(--motion-ease-out)] ..."

// target thumb fragment
"... transition-transform duration-[var(--motion-press)]
 ease-[var(--motion-ease-out)] motion-reduce:transition-none ..."
```

## Repo conventions to follow

- `apps/mvp/src/components/ui/button.tsx:7` is the shared explicit-property,
  press-duration precedent.
- `apps/mvp/src/components/ui/progress.tsx:49` uses the same transform-only
  reduced-motion policy.
- The global fallback in `apps/mvp/src/app/globals.css:302-314` must remain
  untouched by this narrowly scoped plan.

## Steps

1. In `apps/mvp/src/components/ui/switch.tsx`, replace `transition-all` on
   the root with the exact property list, duration, and easing above.
2. Add the same explicit duration/easing and a `motion-reduce:transition-none`
   guard to the thumb's existing `transition-transform` class.
3. Verify all sizes and checked/unchecked translations remain unchanged.

## Boundaries

- Do NOT alter switch dimensions, hit target expansion, focus ring, checked
  state semantics, or `@base-ui/react` behavior.
- Do NOT add a scale/bounce effect; this is a high-frequency settings control.

## Verification

- **Mechanical**: run `npm run lint` and `npm run build` in `apps/mvp`.
- **Feel check**: toggle senior mode and theme repeatedly. The track should
  respond immediately and the thumb should translate smoothly with no jump.
- **Reduced motion**: emulate `prefers-reduced-motion: reduce`; color state
  changes remain understandable while thumb movement is not animated.
- **Done when**: `switch.tsx` contains no `transition-all`; no visual or
  keyboard regression appears in the account/settings menu.
