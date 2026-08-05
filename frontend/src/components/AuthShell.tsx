"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { api, setToken, type User } from "@/lib/api";
import { Sidebar } from "@/components/Sidebar";

export function AuthShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const isPublic =
    pathname === "/login" ||
    pathname === "/onboard" ||
    (pathname.startsWith("/celebrate/") && pathname !== "/celebrate");

  useEffect(() => {
    if (isPublic) {
      setReady(true);
      return;
    }
    api
      .me()
      .then((u) => {
        setUser(u);
        setReady(true);
      })
      .catch(() => {
        setToken(null);
        router.replace("/login");
      });
  }, [isPublic, router, pathname]);

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-hero-wash text-ink-400">
        Loading…
      </div>
    );
  }

  if (isPublic) {
    return <>{children}</>;
  }

  return (
    <div className="min-h-screen bg-hero-wash bg-grain">
      <Sidebar user={user} />
      <main className="ml-0 min-h-screen px-4 py-6 md:ml-60 md:px-10 md:py-8">
        {children}
      </main>
    </div>
  );
}
