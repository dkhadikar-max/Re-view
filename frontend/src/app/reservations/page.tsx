"use client";

import { useEffect, useState } from "react";
import { TopBar } from "@/components/TopBar";
import { Badge, Button, Empty, Panel } from "@/components/ui";
import { api, type Reservation } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { useMoney } from "@/components/WorkspaceProvider";

export default function ReservationsPage() {
  const money = useMoney();
  const [rows, setRows] = useState<Reservation[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    guest_name: "",
    country: "Germany",
    language: "de",
    travel_type: "leisure",
    check_in: new Date().toISOString().slice(0, 10),
    check_out: new Date(Date.now() + 3 * 86400000).toISOString().slice(0, 10),
    room_type: "Deluxe Double",
    total_amount: 350,
    source: "direct",
    communication_preference: "whatsapp",
  });

  async function load() {
    setRows(await api.reservations());
  }

  useEffect(() => {
    load().catch(console.error);
  }, []);

  async function runDecide(id: string) {
    setBusy(id);
    try {
      await api.decide(id);
      await load();
    } finally {
      setBusy(null);
    }
  }

  async function runCheckout(id: string) {
    setBusy(id);
    try {
      await api.checkout(id);
      await load();
    } finally {
      setBusy(null);
    }
  }

  async function createReservation(e: React.FormEvent) {
    e.preventDefault();
    setBusy("create");
    try {
      await api.createReservation(form);
      setShowForm(false);
      await load();
    } finally {
      setBusy(null);
    }
  }

  return (
    <div>
      <TopBar
        title="Reservations"
        subtitle="Every reservation is an event — AI decides the next best action."
        action={
          <Button onClick={() => setShowForm((v) => !v)}>
            {showForm ? "Cancel" : "New reservation"}
          </Button>
        }
      />

      {showForm && (
        <form
          onSubmit={createReservation}
          className="mb-6 animate-fade-up grid gap-3 rounded-2xl border border-ink-200/60 bg-white/70 p-5 opacity-0 sm:grid-cols-2 lg:grid-cols-4"
        >
          {(
            [
              ["guest_name", "Guest name", "text"],
              ["country", "Country", "text"],
              ["language", "Language", "text"],
              ["travel_type", "Travel type", "text"],
              ["check_in", "Check-in", "date"],
              ["check_out", "Check-out", "date"],
              ["room_type", "Room type", "text"],
              ["source", "Source", "text"],
            ] as const
          ).map(([key, label, type]) => (
            <label key={key} className="text-xs text-ink-500">
              {label}
              <input
                type={type}
                required={key === "guest_name"}
                className="mt-1 w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-sm text-ink-900 outline-none focus:border-sea-500"
                value={String(form[key as keyof typeof form])}
                onChange={(e) =>
                  setForm((f) => ({ ...f, [key]: e.target.value }))
                }
              />
            </label>
          ))}
          <div className="sm:col-span-2 lg:col-span-4">
            <Button type="submit" disabled={busy === "create"}>
              Create &amp; trigger AI
            </Button>
          </div>
        </form>
      )}

      <Panel title="All reservations" className="[animation-delay:80ms]">
        {rows.length === 0 ? (
          <Empty>No reservations</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-ink-100 text-xs uppercase tracking-wider text-ink-400">
                  <th className="pb-3 font-medium">Guest</th>
                  <th className="pb-3 font-medium">Dates</th>
                  <th className="pb-3 font-medium">Room</th>
                  <th className="pb-3 font-medium">Source</th>
                  <th className="pb-3 font-medium">Amount</th>
                  <th className="pb-3 font-medium">Status</th>
                  <th className="pb-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-50">
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td className="py-3 font-medium text-ink-900">
                      {r.guest_name}
                    </td>
                    <td className="py-3 text-ink-600">
                      {formatDate(r.check_in)} → {formatDate(r.check_out)}
                    </td>
                    <td className="py-3 text-ink-600">{r.room_type}</td>
                    <td className="py-3 text-ink-600">{r.source}</td>
                    <td className="py-3">
                      {money(r.total_amount, r.currency)}
                    </td>
                    <td className="py-3">
                      <Badge tone={r.status}>
                        {r.status.replace("_", " ")}
                      </Badge>
                    </td>
                    <td className="py-3">
                      <div className="flex flex-wrap gap-1">
                        <Button
                          variant="secondary"
                          disabled={busy === r.id}
                          onClick={() => runDecide(r.id)}
                        >
                          AI decide
                        </Button>
                        {r.status !== "checked_out" &&
                          r.status !== "cancelled" && (
                            <Button
                              variant="ghost"
                              disabled={busy === r.id}
                              onClick={() => runCheckout(r.id)}
                            >
                              Checkout
                            </Button>
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
