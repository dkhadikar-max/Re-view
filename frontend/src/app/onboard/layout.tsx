import type { Metadata } from "next";
import { REVISIT } from "@/lib/brand";

/**
 * SEO_AEO_GEO_AUDIT.md §11 — the hero's actual CTA destination
 * ("Discuss a pilot →") had zero dedicated metadata, inheriting the
 * generic homepage title/description. Kept indexable per explicit
 * decision (real onboarding content, not a thin page).
 */
export const metadata: Metadata = {
  title: "Start a hotel trial",
  description:
    "Set up a ReVisit trial workspace for your hotel — guest intelligence built from your own guest conversations and history.",
  alternates: {
    canonical: "/onboard",
  },
};

export default function OnboardLayout({ children }: { children: React.ReactNode }) {
  return children;
}
