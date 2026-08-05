"use client";

import { FormEvent, Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { Button } from "@/components/ui";
import { ARGUS, REVISIT } from "@/lib/brand";

function safeNext(raw: string | null): string {
  return raw && raw.startsWith("/") && !raw.startsWith("//") ? raw : "/";
}

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const target = safeNext(searchParams.get("next"));
  const forAdmin = target === "/admin" || target.startsWith("/admin?");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const session = await api.login(email.trim(), password);
      if (forAdmin && !session.user?.is_platform_admin) {
        setError(
          "This account is not the platform owner. Sign in with the OWNER_EMAIL account for /admin."
        );
        setLoading(false);
        return;
      }
      router.replace(target);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form
      onSubmit={onSubmit}
      className="w-full max-w-md animate-fade-up rounded-2xl border border-ink-200/70 bg-white/80 p-8 shadow-sm backdrop-blur"
    >
      <p className="text-[10px] font-medium uppercase tracking-[0.18em] text-sea-700">
        {ARGUS.productLine}
      </p>
      <p className="mt-2 font-display text-3xl text-ink-950">{REVISIT.name}</p>
      <p className="mt-1 text-sm text-ink-500">
        {forAdmin ? "Platform owner sign-in" : REVISIT.tagline}
      </p>
      {forAdmin && (
        <p className="mt-3 rounded-xl border border-sea-200 bg-sea-500/10 px-3 py-2 text-xs text-sea-900">
          You opened <span className="font-medium">/admin</span>. After sign-in
          you will return to the platform admin panel.
        </p>
      )}
      {!forAdmin && (
        <ol className="mt-4 space-y-1.5 rounded-xl bg-sea-500/5 px-3 py-3 text-xs text-ink-600">
          {REVISIT.vision.map((line) => (
            <li key={line} className="flex gap-2">
              <span className="text-sea-600">→</span>
              {line}
            </li>
          ))}
        </ol>
      )}
      <label className="mt-6 block text-xs text-ink-500">
        Email
        <input
          type="email"
          required
          autoComplete="username"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@yourhotel.com"
          className="mt-1 w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-sm outline-none focus:border-sea-500"
        />
      </label>
      <label className="mt-3 block text-xs text-ink-500">
        Password
        <input
          type="password"
          required
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="mt-1 w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-sm outline-none focus:border-sea-500"
        />
      </label>
      {error && (
        <p className="mt-3 text-sm text-coral-600" role="alert">
          {error}
        </p>
      )}
      <Button type="submit" className="mt-5 w-full" disabled={loading}>
        {loading ? "Signing in…" : forAdmin ? "Sign in to Admin" : "Sign in"}
      </Button>
      <p className="mt-4 text-center text-sm text-ink-600">
        Hotel evaluating {REVISIT.name}?{" "}
        <Link
          href="/onboard"
          className="font-medium text-sea-700 underline-offset-2 hover:underline"
        >
          Create a free trial →
        </Link>
      </p>
      <p className="mt-3 text-center text-[11px] text-ink-400">
        {REVISIT.productOf} ·{" "}
        <a
          href={ARGUS.siteUrl}
          target="_blank"
          rel="noreferrer"
          className="text-sea-700 underline-offset-2 hover:underline"
        >
          {ARGUS.siteUrl.replace(/^https?:\/\//, "")}
        </a>
      </p>
    </form>
  );
}

export default function LoginPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-hero-wash bg-grain px-4">
      <Suspense
        fallback={
          <div className="w-full max-w-md rounded-2xl border border-ink-200/70 bg-white/80 p-8 text-sm text-ink-400">
            Loading…
          </div>
        }
      >
        <LoginForm />
      </Suspense>
    </div>
  );
}
