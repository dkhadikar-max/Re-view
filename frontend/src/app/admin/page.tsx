"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Shield } from "lucide-react";
import { TopBar } from "@/components/TopBar";
import { Badge, Button, Empty, Panel, Stat } from "@/components/ui";
import {
  api,
  type AdminClient,
  type PlatformAnalytics,
  type User,
} from "@/lib/api";
import { REVISIT } from "@/lib/brand";
import { formatCurrency, formatDate } from "@/lib/utils";

const POLL_MS = 12_000;

export default function PlatformAdminPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [clients, setClients] = useState<AdminClient[]>([]);
  const [analytics, setAnalytics] = useState<PlatformAnalytics | null>(null);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [resetBusy, setResetBusy] = useState<string | null>(null);
  const [resetResult, setResetResult] = useState<{
    hotel: string;
    email: string;
    temporary_password?: string | null;
    message: string;
  } | null>(null);
  const [resetError, setResetError] = useState("");

  async function resetPassword(client: AdminClient) {
    setResetError("");
    setResetResult(null);
    setResetBusy(client.tenant_id);
    try {
      const res = await api.adminResetPassword(client.tenant_id);
      setResetResult({
        hotel: client.hotel_name,
        email: res.email,
        temporary_password: res.temporary_password,
        message: res.message,
      });
    } catch (err) {
      setResetError(err instanceof Error ? err.message : "Reset failed");
    } finally {
      setResetBusy(null);
    }
  }

  const loadLive = useCallback(async (opts?: { silent?: boolean }) => {
    const silent = Boolean(opts?.silent);
    if (silent) setRefreshing(true);
    try {
      const me = user ?? (await api.me());
      if (!user) setUser(me);
      if (!me.is_platform_admin) {
        setError(
          "Platform owner access required. Sign in with the OWNER_EMAIL account."
        );
        return;
      }
      const [c, a] = await Promise.all([
        api.adminClients(),
        api.adminAnalytics(),
      ]);
      setClients(c);
      setAnalytics(a);
      setUpdatedAt(new Date());
      setError("");
    } catch (err) {
      if (!silent) {
        setError(err instanceof Error ? err.message : "Failed to load admin");
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [user]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (cancelled) return;
      await loadLive();
    })();
    return () => {
      cancelled = true;
    };
    // Initial load only — polling is separate
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!user?.is_platform_admin) return;
    const id = window.setInterval(() => {
      void loadLive({ silent: true });
    }, POLL_MS);
    const onFocus = () => void loadLive({ silent: true });
    window.addEventListener("focus", onFocus);
    return () => {
      window.clearInterval(id);
      window.removeEventListener("focus", onFocus);
    };
  }, [user?.is_platform_admin, loadLive]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return clients;
    return clients.filter((c) =>
      [
        c.hotel_name,
        c.manager_email,
        c.manager_name,
        c.country,
        c.city,
        c.plan,
        c.tenant_id,
      ]
        .filter(Boolean)
        .some((v) => String(v).toLowerCase().includes(needle))
    );
  }, [clients, q]);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-ink-400">
        Loading admin…
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-3">
        <TopBar title="Platform Admin" subtitle="Owner access required." />
        <div
          className="rounded-xl border border-coral-200 bg-coral-50 p-4 text-sm text-coral-800"
          role="alert"
        >
          {error}
        </div>
        <Button variant="secondary" onClick={() => router.replace("/")}>
          Back to Dashboard
        </Button>
      </div>
    );
  }

  if (!user?.is_platform_admin || !analytics) {
    return (
      <div className="space-y-3">
        <TopBar title="Platform Admin" subtitle="Unable to load analytics." />
        <div className="rounded-xl border border-ink-200 bg-white p-4 text-sm text-ink-600">
          Admin data did not load. Refresh the page, or confirm you are signed
          in as the platform owner.
        </div>
        <Button variant="secondary" onClick={() => window.location.reload()}>
          Retry
        </Button>
      </div>
    );
  }

  const liveLabel = updatedAt
    ? `Live · updated ${updatedAt.toLocaleTimeString()}`
    : "Live";

  return (
    <div>
      <TopBar
        title="Platform Admin"
        subtitle={`${REVISIT.name} owner view — realtime signups and client footprint (demo seed excluded).`}
      />

      <div className="mb-4 flex flex-wrap items-center gap-2 text-xs text-ink-500">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-sea-200 bg-sea-500/10 px-2.5 py-1 font-medium text-sea-800">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-sea-600" />
          {liveLabel}
          {refreshing ? " · refreshing…" : ""}
        </span>
        <span className="text-ink-400">Auto-refreshes every {POLL_MS / 1000}s</span>
        <Button
          variant="secondary"
          className="!px-2 !py-1 text-xs"
          disabled={refreshing}
          onClick={() => void loadLive({ silent: true })}
        >
          Refresh now
        </Button>
      </div>

      {analytics.storage_durable === false && (
        <div
          className="mb-6 rounded-xl border border-coral-300 bg-coral-50 p-4 text-sm text-coral-900"
          role="alert"
        >
          <p className="font-medium">Storage is not durable</p>
          <p className="mt-1 text-coral-800">
            {analytics.storage_warning ||
              "The API is using ephemeral SQLite. Hotels, passwords, and trials reset on every Railway redeploy."}
          </p>
          <p className="mt-2 text-xs text-coral-700">
            Fix: Railway → API service → Add Postgres plugin → set{" "}
            <code className="rounded bg-white/80 px-1">DATABASE_URL</code> to the
            Postgres URL → set{" "}
            <code className="rounded bg-white/80 px-1">OWNER_PASSWORD</code> →
            redeploy. Backend: {analytics.storage_backend || "sqlite"}
          </p>
        </div>
      )}

      <section className="mb-6 animate-fade-up overflow-hidden rounded-2xl border border-ink-200/60 bg-gradient-to-br from-ink-950 via-ink-900 to-sea-700 p-6 text-white opacity-0">
        <div className="flex items-start gap-3">
          <Shield className="mt-1 h-5 w-5 text-sea-300" />
          <div>
            <p className="text-[10px] uppercase tracking-[0.18em] text-sea-300">
              Owner · {user.email} · realtime only
            </p>
            <h2 className="mt-1 font-display text-2xl tracking-tight md:text-3xl">
              Who is signing up
            </h2>
            <p className="mt-2 max-w-2xl text-sm text-ink-300">
              Live cross-tenant view of hotel trials and workspace activity.
              Seeded demo data is excluded. Tenant dashboards stay isolated.
            </p>
          </div>
        </div>
      </section>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Hotels" value={analytics.total_hotels} accent="sea" />
        <Stat label="Trials" value={analytics.trial_hotels} accent="sand" delay={40} />
        <Stat
          label="Signups · 7 days"
          value={analytics.signups_last_7_days}
          delay={80}
        />
        <Stat
          label="Signups · 30 days"
          value={analytics.signups_last_30_days}
          delay={120}
        />
      </div>
      <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Active hotels" value={analytics.active_hotels} delay={160} />
        <Stat label="Managers" value={analytics.total_managers} delay={200} />
        <Stat label="Guests (all)" value={analytics.total_guests} delay={240} />
        <Stat
          label="Upsell revenue (all)"
          value={formatCurrency(analytics.total_upsell_revenue, "EUR")}
          hint="Mixed currencies summed numerically"
          delay={280}
        />
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <Panel title="By plan" className="[animation-delay:80ms]">
          {analytics.by_plan.length === 0 ? (
            <Empty>No tenants yet</Empty>
          ) : (
            <ul className="space-y-2 text-sm">
              {analytics.by_plan.map((row) => (
                <li
                  key={row.plan}
                  className="flex items-center justify-between rounded-lg bg-ink-50/80 px-3 py-2"
                >
                  <span className="capitalize text-ink-700">{row.plan}</span>
                  <Badge>{row.hotels}</Badge>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="By country" className="[animation-delay:120ms]">
          {analytics.by_country.length === 0 ? (
            <Empty>No countries yet</Empty>
          ) : (
            <ul className="space-y-2 text-sm">
              {analytics.by_country.map((row) => (
                <li
                  key={row.country}
                  className="flex items-center justify-between rounded-lg bg-ink-50/80 px-3 py-2"
                >
                  <span className="text-ink-700">
                    {row.country}{" "}
                    <span className="text-ink-400">· {row.currency}</span>
                  </span>
                  <Badge>{row.hotels}</Badge>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <Panel title="Recent signups" className="mt-6 [animation-delay:160ms]">
        {analytics.recent_signups.length === 0 ? (
          <Empty>No trial signups yet</Empty>
        ) : (
          <ul className="divide-y divide-ink-100 text-sm">
            {analytics.recent_signups.map((s) => (
              <li key={s.tenant_id} className="flex flex-wrap items-center gap-2 py-3">
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-ink-900">{s.hotel_name}</p>
                  <p className="text-xs text-ink-500">
                    {s.manager_email || "—"} · {s.country || "—"} · {s.currency}
                  </p>
                </div>
                <p className="text-xs text-ink-400">{formatDate(s.signed_up_at)}</p>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <Panel title="All clients" className="mt-6 [animation-delay:200ms]">
        <label className="mb-4 block text-xs text-ink-500">
          Search hotels, emails, countries
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="e.g. India, trial, @hotel.com"
            className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-sea-500"
          />
        </label>
        {filtered.length === 0 ? (
          <Empty>No matching clients</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="text-[11px] uppercase tracking-wider text-ink-400">
                <tr className="border-b border-ink-100">
                  <th className="pb-2 pr-3 font-medium">Hotel</th>
                  <th className="pb-2 pr-3 font-medium">Contact</th>
                  <th className="pb-2 pr-3 font-medium">Plan</th>
                  <th className="pb-2 pr-3 font-medium">Market</th>
                  <th className="pb-2 pr-3 font-medium">Activity</th>
                  <th className="pb-2 pr-3 font-medium">Signed up</th>
                  <th className="pb-2 font-medium">Password</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((c) => (
                  <tr key={c.tenant_id} className="border-b border-ink-50 align-top">
                    <td className="py-3 pr-3">
                      <p className="font-medium text-ink-900">{c.hotel_name}</p>
                      <p className="text-[11px] text-ink-400">{c.tenant_id}</p>
                    </td>
                    <td className="py-3 pr-3">
                      <p className="text-ink-800">{c.manager_name || "—"}</p>
                      <p className="text-xs text-ink-500">{c.manager_email || "—"}</p>
                    </td>
                    <td className="py-3 pr-3">
                      <Badge>{c.plan}</Badge>
                      {!c.is_active && (
                        <p className="mt-1 text-[11px] text-coral-600">Inactive</p>
                      )}
                    </td>
                    <td className="py-3 pr-3">
                      <p className="text-ink-700">
                        {[c.city, c.country].filter(Boolean).join(", ") || "—"}
                      </p>
                      <p className="text-xs text-ink-400">
                        {c.currency} · {c.rooms} rooms
                      </p>
                    </td>
                    <td className="py-3 pr-3 text-ink-700">
                      <p>{c.guest_count} guests</p>
                      <p className="text-xs text-ink-500">
                        {c.reservation_count} reservations ·{" "}
                        {formatCurrency(c.upsell_revenue, c.currency)}
                      </p>
                    </td>
                    <td className="py-3 pr-3 text-xs text-ink-500">
                      {formatDate(c.signed_up_at)}
                    </td>
                    <td className="py-3">
                      <Button
                        variant="secondary"
                        disabled={resetBusy === c.tenant_id}
                        onClick={() => void resetPassword(c)}
                      >
                        {resetBusy === c.tenant_id ? "Resetting…" : "Reset"}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {(resetResult || resetError) && (
        <div className="fixed inset-x-4 bottom-4 z-50 mx-auto max-w-lg animate-fade-up rounded-2xl border border-ink-200 bg-white p-5 shadow-lg">
          {resetError && (
            <p className="text-sm text-coral-600" role="alert">
              {resetError}
            </p>
          )}
          {resetResult && (
            <div className="space-y-2 text-sm">
              <p className="font-medium text-ink-900">
                Password reset · {resetResult.hotel}
              </p>
              <p className="text-ink-600">{resetResult.message}</p>
              <p className="text-ink-500">
                Account: <span className="text-ink-800">{resetResult.email}</span>
              </p>
              {resetResult.temporary_password && (
                <p className="rounded-xl bg-ink-50 px-3 py-2 font-mono text-base text-ink-900">
                  {resetResult.temporary_password}
                </p>
              )}
              <p className="text-[11px] text-ink-400">
                Stored as a hash only. Copy now — it will not be shown again.
              </p>
            </div>
          )}
          <Button
            className="mt-3"
            variant="secondary"
            onClick={() => {
              setResetResult(null);
              setResetError("");
            }}
          >
            Close
          </Button>
        </div>
      )}
    </div>
  );
}
