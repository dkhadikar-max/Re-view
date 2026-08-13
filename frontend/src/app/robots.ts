import type { MetadataRoute } from "next";
import { REVISIT } from "@/lib/brand";

/**
 * SEO_AEO_GEO_AUDIT.md §7 — no robots.txt existed at all; every route
 * was indexable by default purely because nothing said otherwise.
 *
 * /app (the authenticated operator dashboard) is disallowed here AND
 * carries its own noindex meta (src/app/app/layout.tsx) — belt and
 * suspenders, since Disallow alone only stops crawling, not indexing
 * of a URL discovered elsewhere.
 *
 * /celebrate is deliberately NOT disallowed here. Its real privacy
 * control is a signed, time-limited (72h) JWT token, verified against
 * app/services/celebrate_rewards.py before this decision was made —
 * robots.txt Disallow would only stop crawling and wouldn't guarantee
 * a discovered token URL stays out of search results, so that route
 * instead carries a real noindex meta tag on the page itself
 * (src/app/celebrate/[token]/layout.tsx), which still applies even if
 * a crawler reaches it. Disallowing it here on top would actually
 * make that meta tag less reliable (a crawler that never fetches the
 * page can't see the noindex tag it's supposed to enforce).
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: ["/app", "/api"],
      },
    ],
    sitemap: `${REVISIT.siteUrl}/sitemap.xml`,
  };
}
