import Link from "next/link";
import { ARGUS, REVISIT } from "@/lib/brand";

/**
 * Public marketing homepage — Direction B (Contemporary Hospitality) as the
 * system, with Direction A (Quiet Luxury) restraint applied here in the
 * hero and, later, the closing pilot CTA specifically (see the design
 * direction decision this PR implements).
 *
 * Scope for this PR: hero only. The remaining Phase 6 sections (How It
 * Works, Guest Experience, Why ReVisit, Hotel Operator, Real Product,
 * Pilot CTA) land in their own follow-up PRs per the agreed sequence —
 * this PR is foundation + routing, not the finished homepage.
 */
export default function HomePage() {
  return (
    <div className="min-h-screen bg-hero-wash bg-grain">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6 md:px-10">
        <div className="animate-fade-in opacity-0">
          <p className="text-[10px] font-medium uppercase tracking-[0.18em] text-sea-700">
            {ARGUS.productLine}
          </p>
          <p className="font-display text-lg text-ink-950">{REVISIT.name}</p>
        </div>
        <Link
          href="/login"
          className="animate-fade-in text-sm font-medium text-ink-700 opacity-0 underline-offset-2 hover:text-sea-700 hover:underline [animation-delay:80ms]"
        >
          Sign in
        </Link>
      </header>

      <main className="mx-auto flex max-w-4xl flex-col items-center px-6 pb-32 pt-20 text-center md:pt-32">
        <h1 className="animate-fade-up text-balance font-display text-display-lg text-ink-950 opacity-0 [animation-delay:120ms] md:text-display-xl lg:text-display-2xl">
          The hotel concierge that turns conversations into action.
        </h1>

        <p className="animate-fade-up mt-8 max-w-xl text-balance text-lg leading-relaxed text-ink-600 opacity-0 [animation-delay:260ms]">
          Guests ask. ReVisit understands. Your team acts.
        </p>

        <div className="animate-fade-up mt-10 flex flex-col items-center gap-3 opacity-0 [animation-delay:380ms] sm:flex-row">
          <Link
            href="/onboard"
            className="inline-flex items-center justify-center rounded-lg bg-sea-600 px-6 py-3 text-sm font-medium text-white shadow-sm shadow-sea-600/20 transition hover:bg-sea-700"
          >
            Discuss a pilot
          </Link>
        </div>
      </main>
    </div>
  );
}
