"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Button } from "@/components/ui";
import { ARGUS, REVISIT } from "@/lib/brand";

function nextPath(): string {
  if (typeof window === "undefined") return "/";
  const n = new URLSearchParams(window.location.search).get("next");
  return n && n.startsWith("/") ? n : "/";
}

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await api.login(email.trim(), password);
      router.replace(nextPath());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-hero-wash bg-grain px-4">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-md animate-fade-up rounded-2xl border border-ink-200/70 bg-white/80 p-8 shadow-sm backdrop-blur"
      >
        <p className="text-[10px] font-medium uppercase tracking-[0.18em] text-sea-700">
          {ARGUS.productLine}
        </p>
        <p className="mt-2 font-display text-3xl text-ink-950">{REVISIT.name}</p>
        <p className="mt-1 text-sm text-ink-500">{REVISIT.tagline}</p>
        <ol className="mt-4 space-y-1.5 rounded-xl bg-sea-500/5 px-3 py-3 text-xs text-ink-600">
          {REVISIT.vision.map((line) => (
            <li key={line} className="flex gap-2">
              <span className="text-sea-600">→</span>
              {line}
            </li>
          ))}
        </ol>
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
          {loading ? "Signing in…" : "Sign in"}
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
    </div>
  );
}
