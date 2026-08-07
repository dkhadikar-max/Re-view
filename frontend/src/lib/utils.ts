import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(amount: number, currency = "EUR") {
  const code = (currency || "EUR").toUpperCase();
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: code,
      maximumFractionDigits: 0,
    }).format(amount);
  } catch {
    return `${code} ${Math.round(Number(amount) || 0).toLocaleString()}`;
  }
}

export function formatDate(value: string) {
  return new Date(value).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function statusTone(status: string) {
  const s = status.toLowerCase();
  if (["sent", "accepted", "approved", "done", "connected", "positive", "completed"].includes(s))
    return "bg-sea-500/15 text-sea-700";
  if (
    [
      "pending",
      "pending_approval",
      "offered",
      "queued",
      "open",
      "confirmed",
      "completed_with_errors",
    ].includes(s)
  )
    return "bg-sand-100 text-ink-800";
  if (["rejected", "failed", "cancelled", "critical", "negative"].includes(s) || s.includes("negative"))
    return "bg-coral-500/15 text-coral-600";
  if (["checked_in", "in_progress", "delivered", "running"].includes(s))
    return "bg-ink-100 text-ink-700";
  return "bg-ink-100 text-ink-600";
}

export function formatRelativeTime(value: string) {
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return "—";
  const diffMs = Date.now() - then;
  const minute = 60_000;
  const hour = 60 * minute;
  const day = 24 * hour;
  if (diffMs < minute) return "just now";
  if (diffMs < hour) {
    const m = Math.round(diffMs / minute);
    return `${m} minute${m === 1 ? "" : "s"} ago`;
  }
  if (diffMs < day) {
    const h = Math.round(diffMs / hour);
    return `${h} hour${h === 1 ? "" : "s"} ago`;
  }
  if (diffMs < 2 * day) return "Yesterday";
  const d = Math.round(diffMs / day);
  if (d < 30) return `${d} days ago`;
  return formatDate(value);
}

export function formatDuration(ms?: number | null) {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms}ms`;
  const totalSeconds = Math.round(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes === 0) return `${seconds}s`;
  return `${minutes}m ${seconds}s`;
}

export function importStatusLabel(status: string) {
  switch (status) {
    case "running":
      return "In Progress";
    case "completed":
      return "Completed";
    case "completed_with_errors":
      return "Completed with Warnings";
    case "failed":
      return "Failed";
    default:
      return status;
  }
}
