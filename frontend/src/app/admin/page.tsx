"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Shield } from "lucide-react";
import { TopBar } from "@/components/TopBar";
import { Badge, Empty, Panel, Stat } from "@/components/ui";
import {
  api,
  type AdminClient,
  type PlatformAnalytics,
  type User,
} from "@/lib/api";
import { REVISIT } from "@/lib/brand";
import { formatCurrency, formatDate } from "@/lib/utils";

export default function PlatformAdminPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [clients, setClients] = useState<AdminClient[]>([]);
  const [analytics, setAnalytics] = useState<PlatformAnalytics | null>(null);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await api.me();
        if (cancelled) return;
        setUser(me);
        if (!me.is_platform_admin) {
          router.replace("/");
          return;
        }
        const [c, a] = await Promise.all([
          api.adminClients(),
          api.adminAnalytics(),
        ]);
        if (cancelled) return;
        setClients(c);
        setAnalytics(a);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load admin");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [router]);

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
      <div className="rounded-xl border border-coral-200 bg-coral-50 p-4 text-sm text-coral-800">
        {error}
      </div>
    );
  }

  if (!user?.is_platform_admin || !analytics) {
    return null;
  }

  return (
    <div>
      <TopBar
        title="Platform Admin"
        subtitle={`${REVISIT.name} owner view — signups, trials, and client footprint.`}
      />

      <section className="mb-6 animate-fade-up overflow-hidden rounded-2xl border border-ink-200/60 bg-gradient-to-br from-ink-950 via-ink-900 to-sea-700 p-6 text-white opacity-0">
        <div className="flex items-start gap-3">
          <Shield className="mt-1 h-5 w-5 text-sea-300" />
          <div>
            <p className="text-[10px] uppercase tracking-[0.18em] text-sea-300">
              Owner · {user.email}
            </p>
            <h2 className="mt-1 font-display text-2xl tracking-tight md:text-3xl">
              Who is signing up
            </h2>
            <p className="mt-2 max-w-2xl text-sm text-ink-300">
              Cross-tenant view of hotel trials and workspace activity. Tenant
              dashboards stay isolated — this panel is platform-only.
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
                  <th className="pb-2 font-medium">Signed up</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((c) => (
                  <tr key={c.tenant_id} className="border-b border-ink-50 align-top">
                    <td className="py-3 pr-3">
                      <p className="font-medium text-ink-900">{c.hotel_name}</p>
                      <p className="text-[11px] text-ink-400">{c.tenant_id}</p>
                      {c.is_demo && (
                        <Badge className="mt-1">Demo</Badge>
                      )}
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
                    <td className="py-3 text-xs text-ink-500">
                      {formatDate(c.signed_up_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
