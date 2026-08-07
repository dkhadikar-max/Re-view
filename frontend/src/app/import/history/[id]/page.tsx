"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Download } from "lucide-react";
import { TopBar } from "@/components/TopBar";
import { Badge, Button, Panel } from "@/components/ui";
import { api, type ImportSessionDetail } from "@/lib/api";
import { formatDuration, importStatusLabel } from "@/lib/utils";

function downloadErrorReport(session: ImportSessionDetail) {
  const lines = [
    "line_number,severity,field,message",
    ...session.errors.map(
      (e) => `${e.line_number},error,${e.field || ""},"${e.message.replace(/"/g, '""')}"`
    ),
    ...session.warnings.map(
      (w) => `${w.line_number},warning,${w.field || ""},"${w.message.replace(/"/g, '""')}"`
    ),
  ];
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `import-report-${session.id}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export default function ImportDetailsPage() {
  const params = useParams<{ id: string }>();
  const [session, setSession] = useState<ImportSessionDetail | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!params.id) return;
    api
      .importSession(params.id)
      .then(setSession)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
  }, [params.id]);

  if (error) {
    return (
      <div className="rounded-xl border border-coral-200 bg-coral-50 p-4 text-sm text-coral-800">
        {error}
      </div>
    );
  }

  if (!session) {
    return (
      <div className="flex h-64 items-center justify-center text-ink-400">
        Loading import details…
      </div>
    );
  }

  const hasIssues = session.warnings.length > 0 || session.errors.length > 0;

  return (
    <div>
      <TopBar
        title={session.filename || "Import details"}
        subtitle={`${session.source} · ${importStatusLabel(session.status)}`}
        action={
          <Link href="/import/history">
            <Button variant="ghost">← All imports</Button>
          </Link>
        }
      />

      <Panel title="Overview" className="[animation-delay:40ms]">
        <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
          <div className="flex justify-between border-b border-ink-100 pb-1.5">
            <dt className="text-ink-400">Filename</dt>
            <dd className="text-ink-900">{session.filename || "—"}</dd>
          </div>
          <div className="flex justify-between border-b border-ink-100 pb-1.5">
            <dt className="text-ink-400">Imported by</dt>
            <dd className="text-ink-900">{session.initiated_by}</dd>
          </div>
          <div className="flex justify-between border-b border-ink-100 pb-1.5">
            <dt className="text-ink-400">Imported at</dt>
            <dd className="text-ink-900">
              {new Date(session.started_at).toLocaleString()}
            </dd>
          </div>
          <div className="flex justify-between border-b border-ink-100 pb-1.5">
            <dt className="text-ink-400">Duration</dt>
            <dd className="text-ink-900">{formatDuration(session.duration_ms)}</dd>
          </div>
        </dl>

        <div className="mt-5 grid gap-3 sm:grid-cols-3">
          <div className="rounded-xl border border-sea-200 bg-sea-500/10 px-4 py-3">
            <p className="text-2xl font-display text-sea-800">{session.rows_imported}</p>
            <p className="text-xs text-ink-500">Imported</p>
          </div>
          <div className="rounded-xl border border-sand-300/60 bg-sand-100/60 px-4 py-3">
            <p className="text-2xl font-display text-ink-800">{session.rows_skipped}</p>
            <p className="text-xs text-ink-500">Skipped</p>
          </div>
          <div className="rounded-xl border border-coral-200 bg-coral-50 px-4 py-3">
            <p className="text-2xl font-display text-coral-700">{session.rows_failed}</p>
            <p className="text-xs text-ink-500">Failed</p>
          </div>
        </div>

        <div className="mt-5 flex flex-wrap gap-3">
          {hasIssues && (
            <Button variant="secondary" onClick={() => downloadErrorReport(session)}>
              <Download className="h-3.5 w-3.5" />
              Download error report
            </Button>
          )}
          <Link href="/reservations">
            <Button variant="secondary">View imported reservations →</Button>
          </Link>
        </div>
      </Panel>

      {session.errors.length > 0 && (
        <Panel title="Errors" className="mt-6 [animation-delay:80ms]">
          <ul className="space-y-1.5 text-sm">
            {session.errors.map((issue, i) => (
              <li key={i} className="text-ink-700">
                <Badge tone="failed">Line {issue.line_number}</Badge>
                {issue.field && <span className="ml-2 text-ink-400">{issue.field}</span>}
                <span className="ml-2">{issue.message}</span>
              </li>
            ))}
          </ul>
        </Panel>
      )}

      {session.warnings.length > 0 && (
        <Panel title="Warnings" className="mt-6 [animation-delay:120ms]">
          <ul className="space-y-1.5 text-sm">
            {session.warnings.map((issue, i) => (
              <li key={i} className="text-ink-700">
                <Badge tone="pending">Line {issue.line_number}</Badge>
                {issue.field && <span className="ml-2 text-ink-400">{issue.field}</span>}
                <span className="ml-2">{issue.message}</span>
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </div>
  );
}
