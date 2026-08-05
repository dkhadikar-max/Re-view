"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Check, Search, Sparkles, UserPlus } from "lucide-react";
import { TopBar } from "@/components/TopBar";
import { Badge, Empty, Panel } from "@/components/ui";
import {
  api,
  type Guest,
  type GuestOpportunity,
} from "@/lib/api";
import { cn, formatCurrency } from "@/lib/utils";

function healthTone(health?: string) {
  if (health === "loyal") return "bg-emerald-500/15 text-emerald-700";
  if (health === "at_risk") return "bg-coral-500/15 text-coral-600";
  return "bg-sand-200/80 text-ink-700";
}

function healthDot(health?: string) {
  if (health === "loyal") return "bg-emerald-500";
  if (health === "at_risk") return "bg-coral-500";
  return "bg-sand-400";
}

function formatShortDate(value?: string | null) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

function Metric({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="rounded-xl bg-white/5 px-3 py-2.5">
      <p className="text-[10px] uppercase tracking-wider text-ink-400">{label}</p>
      <p className="mt-0.5 font-display text-xl text-white">{value}</p>
      {hint && <p className="text-[11px] text-ink-400">{hint}</p>}
    </div>
  );
}

export default function GuestsPage() {
  const [guests, setGuests] = useState<Guest[]>([]);
  const [opportunities, setOpportunities] = useState<GuestOpportunity[]>([]);
  const [selected, setSelected] = useState<Guest | null>(null);
  const [loading, setLoading] = useState(true);
  const [highlightId, setHighlightId] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [minSpend, setMinSpend] = useState("");
  const [minStays, setMinStays] = useState("");
  const [birthdayMonth, setBirthdayMonth] = useState(false);
  const [inactiveDays, setInactiveDays] = useState("");

  useEffect(() => {
    if (typeof window === "undefined") return;
    const id = new URLSearchParams(window.location.search).get("guest");
    if (id) setHighlightId(id);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {
        q: q.trim() || undefined,
        min_spend: minSpend ? Number(minSpend) : undefined,
        min_stays: minStays ? Number(minStays) : undefined,
        birthday_month: birthdayMonth || undefined,
        inactive_days: inactiveDays ? Number(inactiveDays) : undefined,
      };
      const [g, opp] = await Promise.all([
        api.guests(params),
        api.guestOpportunities(),
      ]);
      setGuests(g);
      setOpportunities(opp);
      setSelected((prev) => {
        if (!g.length) return null;
        if (highlightId) {
          const hit = g.find((x) => x.id === highlightId);
          if (hit) return hit;
        }
        const still = prev ? g.find((x) => x.id === prev.id) : null;
        return still || g[0];
      });
    } finally {
      setLoading(false);
    }
  }, [q, minSpend, minStays, birthdayMonth, inactiveDays, highlightId]);

  useEffect(() => {
    const t = setTimeout(() => {
      void load();
    }, 200);
    return () => clearTimeout(t);
  }, [load]);

  function selectOpportunity(opp: GuestOpportunity) {
    const match = guests.find((g) => g.id === opp.guest_id);
    if (match) {
      setSelected(match);
      return;
    }
    void api.guest(opp.guest_id).then(setSelected);
  }

  const nba = selected?.next_best_action;

  return (
    <div>
      <TopBar
        title="Guest Intelligence"
        subtitle="AI remembers every guest — who they are, what they prefer, and what to do next."
      />

      <div className="mb-6 flex flex-wrap items-center justify-between gap-3 animate-fade-up opacity-0">
        <p className="text-sm text-ink-500">
          Demo a client live — onboard them and open their profile in seconds.
        </p>
        <Link
          href="/onboard"
          className="inline-flex items-center gap-2 rounded-xl bg-ink-950 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-ink-800"
        >
          <UserPlus className="h-4 w-4" />
          Onboard a guest
        </Link>
      </div>

      {/* Opportunities */}
      <section className="mb-6 animate-fade-up opacity-0">
        <div className="mb-3 flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-sea-600" />
          <h2 className="font-display text-lg text-ink-900">AI Opportunities</h2>
        </div>
        {opportunities.length === 0 ? (
          <p className="text-sm text-ink-400">No urgent opportunities right now.</p>
        ) : (
          <div className="flex gap-3 overflow-x-auto pb-1">
            {opportunities.map((opp) => (
              <button
                key={`${opp.guest_id}-${opp.title}`}
                type="button"
                onClick={() => selectOpportunity(opp)}
                className="min-w-[220px] shrink-0 rounded-2xl border border-ink-200/60 bg-gradient-to-br from-white/90 to-sea-500/5 px-4 py-3 text-left transition hover:border-sea-500/40 hover:shadow-sm"
              >
                <div className="flex items-center gap-2">
                  <span
                    className={cn("h-2 w-2 rounded-full", healthDot(opp.health))}
                  />
                  <p className="text-sm font-medium text-ink-900">{opp.guest_name}</p>
                </div>
                <p className="mt-1.5 text-sm text-ink-700">{opp.title}</p>
                <p className="mt-0.5 text-xs text-ink-400">{opp.reason}</p>
                <p className="mt-2 text-xs font-medium text-sea-600">
                  {opp.action_label} →
                </p>
              </button>
            ))}
          </div>
        )}
      </section>

      {/* Intelligent search */}
      <section className="mb-6 animate-fade-up rounded-2xl border border-ink-200/60 bg-white/70 p-4 opacity-0 backdrop-blur [animation-delay:60ms]">
        <div className="flex flex-wrap items-end gap-3">
          <label className="min-w-[180px] flex-1">
            <span className="mb-1 block text-[10px] uppercase tracking-wider text-ink-400">
              Find guests who
            </span>
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-300" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="VIP, vegetarian, WhatsApp…"
                className="w-full rounded-xl border border-ink-200 bg-white/80 py-2 pl-9 pr-3 text-sm outline-none focus:border-sea-500"
              />
            </div>
          </label>
          <label>
            <span className="mb-1 block text-[10px] uppercase tracking-wider text-ink-400">
              Spend ≥
            </span>
            <input
              type="number"
              value={minSpend}
              onChange={(e) => setMinSpend(e.target.value)}
              placeholder="1000"
              className="w-28 rounded-xl border border-ink-200 bg-white/80 px-3 py-2 text-sm outline-none focus:border-sea-500"
            />
          </label>
          <label>
            <span className="mb-1 block text-[10px] uppercase tracking-wider text-ink-400">
              Stays ≥
            </span>
            <input
              type="number"
              value={minStays}
              onChange={(e) => setMinStays(e.target.value)}
              placeholder="2"
              className="w-20 rounded-xl border border-ink-200 bg-white/80 px-3 py-2 text-sm outline-none focus:border-sea-500"
            />
          </label>
          <label>
            <span className="mb-1 block text-[10px] uppercase tracking-wider text-ink-400">
              Inactive days ≥
            </span>
            <input
              type="number"
              value={inactiveDays}
              onChange={(e) => setInactiveDays(e.target.value)}
              placeholder="90"
              className="w-24 rounded-xl border border-ink-200 bg-white/80 px-3 py-2 text-sm outline-none focus:border-sea-500"
            />
          </label>
          <label className="flex cursor-pointer items-center gap-2 pb-2 text-sm text-ink-700">
            <input
              type="checkbox"
              checked={birthdayMonth}
              onChange={(e) => setBirthdayMonth(e.target.checked)}
              className="rounded border-ink-300 text-sea-600 focus:ring-sea-500"
            />
            Birthday this month
          </label>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[1fr_400px]">
        <Panel
          title={loading ? "Loading…" : `${guests.length} guests`}
          className="[animation-delay:100ms]"
        >
          {guests.length === 0 ? (
            <Empty>{loading ? "Loading guest intelligence…" : "No guests match"}</Empty>
          ) : (
            <ul className="divide-y divide-ink-50">
              {guests.map((g) => (
                <li key={g.id}>
                  <button
                    type="button"
                    onClick={() => setSelected(g)}
                    className={cn(
                      "flex w-full flex-col gap-2 px-1 py-3.5 text-left transition hover:bg-sea-500/5 sm:flex-row sm:items-center sm:justify-between",
                      selected?.id === g.id && "bg-sea-500/8"
                    )}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className={cn(
                            "h-2.5 w-2.5 shrink-0 rounded-full",
                            healthDot(g.health)
                          )}
                          title={g.health_label}
                        />
                        <p className="font-medium text-ink-900">{g.name}</p>
                        <span
                          className={cn(
                            "rounded-md px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide",
                            healthTone(g.health)
                          )}
                        >
                          {g.health_label || "Neutral"}
                        </span>
                        <span className="text-xs text-ink-400">
                          {g.loyalty_label}
                        </span>
                      </div>
                      <div className="mt-1.5 flex flex-wrap gap-1.5">
                        {(g.tags || []).slice(0, 5).map((tag) => (
                          <span
                            key={tag}
                            className="rounded-md bg-ink-100 px-1.5 py-0.5 text-[11px] text-ink-600"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-4 text-xs sm:pl-4">
                      <div className="text-right">
                        <p className="text-ink-400">Return</p>
                        <p className="font-medium text-ink-800">
                          {Math.round(g.return_probability ?? 0)}%
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="text-ink-400">LTV</p>
                        <p className="font-medium text-ink-800">
                          {Math.round(g.ltv_score)}
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="text-ink-400">Spend</p>
                        <p className="font-medium text-ink-800">
                          {formatCurrency(g.lifetime_spend)}
                        </p>
                      </div>
                      <Badge>{g.preferred_channel || g.communication_preference}</Badge>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        {selected && (
          <aside className="animate-fade-up space-y-4 opacity-0 [animation-delay:140ms]">
            {/* Hero profile */}
            <div className="overflow-hidden rounded-2xl border border-ink-200/60 bg-gradient-to-b from-ink-950 via-ink-900 to-sea-700 p-5 text-white">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-[10px] uppercase tracking-[0.16em] text-sea-300">
                    Living Guest Intelligence
                  </p>
                  <h2 className="mt-1 font-display text-2xl tracking-tight">
                    {selected.name}
                  </h2>
                  <p className="mt-1 text-sm text-ink-300">
                    ★★★★★ {selected.loyalty_label}
                    {selected.avg_rating != null && (
                      <span> · {selected.avg_rating}★ reviews</span>
                    )}
                  </p>
                </div>
                <span
                  className={cn(
                    "rounded-md px-2 py-1 text-xs font-medium",
                    selected.health === "loyal" && "bg-emerald-500/20 text-emerald-200",
                    selected.health === "at_risk" && "bg-coral-500/20 text-coral-200",
                    selected.health === "neutral" && "bg-white/10 text-ink-200"
                  )}
                >
                  {selected.health_label}
                </span>
              </div>

              <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
                <Metric label="LTV" value={String(Math.round(selected.ltv_score))} />
                <Metric
                  label="Return"
                  value={`${Math.round(selected.return_probability ?? 0)}%`}
                />
                <Metric
                  label="Risk"
                  value={`${Math.round(selected.churn_risk ?? 0)}%`}
                  hint={selected.health_label}
                />
                <Metric
                  label="Birthday"
                  value={formatShortDate(selected.birthday)}
                />
                <Metric
                  label="Anniversary"
                  value={formatShortDate(selected.anniversary)}
                />
                <Metric
                  label="Avg spend"
                  value={formatCurrency(selected.average_booking || 0)}
                />
              </div>

              <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                <div className="flex justify-between gap-2 border-t border-white/10 pt-2">
                  <dt className="text-ink-400">Favorite room</dt>
                  <dd>{selected.preferred_room || "—"}</dd>
                </div>
                <div className="flex justify-between gap-2 border-t border-white/10 pt-2">
                  <dt className="text-ink-400">Favorite wine</dt>
                  <dd>{selected.favorite_wine || "—"}</dd>
                </div>
                <div className="flex justify-between gap-2 border-t border-white/10 pt-2">
                  <dt className="text-ink-400">Language</dt>
                  <dd className="uppercase">{selected.language}</dd>
                </div>
                <div className="flex justify-between gap-2 border-t border-white/10 pt-2">
                  <dt className="text-ink-400">Last visit</dt>
                  <dd>
                    {selected.days_since_last_visit != null
                      ? `${selected.days_since_last_visit}d ago`
                      : "—"}
                  </dd>
                </div>
                <div className="flex justify-between gap-2 border-t border-white/10 pt-2 col-span-2">
                  <dt className="text-ink-400">Likely next visit</dt>
                  <dd>{selected.likely_next_visit || "—"}</dd>
                </div>
              </dl>
            </div>

            {/* AI Summary */}
            <div className="rounded-2xl border border-sea-500/20 bg-gradient-to-br from-sea-500/8 to-white/80 p-5">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-sea-600" />
                <h3 className="font-display text-lg text-ink-900">AI Summary</h3>
              </div>
              <p className="mt-2 text-sm leading-relaxed text-ink-700">
                {selected.ai_summary || "Building intelligence…"}
              </p>
              {(selected.recommendations || []).length > 0 && (
                <div className="mt-3">
                  <p className="text-[10px] uppercase tracking-wider text-ink-400">
                    Recommend
                  </p>
                  <ul className="mt-1 space-y-1">
                    {selected.recommendations!.map((r) => (
                      <li key={r} className="text-sm text-ink-800">
                        → {r}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            {/* Predictive metrics */}
            <div className="rounded-2xl border border-ink-200/60 bg-white/70 p-5 backdrop-blur">
              <h3 className="font-display text-lg text-ink-900">Predictions</h3>
              <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
                {[
                  ["Likelihood to return", selected.return_probability],
                  ["Upsell probability", selected.upsell_probability],
                  ["Review probability", selected.review_probability],
                  ["Churn risk", selected.churn_risk],
                ].map(([label, value]) => (
                  <div key={String(label)}>
                    <p className="text-xs text-ink-400">{label}</p>
                    <div className="mt-1 flex items-center gap-2">
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-ink-100">
                        <div
                          className={cn(
                            "h-full rounded-full",
                            label === "Churn risk" ? "bg-coral-500" : "bg-sea-500"
                          )}
                          style={{ width: `${Math.min(100, Number(value) || 0)}%` }}
                        />
                      </div>
                      <span className="w-10 text-right text-xs font-medium text-ink-700">
                        {Math.round(Number(value) || 0)}%
                      </span>
                    </div>
                  </div>
                ))}
                <div>
                  <p className="text-xs text-ink-400">Preferred channel</p>
                  <p className="mt-1 font-medium capitalize text-ink-800">
                    {selected.preferred_channel}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-ink-400">Preferred time</p>
                  <p className="mt-1 font-medium text-ink-800">
                    {selected.preferred_time}
                  </p>
                </div>
              </div>
            </div>

            {/* Remembers */}
            <div className="rounded-2xl border border-ink-200/60 bg-white/70 p-5 backdrop-blur">
              <h3 className="font-display text-lg text-ink-900">Remembers</h3>
              {(selected.remembers || []).length === 0 ? (
                <p className="mt-2 text-sm text-ink-400">No preferences captured yet</p>
              ) : (
                <ul className="mt-3 space-y-2">
                  {selected.remembers!.map((item) => (
                    <li
                      key={item}
                      className="flex items-center gap-2 text-sm text-ink-800"
                    >
                      <Check className="h-3.5 w-3.5 shrink-0 text-sea-600" />
                      {item}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* Next best action */}
            {nba && (
              <div className="rounded-2xl border border-sand-300/50 bg-gradient-to-br from-sand-100/80 to-white p-5">
                <p className="text-[10px] uppercase tracking-wider text-sand-400">
                  Next best action
                </p>
                <h3 className="mt-1 font-display text-xl text-ink-900">{nba.title}</h3>
                <p className="mt-1 text-sm text-ink-600">{nba.detail}</p>
                <p className="mt-3 text-sm font-medium text-ink-900">
                  {nba.recommendation}
                </p>
                <div className="mt-3 flex gap-4 text-xs text-ink-500">
                  <span>
                    Redemption{" "}
                    <strong className="text-ink-800">
                      {Math.round(nba.expected_redemption * 100)}%
                    </strong>
                  </span>
                  <span>
                    Expected revenue{" "}
                    <strong className="text-ink-800">
                      {formatCurrency(nba.expected_revenue)}
                    </strong>
                  </span>
                </div>
                <p className="mt-3 text-sm font-medium text-sea-600">
                  {nba.action_label} →
                </p>
              </div>
            )}

            {/* Timeline */}
            <div className="rounded-2xl border border-ink-200/60 bg-white/70 p-5 backdrop-blur">
              <h3 className="font-display text-lg text-ink-900">Timeline</h3>
              {(selected.timeline || []).length === 0 ? (
                <p className="mt-2 text-sm text-ink-400">No history yet</p>
              ) : (
                <ol className="mt-3 space-y-0">
                  {selected.timeline!.map((ev, i) => (
                    <li key={`${ev.at}-${ev.label}-${i}`} className="flex gap-3">
                      <div className="flex w-4 flex-col items-center">
                        <span className="mt-1.5 h-2 w-2 rounded-full bg-sea-500" />
                        {i < selected.timeline!.length - 1 && (
                          <span className="w-px flex-1 bg-ink-200" />
                        )}
                      </div>
                      <div className="pb-4">
                        <p className="text-sm text-ink-800">{ev.label}</p>
                        <p className="text-[11px] text-ink-400">
                          {formatShortDate(ev.at)}
                        </p>
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}
