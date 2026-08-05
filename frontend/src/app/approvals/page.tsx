"use client";

import { useEffect, useState } from "react";
import { TopBar } from "@/components/TopBar";
import { Badge, Button, Empty, Panel } from "@/components/ui";
import { api, type Approval } from "@/lib/api";

export default function ApprovalsPage() {
  const [pending, setPending] = useState<Approval[]>([]);
  const [history, setHistory] = useState<Approval[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  async function load() {
    const [p, all] = await Promise.all([
      api.approvals("pending"),
      api.approvals(),
    ]);
    setPending(p);
    setHistory(all.filter((a) => a.status !== "pending"));
  }

  useEffect(() => {
    load().catch(console.error);
  }, []);

  async function act(id: string, action: "approve" | "reject") {
    setBusy(id);
    try {
      await api.actApproval(id, action);
      await load();
    } finally {
      setBusy(null);
    }
  }

  return (
    <div>
      <TopBar
        title="Approval Queue"
        subtitle="AI never executes directly — every low-confidence or sensitive action waits here."
      />

      <Panel
        title={`${pending.length} pending`}
        className="mb-6 [animation-delay:80ms]"
      >
        {pending.length === 0 ? (
          <Empty>Queue is clear</Empty>
        ) : (
          <ul className="space-y-4">
            {pending.map((a) => (
              <li
                key={a.id}
                className="rounded-xl border border-ink-100 bg-ink-50/50 p-4"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="font-medium text-ink-900">{a.title}</h3>
                  <Badge>{a.approval_type.replace("_", " ")}</Badge>
                  {a.confidence != null && (
                    <span className="text-xs text-ink-400">
                      {Math.round(a.confidence * 100)}% confidence
                    </span>
                  )}
                </div>
                <pre className="mt-3 max-h-40 overflow-y-auto whitespace-pre-wrap font-sans text-sm text-ink-700">
                  {a.content}
                </pre>
                <div className="mt-4 flex gap-2">
                  <Button
                    disabled={busy === a.id}
                    onClick={() => act(a.id, "approve")}
                  >
                    Approve &amp; send
                  </Button>
                  <Button
                    variant="danger"
                    disabled={busy === a.id}
                    onClick={() => act(a.id, "reject")}
                  >
                    Reject
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <Panel title="History" className="[animation-delay:120ms]">
        {history.length === 0 ? (
          <Empty>No reviewed items yet</Empty>
        ) : (
          <ul className="divide-y divide-ink-50">
            {history.map((a) => (
              <li
                key={a.id}
                className="flex items-center justify-between gap-3 py-3"
              >
                <div>
                  <p className="text-sm font-medium text-ink-900">{a.title}</p>
                  <p className="text-xs text-ink-400">
                    {a.reviewed_by || "—"} · {a.approval_type}
                  </p>
                </div>
                <Badge tone={a.status}>{a.status}</Badge>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
