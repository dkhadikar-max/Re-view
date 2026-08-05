"use client";

import { useEffect, useState } from "react";
import { TopBar } from "@/components/TopBar";
import { Badge, Empty, Panel } from "@/components/ui";
import { api, type Guest } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";

export default function GuestsPage() {
  const [guests, setGuests] = useState<Guest[]>([]);
  const [selected, setSelected] = useState<Guest | null>(null);

  useEffect(() => {
    api.guests().then((g) => {
      setGuests(g);
      setSelected(g[0] || null);
    });
  }, []);

  return (
    <div>
      <TopBar
        title="Guest Memory"
        subtitle="Continuously evolving profiles — preferences, LTV, satisfaction, and history."
      />

      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <Panel title={`${guests.length} guests`} className="[animation-delay:80ms]">
          {guests.length === 0 ? (
            <Empty>No guests yet</Empty>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-ink-100 text-xs uppercase tracking-wider text-ink-400">
                    <th className="pb-3 font-medium">Guest</th>
                    <th className="pb-3 font-medium">Type</th>
                    <th className="pb-3 font-medium">LTV</th>
                    <th className="pb-3 font-medium">Spend</th>
                    <th className="pb-3 font-medium">Channel</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ink-50">
                  {guests.map((g) => (
                    <tr
                      key={g.id}
                      onClick={() => setSelected(g)}
                      className={`cursor-pointer transition hover:bg-sea-500/5 ${
                        selected?.id === g.id ? "bg-sea-500/8" : ""
                      }`}
                    >
                      <td className="py-3">
                        <p className="font-medium text-ink-900">{g.name}</p>
                        <p className="text-xs text-ink-400">
                          {g.country} · {g.language.toUpperCase()}
                        </p>
                      </td>
                      <td className="py-3 capitalize text-ink-600">
                        {g.travel_type || "—"}
                      </td>
                      <td className="py-3">
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 w-16 overflow-hidden rounded-full bg-ink-100">
                            <div
                              className="h-full rounded-full bg-sea-500"
                              style={{ width: `${g.ltv_score}%` }}
                            />
                          </div>
                          <span className="text-xs text-ink-500">
                            {Math.round(g.ltv_score)}
                          </span>
                        </div>
                      </td>
                      <td className="py-3 text-ink-700">
                        {formatCurrency(g.lifetime_spend)}
                      </td>
                      <td className="py-3">
                        <Badge>{g.communication_preference}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        {selected && (
          <aside className="animate-fade-up space-y-4 opacity-0 [animation-delay:120ms]">
            <div className="rounded-2xl border border-ink-200/60 bg-gradient-to-b from-ink-950 to-ink-900 p-5 text-white">
              <p className="text-xs uppercase tracking-wider text-ink-400">
                Profile
              </p>
              <h2 className="mt-2 font-display text-2xl">{selected.name}</h2>
              <p className="mt-1 text-sm text-ink-300">
                {selected.email || "No email"} · {selected.phone || "No phone"}
              </p>
              <div className="mt-5 grid grid-cols-2 gap-3">
                <div>
                  <p className="text-xs text-ink-400">LTV score</p>
                  <p className="font-display text-2xl text-sea-300">
                    {Math.round(selected.ltv_score)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-ink-400">Satisfaction</p>
                  <p className="font-display text-2xl">
                    {Math.round(selected.satisfaction_score)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-ink-400">Stays</p>
                  <p className="text-lg">{selected.stay_count}</p>
                </div>
                <div>
                  <p className="text-xs text-ink-400">Lifetime spend</p>
                  <p className="text-lg">
                    {formatCurrency(selected.lifetime_spend)}
                  </p>
                </div>
              </div>
            </div>

            <div className="rounded-2xl border border-ink-200/60 bg-white/70 p-5 backdrop-blur">
              <h3 className="font-display text-lg text-ink-900">Preferences</h3>
              <dl className="mt-3 space-y-2 text-sm">
                <div className="flex justify-between gap-2">
                  <dt className="text-ink-400">Travel type</dt>
                  <dd className="capitalize text-ink-800">
                    {selected.travel_type || "—"}
                  </dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-ink-400">Purpose</dt>
                  <dd className="capitalize text-ink-800">
                    {selected.purpose || "—"}
                  </dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-ink-400">Children</dt>
                  <dd className="text-ink-800">{selected.children}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-ink-400">Dietary</dt>
                  <dd className="text-ink-800">
                    {selected.dietary_preferences || "None noted"}
                  </dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-ink-400">Complaints</dt>
                  <dd className="text-ink-800">{selected.complaint_history}</dd>
                </div>
              </dl>
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}
