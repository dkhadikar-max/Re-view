import type { Metadata } from "next";

/**
 * SEO_AEO_GEO_AUDIT.md §7/§14 — this page renders real guest PII
 * (first name, property name, birthday/anniversary once submitted)
 * behind a signed JWT token (see app/services/celebrate_rewards.py's
 * create_guest_celebrate_token — 72h expiry, verified before this
 * decision). That token, not this noindex tag, is the actual access
 * control; noindex only reduces the chance a valid, unexpired link
 * gets discovered and surfaced by a search engine while it's live.
 * Deliberately a real meta tag here (not just a robots.txt Disallow)
 * so it still applies even if a crawler does reach the page once.
 */
export const metadata: Metadata = {
  robots: {
    index: false,
    follow: false,
  },
};

export default function CelebrateTokenLayout({ children }: { children: React.ReactNode }) {
  return children;
}
