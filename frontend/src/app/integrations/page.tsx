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

  return (
    <div>
      <TopBar
        title="V1 Integrations"
        subtitle="Cloudbeds → WhatsApp → Email → OpenAI → Google → Stripe. Postgres + Redis — no Kafka."
      />

      <div className="mb-6 animate-fade-up rounded-2xl border border-ink-200/60 bg-gradient-to-br from-sea-800 via-ink-900 to-ink-950 p-6 text-white opacity-0">
        <p className="text-xs uppercase tracking-wider text-sea-200">
          {status.milestone} · {status.version}
        </p>
        <h2 className="mt-2 font-display text-3xl">
          {status.ready_for_first_hotel
            ? "Ready for first hotel"
            : "Configure live credentials"}
        </h2>
        <p className="mt-2 text-sm text-ink-200">
          Queue backend: {status.queue_backend}
          {status.blockers.length > 0
            ? ` · Blockers: ${status.blockers.join(", ")}`
            : " · Mock mode is fine for demos"}
        </p>
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

      <div className="space-y-3">
        {status.integrations.map((item) => (
          <Panel
            key={item.provider}
            title={`P${item.priority} · ${item.provider}`}
            action={
              <Badge tone={item.mode === "live" ? "accepted" : "draft"}>
                {item.mode}
              </Badge>
            }
          >
            <p className="text-sm text-ink-600">{item.detail}</p>
            <p className="mt-2 text-xs text-ink-400">
              {item.configured ? "Credentials present" : "Using mock adapter"}
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
