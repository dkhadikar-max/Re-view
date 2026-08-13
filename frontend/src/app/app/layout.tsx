import type { Metadata } from "next";

/**
 * SEO_AEO_GEO_AUDIT.md §7 — the authenticated operator dashboard had
 * no indexing control at all. Every page under /app/* is a Client
 * Component (uses hooks/state) and so can't export `metadata`
 * itself; this Server Component layout wraps them all and supplies
 * one, without changing any of their behavior or rendering.
 */
export const metadata: Metadata = {
  robots: {
    index: false,
    follow: false,
  },
};

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return children;
}
