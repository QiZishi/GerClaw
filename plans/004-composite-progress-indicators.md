# 004 — Animate progress with transforms, not layout width

- **Status**: DONE
- **Commit**: 6eeefd4
- **Severity**: MEDIUM
- **Category**: Performance / accessibility
- **Estimated scope**: 3 files, roughly 50 lines

## Problem

Reusable and CGA audio progress bars use broad or width transitions:

```tsx
/* apps/mvp/src/components/ui/progress.tsx:48 — current */
className={cn("h-full bg-primary transition-all", className)}

/* apps/mvp/src/components/cga/CgaAssessment.tsx:592 — current */
style={{ width: `${Math.round(questionAudioProgress * 100)}%` }}
className="h-full rounded-full bg-primary transition-[width] duration-150 ..."
```

Changing width can force layout for every update. Audio progress updates often,
so it should use a compositor transform. Motion also must stop in reduced mode
without hiding the exact progress value.

## Target

Keep the progress track's layout stable and scale its fill from the left:

```tsx
className="h-full origin-left bg-primary transition-transform duration-150 ease-[var(--motion-ease-out)] motion-reduce:transition-none"
style={{ transform: `scaleX(${Math.round(progress * 100) / 100})` }}
```

Use a bounded number in `[0, 1]` before passing it into `scaleX`. Retain all
ARIA progress semantics and textual labels.

## Repo conventions to follow

- `apps/mvp/src/components/chat/MessageBubble.tsx:235` keeps its tool-progress
  indicator explicitly scoped to `transition-[width]` and disables it in
  reduced motion; preserve this behavior until converted in the same pattern.
- `apps/mvp/src/components/cga/CgaAssessment.tsx:592` already includes a
  `motion-reduce:transition-none` guard.

## Steps

1. In `apps/mvp/src/components/ui/progress.tsx`, replace `transition-all` with
   `transition-transform duration-150 ease-[var(--motion-ease-out)]`, set an
   origin-left transform fill via the Base UI value style/API, and retain the
   track's overflow clipping.
2. In `apps/mvp/src/components/cga/CgaAssessment.tsx`, clamp
   `questionAudioProgress` to `[0, 1]`, substitute `transform: scaleX(...)`
   for its width style, and retain `motion-reduce:transition-none`.
3. Inspect the tool-progress line in `MessageBubble.tsx`; convert it in the
   same commit only if its value can be represented with a clamped `scaleX` and
   its accessible value remains unchanged. Otherwise leave it untouched and
   document why in the PR.

## Boundaries

- Do NOT change media playback state, scrubbing, elapsed-time calculation,
  progress values, ARIA roles or any clinical assessment result.
- Do NOT use JavaScript timers or requestAnimationFrame for progress visuals.
- Do NOT animate color, width, padding or surrounding layout.

## Verification

- **Mechanical**: from `apps/mvp`, run `npm run lint`, `npm run build`, and
  `npm run test:audio`.
- **Feel check**: play, pause and resume a CGA question. The fill advances from
  the left without reflow, pause stops visual updates, and reduced-motion keeps
  an accurate static fill without easing. In DevTools Performance, verify the
  fill updates as transform rather than Layout events.
- **Done when**: the targeted indicators contain no `transition-all` or
  `transition-[width]`, and their visual and accessible values agree.
