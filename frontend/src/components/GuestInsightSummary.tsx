"use client";

/**
 * Guest Insight — GUEST_INSIGHT_CONTRACT.md §1, frozen v1.
 *
 * A summary layer above the existing, unchanged Evidence Chain
 * (Phase 4A) — never a rewrite or renormalization of it. Frozen
 * hierarchy: Evidence -> Insight -> Recommended action. Every line
 * here is built from the same `MemoryEvidence` the Evidence Chain
 * already renders; there is no separate data path.
 *
 * Only two of the four taxonomy states are reachable in this PR:
 *
 *   - Confirmed — every item this module renders, since
 *     `get_guest_memory_evidence` is confirmed-only by construction
 *     (unchanged, GUEST_MEMORY_EVIDENCE_CHAIN.md).
 *   - Empty — no qualifying evidence exists for this guest yet. Never
 *     rendered or read as "guest has no preferences" -- it means
 *     nothing has been explicitly stated and applied.
 *
 * "Needs review" is a real, named state in the frozen contract, but
 * ships with no trigger in this PR (GUEST_INSIGHT_CONTRACT.md's own
 * "Open finding" -- no GuestMemoryAgent pattern currently produces a
 * genuine dietary conflict, and adding one is explicitly out of scope
 * here). Nothing in this component fabricates that state to look more
 * complete than the system actually is. "Not tracked" already exists,
 * unchanged, inside the Evidence Chain itself (the per-field "no
 * linked message on record" case) -- this summary doesn't need a
 * second copy of that distinction.
 */

import type { MemoryEvidence } from "@/lib/api";

function CategoryTag({ category }: { category?: string | null }) {
  if (!category) return null;
  return (
    <span className="rounded-md bg-sea-500/10 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-sea-700">
      {category}
    </span>
  );
}

export function GuestInsightSummary({
  evidence,
  loading,
}: {
  evidence: MemoryEvidence[];
  loading?: boolean;
}) {
  return (
    <div className="rounded-2xl border border-ink-200/60 bg-white/70 p-5 backdrop-blur">
      <h3 className="font-display text-lg text-ink-900">Guest Insight</h3>
      <p className="mt-1 text-xs text-ink-400">
        What ReVisit knows about this guest, at a glance.
      </p>

      {loading ? (
        <p className="mt-4 text-sm text-ink-400">Loading…</p>
      ) : evidence.length === 0 ? (
        <p className="mt-4 text-sm text-ink-400">
          No confirmed guest insight yet — nothing has been explicitly stated and applied.
        </p>
      ) : (
        <ul className="mt-4 space-y-3">
          {evidence.map((item) => (
            <li key={item.field} className="flex items-start gap-2">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-1.5">
                  <CategoryTag category={item.category} />
                  <span className="rounded-md bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-emerald-700">
                    Confirmed
                  </span>
                </div>
                <p className="mt-1 text-sm text-ink-800">{item.insight}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
