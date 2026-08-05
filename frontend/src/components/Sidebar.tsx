"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
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
} from "lucide-react";
import { cn } from "@/lib/utils";

const nav = [
  { href: "/", label: "Operations", icon: LayoutDashboard },
  { href: "/guests", label: "Guest Memory", icon: Users },
  { href: "/reservations", label: "Reservations", icon: CalendarDays },
  { href: "/messages", label: "Messages", icon: MessageSquare },
  { href: "/reviews", label: "Reviews", icon: Star },
  { href: "/approvals", label: "Approvals", icon: CheckSquare },
  { href: "/revenue", label: "Revenue", icon: TrendingUp },
  { href: "/intelligence", label: "Intelligence", icon: Sparkles },
  { href: "/tasks", label: "Tasks", icon: ListTodo },
  { href: "/activity", label: "Event Stream", icon: Activity },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed inset-y-0 left-0 z-30 flex w-60 flex-col border-r border-ink-200/80 bg-ink-950 text-ink-100">
      <div className="relative overflow-hidden border-b border-white/10 px-5 py-6">
        <div className="absolute -right-6 -top-6 h-24 w-24 rounded-full bg-sea-500/20 blur-2xl" />
        <div className="absolute -bottom-8 left-4 h-16 w-16 rounded-full bg-sand-400/20 blur-xl" />
        <p className="font-display text-2xl tracking-tight text-white animate-fade-in">
          GRA
        </p>
        <p className="mt-1 text-xs leading-relaxed text-ink-300">
          Guest Revenue Agent
        </p>
      </div>

      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-4">
        {nav.map((item, i) => {
          const active =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              style={{ animationDelay: `${i * 30}ms` }}
              className={cn(
                "animate-fade-up flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors opacity-0",
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
        <p className="text-sm text-ink-200">Sofia Marino · Manager</p>
      </div>
    </aside>
  );
}
