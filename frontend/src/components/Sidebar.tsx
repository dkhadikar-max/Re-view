"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  Users,
  CalendarDays,
  MessageSquare,
  Star,
  CheckSquare,
  Sparkles,
  Settings,
  Activity,
  TrendingUp,
  ListTodo,
  LogOut,
  Menu,
  X,
  Gift,
  Plug,
} from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { setToken, type User } from "@/lib/api";

const nav = [
  { href: "/", label: "Operations", icon: LayoutDashboard },
  { href: "/analytics", label: "Sales Analytics", icon: TrendingUp },
  { href: "/guests", label: "Guest Memory", icon: Users },
  { href: "/celebrate", label: "Celebrate Rewards", icon: Gift },
  { href: "/reservations", label: "Reservations", icon: CalendarDays },
  { href: "/messages", label: "Messages", icon: MessageSquare },
  { href: "/reviews", label: "Reviews", icon: Star },
  { href: "/approvals", label: "Approvals", icon: CheckSquare },
  { href: "/revenue", label: "Revenue", icon: TrendingUp },
  { href: "/intelligence", label: "Intelligence", icon: Sparkles },
  { href: "/tasks", label: "Tasks", icon: ListTodo },
  { href: "/activity", label: "Event Stream", icon: Activity },
  { href: "/integrations", label: "Integrations", icon: Plug },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar({ user }: { user: User | null }) {
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);

  function logout() {
    setToken(null);
    router.replace("/login");
  }

  const content = (
    <>
      <div className="relative overflow-hidden border-b border-white/10 px-5 py-6">
        <div className="absolute -right-6 -top-6 h-24 w-24 rounded-full bg-sea-500/20 blur-2xl" />
        <p className="font-display text-2xl tracking-tight text-white">Revisit</p>
        <p className="mt-1 text-xs leading-relaxed text-ink-300">
          Guest revenue, after booking
        </p>
      </div>

      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-4" aria-label="Main">
        {nav.map((item) => {
          const active =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              onClick={() => setOpen(false)}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors",
                active
                  ? "bg-white/10 text-white"
                  : "text-ink-300 hover:bg-white/5 hover:text-white"
              )}
            >
              <Icon className="h-4 w-4 shrink-0 opacity-80" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-white/10 px-4 py-4">
        <p className="text-xs text-ink-400">Azure Coast Resort</p>
        <p className="text-sm text-ink-200">
          {user?.name || "User"} · {user?.role || "—"}
        </p>
        <button
          onClick={logout}
          className="mt-3 inline-flex items-center gap-2 text-xs text-ink-300 hover:text-white"
        >
          <LogOut className="h-3.5 w-3.5" />
          Sign out
        </button>
      </div>
    </>
  );

  return (
    <>
      <button
        className="fixed left-4 top-4 z-40 flex h-10 w-10 items-center justify-center rounded-full border border-ink-200 bg-white/90 text-ink-800 md:hidden"
        onClick={() => setOpen((v) => !v)}
        aria-label={open ? "Close menu" : "Open menu"}
      >
        {open ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
      </button>

      {open && (
        <button
          className="fixed inset-0 z-30 bg-ink-950/40 md:hidden"
          aria-label="Close menu overlay"
          onClick={() => setOpen(false)}
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-30 flex w-60 flex-col border-r border-ink-200/80 bg-ink-950 text-ink-100 transition-transform md:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full"
        )}
      >
        {content}
      </aside>
    </>
  );
}
