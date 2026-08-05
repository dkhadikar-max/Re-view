"use client";

import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, Sparkles } from "lucide-react";
import { api, setToken } from "@/lib/api";
import { Button } from "@/components/ui";
import { ARGUS, REVISIT } from "@/lib/brand";
import { cn } from "@/lib/utils";

const PREF_OPTIONS = [
  "Late checkout",
  "Sparkling water",
  "No feather pillows",
  "Quiet room",
  "High floor",
  "Airport pickup",
];

const TRAVEL = [
  { value: "luxury", label: "Luxury" },
  { value: "business", label: "Business" },
  { value: "family", label: "Family" },
  { value: "leisure", label: "Leisure" },
] as const;

export default function OnboardPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [country, setCountry] = useState("Germany");
  const [language, setLanguage] = useState("en");
  const [travelType, setTravelType] =
    useState<(typeof TRAVEL)[number]["value"]>("luxury");
  const [purpose, setPurpose] = useState("anniversary");
  const [preferredRoom, setPreferredRoom] = useState("Sea View Suite");
  const [dietary, setDietary] = useState("");
  const [favoriteWine, setFavoriteWine] = useState("Sauvignon Blanc");
  const [channel, setChannel] = useState<"whatsapp" | "email" | "sms">(
    "whatsapp"
  );
  const [company, setCompany] = useState("");
  const [birthday, setBirthday] = useState("");
  const [anniversary, setAnniversary] = useState("");
  const [children, setChildren] = useState(0);
  const [pets, setPets] = useState(false);
  const [prefs, setPrefs] = useState<string[]>([
    "Late checkout",
    "Sparkling water",
    "No feather pillows",
  ]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [step, setStep] = useState<"form" | "done">("form");
  const [doneName, setDoneName] = useState("");

  const firstName = useMemo(
    () => name.trim().split(/\s+/)[0] || "there",
    [name]
  );

  function togglePref(p: string) {
    setPrefs((prev) =>
      prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]
    );
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await api.demoOnboard({
        name: name.trim(),
        email: email.trim() || undefined,
        phone: phone.trim() || undefined,
        country,
        language,
        travel_type: travelType,
        purpose,
        preferred_room: preferredRoom,
        dietary_preferences: dietary.trim() || undefined,
        birthday: birthday || undefined,
        anniversary: anniversary || undefined,
        children,
        pets,
        communication_preference: channel,
        favorite_wine: favoriteWine.trim() || undefined,
        remembers: prefs,
        company_or_hotel: company.trim() || undefined,
        open_dashboard: true,
      });
      setDoneName(res.guest.name);
      if (res.access_token) {
        setToken(res.access_token);
      }
      setStep("done");
      // Brief beat so the wow message lands, then open intelligence
      setTimeout(() => {
        router.replace(res.dashboard_path || `/guests?guest=${res.guest.id}`);
      }, 1400);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create profile");
    } finally {
      setBusy(false);
    }
  }

  if (step === "done") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-hero-wash bg-grain px-4">
        <div className="w-full max-w-md animate-fade-up rounded-2xl border border-ink-200/70 bg-gradient-to-b from-ink-950 to-sea-700 p-8 text-center text-white shadow-sm">
          <Sparkles className="mx-auto h-8 w-8 text-sea-300" />
          <p className="mt-4 text-[10px] uppercase tracking-[0.18em] text-sea-300">
            Living Guest Intelligence
          </p>
          <h1 className="mt-2 font-display text-3xl">
            Welcome, {doneName.split(" ")[0]}
          </h1>
          <p className="mt-3 text-sm text-ink-300">
            Revisit already remembers your preferences. Opening your hotel
            profile…
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-hero-wash bg-grain px-4 py-10">
      <div className="mx-auto grid max-w-5xl gap-8 lg:grid-cols-[1fr_1.15fr]">
        <aside className="animate-fade-up self-start opacity-0 lg:sticky lg:top-10">
          <p className="text-[10px] font-medium uppercase tracking-[0.18em] text-sea-700">
            {ARGUS.productLine} · {REVISIT.name}
          </p>
          <h1 className="mt-3 font-display text-4xl tracking-tight text-ink-950 md:text-5xl">
            See yourself in Guest Intelligence
          </h1>
          <p className="mt-4 max-w-md text-sm leading-relaxed text-ink-600">
            Enter your details once. Revisit builds a living profile — what the
            hotel remembers, what you prefer, and the next best action for your
            stay.
          </p>
          <ul className="mt-8 space-y-3 text-sm text-ink-700">
            {[
              "AI summary written about you",
              "Preferences the hotel never forgets",
              "Predictions & next best action",
            ].map((line) => (
              <li key={line} className="flex items-start gap-2">
                <Check className="mt-0.5 h-4 w-4 shrink-0 text-sea-600" />
                {line}
              </li>
            ))}
          </ul>
          <p className="mt-10 text-xs text-ink-400">
            Demo hotel: Azure Coast Resort. Already have access?{" "}
            <a href="/login" className="text-sea-700 underline-offset-2 hover:underline">
              Sign in
            </a>
          </p>
        </aside>

        <form
          onSubmit={onSubmit}
          className="animate-fade-up rounded-2xl border border-ink-200/70 bg-white/85 p-6 shadow-sm backdrop-blur opacity-0 [animation-delay:80ms] sm:p-8"
        >
          <p className="text-xs uppercase tracking-wider text-ink-400">
            Guest onboarding
          </p>
          <h2 className="mt-1 font-display text-2xl text-ink-900">
            Hi {firstName === "there" ? "there" : firstName} — tell us about you
          </h2>

          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            <label className="sm:col-span-2 text-xs text-ink-500">
              Full name *
              <input
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Marie Dupont"
                className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-sea-500"
              />
            </label>
            <label className="text-xs text-ink-500">
              Email
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-sea-500"
              />
            </label>
            <label className="text-xs text-ink-500">
              Phone
              <input
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+49 …"
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
              Language
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-sea-500"
              >
                <option value="en">English</option>
                <option value="de">German</option>
                <option value="fr">French</option>
                <option value="es">Spanish</option>
                <option value="it">Italian</option>
                <option value="pt">Portuguese</option>
              </select>
            </label>
            <label className="text-xs text-ink-500">
              Your hotel / company
              <input
                value={company}
                onChange={(e) => setCompany(e.target.value)}
                placeholder="Optional — for the demo"
                className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-sea-500"
              />
            </label>
            <label className="text-xs text-ink-500">
              Preferred channel
              <select
                value={channel}
                onChange={(e) =>
                  setChannel(e.target.value as "whatsapp" | "email" | "sms")
                }
                className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-sea-500"
              >
                <option value="whatsapp">WhatsApp</option>
                <option value="email">Email</option>
                <option value="sms">SMS</option>
              </select>
            </label>
          </div>

          <p className="mt-6 text-[10px] uppercase tracking-wider text-ink-400">
            How you travel
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {TRAVEL.map((t) => (
              <button
                key={t.value}
                type="button"
                onClick={() => setTravelType(t.value)}
                className={cn(
                  "rounded-xl border px-3 py-2 text-sm transition",
                  travelType === t.value
                    ? "border-sea-500 bg-sea-500/10 text-sea-700"
                    : "border-ink-200 text-ink-600 hover:border-ink-300"
                )}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <label className="text-xs text-ink-500">
              Purpose
              <input
                value={purpose}
                onChange={(e) => setPurpose(e.target.value)}
                placeholder="anniversary, business…"
                className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-sea-500"
              />
            </label>
            <label className="text-xs text-ink-500">
              Favorite room
              <input
                value={preferredRoom}
                onChange={(e) => setPreferredRoom(e.target.value)}
                className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-sea-500"
              />
            </label>
            <label className="text-xs text-ink-500">
              Dietary
              <input
                value={dietary}
                onChange={(e) => setDietary(e.target.value)}
                placeholder="vegetarian, gluten-free…"
                className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-sea-500"
              />
            </label>
            <label className="text-xs text-ink-500">
              Favorite wine
              <input
                value={favoriteWine}
                onChange={(e) => setFavoriteWine(e.target.value)}
                className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-sea-500"
              />
            </label>
            <label className="text-xs text-ink-500">
              Birthday
              <input
                type="date"
                value={birthday}
                onChange={(e) => setBirthday(e.target.value)}
                className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-sea-500"
              />
            </label>
            <label className="text-xs text-ink-500">
              Anniversary
              <input
                type="date"
                value={anniversary}
                onChange={(e) => setAnniversary(e.target.value)}
                className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-sea-500"
              />
            </label>
            <label className="text-xs text-ink-500">
              Children
              <input
                type="number"
                min={0}
                max={10}
                value={children}
                onChange={(e) => setChildren(Number(e.target.value) || 0)}
                className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-sea-500"
              />
            </label>
            <label className="flex cursor-pointer items-end gap-2 pb-2.5 text-sm text-ink-700">
              <input
                type="checkbox"
                checked={pets}
                onChange={(e) => setPets(e.target.checked)}
                className="rounded border-ink-300 text-sea-600"
              />
              Travelling with pets
            </label>
          </div>

          <p className="mt-6 text-[10px] uppercase tracking-wider text-ink-400">
            What should the hotel remember?
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {PREF_OPTIONS.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => togglePref(p)}
                className={cn(
                  "rounded-xl border px-3 py-1.5 text-xs transition",
                  prefs.includes(p)
                    ? "border-sea-500 bg-sea-500/10 text-sea-700"
                    : "border-ink-200 text-ink-500 hover:border-ink-300"
                )}
              >
                {prefs.includes(p) ? "✓ " : ""}
                {p}
              </button>
            ))}
          </div>

          {error && (
            <p className="mt-4 text-sm text-coral-600" role="alert">
              {error}
            </p>
          )}

          <Button type="submit" className="mt-6 w-full" disabled={busy || !name.trim()}>
            {busy ? "Building your profile…" : "Create my Guest Intelligence"}
          </Button>
          <p className="mt-3 text-center text-[11px] text-ink-400">
            Opens the hotel dashboard with your profile selected.
          </p>
        </form>
      </div>
    </div>
  );
}
