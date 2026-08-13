import type { MetadataRoute } from "next";
import { REVISIT } from "@/lib/brand";

/**
 * SEO_AEO_GEO_AUDIT.md §7/§11 — only genuinely indexable, canonical
 * content goes here. /login is deliberately excluded (a bare auth
 * form is not something worth ranking); /celebrate/[token],
 * /activity, and /integrations are excluded per §7/§14 (per-guest
 * token page, and two dead redirect stubs with no unique content).
 */
export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  return [
    {
      url: REVISIT.siteUrl,
      lastModified: now,
      changeFrequency: "monthly",
      priority: 1,
    },
    {
      url: `${REVISIT.siteUrl}/onboard`,
      lastModified: now,
      changeFrequency: "monthly",
      priority: 0.8,
    },
  ];
}
