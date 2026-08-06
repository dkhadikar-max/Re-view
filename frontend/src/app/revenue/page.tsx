"use client";

import { useEffect, useState } from "react";
import { TopBar } from "@/components/TopBar";
import { Badge, Button, Empty, Panel, Stat } from "@/components/ui";
import { useMoney, useWorkspaceCurrency } from "@/components/WorkspaceProvider";
import {
  api,
  type DashboardStats,
  type Offer,
  type SalesAnalytics,
} from "@/lib/api";
import { ARGUS, REVISIT } from "@/lib/brand";

export default function RevenuePage() {
  const money = useMoney();
  const currency = useWorkspaceCurrency();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [offers, setOffers] = useState<Offer[]>([]);
  const [analytics, setAnalytics] = useState<SalesAnalytics | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function load() {
    const [s, o, a] = await Promise.all([
      api.stats(),
      api.offers(),
      api.salesAnalytics(30),
    ]);
    setStats(s);
    setOffers(o);
    setAnalytics(a);
  }

  useEffect(() => {
    load().catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
  }, []);

  async function accept(id: string) {
    setBusy(id);
    try {
      await api.acceptOffer(id);
      await load();
    } finally {
      setBusy(null);
    }
  }

  async function paymentLink(id: string) {
    setBusy(id);
    try {
      const link = await api.createPaymentLink(id);
      await load();
      if (link.url) window.open(link.url, "_blank", "noopener,noreferrer");
    } finally {
      setBusy(null);
    }
  }

  if (error) {
    return (
      <div className="rounded-xl border border-coral-200 bg-coral-50 p-4 text-sm text-coral-800">
        {error}
      </div>
    );
  }

  if (!stats || !analytics) {
    return (
      <div className="flex h-64 items-center justify-center text-ink-400">
        Loading revenue…
      </div>
    );
  }

  return (
    <div>
      <TopBar
        title="Revenue"
        subtitle="Upsells, reviews, and repeat guests — the outcomes this platform drives."
      />

      <div className="mb-6 animate-fade-up rounded-2xl border border-ink-200/60 bg-gradient-to-br from-ink-950 via-ink-900 to-sea-800 p-6 text-white opacity-0">
        <p className="text-xs uppercase tracking-wider text-ink-300">
          {REVISIT.name} · {ARGUS.productLine} · {currency} · last {analytics.period_days} days
        </p>
        <h2 className="mt-2 font-display text-3xl">One paying hotel. These numbers.</h2>
        <p className="mt-2 max-w-2xl text-sm text-ink-200">
          Upsells → Stripe payment link → paid webhook → guest memory.
        </p>
      </div>

      <p className="mb-3 text-xs font-medium uppercase tracking-wider text-ink-400">
        Revenue
      </p>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Revenue today" value={money(stats.revenue_today)} accent="sea" />
        <Stat
          label="Upsell revenue"
          value={money(stats.upsell_revenue)}
          hint={`${analytics.upsell_conversion}% conversion`}
          accent="sand"
          delay={40}
        />
        <Stat
          label="Repeat guests"
          value={stats.repeat_guests}
          hint={`${analytics.repeat_guest_rate}% of book of business`}
          delay={80}
        />
        <Stat
          label="Average spend"
          value={money(stats.average_spend)}
          delay={120}
        />
      </div>

      <p className="mb-3 mt-6 text-xs font-medium uppercase tracking-wider text-ink-400">
        Guest health
      </p>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label="Review rate"
          value={`${analytics.review_rate}%`}
          hint="Guests with prior reviews"
          accent="sea"
        />
        <Stat
          label="Guest satisfaction"
          value={analytics.guest_satisfaction}
          hint={`Google proxy ${analytics.google_rating_proxy}★`}
          delay={40}
        />
        <Stat
          label="Messages"
          value={analytics.ai_messages}
          hint={`${analytics.ai_messages_sent} delivered/sent`}
          delay={80}
        />
        <Stat
          label="Rewards enrolled"
          value={analytics.celebrations_enrolled}
          hint={`${money(analytics.room_revenue_active)} active room revenue`}
          delay={120}
        />
      </div>

      <Panel title="Offers" className="mt-8 [animation-delay:160ms]">
        {offers.length === 0 ? (
          <Empty>
            No offers yet. Once a reservation is recommended an upsell, it will
            appear here.
          </Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-ink-100 text-xs uppercase tracking-wider text-ink-400">
                  <th className="pb-3 font-medium">Offer</th>
                  <th className="pb-3 font-medium">Guest</th>
                  <th className="pb-3 font-medium">Price</th>
                  <th className="pb-3 font-medium">Status</th>
                  <th className="pb-3 font-medium"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-50">
                {offers.map((o) => (
                  <tr key={o.id}>
                    <td className="py-3">
                      <p className="font-medium text-ink-900">{o.name}</p>
                      <p className="text-xs text-ink-400">{o.description}</p>
                      {o.payment_link_url && (
                        <a
                          href={o.payment_link_url}
                          target="_blank"
                          rel="noreferrer"
                          className="mt-1 inline-block text-xs text-sea-700 underline"
                        >
                          Payment link
                        </a>
                      )}
                    </td>
                    <td className="py-3 text-ink-600">{o.guest_name}</td>
                    <td className="py-3">
                      {money(o.price, o.currency)}
                    </td>
                    <td className="py-3">
                      <Badge tone={o.paid_at ? "accepted" : o.status}>
                        {o.paid_at ? "paid" : o.status}
                      </Badge>
                    </td>
                    <td className="py-3">
                      <div className="flex flex-wrap gap-2">
                        {o.status === "offered" && (
                          <>
                            <Button
                              variant="secondary"
                              disabled={busy === o.id}
                              onClick={() => paymentLink(o.id)}
                            >
                              Stripe link
                            </Button>
                            <Button
                              variant="secondary"
                              disabled={busy === o.id}
                              onClick={() => accept(o.id)}
                            >
                              Mark accepted
                            </Button>
                          </>
                        )}
                      </div>
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
