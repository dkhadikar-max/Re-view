"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Check, Building2 } from "lucide-react";
import { api, setToken } from "@/lib/api";
import { Button } from "@/components/ui";
import { ARGUS, REVISIT } from "@/lib/brand";

export default function HotelSignupPage() {
  const router = useRouter();
  const [hotelName, setHotelName] = useState("");
  const [yourName, setYourName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [city, setCity] = useState("");
  const [country, setCountry] = useState("Germany");
  const [rooms, setRooms] = useState(48);
  const [sampleData, setSampleData] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await api.hotelSignup({
        hotel_name: hotelName.trim(),
        your_name: yourName.trim(),
        email: email.trim(),
        password,
        city: city.trim() || "Berlin",
        country: country.trim() || "Germany",
        rooms,
        include_sample_data: sampleData,
      });
      setToken(res.access_token);
      setDone(true);
      setTimeout(() => {
        router.replace(res.dashboard_path || "/");
      }, 1200);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create account");
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-hero-wash bg-grain px-4">
        <div className="w-full max-w-md animate-fade-up rounded-2xl border border-ink-200/70 bg-gradient-to-b from-ink-950 to-sea-700 p-8 text-center text-white">
          <Building2 className="mx-auto h-8 w-8 text-sea-300" />
          <p className="mt-4 text-[10px] uppercase tracking-[0.18em] text-sea-300">
            {REVISIT.name} trial
          </p>
          <h1 className="mt-2 font-display text-3xl">Your hotel is ready</h1>
          <p className="mt-3 text-sm text-ink-300">
            Opening Operations — explore Guest Intelligence, approvals, and revenue.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-hero-wash bg-grain px-4 py-10">
      <div className="mx-auto grid max-w-5xl gap-8 lg:grid-cols-[1fr_1.05fr]">
        <aside className="animate-fade-up self-start opacity-0 lg:sticky lg:top-10">
          <p className="text-[10px] font-medium uppercase tracking-[0.18em] text-sea-700">
            {ARGUS.productLine} · {REVISIT.name}
          </p>
          <h1 className="mt-3 font-display text-4xl tracking-tight text-ink-950 md:text-5xl">
            See Revisit for your hotel
          </h1>
          <p className="mt-4 max-w-md text-sm leading-relaxed text-ink-600">
            Create a free trial workspace. Walk Guest Intelligence, AI approvals,
            and revenue — as if your property were already live.
          </p>
          <ul className="mt-8 space-y-3 text-sm text-ink-700">
            {[
              "Your own hotel account — not a shared sandbox",
              "Sample guests so Intelligence looks real on day one",
              "Sign back in anytime with your email",
            ].map((line) => (
              <li key={line} className="flex items-start gap-2">
                <Check className="mt-0.5 h-4 w-4 shrink-0 text-sea-600" />
                {line}
              </li>
            ))}
          </ul>
          <p className="mt-10 text-xs text-ink-400">
            Already have an account?{" "}
            <Link href="/login" className="text-sea-700 underline-offset-2 hover:underline">
              Sign in
            </Link>
          </p>
        </aside>

        <form
          onSubmit={onSubmit}
          className="animate-fade-up rounded-2xl border border-ink-200/70 bg-white/85 p-6 shadow-sm backdrop-blur opacity-0 [animation-delay:80ms] sm:p-8"
        >
          <p className="text-xs uppercase tracking-wider text-ink-400">
            Hotel trial signup
          </p>
          <h2 className="mt-1 font-display text-2xl text-ink-900">
            Create your workspace
          </h2>

          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            <label className="sm:col-span-2 text-xs text-ink-500">
              Hotel / property name *
              <input
                required
                value={hotelName}
                onChange={(e) => setHotelName(e.target.value)}
                placeholder="Azure Coast Resort"
                className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-sea-500"
              />
            </label>
            <label className="sm:col-span-2 text-xs text-ink-500">
              Your name *
              <input
                required
                value={yourName}
                onChange={(e) => setYourName(e.target.value)}
                placeholder="Sofia Marino"
                className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-sea-500"
              />
            </label>
            <label className="text-xs text-ink-500">
              Work email *
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@yourhotel.com"
                className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-sea-500"
              />
            </label>
            <label className="text-xs text-ink-500">
              Password *
              <input
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-sea-500"
              />
            </label>
            <label className="text-xs text-ink-500">
              City
              <input
                value={city}
                onChange={(e) => setCity(e.target.value)}
                placeholder="Berlin"
                className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-sea-500"
              />
            </label>
            <label className="text-xs text-ink-500">
              Country
              <input
                value={country}
                onChange={(e) => setCountry(e.target.value)}
                className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-sea-500"
              />
            </label>
            <label className="text-xs text-ink-500">
              Rooms
              <input
                type="number"
                min={5}
                max={2000}
                value={rooms}
                onChange={(e) => setRooms(Number(e.target.value) || 48)}
                className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-sea-500"
              />
            </label>
            <label className="flex cursor-pointer items-end gap-2 pb-2.5 text-sm text-ink-700">
              <input
                type="checkbox"
                checked={sampleData}
                onChange={(e) => setSampleData(e.target.checked)}
                className="rounded border-ink-300 text-sea-600"
              />
              Include sample guests
            </label>
          </div>

          {error && (
            <p className="mt-4 text-sm text-coral-600" role="alert">
              {error}
            </p>
          )}

          <Button
            type="submit"
            className="mt-6 w-full"
            disabled={busy || !hotelName.trim() || !yourName.trim() || !email.trim()}
          >
            {busy ? "Creating workspace…" : "Start free trial"}
          </Button>
          <p className="mt-3 text-center text-[11px] text-ink-400">
            No credit card. You&apos;ll land in your hotel dashboard immediately.
          </p>
        </form>
      </div>
    </div>
  );
}
