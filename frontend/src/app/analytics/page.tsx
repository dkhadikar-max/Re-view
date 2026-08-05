"use client";

import { useEffect, useState } from "react";
import { TopBar } from "@/components/TopBar";
import { Button, Panel, Stat } from "@/components/ui";
import { api, type SalesAnalytics } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";

export default function AnalyticsPage() {
  const [data, setData] = useState<SalesAnalytics | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .salesAnalytics(30)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
  }, []);

  if (error) {
    return (
      <div className="rounded-xl border border-coral-200 bg-coral-50 p-4 text-sm text-coral-800">
        {error}
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex h-64 items-center justify-center text-ink-400">
        Loading sales analytics…
      </div>
    );
  }

  return (
    <div>
      <TopBar
        title="Sales Analytics"
        subtitle="The V1 demo board — review rate, repeat guests, upsell revenue, AI messages."
      />

      <div className="mb-6 animate-fade-up rounded-2xl border border-ink-200/60 bg-gradient-to-br from-ink-950 via-ink-900 to-sea-800 p-6 text-white opacity-0">
        <p className="text-xs uppercase tracking-wider text-ink-300">
          Revisit · last {data.period_days} days
        </p>
        <h2 className="mt-2 font-display text-3xl">One paying hotel. These numbers.</h2>
        <p className="mt-2 max-w-2xl text-sm text-ink-200">
          Revenue attributed to upsells · AI outbound volume · guest satisfaction proxy
          from Guest Memory.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <Stat
          label="Review rate"
          value={`${data.review_rate}%`}
          hint="Guests with prior reviews"
          accent="sea"
        />
        <Stat
          label="Repeat guests"
          value={data.repeat_guests}
          hint={`${data.repeat_guest_rate}% of book of business`}
          accent="sand"
          delay={40}
        />
        <Stat
          label="Revenue generated"
          value={formatCurrency(data.revenue_generated)}
          hint="Attributed upsell revenue"
          accent="coral"
          delay={80}
        />
        <Stat
          label="AI messages"
          value={data.ai_messages}
          hint={`${data.ai_messages_sent} delivered/sent`}
          delay={120}
        />
        <Stat
          label="Upsell conversion"
          value={`${data.upsell_conversion}%`}
          hint={formatCurrency(data.upsell_revenue) + " accepted"}
          accent="sea"
          delay={160}
        />
        <Stat
          label="Guest satisfaction"
          value={data.guest_satisfaction}
          hint={`Google proxy ${data.google_rating_proxy}★`}
          delay={200}
        />
      </div>

      <Panel title="Celebrate + in-house" className="mt-8 [animation-delay:240ms]">
        <div className="flex flex-wrap gap-6 text-sm text-ink-600">
          <p>
            Celebrations enrolled:{" "}
            <span className="font-medium text-ink-900">
              {data.celebrations_enrolled}
            </span>
          </p>
          <p>
            Active room revenue:{" "}
            <span className="font-medium text-ink-900">
              {formatCurrency(data.room_revenue_active)}
            </span>
          </p>
          <p className="text-ink-400">
            Generated {new Date(data.generated_at).toLocaleString()}
          </p>
        </div>
        <Button
          className="mt-4"
          variant="secondary"
          onClick={() =>
            api.salesAnalytics(30).then(setData).catch((e) => setError(String(e)))
          }
        >
          Refresh
        </Button>
      </Panel>
    </div>
  );
}
