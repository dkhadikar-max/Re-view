/** Argus OS — parent platform branding for Revisit. */

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
  siteUrl:
    process.env.NEXT_PUBLIC_REVISIT_SITE_URL || "https://revisit.argusai.online",
  parent: ARGUS,
  celebrateLoop: [
    "Guest leaves honest review",
    "Unlocks Birthday Reward",
    "Returns months later",
    "Hotel earns another booking",
  ],
} as const;
