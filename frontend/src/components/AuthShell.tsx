"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { api, setToken, type Property, type User } from "@/lib/api";
import { Sidebar } from "@/components/Sidebar";
import { WorkspaceProvider } from "@/components/WorkspaceProvider";
import { currencyForCountry } from "@/lib/currency";

export function AuthShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [property, setProperty] = useState<Property | null>(null);
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
    let cancelled = false;
    api
      .me()
      .then(async (u) => {
        if (cancelled) return;
        setUser(u);
        try {
          const props = await api.properties();
          const first = props[0] || null;
          if (first && !first.currency) {
            first.currency = currencyForCountry(first.country);
          }
          if (!cancelled) setProperty(first);
        } catch {
          if (!cancelled) setProperty(null);
        }
        setReady(true);
      })
      .catch(() => {
        if (cancelled) return;
        setToken(null);
        router.replace("/login");
      });
    return () => {
      cancelled = true;
    };
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
    <WorkspaceProvider property={property}>
      <div className="min-h-screen bg-hero-wash bg-grain">
        <Sidebar user={user} propertyName={property?.name || null} />
        <main className="ml-0 min-h-screen px-4 py-6 md:ml-60 md:px-10 md:py-8">
          {children}
        </main>
      </div>
    </WorkspaceProvider>
  );
}
