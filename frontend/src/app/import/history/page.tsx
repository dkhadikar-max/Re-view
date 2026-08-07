"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { TopBar } from "@/components/TopBar";
import { Badge, Button, Empty, Panel } from "@/components/ui";
import { api, type ImportSessionListItem } from "@/lib/api";
import { formatRelativeTime, importStatusLabel, statusTone } from "@/lib/utils";

const SOURCE_FILTERS: { value: string; label: string }[] = [
  { value: "", label: "All sources" },
  { value: "csv", label: "CSV" },
  { value: "manual", label: "Manual" },
  { value: "pdf", label: "PDF" },
  { value: "email", label: "Email" },
  { value: "cloudbeds", label: "Cloudbeds" },
];

const STATUS_FILTERS: { value: string; label: string }[] = [
  { value: "", label: "All statuses" },
  { value: "completed", label: "Completed" },
  { value: "completed_with_errors", label: "Completed with Warnings" },
  { value: "failed", label: "Failed" },
  { value: "running", label: "In Progress" },
];

function sourceLabel(source: string) {
  return SOURCE_FILTERS.find((s) => s.value === source)?.label || source;
}

export default function ImportHistoryPage() {
  const [sessions, setSessions] = useState<ImportSessionListItem[]>([]);
  const [source, setSource] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    api
      .importSessions({ source: source || undefined, status: statusFilter || undefined })
      .then(setSessions)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [source, statusFilter]);

  return (
    <div>
      <TopBar
        title="Import History"
        subtitle="Every import, where it came from, and what happened."
        action={
          <Link href="/import">
            <Button variant="secondary">New import</Button>
          </Link>
        }
      />

      {error && (
        <p className="mb-4 rounded-lg border border-coral-200 bg-coral-50 px-3 py-2 text-sm text-coral-800">
          {error}
        </p>
      )}

      <div className="mb-4 flex flex-wrap gap-3">
        <label className="text-xs text-ink-500">
          Source
          <select
            value={source}
            onChange={(e) => setSource(e.target.value)}
            className="ml-2 rounded-lg border border-ink-200 bg-white px-2 py-1.5 text-sm text-ink-800 outline-none focus:border-sea-500"
          >
            {SOURCE_FILTERS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs text-ink-500">
          Status
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="ml-2 rounded-lg border border-ink-200 bg-white px-2 py-1.5 text-sm text-ink-800 outline-none focus:border-sea-500"
          >
            {STATUS_FILTERS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <Panel title={loading ? "Loading…" : `${sessions.length} imports`}>
        {sessions.length === 0 ? (
          <Empty>
            {loading
              ? "Loading import history…"
              : "No imports yet. Once you import reservations, they'll show up here."}
          </Empty>
        ) : (
          <ul className="divide-y divide-ink-50">
            {sessions.map((s) => (
              <li
                key={s.id}
                className="flex flex-wrap items-center justify-between gap-3 py-4"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-medium text-ink-900">
                      {s.filename || `${sourceLabel(s.source)} entry`}
                    </p>
                    <Badge>{sourceLabel(s.source)}</Badge>
                    <Badge tone={s.status}>{importStatusLabel(s.status)}</Badge>
                  </div>
                  <p className="mt-1 text-xs text-ink-500">
                    {s.rows_imported} imported
                    {s.rows_skipped > 0 && ` · ${s.rows_skipped} skipped`}
                    {s.rows_failed > 0 && ` · ${s.rows_failed} failed`}
                    {" · "}
                    {formatRelativeTime(s.started_at)} · by {s.initiated_by}
                  </p>
                </div>
                <Link
                  href={`/import/history/${s.id}`}
                  className="shrink-0 text-sm font-medium text-sea-600 hover:underline"
                >
                  View Details →
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
