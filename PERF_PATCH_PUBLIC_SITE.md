# Public Site Scroll Performance Patch — implemented, not yet merged

Status: **Implementation complete, verified, pending PR review.** Grounded
in a direct read of the shipped `SignatureSequence.tsx`/`Hero.tsx`/
`marketing.css` (PR #45) — every finding below was confirmed against
the real code before anything was changed, not assumed.

## Findings, verified against the real code

1. **900vh + `position: sticky`** — `marketing.css:80-81`. Confirmed.
2. **Per-frame layout reads** — `SignatureSequence.tsx`'s scroll RAF
   called `getBoundingClientRect()`, `offsetHeight`, and read
   `window.innerHeight` every frame it ran. Confirmed (already
   correctly throttled to once per animation frame via a `ticking`
   flag — the frequency claim was about the read cost per frame, not
   about the throttling, which was already correct).
3. **Both images loaded eagerly** — the hospitality `<img>` had no
   `loading` attribute and was mounted with a real `src` from page
   load, just `opacity: 0`. Confirmed.
4. **Full-viewport `feTurbulence`** — `Hero.tsx`, `numOctaves={3}`,
   `stitchTiles="stitch"`, at 100%×100%. Confirmed.
5. **Stacked compositing** — `mix-blend-mode` (×4), inset
   `box-shadow`, `backdrop-filter: blur`, `will-change`. Confirmed.

One correction: passive scroll listeners were already in place in
both files before this patch — nothing to change there.

## What changed

**Patch A — no visual/product change:**
- `SignatureSequence.tsx`: geometry (`offsetTop`, `total`) now cached
  once on mount + recomputed on resize, not on every scroll frame.
  `stageTop` is now `offsetTop - window.scrollY` (arithmetic on an
  already-free value) instead of `getBoundingClientRect()`.
- The hospitality image is mounted with no `src` and stays unpainted
  until `ensureHospLoaded()` sets it — triggered a beat early
  (`action-team`) so it has time to decode before its pulse-in, with
  `hospActive` as a safety net for the rail's `jumpTo()` landing
  directly on a later beat.
- `Hero.tsx`'s SVG `feTurbulence` filter replaced with a precomputed,
  tiled 64×64 noise PNG (`marketing.css`'s `.rv-grain`, quantized to
  16 colors to keep the embed small — ~2.2KB). **Opacity corrected to
  match**: the original SVG compounded two opacities (0.35 outer ×
  0.05 inner rect ≈ 0.0175 effective) — the single replacement element
  carries that combined value directly (`opacity: 0.0175`), not the
  outer 0.35 alone, which would have made the grain ~20x more visible
  and been a real regression.
- `.rv-ground` gained `isolation: isolate; contain: layout paint` —
  gives each ground layer its own compositing/stacking boundary so
  its `mix-blend-mode` layers don't negotiate against the rest of the
  page. Purely a compositing-boundary change; renders identically.

**Patch B — UX, one number:**
- `.rv-sequence-wrap` height: `900vh` → `750vh` (middle of the
  700-750vh range discussed). `RANGES` in `SignatureSequence.tsx` are
  fractional (0-1), so every beat's relative pacing and order is
  unchanged — this compresses total scroll distance uniformly. Flagged
  as tunable further against real device/user testing, not a final
  number.

**Removed** (explicit follow-up decision, not part of the original
patch scope): the `rv-act-marker` chapter-label UI ("ACT V —
Experience", "FINAL FRAME — Revisit") — refs, scroll-handler logic,
JSX, and both CSS rule blocks (including the mobile `display: none`
override) removed entirely from `SignatureSequence.tsx` and
`marketing.css`.

## Verification

- Frontend typecheck: clean.
- Production build (`next build`): compiled successfully, all 21
  static pages generated including `/`.
- Browser QA, desktop + mobile, real dev server:
  - Zero `hospitality.jpg` network request at page load; exactly one
    on-demand fetch (200 OK) once the sequence approaches its beat.
  - Visual continuity confirmed at Hero, Act II ("Good to be back"),
    Act IV ("Team informed" panel), Act V, and Final Frame — content,
    copy, and transitions unchanged from the pre-patch version.
  - No Act-marker label rendered anywhere after removal (previously
    visible top-left at every non-"world" beat).
  - No console errors in a fresh tab (a same-tab console read
    surfaced stale entries from mid-edit HMR reloads — not present in
    the final state).

## Explicitly not touched

Guest Insight, Evidence Chain, memory model, WhatsApp architecture,
approved visual direction (images, copy, story beats), any backend
file. Diff is exactly 3 files: `Hero.tsx`, `SignatureSequence.tsx`,
`marketing.css`.
