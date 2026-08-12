"use client";

import { useEffect, useMemo, useState } from "react";
import { TopBar } from "@/components/TopBar";
import { Badge, Button, Empty, Panel } from "@/components/ui";
import { api, type Approval } from "@/lib/api";

export default function ApprovalsPage() {
  const [pending, setPending] = useState<Approval[]>([]);
  const [history, setHistory] = useState<Approval[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkError, setBulkError] = useState("");

  async function load() {
    const [p, all] = await Promise.all([
      api.approvals("pending"),
      api.approvals(),
    ]);
    setPending(p);
    setHistory(all.filter((a) => a.status !== "pending"));
    // Drop selections for items no longer pending (approved/rejected elsewhere).
    setSelected((prev) => {
      const stillPending = new Set(p.map((a) => a.id));
      const next = new Set([...prev].filter((id) => stillPending.has(id)));
      return next;
    });
  }

  useEffect(() => {
    load().catch(console.error);
  }, []);

  const allSelected = pending.length > 0 && selected.size === pending.length;
  const anyBusy = bulkBusy || busy !== null;

  function toggleOne(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(pending.map((a) => a.id)));
  }

  async function act(id: string, action: "approve" | "reject") {
    setBusy(id);
    try {
      await api.actApproval(id, action);
      await load();
    } finally {
      setBusy(null);
    }
  }

  async function bulkAct(action: "approve" | "reject") {
    const ids = [...selected];
    if (ids.length === 0) return;
    setBulkBusy(true);
    setBulkError("");
    try {
      const results = await Promise.allSettled(
        ids.map((id) => api.actApproval(id, action))
      );
      const failed = results.filter((r) => r.status === "rejected").length;
      if (failed > 0) {
        setBulkError(
          `${failed} of ${ids.length} ${
            failed === 1 ? "item" : "items"
          } failed to ${action}. The rest were processed — try the remaining ones again.`
        );
      }
      await load();
    } finally {
      setBulkBusy(false);
    }
  }

  const selectedLabel = useMemo(
    () => `${selected.size} selected`,
    [selected.size]
  );

  return (
    <div>
      <TopBar
        title="Approval Queue"
        subtitle="Nothing goes out without approval — sensitive or needs-review actions wait here."
      />

      <Panel
        title={`${pending.length} pending`}
        action={
          pending.length > 0 ? (
            <label className="flex cursor-pointer items-center gap-2 text-xs text-ink-500">
              <input
                type="checkbox"
                checked={allSelected}
                onChange={toggleAll}
                disabled={anyBusy}
                className="rounded border-ink-300 text-sea-600 focus:ring-sea-500"
              />
              Select all
            </label>
          ) : undefined
        }
        className="mb-6 [animation-delay:80ms]"
      >
        {pending.length === 0 ? (
          <Empty>Queue is clear</Empty>
        ) : (
          <>
            {selected.size > 0 && (
              <div className="mb-4 flex flex-wrap items-center gap-3 rounded-xl border border-sea-200 bg-sea-500/10 px-4 py-3">
                <span className="text-sm font-medium text-sea-900">
                  {selectedLabel}
                </span>
                <Button
                  disabled={anyBusy}
                  onClick={() => bulkAct("approve")}
                >
                  {bulkBusy ? "Approving…" : "Approve selected"}
                </Button>
                <Button
                  variant="danger"
                  disabled={anyBusy}
                  onClick={() => bulkAct("reject")}
                >
                  {bulkBusy ? "Rejecting…" : "Reject selected"}
                </Button>
                <Button
                  variant="ghost"
                  disabled={anyBusy}
                  onClick={() => setSelected(new Set())}
                >
                  Clear
                </Button>
              </div>
            )}
            {bulkError && (
              <p className="mb-4 text-sm text-coral-600" role="alert">
                {bulkError}
              </p>
            )}
            <ul className="space-y-4">
              {pending.map((a) => (
                <li
                  key={a.id}
                  className="flex gap-3 rounded-xl border border-ink-100 bg-ink-50/50 p-4"
                >
                  <input
                    type="checkbox"
                    checked={selected.has(a.id)}
                    onChange={() => toggleOne(a.id)}
                    disabled={anyBusy}
                    className="mt-1 h-4 w-4 shrink-0 rounded border-ink-300 text-sea-600 focus:ring-sea-500"
                    aria-label={`Select ${a.title}`}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-medium text-ink-900">{a.title}</h3>
                      <Badge>{a.approval_type.replace("_", " ")}</Badge>
                    </div>
                    <pre className="mt-3 max-h-40 overflow-y-auto whitespace-pre-wrap font-sans text-sm text-ink-700">
                      {a.content}
                    </pre>
                    <div className="mt-4 flex gap-2">
                      <Button
                        disabled={busy === a.id || bulkBusy}
                        onClick={() => act(a.id, "approve")}
                      >
                        Approve &amp; send
                      </Button>
                      <Button
                        variant="danger"
                        disabled={busy === a.id || bulkBusy}
                        onClick={() => act(a.id, "reject")}
                      >
                        Reject
                      </Button>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </>
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
