"use client";

import { useEffect, useState } from "react";
import { TopBar } from "@/components/TopBar";
import { Badge, Button, Panel } from "@/components/ui";
import { api, type V1Readiness } from "@/lib/api";

export default function IntegrationsPage() {
  const [status, setStatus] = useState<V1Readiness | null>(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    const s = await api.integrationsStatus();
    setStatus(s);
  }

  useEffect(() => {
    load().catch((e) => setError(e instanceof Error ? e.message : "Failed"));
  }, []);

  async function syncCloudbeds() {
    setBusy(true);
    setError("");
    try {
      const res = await api.syncCloudbeds();
      setMsg(res.message || `Imported ${res.imported}`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sync failed");
    } finally {
      setBusy(false);
    }
  }

  if (!status) {
    return (
      <div className="flex h-64 items-center justify-center text-ink-400">
        {error || "Loading integrations…"}
      </div>
    );
  }

  const ownership = status.ownership || [];

  return (
    <div>
      <TopBar
        title="Integrations"
        subtitle="Revisit runs AI + Postgres + Redis. The hotel connects PMS, WhatsApp, email, Stripe, Google."
      />

      <div className="mb-6 animate-fade-up rounded-2xl border border-ink-200/60 bg-gradient-to-br from-sea-800 via-ink-900 to-ink-950 p-6 text-white opacity-0">
        <p className="text-xs uppercase tracking-wider text-sea-200">
          {status.platform || "Argus OS"} · {status.milestone} · {status.version}
        </p>
        <h2 className="mt-2 font-display text-3xl">
          {status.ready_for_first_hotel
            ? "Ready for first hotel"
            : "Configure live credentials"}
        </h2>
        <p className="mt-2 text-sm text-ink-200">
          Queue: {status.queue_backend}
          {status.blockers.length > 0
            ? ` · Blockers: ${status.blockers.join(", ")}`
            : " · Mock mode is fine for demos"}
        </p>
        <div className="mt-4 flex flex-wrap gap-2 text-xs">
          {(status.platform_pays || []).map((s) => (
            <span
              key={s}
              className="rounded-md bg-white/10 px-2 py-1 text-ink-100"
            >
              Platform: {s}
            </span>
          ))}
        </div>
      </div>

      {error && (
        <p className="mb-4 rounded-lg border border-coral-200 bg-coral-50 px-3 py-2 text-sm text-coral-800">
          {error}
        </p>
      )}
      {msg && (
        <p className="mb-4 rounded-lg border border-sea-200 bg-sea-50 px-3 py-2 text-sm text-sea-900">
          {msg}
        </p>
      )}

      <Panel title="Whose account?" className="mb-8">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-ink-100 text-xs uppercase tracking-wider text-ink-400">
                <th className="pb-3 font-medium">Service</th>
                <th className="pb-3 font-medium">Free?</th>
                <th className="pb-3 font-medium">Paid?</th>
                <th className="pb-3 font-medium">Account</th>
                <th className="pb-3 font-medium">V1</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-50">
              {ownership.map((row) => (
                <tr key={row.service}>
                  <td className="py-3">
                    <p className="font-medium text-ink-900">{row.service}</p>
                    <p className="text-xs text-ink-400">{row.category}</p>
                  </td>
                  <td className="py-3 text-ink-600">{row.free_tier}</td>
                  <td className="py-3 text-ink-600">{row.paid}</td>
                  <td className="py-3">
                    <Badge
                      tone={
                        row.account_owner === "platform" ? "accepted" : "offered"
                      }
                    >
                      {row.account_label}
                    </Badge>
                  </td>
                  <td className="py-3 text-xs text-ink-500">
                    {!row.implemented
                      ? "Roadmap"
                      : row.v1_required
                        ? "Required"
                        : "Optional"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <div className="space-y-3">
        {status.integrations.map((item) => (
          <Panel
            key={item.provider}
            title={`P${item.priority} · ${item.provider}`}
            action={
              <div className="flex items-center gap-2">
                <Badge
                  tone={
                    item.account_owner === "platform" ? "accepted" : "offered"
                  }
                >
                  {item.account_label || "Client"}
                </Badge>
                <Badge tone={item.mode === "live" ? "accepted" : "draft"}>
                  {item.mode}
                </Badge>
              </div>
            }
          >
            <p className="text-sm text-ink-600">{item.detail}</p>
            <p className="mt-2 text-xs text-ink-400">
              {item.configured ? "Credentials present" : "Using mock adapter"}
              {item.free_tier ? ` · Free: ${item.free_tier}` : ""}
              {item.paid ? ` · Paid: ${item.paid}` : ""}
            </p>
            {item.provider === "Cloudbeds" && (
              <Button
                className="mt-4"
                variant="secondary"
                disabled={busy}
                onClick={syncCloudbeds}
              >
                Sync reservations
              </Button>
            )}
          </Panel>
        ))}
      </div>
    </div>
  );
}
