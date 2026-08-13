# SEO / AEO / GEO Implementation — findings 1–8, verified

Status: **Implemented, verified, pending PR review.** Implements
`SEO_AEO_GEO_AUDIT.md`'s 8 findings exactly as scoped and approved —
1–6 in full, 7 as information-architecture improvement (no thin
pages), 8 as concise, verifiable AEO content. The audit stays the
baseline record and was not rewritten to look cleaner than what it
found.

## What changed, per finding

### 1–2. Metadata + canonical identity (`layout.tsx`, `brand.ts`)

- Title: `"Revisit · Argus OS"` → `"Guest Intelligence for Hotels |
  Revisit"`. ReVisit is now the primary entity; Argus OS stays the
  parent relationship (title template `%s | Revisit` for child
  routes), not the headline.
- Description: dropped "Guest Experience Platform" + internal feature
  names ("Celebrate Rewards, approvals") in favor of the locked
  positioning: *"ReVisit turns guest conversations and history into
  intelligence hotel teams can act on — recognizing returning guests,
  remembering preferences, and carrying context into every stay."*
- `metadataBase`, `alternates.canonical`, and a default `robots:
  {index: true, follow: true}` all added at the root — previously
  absent.
- `productBlurb` (Stripe upsells, review-reply drafting) was **not**
  touched or reused anywhere, per the explicit instruction to verify
  those capabilities before using that copy.

### 3. JSON-LD (`StructuredData.tsx`)

Four types, each individually justified — **not** the original five.
`WebPage` was reconsidered during implementation and dropped: it
mostly duplicated title/description/canonical, has no Google
rich-result behavior of its own, and its only distinct property
(`isPartOf`) was thin value for the duplication. The reasoning for
every remaining type (including why `Service` won't produce a rich
result, and Google's 2023 restriction on `FAQPage` rich-result
eligibility to authoritative gov/health sites) is documented directly
in the component's own comment block, not just here.

- `Organization` — name, url, `parentOrganization` (Argus OS) — all
  plain fact.
- `WebSite` — name, url.
- `Service` — `serviceType`/`description`/`audience` pulled from the
  same locked description and "hotels and hospitality operators"
  framing already visible on the page. Kept for GEO entity clarity,
  not a SERP feature.
- `FAQPage` — generated from `answerBlocksData.ts`'s `ANSWER_BLOCKS`
  array, the same array `AnswerBlocks.tsx` renders visibly. One source
  of truth — the schema cannot drift from the visible page, because
  it's the same data.

No ratings, reviews, pricing, customer counts, awards, or integration
claims anywhere in the graph.

### 4. `robots.ts` + `sitemap.ts` + indexing policy

- `robots.txt`: `Allow: /`, `Disallow: /app`, `Disallow: /api`.
  `/celebrate` is **deliberately not** disallowed here — see below.
- `sitemap.xml`: exactly `/` and `/onboard`. `/login` excluded (a bare
  auth form isn't worth ranking); `/celebrate/[token]`, `/activity`,
  `/integrations` excluded (tokenized guest page, and two dead
  redirect stubs with no unique content).
- `/app/*` noindex: a new `src/app/app/layout.tsx` Server Component
  supplies `robots: {index: false, follow: false}` to the entire
  authenticated tree — every page under it is a Client Component and
  couldn't export metadata itself, so this was the correct mechanism,
  not a per-page change.
- `/celebrate/[token]` noindex: **investigated before deciding**, per
  the explicit instruction that robots directives aren't a security
  control. Read `app/services/celebrate_rewards.py`'s
  `create_guest_celebrate_token` directly: the token is a signed JWT
  with a 72-hour expiry — real, independent access control, not
  security-by-obscurity. This page also renders real guest PII (first
  name, property name, and once submitted, birthday/anniversary) once
  a valid token resolves. Conclusion: the JWT signature + expiry is
  and remains the actual security boundary; `noindex` is an honest,
  additive reduction in *discovery* surface (keeps a still-valid link
  from being crawled/cached/surfaced in search results), implemented
  as a **real meta tag** (`src/app/celebrate/[token]/layout.tsx`), not
  a `robots.txt` `Disallow` — a `Disallow` only stops crawling and
  wouldn't guarantee a discovered URL stays out of results, while the
  meta tag holds even if a crawler does reach the page once.

Both noindex decisions verified against the actual server-rendered
HTML (`curl`), not just the file existing — see Verification below.

### 5. Favicon (`icon.tsx`)

None existed before (`public/` had only the unmodified Next.js
starter SVGs). Added a minimal, explicitly-temporary placeholder — a
single-letter "R" mark in the site's own dusk/signal colors, generated
via `next/og`'s `ImageResponse`, same "clearly a stand-in, not a
design decision" framing already used for the licensed marketing
photography (`CREDITS.md`).

### 6. H2/H3 semantic hierarchy

Added entirely inside the **new** `AnswerBlocks` section — one H2
("About ReVisit"), six H3s (one per question) — rather than retrofitted
into `SignatureSequence.tsx`'s own copy. **Zero changes to
`Hero.tsx`/`SignatureSequence.tsx`** (confirmed via diff — neither
file appears in `git status` for this branch); the cinematic sequence
and its already-verified PR #50 performance work are untouched. The
homepage's meaning no longer depends on the animation to exist in
crawlable HTML — it existed there already (Phase 4A precedent applies
here too: the sequence's own copy was always server-rendered, just
unmarked) — and now also has a real, separate, permanent section
stating it plainly.

### 7. Information architecture (no new pages)

No new routes created. `/onboard` — the hero's actual CTA destination
— got dedicated metadata (title, description, canonical) instead of
inheriting the generic homepage description, per the explicit decision
to keep it as real content worth indexing rather than build thin pages
for URL volume.

### 8. AEO answer content (`answerBlocksData.ts`, `AnswerBlocks.tsx`)

Six question/answer pairs, all grounded in real, shipped capability —
`MemoryManager`'s confirmed-only memory, the Evidence Chain's
quote-linked provenance, and the "not a chatbot" positioning using
close to the exact language given for that answer. No claims about
WhatsApp specifics, cross-hotel memory, predictive scoring, autonomous
actions, or anything not already verified elsewhere in this
repository's own frozen contracts (`MEMORY_MANAGER.md`,
`GUEST_MEMORY_EVIDENCE_CHAIN.md`, `PHASE4_PRODUCT_REVIEW.md`).

