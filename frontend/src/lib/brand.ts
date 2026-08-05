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
  name: "Revisit",
  tagline: "AI Guest Operating System",
  /** Compact line used under the product name in chrome */
  shortPitch: "AI-assisted guest revenue — human approved",
  /** Meta / share description */
  description:
    "Revisit — the AI Guest Operating System from Argus OS. Guest intelligence, Celebrate Rewards, approvals, and revenue after booking.",
  /** Suggested blurb when linking from the Argus product grid */
  productBlurb:
    "AI Guest Operating System. Syncs Cloudbeds, messages guests on WhatsApp/email, drafts review replies, and runs Stripe upsells — with manager approval on every commercial action.",
  siteUrl:
    process.env.NEXT_PUBLIC_REVISIT_SITE_URL || "https://revisit.argusai.online",
  parent: ARGUS,
  /** Browser / og title pattern */
  title: "Revisit · Argus OS",
  /** Footer / attribution */
  productOf: `A product of ${ARGUS.productLine}`,
  celebrateLoop: [
    "Guest leaves honest review",
    "Unlocks Birthday Reward",
    "Returns months later",
    "Hotel earns another booking",
  ],
} as const;
