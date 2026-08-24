import Link from "next/link";
import { Sparkles } from "lucide-react";

/**
 * P4 onboarding audit (CTO P0) — "make sample data impossible to
 * misunderstand." Shown persistently across every /app page while
 * Property.has_real_data is false (every trial workspace starts this way
 * — see hotel_signup.py's seed_trial_demo_data), auto-hidden the moment a
 * real guest/reservation is imported (import_orchestrator.py's
 * mark_real_data_imported flips the flag server-side; no client logic
 * needed here beyond reading it).
 */
export function SampleDataBanner() {
  return (
    <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-300/70 bg-amber-50 px-4 py-3 text-amber-900">
      <div className="flex items-start gap-2.5">
        <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
        <p className="text-sm leading-relaxed">
          <span className="font-medium">Sample workspace.</span>{" "}
          You&apos;re exploring ReVisit with example hotel data. Import your
          guests to see your hotel&apos;s memory layer.
        </p>
      </div>
      <Link
        href="/app/import"
        className="shrink-0 whitespace-nowrap rounded-lg border border-amber-400 bg-white px-3 py-1.5 text-xs font-medium text-amber-800 transition hover:bg-amber-100"
      >
        Import your data →
      </Link>
    </div>
  );
}
