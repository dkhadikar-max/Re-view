"use client";

import { useEffect, useState } from "react";
import { TopBar } from "@/components/TopBar";
import { Badge, Button, Empty, Panel } from "@/components/ui";
import { api, type Connector, type Property, type Workflow } from "@/lib/api";
import { RefreshCw } from "lucide-react";

export default function SettingsPage() {
  const [property, setProperty] = useState<Property | null>(null);
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [syncMsg, setSyncMsg] = useState("");
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    const [props, c, w] = await Promise.all([
      api.properties(),
      api.connectors(),
      api.workflows(),
    ]);
    setProperty(props[0] || null);
    setConnectors(c);
    setWorkflows(w);
  }

  useEffect(() => {
    load().catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
  }, []);

  async function sync() {
    setSyncing(true);
    setError("");
    try {
      const res = await api.syncPms();
      setSyncMsg(res.message);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sync failed");
    } finally {
      setSyncing(false);
    }
  }

  async function tick() {
    setSyncing(true);
    setError("");
    try {
      const res = await api.tickWorkers();
      setSyncMsg(
        `Workers: ${res.events_processed} events, ${res.messages_delivered} messages, ${res.workflows_advanced} workflows`
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Worker tick failed");
    } finally {
      setSyncing(false);
    }
  }

  return (
    <div>
      <TopBar
        title="Settings"
        subtitle="Property context, PMS connectors, and event-driven workflows."
      />

      {property && (
        <div className="mb-6 animate-fade-up rounded-2xl border border-ink-200/60 bg-gradient-to-br from-ink-950 via-ink-900 to-sea-700 p-6 text-white opacity-0">
          <p className="text-xs uppercase tracking-wider text-ink-300">
            Property
          </p>
          <h2 className="mt-2 font-display text-3xl">{property.name}</h2>
          <p className="mt-1 text-ink-300">
            {property.city}, {property.country} · {property.rooms} rooms ·{" "}
            {property.google_rating}★ Google
          </p>
          <p className="mt-4 max-w-2xl text-sm leading-relaxed text-ink-200">
            Brand voice: {property.brand_voice}
          </p>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel
          title="Connectors"
          action={
            <div className="flex gap-2">
              <Button variant="secondary" onClick={tick} disabled={syncing}>
                Run workers
              </Button>
              <Button variant="secondary" onClick={sync} disabled={syncing}>
                <RefreshCw className={`h-3.5 w-3.5 ${syncing ? "animate-spin" : ""}`} />
                Sync Cloudbeds
              </Button>
            </div>
          }
          className="[animation-delay:80ms]"
        >
          {error && <p className="mb-3 text-sm text-coral-600">{error}</p>}
          {syncMsg && (
            <p className="mb-3 text-sm text-sea-700">{syncMsg}</p>
          )}
          {connectors.length === 0 ? (
            <Empty>No connectors</Empty>
          ) : (
            <ul className="divide-y divide-ink-50">
              {connectors.map((c) => (
                <li
                  key={c.id}
                  className="flex items-center justify-between gap-3 py-3"
                >
                  <div>
                    <p className="font-medium text-ink-900">{c.provider}</p>
                    <p className="text-xs text-ink-400">
                      {c.last_sync_at
                        ? `Last sync ${new Date(c.last_sync_at).toLocaleString()}`
                        : "Never synced"}
                    </p>
                  </div>
                  <Badge tone={c.status}>{c.status}</Badge>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Workflows" className="[animation-delay:120ms]">
          {workflows.length === 0 ? (
            <Empty>No workflows</Empty>
          ) : (
            <ul className="divide-y divide-ink-50">
              {workflows.map((w) => (
                <li
                  key={w.id}
                  className="flex items-center justify-between gap-3 py-3"
                >
                  <div>
                    <p className="font-medium text-ink-900">{w.name}</p>
                    <p className="text-xs text-ink-400">
                      Trigger: {w.trigger_event} · {w.runs} runs
                    </p>
                  </div>
                  <Badge tone={w.status}>{w.status}</Badge>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <Panel title="Architecture" className="mt-6 [animation-delay:160ms]">
        <pre className="overflow-x-auto whitespace-pre text-xs leading-relaxed text-ink-600">
{`Booking channels → PMS → Revisit
  AI Brain · Guest Memory · Decision Engine
  Workflow Engine · Review Engine · Revenue Engine
         ↓
WhatsApp · Email · SMS · Google · Stripe · Dashboard`}
        </pre>
      </Panel>
    </div>
  );
}
