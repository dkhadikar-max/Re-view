# SEO / AEO / GEO / AI Search Audit — read-only, nothing implemented yet

Status: **Audit only, per explicit instruction.** Every finding below
is grounded in a direct read of the real, current code on `main`
(`858424d`) — `src/app/layout.tsx`, `src/app/page.tsx`,
`src/lib/brand.ts`, `src/components/marketing/*`, `next.config.ts`,
and the full `src/app` route tree. Nothing was assumed. This document
does not change anything and does not authorize implementation on its
own — per the instruction, gaps get reviewed and approved before any
code changes.

---

## 1. Route inventory (ground truth for everything below)

| Route | Type | Current state |
|---|---|---|
| `/` | Public marketing homepage | Real content, no dedicated metadata beyond root layout |
| `/onboard` | Public trial signup (the hero CTA's actual destination) | Real content, **zero dedicated metadata** — inherits the generic root title/description |
| `/login` | Public auth form | No dedicated metadata |
| `/celebrate/[token]` | Guest-facing, **per-guest tokenized** reward page | Dynamic (`ƒ`), no metadata, no robots directive |
| `/activity` | **Dead stub** — `redirect("/app")`, comment: "Event stream removed from the product surface" | Not real content |
| `/integrations` | **Dead stub** — `redirect("/app")`, comment: "Integrations UI removed from the product surface" | Not real content |
| `/app/*` (guests, settings, tasks, revenue, reviews, …) | Authenticated operator dashboard | **No `noindex`, no auth-gate-aware robots directive anywhere in the codebase** |
| `/api/*` | API proxy route | Not an HTML page; not a crawl concern |

**Only `/` and `/onboard` are genuine public marketing/conversion
content today.** Everything else is either authenticated, a dead
redirect stub, or a tokenized guest-specific page.

## 2. Metadata (`src/app/layout.tsx`)

```ts
export const metadata: Metadata = {
  title: REVISIT.title,          // "Revisit · Argus OS"
  description: REVISIT.description,
  applicationName: REVISIT.name,
};
```

- **No `metadataBase`** — required for Next.js to resolve any relative
  OG/Twitter image URL to an absolute one. Currently a hard blocker to
  adding OG images correctly.
- **No canonical URL** anywhere, on any route.
- **No Open Graph fields** (`openGraph: {...}`) at all.
- **No Twitter/X card fields** (`twitter: {...}`) at all.
- **No icons/favicon config** — see §6.
- **No `robots` field** — see §7.
- **No per-route metadata** on `/onboard`, `/login`, or `/celebrate/[token]`
  — every page shares the one root title/description.
- `lang="en"` **is** correctly set on `<html>` — one real thing already right.

### Current title and description, verbatim (`src/lib/brand.ts`)

- Title: `"Revisit · Argus OS"` — leads with the parent brand, not
  ReVisit itself, and communicates nothing about what the product
  does. Directly the problem the brief's §2/§3/§7 describe.
- Description: `"Revisit — the Guest Experience Platform from Argus
  OS. Guest intelligence, Celebrate Rewards, approvals, and revenue
  after booking."` — leads with "Guest Experience Platform" (not the
  requested "guest intelligence" framing), and lists internal feature
  names ("Celebrate Rewards, approvals") that mean nothing to an
  outside searcher or an AI system trying to categorize the product.
- `productBlurb` (unused in metadata today, but worth flagging before
  it becomes a copy source): *"Syncs Cloudbeds, messages guests on
  WhatsApp/email, drafts review replies, and runs Stripe upsells —
  with manager approval on every commercial action."* **This needs a
  capability check before any of it is reused as public copy** — this
  audit did not verify whether Stripe/review-reply-drafting are live,
  shipped capabilities or aspirational roadmap items. Flagging per the
  Product Truth Principle rather than asserting either way.

## 3. Heading hierarchy & semantic structure

- **One real `<h1>`** exists: `Hero.tsx` — "Every guest conversation
  can become hotel action." Correctly a single H1, present in the
  initial render (not injected only after scroll/JS).
- **Zero `<h2>`/`<h3>` anywhere on the homepage.** Every other piece of
  copy in `SignatureSequence.tsx` (the Act II–V content: "A returning
  guest, on their third stay," "Vegetarian dining preference," "Team
  informed," etc.) is rendered as `<p>`, `<span>`, or `<b>` — never a
  heading. There is no crawlable section structure beneath the H1 at
  all today.
- This matters independent of the animation: the *text* is present in
  server-rendered HTML (see §5) — the gap is that nothing marks it as
  structured content a machine can section and rank by importance.

## 4. Internal linking

- `MarketingNav.tsx`: exactly one link, "Sign in" → `/login`.
- `Hero.tsx`: exactly one link, "Discuss a pilot →" → `/onboard`.
- **Total internal links on the homepage: 2.** No links to any
  supporting content (none exists yet — see §11), no descriptive
  anchor text to evaluate yet since there's nothing to link to.
- This is a direct, unavoidable consequence of §11 (no supporting
  pages exist) as much as it is a linking problem on its own.

## 5. JavaScript rendering / crawlability of the cinematic content

**This is better than it might look.** `SignatureSequence.tsx`'s beat
panels (`rv-beat-panel`, `rv-hosp-line`) are always present in the JSX
— they start at `opacity: 0` and get a `.on` class toggled by scroll
position, but **the text itself is never conditionally rendered**.
Server-rendered HTML for `/` already contains every beat's real
copy — "A returning guest, on their third stay," "Vegetarian dining
preference," "Restaurant & service team informed," "They shouldn't
have to tell you twice," "Guest intelligence for hospitality." — *not*
gated behind client-side JS execution. A crawler or an AI system
reading raw HTML already sees this content.

**The gap is not crawlability of content that exists — it's that this
content isn't marked up as the site's actual meaning.** It reads to a
machine as a sequence of unlabeled paragraphs inside an opacity
animation, not as "here is what ReVisit does, here is how it works."
Per the brief's own framing: don't make meaning *depend* on the
animation (already true) — but also don't make meaning depend on a
machine inferring structure from scroll-choreography copy alone.

## 6. Site identity / favicon

**No custom favicon exists.** `public/` contains only the unmodified
Next.js starter SVGs (`file.svg`, `globe.svg`, `next.svg`,
`vercel.svg`, `window.svg`) — no `favicon.ico`, no `icon.png`, no
`apple-icon`, nothing in `src/app` matching Next's file-based icon
convention. The browser tab currently shows either a blank icon or a
default. This is a real, visible gap, independent of any SEO scoring.

## 7. `robots.txt` / `sitemap.xml` / crawl control

- **No `robots.txt`** — no `src/app/robots.ts`, no `public/robots.txt`.
- **No `sitemap.xml`** — no `src/app/sitemap.ts`, no static file.
- **No `noindex` anywhere** — not on `/app/*` (authenticated), not on
  `/celebrate/[token]` (tokenized, guest-specific), not on the dead
  `/activity`/`/integrations` redirect stubs.
- **No `middleware.ts`** exists to add any crawl/index control at the
  routing layer either.
- Net effect: **every route in this app is currently indexable by
  default**, including the operator dashboard and guest-token pages,
  simply because nothing says otherwise. Authenticated routes would
  hit an auth wall if actually crawled, but an indexed, auth-gated
  `/app/guests` URL showing up in search results is still not
  correct practice, and `/celebrate/[token]` URLs are guest-specific
  tokens that have no business being crawlable at all.

## 8. Structured data (JSON-LD)

**None exists anywhere in the codebase.** No `Organization`, no
`WebSite`, no `SoftwareApplication`/`Service`, no `FAQPage`, no
`BreadcrumbList`. A full gap, not a partial one.

## 9. Open Graph / Twitter / share preview

**None exists.** Sharing the homepage link today (Slack, Twitter/X,
iMessage, LinkedIn) would show whatever bare fallback the platform
generates from the raw title/description — no image, no curated
preview.

## 10. Images: alt text, dimensions, loading

- **Every image on the homepage has `alt=""`** — 11 occurrences across
  `Hero.tsx` and `SignatureSequence.tsx` (including its
  `StaticFallback`). This is *defensible* for the sticky-stage
  background photos, which sit behind meaningful text overlays and
  arguably qualify as decorative — empty alt is the textbook-correct
  pattern for genuinely decorative images, not a blanket error. It's
  a closer call for the Hero's `arrival.jpg`, which is a specific,
  licensed, credited photo (the credit line names it explicitly in
  visible text) and could reasonably carry real alt text. Flagging as
  a judgment call for the review step, not asserting either way.
- **No explicit `width`/`height`** on any of these `<img>` tags — they
  rely entirely on CSS (`position: absolute; inset: -4%; width: 108%;
  height: 108%`) for sizing, which is consistent with the
  scroll-driven full-bleed design, but means there's no intrinsic
  size hint for the browser's layout engine before CSS loads.
  Practically low CLS risk here since these are `position: absolute`
  layers with no reflow effect on surrounding content either way —
  noting for completeness, not flagging as urgent.
- **Deferred loading**: already correctly handled by the just-merged
  performance patch (PR #50) — the hospitality image loads on demand,
  not eagerly. Not a new gap.

## 11. Supporting content pages

**None exist.** No `/guest-intelligence`, `/how-it-works`,
`/guest-memory`, `/hotel-guest-experience`, `/security`, `/faq`, or
similar. The entire public site is the single homepage plus the
signup form. This is the direct cause of §4's thin internal-linking
graph — there's genuinely nothing yet to link *to*.

## 12. `llms.txt`

Does not exist. Given the AEO/GEO framing, worth evaluating — but per
the brief's own instruction, only if there's enough real, authoritative
content to summarize; right now that content (the answer blocks,
supporting pages) doesn't exist yet either, so an `llms.txt` today
would have almost nothing accurate to point to.

## 13. Performance baseline (carried over from PR #50, not re-audited here)

PR #50 already addressed the scroll-performance findings (900vh→750vh,
cached scroll geometry, deferred hospitality image, replaced
`feTurbulence` with a static noise tile, compositing isolation). Font
loading is already well-handled — `next/font/google` (Fraunces,
Outfit) self-hosts and subsets fonts automatically, no external font
request, automatic `font-display` handling. This audit did not re-run
Lighthouse/Core Web Vitals numbers; that's listed as a verification
step (§7 of the task) to run *after* implementation, not part of the
audit itself, since the SEO/AEO changes below are markup/metadata
additions that shouldn't meaningfully move LCP/CLS/INP on their own —
worth confirming empirically once implemented, not assuming.

## 14. Duplicate / thin content, 404 / redirect behavior

- `/activity` and `/integrations` are both real, live routes that
  serve **no unique content** — pure redirects to `/app`, with
  explicit code comments confirming the underlying features were
  removed. If either were ever indexed, they'd read as broken or
  pointless pages. Not currently linked from anywhere in the public
  site, so low risk today, but worth an explicit `noindex` or a real
  `410 Gone` if search engines ever discover them independently
  (e.g., from an old external link).
- No custom 404 page was found (`src/app/not-found.tsx` doesn't
  exist) — Next.js serves its default. Not investigated further since
  it wasn't in the explicit checklist beyond "404/redirect behavior,"
  and a default 404 is not a factual-accuracy or product-truth
  concern, just a polish item.

## 15. Accessibility signals relevant to machine comprehension

- Single H1, present — good.
- Zero landmark elements beyond the implicit `<nav>`/`<body>` — no
  `<main>`, no `<section>` boundaries anywhere in `page.tsx` or its
  children.
- `prefers-reduced-motion` is already handled thoroughly — confirmed
  in `SignatureSequence.tsx`'s `StaticFallback` component (every beat
  rendered in normal document flow, always visible, no scroll-linked
  animation) and in `marketing.css`'s reduced-motion media query. This
  is a genuine existing strength, not a gap.
- Link text: "Sign in" and "Discuss a pilot →" are both reasonably
  descriptive already; no "click here"/"learn more" anti-patterns
  found in the current 2-link inventory.

---

## Summary: what's actually missing, ranked by how foundational it is

1. **No canonical entity identity in metadata** — title leads with
   "Argus OS," description uses "Guest Experience Platform" and
   internal feature names instead of "guest intelligence for
   hospitality." (§2)
2. **No structured data at all** — zero JSON-LD. (§8)
3. **No canonical URL, no OG, no Twitter card, no `metadataBase`.** (§2, §9)
4. **No `robots.txt`, no `sitemap.xml`, no noindex on authenticated or
   tokenized routes.** (§7)
5. **No favicon.** (§6)
6. **No semantic section structure (H2/H3) beneath the single H1** —
   real content exists in HTML already, just unmarked. (§3, §5)
7. **No supporting content pages** — direct cause of thin internal
   linking. (§4, §11)
8. **No AEO answer-block content anywhere** (what is ReVisit / is it a
   chatbot / how does it remember preferences, etc.) — not started.

## What this audit does not do

It does not implement anything. It does not decide which supporting
pages get built, what the final title/description copy is, or what
schema gets added — those are the "review the audit and identify
actual gaps" step, per the instruction. It does not re-verify product
capabilities (Stripe, review-reply drafting) referenced in
`productBlurb` — flagged for whoever writes new copy to check first,
not resolved here.