## A real bug found and fixed during implementation

`AnswerBlocks.tsx` (component) and the original `answerBlocks.ts`
(data file) differ only by the first letter's case — which
`next build` correctly failed on: Windows' filesystem is
case-insensitive, so these were the same file on disk even though git
and macOS/Linux treat them as distinct. Renamed the data file to
`answerBlocksData.ts`. Confirmed via a second clean typecheck + build
after the fix, not assumed fixed.

## Verification

1. **Frontend typecheck**: clean (twice — once before the case-fix,
   confirming the bug, once after).
2. **Production build**: succeeded, 26/26 static pages generated,
   including the new `/icon`, `/opengraph-image`, `/twitter-image`,
   `/robots.txt`, `/sitemap.xml` routes.
3. **Generated output inspected directly** (not assumed):
   - `robots.txt`: `curl`'d — exact `Allow`/`Disallow`/`Sitemap`
     content confirmed.
   - `sitemap.xml`: `curl`'d — exactly `/` and `/onboard`, correct
     `lastmod`/`priority`.
   - Homepage `<head>`: inspected via `document.querySelector` in a
     real browser tab — title, canonical, meta description, OG
     title/description/image/type, Twitter card/image, `robots`
     meta (`index, follow`), favicon link, and the JSON-LD script
     (4 nodes, `WebPage` correctly absent) all present and correct.
   - `/onboard`: dedicated title (`"Start a hotel trial | Revisit"`
     — title template applied correctly), dedicated canonical,
     `index, follow` confirmed via `curl`.
4. **`/app/*` and `/celebrate/[token]` indexing**: verified via `curl`
   against the **raw server response**, not the browser's live DOM
   (which had already client-redirected `/app/guests` to `/login` by
   the time it was inspected — expected auth-guard behavior, not a
   verification gap, since the noindex tag is in the initial HTML a
   crawler actually receives). Both routes confirmed
   `<meta name="robots" content="noindex, nofollow"/>` in the raw
   response.
5. **Browser QA, desktop + mobile**: heading hierarchy confirmed (one
   H1, one H2, six H3s, correctly nested); `AnswerBlocks` section
   screenshotted at both viewport sizes — dark editorial palette,
   Fraunces display heading, hairline dividers, matches the rest of
   the site's restraint; descriptive CTA anchor text ("Start a hotel
   trial with ReVisit →", not "Learn more").
6. **Reduced motion**: not re-screenshotted — `git diff` confirms zero
   changes to `SignatureSequence.tsx` (its `StaticFallback` component
   is the entire reduced-motion path) and `marketing.css`'s diff is
   19 insertions, 0 deletions, purely additive. Nothing in the
   reduced-motion path changed, so its already-verified PR #50 state
   still applies; re-testing something unmodified wasn't performed.
7. **Performance**: no formal Lighthouse run in this environment, so
   the claim here is architectural, not a measured score —
   `AnswerBlocks.tsx` and `StructuredData.tsx` are Server Components
   (no `"use client"`), adding zero client-side JavaScript; the JSON-LD
   script adds ~2.9KB to the HTML response; `icon.tsx`/
   `opengraph-image.tsx`/`twitter-image.tsx` are server-generated
   image routes never fetched by a regular page visitor. No scroll
   handler, animation, or image-loading code from PR #50 was touched.
8. **Diff audit**: `git status` shows zero backend files, zero changes
   to `Hero.tsx`/`SignatureSequence.tsx`, zero changes to any Guest
   Insight/Evidence Chain file. Grepped every new/changed file for
   "predict/autonomous/whatsapp/cross-hotel/customer/integration/
   award/rating/review" — every hit is either an explicit
   guardrail comment (documenting what was deliberately *not*
   claimed) or unrelated diff context; no such claim actually
   shipped in metadata, JSON-LD, or visible copy.

## Known limitations / deferred work

- Favicon is a placeholder monogram, not a real logo mark — same
  "temporary, not a design decision" status as the licensed
  photography.
- `llms.txt` was not implemented — the audit's own conclusion was that
  there wasn't yet enough authoritative content to summarize; that's
  less true now that `AnswerBlocks` exists, worth revisiting as its
  own small follow-up rather than folding in here.
- No formal Lighthouse/Core Web Vitals numbers were captured (tooling
  not available in this environment) — the "no regression" conclusion
  is architectural (see §7 above), not measured. Worth a real
  Lighthouse pass in CI or manually before/if this becomes a launch
  blocker concern.
- `/login` was left without dedicated metadata or an explicit robots
  override — inherits the site default (`index, follow`). Not flagged
  as a gap requiring a decision in this PR; noted for whoever reviews
  in case the call should go the other way.
