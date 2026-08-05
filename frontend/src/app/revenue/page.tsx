"use client";

import { useEffect, useState } from "react";
import { TopBar } from "@/components/TopBar";
import { Badge, Button, Empty, Panel, Stat } from "@/components/ui";
import { useMoney } from "@/components/WorkspaceProvider";
import { api, type DashboardStats, type Offer } from "@/lib/api";

export default function RevenuePage() {
  const money = useMoney();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [offers, setOffers] = useState<Offer[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  async function load() {
    const [s, o] = await Promise.all([api.stats(), api.offers()]);
    setStats(s);
    setOffers(o);
  }

  useEffect(() => {
    load().catch(console.error);
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

  if (!stats) {
    return (
      <div className="flex h-64 items-center justify-center text-ink-400">
        Loading revenue…
      </div>
    );
  }

  return (
    <div>
      <TopBar
        title="Revenue Engine"
        subtitle="Upsells → Stripe payment link → paid webhook → guest memory."
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label="Revenue today"
          value={money(stats.revenue_today)}
          accent="sea"
        />
        <Stat
          label="Upsell revenue"
          value={money(stats.upsell_revenue)}
          accent="sand"
          delay={40}
        />
        <Stat
          label="Repeat guests"
          value={stats.repeat_guests}
          delay={80}
        />
        <Stat
          label="Average spend"
          value={money(stats.average_spend)}
          delay={120}
        />
      </div>

      <Panel title="Offers" className="mt-8 [animation-delay:160ms]">
        {offers.length === 0 ? (
          <Empty>No offers yet</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-ink-100 text-xs uppercase tracking-wider text-ink-400">
                  <th className="pb-3 font-medium">Offer</th>
                  <th className="pb-3 font-medium">Guest</th>
                  <th className="pb-3 font-medium">Price</th>
                  <th className="pb-3 font-medium">Confidence</th>
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
                    <td className="py-3 text-ink-500">
                      {Math.round(o.confidence * 100)}%
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
