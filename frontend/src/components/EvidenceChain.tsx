"use client";

/**
 * Guest Memory Evidence Chain — Phase 4A (GUEST_MEMORY_EVIDENCE_CHAIN.md).
 *
 * One row per confirmed memory, collapsed to a single scannable line by
 * default — field, value, and the Guest Insight sentence — so a guest
 * with several confirmed preferences (or, longer term, hundreds of
 * guests reviewed in a session) doesn't force an operator to scroll
 * past a full 7-step chain for every fact. Expanding a row reveals the
 * whole chain: Guest -> Memory -> Evidence -> Guest Insight -> Hotel
 * Intelligence -> Action -> Outcome. Renders exactly what
 * `GET /guests/{id}/memory-evidence` returns — no step here invents a
 * capability the backend doesn't have:
 *
 *   - Evidence is the guest's own words, or an honest "no message on
 *     record" for anything logged before provenance existed.
 *   - Guest Insight and Hotel Intelligence are the backend's own
 *     fixed templates over real facts, never re-derived here.
 *   - Action never claims a team was "informed" — no restaurant/PMS
 *     notification integration exists yet.
 *   - Outcome is deliberately unclaimed — there is no closed-loop
 *     signal (a confirmed reservation, a completed task) wired to
 *     this chain yet. Shown as a distinct, muted step rather than
 *     silently omitted, so the chain's real boundary stays visible.
 */

import { useState } from "react";
import { ChevronDown, Quote, User } from "lucide-react";
import type { MemoryEvidence } from "@/lib/api";
import { cn } from "@/lib/utils";

function formatEvidenceDate(value?: string | null) {
  if (!value) return null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function ChainStep({
  label,
  children,
  muted,
}: {
  label: string;
  children: React.ReactNode;
  muted?: boolean;
}) {
  return (
    <div className="relative flex gap-3 pb-5 last:pb-0">
      <div className="flex flex-col items-center">
        <span
          className={cn(
            "mt-1 h-2 w-2 shrink-0 rounded-full",
            muted ? "bg-ink-200" : "bg-sea-500"
          )}
        />
        <span className="w-px flex-1 bg-ink-200/70 last:hidden" />
      </div>
      <div className="min-w-0 flex-1">
        <p
          className={cn(
            "text-[10px] font-medium uppercase tracking-wider",
            muted ? "text-ink-300" : "text-ink-400"
          )}
        >
          {label}
        </p>
        <div className={cn("mt-0.5 text-sm leading-relaxed", muted ? "text-ink-400" : "text-ink-800")}>
          {children}
        </div>
      </div>
    </div>
  );
}

function SingleEvidenceChain({
  guestName,
  evidence,
}: {
  guestName: string;
  evidence: MemoryEvidence;
}) {
  const [expanded, setExpanded] = useState(false);
  const date = formatEvidenceDate(evidence.evidence_date);

  return (
    <div className="rounded-2xl border border-ink-200/60 bg-white/70 backdrop-blur">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        className="flex w-full items-start gap-3 p-5 text-left"
      >
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h4 className="font-display text-base text-ink-900">{evidence.field_label}</h4>
            {evidence.confirmed && (
              <span className="rounded-md bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-emerald-700">
                Confirmed
              </span>
            )}
            <span className="text-sm font-medium text-ink-800">{evidence.value}</span>
          </div>
          <p className="mt-1 truncate text-xs text-ink-400">{evidence.insight}</p>
        </div>
        <ChevronDown
          className={cn(
            "mt-1 h-4 w-4 shrink-0 text-ink-300 transition-transform",
            expanded && "rotate-180"
          )}
        />
      </button>

      {expanded && (
        <div className="border-t border-ink-100 px-5 pb-5 pt-4">
          <ChainStep label="Guest">
            <span className="inline-flex items-center gap-1.5">
              <User className="h-3.5 w-3.5 shrink-0 text-ink-400" />
              Recognized at check-in and carried forward for this stay — {guestName}.
            </span>
          </ChainStep>

          <ChainStep label="Memory">
            <span className="font-medium text-ink-900">{evidence.value}</span>
          </ChainStep>

          <ChainStep label="Evidence">
            {evidence.evidence_quote ? (
              <div>
                <p className="flex gap-1.5 italic text-ink-700">
                  <Quote className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-300" />
                  <span>&ldquo;{evidence.evidence_quote}&rdquo;</span>
                </p>
                <p className="mt-1 text-xs text-ink-400">
                  {[evidence.evidence_channel, date].filter(Boolean).join(" · ") ||
                    "Source on record"}
                </p>
              </div>
            ) : (
              <p className="text-ink-400">
                No linked message on record — this memory was captured before per-message
                evidence was tracked.
              </p>
            )}
          </ChainStep>

          <ChainStep label="Guest Insight">{evidence.insight}</ChainStep>

          <ChainStep label="Hotel Intelligence">{evidence.hotel_intelligence}</ChainStep>

          <ChainStep label="Action">
            <span className="inline-flex items-center rounded-md bg-sea-500/10 px-2 py-0.5 text-xs font-medium text-sea-700">
              Available for this stay
            </span>
          </ChainStep>

          <ChainStep label="Outcome" muted>
            Not tracked yet — ReVisit doesn&apos;t have a closed-loop signal (e.g. a confirmed
            reservation update) wired to this chain today.
          </ChainStep>
        </div>
      )}
    </div>
  );
}

export function EvidenceChain({
  guestName,
  evidence,
  loading,
}: {
  guestName: string;
  evidence: MemoryEvidence[];
  loading?: boolean;
}) {
  return (
    <div className="rounded-2xl border border-ink-200/60 bg-white/70 p-5 backdrop-blur">
      <h3 className="font-display text-lg text-ink-900">Evidence Chain</h3>
      <p className="mt-1 text-xs text-ink-400">
        What ReVisit remembers about this guest, and where it came from. Click a preference to
        see the full chain.
      </p>

      {loading ? (
        <p className="mt-4 text-sm text-ink-400">Loading evidence…</p>
      ) : evidence.length === 0 ? (
        <p className="mt-4 text-sm text-ink-400">
          No confirmed memory for this guest yet — nothing has been explicitly stated and
          applied.
        </p>
      ) : (
        <div className="mt-4 space-y-3">
          {evidence.map((item) => (
            <SingleEvidenceChain key={item.field} guestName={guestName} evidence={item} />
          ))}
        </div>
      )}
    </div>
  );
}
