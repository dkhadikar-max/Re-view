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
  type Task,
} from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/utils";

export default function OperationsPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [arrivals, setArrivals] = useState<Reservation[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [syncing, setSyncing] = useState(false);
  const [syncMsg, setSyncMsg] = useState("");

  const load = useCallback(async () => {
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
  }, []);

  useEffect(() => {
    load().catch(console.error);
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

  if (!stats) {
    return (
      <div className="flex h-64 items-center justify-center text-ink-400">
        Loading operations…
      </div>
    );
  }

  return (
    <div>
      <TopBar
        title="Today at the property"
        subtitle="What needs attention now — arrivals, messages, reviews, and revenue opportunities."
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

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Arrivals" value={stats.arrivals_today} accent="sea" delay={0} />
        <Stat label="Departures" value={stats.departures_today} accent="sand" delay={40} />
        <Stat
          label="Pending approvals"
          value={stats.pending_approvals}
          accent="coral"
          delay={80}
        />
        <Stat
          label="Upsell revenue"
          value={formatCurrency(stats.upsell_revenue)}
          hint={`${stats.upsells_waiting} offers waiting`}
          accent="sea"
          delay={120}
        />
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label="Revenue today"
          value={formatCurrency(stats.revenue_today)}
          delay={160}
        />
        <Stat
          label="Google rating"
          value={stats.google_rating.toFixed(1)}
          hint={`${stats.review_conversion}% review conversion`}
          delay={200}
        />
        <Stat
          label="AI hours saved"
          value={`${stats.ai_saved_hours}h`}
          hint={`${stats.response_time_hours}h avg response`}
          delay={240}
        />
        <Stat
          label="Open tasks"
          value={stats.open_tasks}
          hint={`${stats.negative_reviews} negative reviews`}
          accent="coral"
          delay={280}
        />
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <Panel
          title="Today's arrivals"
          action={
            <Link href="/reservations" className="text-xs text-sea-600 hover:underline">
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
            <Link href="/approvals" className="text-xs text-sea-600 hover:underline">
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
                    {a.confidence != null && (
                      <span className="shrink-0 text-xs text-ink-400">
                        {Math.round(a.confidence * 100)}%
                      </span>
                    )}
                  </div>
                  <div className="mt-3 flex gap-2">
                    <Button onClick={() => handleApproval(a.id, "approve")}>
                      Approve
                    </Button>
                    <Button
                      variant="ghost"
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

        <Panel title="Negative reviews" className="[animation-delay:400ms]">
          {reviews.length === 0 ? (
            <Empty>No unresolved negative reviews</Empty>
          ) : (
            <ul className="space-y-3">
              {reviews.map((r) => (
                <li key={r.id} className="border-l-2 border-coral-500 pl-3">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{r.guest_name}</span>
                    <Badge tone="negative">{r.rating}★</Badge>
                  </div>
                  <p className="mt-1 text-xs text-ink-500 line-clamp-2">{r.body}</p>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Open tasks" className="[animation-delay:440ms]">
          {tasks.length === 0 ? (
            <Empty>No open tasks</Empty>
          ) : (
            <ul className="divide-y divide-ink-100">
              {tasks.map((t) => (
                <li key={t.id} className="flex items-center justify-between gap-3 py-3">
                  <div>
                    <p className="text-sm font-medium text-ink-900">{t.title}</p>
                    <p className="text-xs text-ink-500">
                      {t.assignee || "Unassigned"}
                    </p>
                  </div>
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
