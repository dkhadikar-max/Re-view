"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Button } from "@/components/ui";
import { ARGUS, REVISIT } from "@/lib/brand";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("manager@azurecoast.demo");
  const [password, setPassword] = useState("ChangeMe123!");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await api.login(email, password);
      router.replace("/");
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
        <p className="mt-1 text-sm text-ink-500">
          Sign in to manage guest revenue after booking
        </p>
        <label className="mt-6 block text-xs text-ink-500">
          Email
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-sm outline-none focus:border-sea-500"
          />
        </label>
        <label className="mt-3 block text-xs text-ink-500">
          Password
          <input
            type="password"
            required
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
        <p className="mt-4 text-xs text-ink-400">
          Demo: manager@azurecoast.demo / ChangeMe123!
        </p>
        <p className="mt-3 text-center text-[11px] text-ink-400">
          A product of{" "}
          <a
            href={ARGUS.siteUrl}
            target="_blank"
            rel="noreferrer"
            className="text-sea-700 underline-offset-2 hover:underline"
          >
            {ARGUS.productLine}
          </a>
          {" · "}
          <span className="text-ink-500">{REVISIT.siteUrl.replace(/^https?:\/\//, "")}</span>
        </p>
      </form>
    </div>
  );
}
