"use client";

import { Bell } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type Notification } from "@/lib/api";

export function TopBar({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}) {
  const [notes, setNotes] = useState<Notification[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    api.notifications().then(setNotes).catch(() => setNotes([]));
  }, []);

  const unread = notes.filter((n) => !n.read).length;

  return (
    <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="animate-fade-up">
        <h1 className="font-display text-3xl tracking-tight text-ink-950 md:text-4xl">
          {title}
        </h1>
        {subtitle && (
          <p className="mt-1.5 max-w-xl text-sm text-ink-500">{subtitle}</p>
        )}
      </div>
      <div className="flex items-center gap-3">
        {action}
        <div className="relative">
          <button
            onClick={() => setOpen((v) => !v)}
            className="relative flex h-10 w-10 items-center justify-center rounded-full border border-ink-200 bg-white/70 text-ink-700 backdrop-blur transition hover:border-sea-400"
            aria-label="Notifications"
          >
            <Bell className="h-4 w-4" />
            {unread > 0 && (
              <span className="absolute -right-0.5 -top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-coral-500 text-[10px] text-white animate-pulse-soft">
                {unread}
              </span>
            )}
          </button>
          {open && (
            <div className="absolute right-0 z-40 mt-2 w-80 overflow-hidden rounded-xl border border-ink-200 bg-white shadow-lg animate-fade-in">
              <div className="border-b border-ink-100 px-4 py-3 text-sm font-medium">
                Notifications
              </div>
              <ul className="max-h-72 overflow-y-auto">
                {notes.length === 0 && (
                  <li className="px-4 py-6 text-sm text-ink-400">All clear</li>
                )}
                {notes.map((n) => (
                  <li
                    key={n.id}
                    className="border-b border-ink-50 px-4 py-3 last:border-0"
                  >
                    <p className="text-sm font-medium text-ink-900">{n.title}</p>
                    <p className="mt-0.5 text-xs text-ink-500">{n.body}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
