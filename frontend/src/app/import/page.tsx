"use client";

import { useState } from "react";
import Link from "next/link";
import {
  CheckCircle2,
  Download,
  FileSpreadsheet,
  FileText,
  Mail,
  PenLine,
  Plug,
} from "lucide-react";
import { TopBar } from "@/components/TopBar";
import { Badge, Button, Panel } from "@/components/ui";
import { api, type CsvValidationReport, type ImportSummary } from "@/lib/api";
import { useMoney } from "@/components/WorkspaceProvider";

const CSV_TEMPLATE_COLUMNS = [
  "name",
  "email",
  "phone",
  "check_in",
  "check_out",
  "adults",
  "children",
  "country",
  "amount",
];

function downloadCsvTemplate() {
  const csv = CSV_TEMPLATE_COLUMNS.join(",") + "\n";
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "revisit-reservations-template.csv";
  a.click();
  URL.revokeObjectURL(url);
}

type Source = "csv" | "manual";
type ComingSoonSource = "pdf" | "email" | "cloudbeds" | "mews" | "opera";
type Step = "source" | "upload" | "validate" | "review" | "summary";

const SOURCES: {
  id: Source | ComingSoonSource;
  label: string;
  description: string;
  icon: typeof FileSpreadsheet;
  enabled: boolean;
}[] = [
  {
    id: "csv",
    label: "CSV",
    description: "Upload a spreadsheet export from any PMS or booking tool.",
    icon: FileSpreadsheet,
    enabled: true,
  },
  {
    id: "manual",
    label: "Manual Entry",
    description: "Type in one reservation by hand.",
    icon: PenLine,
    enabled: true,
  },
  {
    id: "pdf",
    label: "Booking PDF",
    description: "Extract reservations from a booking confirmation PDF.",
    icon: FileText,
    enabled: false,
  },
  {
    id: "email",
    label: "Booking Email",
    description: "Forward booking confirmation emails for automatic import.",
    icon: Mail,
    enabled: false,
  },
  {
    id: "cloudbeds",
    label: "Cloudbeds",
    description: "Direct PMS sync.",
    icon: Plug,
    enabled: false,
  },
  {
    id: "mews",
    label: "Mews",
    description: "Direct PMS sync.",
    icon: Plug,
    enabled: false,
  },
  {
    id: "opera",
    label: "Opera",
    description: "Direct PMS sync.",
    icon: Plug,
    enabled: false,
  },
];

const REQUIRED_CSV_COLUMNS = ["name", "check_in", "check_out", "amount"];

function parseCsvPreview(text: string) {
  const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
  if (lines.length === 0) return { headers: [], rows: [] as string[][], rowCount: 0 };
  const headers = lines[0].split(",").map((h) => h.trim());
  const rows = lines.slice(1, 6).map((line) => line.split(","));
  return { headers, rows, rowCount: lines.length - 1 };
}

