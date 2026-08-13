/** Argus OS — parent platform branding for Revisit.
 *
 * Single source of truth for product naming across UI metadata,
 * shell chrome, and public trial surfaces.
 */

export const ARGUS = {
  name: "Argus",
  productLine: "Argus OS",
  tagline: "Decision operating system",
  siteUrl:
    process.env.NEXT_PUBLIC_ARGUS_SITE_URL || "https://argusai.online",
  githubUrl: "https://github.com/dkhadikar-max/ARGUS-OS",
} as const;

export const REVISIT = {
  name: "ReVisit",
  tagline: "The guest relationship layer for hotels",
  /** Compact line used under the product name in chrome */
  shortPitch: "Guest revenue & engagement — approval required for sensitive actions",
  /** Meta / share description */
  description:
    "ReVisit is the guest relationship layer for hotels — guest intelligence that remembers every preference, so every stay can be more personal.",
  siteUrl:
    process.env.NEXT_PUBLIC_REVISIT_SITE_URL || "https://revisit.argusai.online",
  parent: ARGUS,
  /** Browser / og title pattern */
  title: "ReVisit — Guest intelligence for hotels",
  /** Footer / attribution */
  productOf: `A product of ${ARGUS.productLine}`,
  /** Login / brand vision — not the Celebrate loop */
  vision: [
    "Every guest known before they arrive",
    "Every touchpoint guided by memory",
    "Every commercial action reviewed before it ships",
    "Lifetime that compounds stay after stay",
  ],
  celebrateLoop: [
    "Guest leaves honest review",
    "Unlocks Birthday Reward",
    "Returns months later",
    "Hotel earns another booking",
  ],
} as const;
