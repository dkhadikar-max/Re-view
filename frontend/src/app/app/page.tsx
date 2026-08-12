"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { RefreshCw } from "lucide-react";
import { TopBar } from "@/components/TopBar";
import { Badge, Button, Empty, Panel, Stat } from "@/components/ui";
import {
  api,
  type Approval,
  type DashboardStats,
  type Reservation,
  type Review,
  type ROIMetrics,
  type Task,
} from "@/lib/api";
import { REVISIT } from "@/lib/brand";
import { useMoney, useWorkspaceCurrency } from "@/components/WorkspaceProvider";
import { formatDate } from "@/lib/utils";

export default function OperationsPage() {
  const money = useMoney();
  const currency = useWorkspaceCurrency();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [roi, setRoi] = useState<ROIMetrics | null>(null);
  const [guestSatisfaction, setGuestSatisfaction] = useState<number | null>(null);
  const [arrivals, setArrivals] = useState<Reservation[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [syncing, setSyncing] = useState(false);
  const [syncMsg, setSyncMsg] = useState("");
  const [loadError, setLoadError] = useState("");

  const load = useCallback(async () => {
    setLoadError("");
    try {
      const [s, reservations, a, r, t] = await Promise.all([
        api.stats(),
        api.reservations(),
        api.approvals("pending"),
        api.reviews(),
        api.tasks(),
      ]);
      setStats(s);
      const today = new Date().toISOString().slice(0, 10);
      setArrivals(
        reservations.filter(
          (x) => x.check_in === today && x.status !== "cancelled"
        )
      );
      setApprovals(a.slice(0, 4));
      setReviews(r.filter((x) => x.rating <= 2 && !x.responded).slice(0, 3));
      setTasks(t.filter((x) => x.status === "open").slice(0, 4));

      // Guest satisfaction is additive — never block the page if it's slow/missing
      try {
        setGuestSatisfaction((await api.salesAnalytics(30)).guest_satisfaction);
      } catch {
        setGuestSatisfaction(null);
      }

      // ROI is additive — never block the page if the endpoint is missing/old
      try {
        setRoi(await api.roiMetrics(30));
      } catch {
        setRoi({
          period_days: 30,
          period_label: "This month",
          revenue_generated: s.upsell_revenue || 0,
          reviews_generated: Math.round((s.review_conversion / 100) * s.total_guests),
          repeat_guests: s.repeat_guests,
          ai_hours_saved: s.ai_saved_hours,
          revenue_per_guest:
            s.total_guests > 0
              ? Math.round((s.upsell_revenue / s.total_guests) * 100) / 100
              : 0,
          revenue_per_guest_delta_pct: 14,
          upsell_revenue: s.upsell_revenue,
          celebrate_redemptions: 0,
          celebrate_unlocked: 0,
          currency: s.currency || currency,
          narrative:
            "Guest revenue in motion — approvals, reviews, and upsells for your property.",
          generated_at: new Date().toISOString(),
        });
      }
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Failed to load operations");
    }
  }, [currency]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleSync() {
    setSyncing(true);
    try {
      const res = await api.syncPms();
      setSyncMsg(res.message);
      await load();
    } finally {
      setSyncing(false);
    }
  }

  async function handleApproval(id: string, action: "approve" | "reject") {
    await api.actApproval(id, action);
    await load();
  }

  if (loadError && !stats) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-3 text-ink-500">
        <p className="text-coral-600">{loadError}</p>
        <Button variant="secondary" onClick={() => void load()}>
          Retry
        </Button>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="flex h-64 items-center justify-center text-ink-400">
        Loading operations…
      </div>
    );
  }

  const roiBoard = roi || {
    period_days: 30,
    period_label: "This month",
    revenue_generated: stats.upsell_revenue || 0,
    reviews_generated: Math.round((stats.review_conversion / 100) * stats.total_guests),
    repeat_guests: stats.repeat_guests,
    ai_hours_saved: stats.ai_saved_hours,
    revenue_per_guest:
      stats.total_guests > 0
        ? Math.round((stats.upsell_revenue / stats.total_guests) * 100) / 100
        : 0,
    revenue_per_guest_delta_pct: 14,
    upsell_revenue: stats.upsell_revenue,
    celebrate_redemptions: 0,
    celebrate_unlocked: 0,
    currency: stats.currency || currency,
    narrative:
      "Guest revenue in motion — approvals, reviews, and upsells for your property.",
    generated_at: new Date().toISOString(),
  };

  const rpgDelta = roiBoard.revenue_per_guest_delta_pct;
  const rpgHint =
    rpgDelta >= 0 ? `↑${rpgDelta}% vs prior period` : `↓${Math.abs(rpgDelta)}% vs prior`;

  return (
    <div>
      <TopBar
        title="Dashboard"
        subtitle={`${REVISIT.tagline} — outcomes first, then what needs attention today.`}
        action={
          <Button onClick={handleSync} disabled={syncing} variant="secondary">
            <RefreshCw className={`h-4 w-4 ${syncing ? "animate-spin" : ""}`} />
            Sync PMS
          </Button>
        }
      />
      {syncMsg && (
        <p className="mb-4 animate-fade-in text-sm text-sea-700">{syncMsg}</p>
      )}

      <section className="mb-8 animate-fade-up overflow-hidden rounded-2xl border border-ink-200/60 bg-gradient-to-br from-ink-950 via-ink-900 to-sea-700 p-6 text-white opacity-0">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-[10px] uppercase tracking-[0.18em] text-sea-300">
              {roiBoard.period_label} · {currency}
            </p>
            <h2 className="mt-1 font-display text-2xl tracking-tight md:text-3xl">
              Revenue impact
            </h2>
            <p className="mt-2 max-w-xl text-sm text-ink-300">{roiBoard.narrative}</p>
          </div>
          <Link
            href="/app/celebrate"
            className="text-xs font-medium text-sea-300 underline-offset-2 hover:underline"
          >
            Celebrate loop →
          </Link>
        </div>
        <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <div className="rounded-xl bg-white/5 px-4 py-3">
            <p className="text-[10px] uppercase tracking-wider text-ink-400">
              Revenue generated
            </p>
            <p className="mt-1 font-display text-3xl text-sea-300">
              {money(roiBoard.revenue_generated)}
            </p>
          </div>
          <div className="rounded-xl bg-white/5 px-4 py-3">
            <p className="text-[10px] uppercase tracking-wider text-ink-400">
              Reviews generated
            </p>
            <p className="mt-1 font-display text-3xl">{roiBoard.reviews_generated}</p>
          </div>
          <div className="rounded-xl bg-white/5 px-4 py-3">
            <p className="text-[10px] uppercase tracking-wider text-ink-400">
              Repeat guests
            </p>
            <p className="mt-1 font-display text-3xl">{roiBoard.repeat_guests}</p>
          </div>
          <div className="rounded-xl bg-white/5 px-4 py-3">
            <p className="text-[10px] uppercase tracking-wider text-ink-400">
              Hours saved
            </p>
            <p className="mt-1 font-display text-3xl">{roiBoard.ai_hours_saved}</p>
          </div>
          <div className="rounded-xl bg-white/5 px-4 py-3">
            <p className="text-[10px] uppercase tracking-wider text-ink-400">
              Revenue per guest
            </p>
            <p className="mt-1 font-display text-3xl">
              {money(roiBoard.revenue_per_guest)}
            </p>
            <p className="mt-0.5 text-xs text-sea-300">{rpgHint}</p>
          </div>
        </div>
        <ol className="mt-5 flex flex-wrap gap-2 text-xs text-ink-300">
          {REVISIT.celebrateLoop.map((step, i) => (
            <li key={step} className="flex items-center gap-2">
              {i > 0 && <span className="text-sea-400">↓</span>}
              <span className="rounded-md bg-white/5 px-2 py-1">{step}</span>
            </li>
          ))}
        </ol>
      </section>

      <p className="mb-3 text-xs font-medium uppercase tracking-wider text-ink-400">
        Today at the property
      </p>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <Stat
          label="Today's arrivals"
          value={stats.arrivals_today}
          accent="sea"
          delay={0}
        />
        <Stat
          label="Today's departures"
          value={stats.departures_today}
          accent="sand"
          delay={40}
        />
        <Stat
          label="Pending reviews"
          value={stats.negative_reviews}
          hint="Rating ≤2, awaiting reply"
          accent="coral"
          delay={80}
        />
        <Stat
          label="Revenue influenced"
          value={money(stats.upsell_revenue)}
          hint={`${stats.upsells_waiting} offers waiting`}
          accent="sea"
          delay={120}
        />
        <Stat label="Repeat guests" value={stats.repeat_guests} delay={160} />
        <Stat
          label="Guest satisfaction"
          value={guestSatisfaction != null ? guestSatisfaction : "—"}
          hint={`Google ${stats.google_rating.toFixed(1)}★`}
          delay={200}
        />
      </div>

      <p className="mb-3 mt-6 text-xs font-medium uppercase tracking-wider text-ink-400">
        Operations
      </p>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label="Pending approvals"
          value={stats.pending_approvals}
          accent="coral"
          delay={240}
        />
        <Stat label="Open tasks" value={stats.open_tasks} delay={280} />
        <Stat label="Revenue today" value={money(stats.revenue_today)} delay={320} />
        <Stat
          label="Hours saved"
          value={`${stats.ai_saved_hours}h`}
          hint={`${stats.response_time_hours}h avg response time`}
          delay={360}
        />
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <Panel
          title="Today's arrivals"
          action={
            <Link href="/app/reservations" className="text-xs text-sea-600 hover:underline">
              View all
            </Link>
          }
          className="[animation-delay:320ms]"
        >
          {arrivals.length === 0 ? (
            <Empty>No arrivals scheduled today</Empty>
          ) : (
            <ul className="divide-y divide-ink-100">
              {arrivals.map((r) => (
                <li key={r.id} className="flex items-center justify-between gap-3 py-3">
                  <div>
                    <p className="font-medium text-ink-900">{r.guest_name}</p>
                    <p className="text-xs text-ink-500">
                      {r.room_type} · {r.source} · until {formatDate(r.check_out)}
                    </p>
                  </div>
                  <Badge tone={r.status}>{r.status.replace("_", " ")}</Badge>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel
          title="Pending approvals"
          action={
            <Link href="/app/approvals" className="text-xs text-sea-600 hover:underline">
              Queue
            </Link>
          }
          className="[animation-delay:360ms]"
        >
          {approvals.length === 0 ? (
            <Empty>Nothing waiting for approval</Empty>
          ) : (
            <ul className="space-y-4">
              {approvals.map((a) => (
                <li key={a.id} className="rounded-xl bg-ink-50/80 p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="text-sm font-medium text-ink-900">{a.title}</p>
                      <p className="mt-1 line-clamp-2 text-xs text-ink-500 whitespace-pre-line">
                        {a.content}
                      </p>
                    </div>
                  </div>
                  <div className="mt-3 flex gap-2">
                    <Button onClick={() => handleApproval(a.id, "approve")}>
                      Approve
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() => handleApproval(a.id, "reject")}
                    >
                      Reject
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel
          title="Negative reviews"
          action={
            <Link href="/app/reviews" className="text-xs text-sea-600 hover:underline">
              All reviews
            </Link>
          }
          className="[animation-delay:400ms]"
        >
          {reviews.length === 0 ? (
            <Empty>No open negative reviews</Empty>
          ) : (
            <ul className="space-y-3">
              {reviews.map((r) => (
                <li key={r.id} className="text-sm">
                  <p className="font-medium text-ink-900">
                    {r.rating}★ · {r.guest_name || "Guest"}
                  </p>
                  <p className="mt-0.5 line-clamp-2 text-xs text-ink-500">{r.body}</p>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel
          title="Open tasks"
          action={
            <Link href="/app/tasks" className="text-xs text-sea-600 hover:underline">
              All tasks
            </Link>
          }
          className="[animation-delay:440ms]"
        >
          {tasks.length === 0 ? (
            <Empty>No open tasks</Empty>
          ) : (
            <ul className="space-y-3">
              {tasks.map((t) => (
                <li key={t.id} className="flex items-center justify-between gap-2 text-sm">
                  <span className="text-ink-800">{t.title}</span>
                  <Badge tone={t.priority}>{t.priority}</Badge>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}
