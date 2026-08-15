"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { api, setToken, type Property, type User } from "@/lib/api";
import { Sidebar } from "@/components/Sidebar";
import { SampleDataBanner } from "@/components/SampleDataBanner";
import { WorkspaceProvider } from "@/components/WorkspaceProvider";
import { currencyForCountry } from "@/lib/currency";

export function AuthShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [property, setProperty] = useState<Property | null>(null);
  const [ready, setReady] = useState(false);
  // Only /app and its subpaths are the authenticated hotel application.
  // Everything else (public marketing site, /login, /onboard, guest-facing
  // /celebrate/:token pages, and any future public route) renders directly,
  // with no api.me() call and no Sidebar/WorkspaceProvider wrap. This is
  // an allowlist of what's PROTECTED, not what's public, so adding a new
  // public page never requires touching this file.
  const isAppRoute = pathname === "/app" || pathname.startsWith("/app/");

  useEffect(() => {
    if (!isAppRoute) {
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
        const next = pathname ? `?next=${encodeURIComponent(pathname)}` : "";
        router.replace(`/login${next}`);
      });
    return () => {
      cancelled = true;
    };
  }, [isAppRoute, router, pathname]);

  if (!isAppRoute) {
    return <>{children}</>;
  }

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-hero-wash text-ink-400">
        Loading…
      </div>
    );
  }

  return (
    <WorkspaceProvider property={property}>
      <div className="min-h-screen bg-hero-wash bg-grain">
        <Sidebar user={user} propertyName={property?.name || null} />
        <main className="ml-0 min-h-screen px-4 pb-6 pt-20 md:ml-60 md:px-10 md:pb-8 md:pt-8">
          {property && !property.has_real_data && <SampleDataBanner />}
          {children}
        </main>
      </div>
    </WorkspaceProvider>
  );
}