export default function DataImportPage() {
  const money = useMoney();
  const [step, setStep] = useState<Step>("source");
  const [source, setSource] = useState<Source | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // CSV state
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<{
    headers: string[];
    rows: string[][];
    rowCount: number;
  } | null>(null);
  const [validation, setValidation] = useState<CsvValidationReport | null>(null);
  const [validating, setValidating] = useState(false);

  // Manual entry state
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

  const [summary, setSummary] = useState<ImportSummary | null>(null);
  const [skippedCount, setSkippedCount] = useState(0);
  const [earlyAccessSent, setEarlyAccessSent] = useState<Set<string>>(new Set());

  async function joinEarlyAccess(id: string) {
    try {
      await api.requestEarlyAccess(id);
      setEarlyAccessSent((prev) => new Set(prev).add(id));
    } catch {
      // Non-critical — worst case the click just doesn't register.
    }
  }

  function reset() {
    setStep("source");
    setSource(null);
    setFile(null);
    setPreview(null);
    setValidation(null);
    setSummary(null);
    setSkippedCount(0);
    setError("");
  }

  function selectSource(id: Source | ComingSoonSource) {
    if (id !== "csv" && id !== "manual") return; // Coming Soon — not selectable
    setSource(id);
    setStep("upload");
    setError("");
  }

  async function onFileChosen(f: File) {
    setFile(f);
    setError("");
    setValidation(null);
    try {
      const text = await f.text();
      setPreview(parseCsvPreview(text));
    } catch {
      setError("Could not read that file. Please choose a CSV file.");
      setPreview(null);
      return;
    }
    setValidating(true);
    try {
      const report = await api.validateCsv(f);
      setValidation(report);
      setStep("validate");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not validate that file");
    } finally {
      setValidating(false);
    }
  }


  async function runImport() {
    setBusy(true);
    setError("");
    try {
      if (source === "csv" && file) {
        const result = await api.importCsv(file);
        setSkippedCount(result.rows_skipped || 0);
        if (result.import_session_id) {
          setSummary(await api.importSummary(result.import_session_id));
        }
        setStep("summary");
      } else if (source === "manual") {
        const result = await api.createReservation(form);
        if (result.import_session_id) {
          setSummary(await api.importSummary(result.import_session_id));
        }
        setStep("summary");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <TopBar
        title="Import Reservations"
        subtitle="Bring reservations in from wherever they live today — one flow, any source."
      />

      {error && (
        <p className="mb-4 rounded-lg border border-coral-200 bg-coral-50 px-3 py-2 text-sm text-coral-800">
          {error}
        </p>
      )}

      {step === "source" && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {SOURCES.map((s) => {
            const Icon = s.icon;
            if (s.enabled) {
              return (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => selectSource(s.id)}
                  className="animate-fade-up rounded-2xl border border-ink-200/60 bg-white/70 p-5 text-left opacity-0 transition hover:border-sea-400 hover:shadow-sm"
                >
                  <Icon className="h-5 w-5 text-sea-600" />
                  <p className="mt-3 font-display text-lg text-ink-900">{s.label}</p>
                  <p className="mt-1 text-sm text-ink-500">{s.description}</p>
                </button>
              );
            }
            const requested = earlyAccessSent.has(s.id);
            return (
              <div
                key={s.id}
                className="animate-fade-up rounded-2xl border border-ink-100 bg-ink-50/60 p-5 opacity-0"
              >
                <div className="flex items-center justify-between gap-2">
                  <Icon className="h-5 w-5 text-ink-400" />
                  <Badge>Coming soon</Badge>
                </div>
                <p className="mt-3 font-display text-lg text-ink-700">{s.label}</p>
                <p className="mt-1 text-sm text-ink-500">{s.description}</p>
                <button
                  type="button"
                  disabled={requested}
                  onClick={() => void joinEarlyAccess(s.id)}
                  className="mt-3 text-xs font-medium text-sea-600 hover:underline disabled:text-sea-400 disabled:no-underline"
                >
                  {requested ? "You're on the list ✓" : "Join early access →"}
                </button>
              </div>
            );
          })}
        </div>
      )}

      {step === "upload" && source === "csv" && (
        <Panel title="Upload a CSV" className="[animation-delay:40ms]">
          <p className="text-sm text-ink-500">
            Required columns: {REQUIRED_CSV_COLUMNS.join(", ")}. Optional: email,
            phone, country, language, travel_type, room_type, adults, children,
            currency, special_requests, channel.
          </p>
          <button
            type="button"
            onClick={downloadCsvTemplate}
            className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-sea-600 hover:underline"
          >
            <Download className="h-3.5 w-3.5" />
            Download CSV template
          </button>
          <input
            type="file"
            accept=".csv"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void onFileChosen(f);
            }}
            className="mt-4 block w-full text-sm text-ink-600 file:mr-4 file:rounded-lg file:border-0 file:bg-sea-600 file:px-4 file:py-2 file:text-sm file:font-medium file:text-white hover:file:bg-sea-700"
          />
          {validating && (
            <p className="mt-4 text-sm text-ink-500">Validating…</p>
          )}
        </Panel>
      )}

      {step === "validate" && source === "csv" && validation && (
        <Panel title="Validation results" className="[animation-delay:40ms]">
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-xl border border-sea-200 bg-sea-500/10 px-4 py-3">
              <p className="text-2xl font-display text-sea-800">
                ✓ {validation.valid_count}
              </p>
              <p className="text-xs text-ink-500">Valid</p>
            </div>
            <div className="rounded-xl border border-sand-300/60 bg-sand-100/60 px-4 py-3">
              <p className="text-2xl font-display text-ink-800">
                ⚠ {validation.warning_count}
              </p>
              <p className="text-xs text-ink-500">Warnings</p>
            </div>
            <div className="rounded-xl border border-coral-200 bg-coral-50 px-4 py-3">
              <p className="text-2xl font-display text-coral-700">
                ✗ {validation.error_count}
              </p>
              <p className="text-xs text-ink-500">Errors</p>
            </div>
          </div>

          {validation.errors.length > 0 && (
            <div className="mt-5">
              <p className="text-xs font-medium uppercase tracking-wider text-coral-700">
                Errors — these rows will be skipped
              </p>
              <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto text-sm">
                {validation.errors.map((issue, i) => (
                  <li key={i} className="text-ink-700">
                    <span className="text-coral-600">Line {issue.line_number}</span>
                    {issue.field && <span className="text-ink-400"> · {issue.field}</span>}
                    {" — "}
                    {issue.message}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {validation.warnings.length > 0 && (
            <div className="mt-5">
              <p className="text-xs font-medium uppercase tracking-wider text-ink-500">
                Warnings — these will still import
              </p>
              <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto text-sm">
                {validation.warnings.map((issue, i) => (
                  <li key={i} className="text-ink-600">
                    <span className="text-ink-400">Line {issue.line_number}</span>
                    {issue.field && <span className="text-ink-400"> · {issue.field}</span>}
                    {" — "}
                    {issue.message}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="mt-5 flex gap-2">
            <Button
              disabled={validation.valid_count === 0}
              onClick={() => setStep("review")}
            >
              {validation.error_count > 0
                ? `Continue with ${validation.valid_count} valid`
                : "Continue to review"}
            </Button>
            <Button variant="ghost" onClick={() => setStep("upload")}>
              Fix file
            </Button>
          </div>
          {validation.valid_count === 0 && (
            <p className="mt-3 text-sm text-coral-600">
              No valid rows to import — fix the errors above and re-upload.
            </p>
          )}
        </Panel>
      )}

      {step === "upload" && source === "manual" && (
        <Panel title="Enter a reservation" className="[animation-delay:40ms]">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {(
              [
                ["guest_name", "Guest name", "text"],
                ["country", "Country", "text"],
                ["language", "Language", "text"],
                ["travel_type", "Travel type", "text"],
                ["check_in", "Check-in", "date"],
                ["check_out", "Check-out", "date"],
                ["room_type", "Room type", "text"],
                ["total_amount", "Amount", "number"],
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
                    setForm((f) => ({
                      ...f,
                      [key]: type === "number" ? Number(e.target.value) || 0 : e.target.value,
                    }))
                  }
                />
              </label>
            ))}
          </div>
          <Button
            className="mt-5"
            disabled={!form.guest_name.trim()}
            onClick={() => setStep("review")}
          >
            Continue to review
          </Button>
        </Panel>
      )}

      {step === "review" && source === "csv" && preview && (
        <Panel title="Review before importing" className="[animation-delay:40ms]">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-ink-100 text-xs uppercase tracking-wider text-ink-400">
                  {preview.headers.map((h) => (
                    <th key={h} className="pb-2 pr-4 font-medium">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-50">
                {preview.rows.map((row, i) => (
                  <tr key={i}>
                    {row.map((cell, j) => (
                      <td key={j} className="py-2 pr-4 text-ink-700">
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-4 text-sm text-ink-500">
            {validation ? (
              <>
                Importing {validation.valid_count} reservation
                {validation.valid_count === 1 ? "" : "s"}.
                {validation.error_count > 0 &&
                  ` ${validation.error_count} row${validation.error_count === 1 ? "" : "s"} with errors will be skipped.`}
              </>
            ) : (
              <>
                Importing all {preview.rowCount} reservation
                {preview.rowCount === 1 ? "" : "s"}.
              </>
            )}
          </p>
          <div className="mt-4 flex gap-2">
            <Button disabled={busy} onClick={() => void runImport()}>
              {busy
                ? "Importing…"
                : `Import ${validation ? validation.valid_count : preview.rowCount} reservations`}
            </Button>
            <Button
              variant="ghost"
              disabled={busy}
              onClick={() => setStep(validation ? "validate" : "upload")}
            >
              Back
            </Button>
          </div>
        </Panel>
      )}

      {step === "review" && source === "manual" && (
        <Panel title="Review before importing" className="[animation-delay:40ms]">
          <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
            <div className="flex justify-between border-b border-ink-100 pb-1">
              <dt className="text-ink-400">Guest</dt>
              <dd className="text-ink-900">{form.guest_name || "—"}</dd>
            </div>
            <div className="flex justify-between border-b border-ink-100 pb-1">
              <dt className="text-ink-400">Dates</dt>
              <dd className="text-ink-900">
                {form.check_in} → {form.check_out}
              </dd>
            </div>
            <div className="flex justify-between border-b border-ink-100 pb-1">
              <dt className="text-ink-400">Room</dt>
              <dd className="text-ink-900">{form.room_type}</dd>
            </div>
            <div className="flex justify-between border-b border-ink-100 pb-1">
              <dt className="text-ink-400">Amount</dt>
              <dd className="text-ink-900">{money(form.total_amount)}</dd>
            </div>
          </dl>
          <div className="mt-4 flex gap-2">
            <Button
              disabled={busy || !form.guest_name.trim()}
              onClick={() => void runImport()}
            >
              {busy ? "Importing…" : "Import reservation"}
            </Button>
            <Button variant="ghost" disabled={busy} onClick={() => setStep("upload")}>
              Back
            </Button>
          </div>
        </Panel>
      )}

      {step === "summary" && (
        <div className="animate-fade-up rounded-2xl border border-ink-200/60 bg-gradient-to-br from-ink-950 via-ink-900 to-sea-700 p-6 text-white opacity-0">
          <div className="flex items-center gap-2 text-sea-300">
            <CheckCircle2 className="h-4 w-4" />
            <p className="text-[10px] uppercase tracking-[0.18em]">Import complete</p>
          </div>
          {summary ? (
            <>
              <h2 className="mt-2 font-display text-3xl">
                {summary.reservations_imported} Reservation
                {summary.reservations_imported === 1 ? "" : "s"} Imported
              </h2>
              <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <div className="rounded-xl bg-white/5 px-4 py-3">
                  <p className="text-[10px] uppercase tracking-wider text-ink-400">
                    Guests created
                  </p>
                  <p className="mt-1 font-display text-3xl">{summary.guests_created}</p>
                </div>
                <div className="rounded-xl bg-white/5 px-4 py-3">
                  <p className="text-[10px] uppercase tracking-wider text-ink-400">
                    Returning guests
                  </p>
                  <p className="mt-1 font-display text-3xl">{summary.returning_guests}</p>
                </div>
                <div className="rounded-xl bg-white/5 px-4 py-3">
                  <p className="text-[10px] uppercase tracking-wider text-ink-400">
                    Birthdays this month
                  </p>
                  <p className="mt-1 font-display text-3xl">
                    {summary.birthdays_this_month}
                  </p>
                </div>
                <div className="rounded-xl bg-white/5 px-4 py-3">
                  <p className="text-[10px] uppercase tracking-wider text-ink-400">
                    Reviews scheduled
                  </p>
                  <p className="mt-1 font-display text-3xl">
                    {summary.reviews_scheduled}
                  </p>
                </div>
              </div>
              <p className="mt-4 text-sm text-ink-300">
                {summary.upsell_opportunities} upsell opportunit
                {summary.upsell_opportunities === 1 ? "y" : "ies"} already queued for
                approval.
              </p>
              {skippedCount > 0 && (
                <p className="mt-2 text-sm text-sand-300">
                  {skippedCount} row{skippedCount === 1 ? "" : "s"} skipped due to
                  validation errors.
                </p>
              )}
            </>
          ) : (
            <h2 className="mt-2 font-display text-3xl">Import complete</h2>
          )}
          <div className="mt-6 flex flex-wrap gap-3 border-t border-white/10 pt-5">
            <Link href="/">
              <Button variant="secondary">Continue →</Button>
            </Link>
            <Link href="/guests">
              <Button variant="secondary">Open Guest Memory →</Button>
            </Link>
            <Link href="/reservations">
              <Button variant="secondary">View Reservations →</Button>
            </Link>
            <Button variant="ghost" className="!text-white" onClick={reset}>
              Import more
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
