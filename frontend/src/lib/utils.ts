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
  if (["sent", "accepted", "approved", "done", "connected", "positive"].includes(s))
    return "bg-sea-500/15 text-sea-700";
  if (["pending", "pending_approval", "offered", "queued", "open", "confirmed"].includes(s))
    return "bg-sand-100 text-ink-800";
  if (["rejected", "failed", "cancelled", "critical", "negative"].includes(s) || s.includes("negative"))
    return "bg-coral-500/15 text-coral-600";
  if (["checked_in", "in_progress", "delivered"].includes(s))
    return "bg-ink-100 text-ink-700";
  return "bg-ink-100 text-ink-600";
}
