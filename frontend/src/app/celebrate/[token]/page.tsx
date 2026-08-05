"use client";

import { FormEvent, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, type GuestCelebrateStatus } from "@/lib/api";
import { ARGUS, REVISIT } from "@/lib/brand";
import { Button } from "@/components/ui";

export default function GuestCelebratePage() {
  const params = useParams<{ token: string }>();
  const token = params.token;
  const [status, setStatus] = useState<GuestCelebrateStatus | null>(null);
  const [error, setError] = useState("");
  const [done, setDone] = useState<{ message: string; coupons: string[] } | null>(
    null
  );
  const [birthday, setBirthday] = useState("");
  const [anniversary, setAnniversary] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!token) return;
    api
      .celebratePublicStatus(token)
      .then(setStatus)
      .catch((e) => setError(e instanceof Error ? e.message : "Invalid link"));
  }, [token]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setBusy(true);
    setError("");
    try {
      const res = await api.celebrateSubmitDates(token, {
        birthday,
        anniversary: anniversary || undefined,
        confirm,
      });
      setDone({ message: res.message, coupons: res.coupons_created || [] });
      const refreshed = await api.celebratePublicStatus(token);
      setStatus(refreshed);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save dates");
    } finally {
      setBusy(false);
    }
  }

  if (error && !status) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-hero-wash px-4">
        <p className="text-coral-600">{error}</p>
      </div>
    );
  }

  if (!status) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-hero-wash text-ink-400">
        Loading your reward…
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-hero-wash bg-grain px-4 py-12">
      <div className="mx-auto max-w-lg animate-fade-up rounded-2xl border border-ink-200/70 bg-white/85 p-8 shadow-sm backdrop-blur">
        <p className="text-xs uppercase tracking-wider text-sea-700">
          {status.property_name || "Celebrate Rewards"}
        </p>
        <h1 className="mt-2 font-display text-3xl text-ink-950">Thank you!</h1>
        <p className="mt-2 text-sm text-ink-500">{status.tagline}</p>

        <div className="mt-6 rounded-xl bg-gradient-to-br from-sea-500/10 to-sand-100/80 p-4">
          <p className="font-display text-xl text-ink-900">★★★★★</p>
          <p className="mt-2 text-sm text-ink-700">
            Hi {status.guest_name.split(" ")[0]}, you&apos;ve unlocked our Celebrate
            Rewards for leaving a review.
          </p>
          <ul className="mt-3 space-y-1 text-sm text-ink-700">
            {status.offers.birthday.enabled && (
              <li>
                Birthday: {status.offers.birthday.discount_pct}% off (
                {status.offers.birthday.window})
              </li>
            )}
            {status.offers.anniversary.enabled && (
              <li>
                Anniversary: {status.offers.anniversary.discount_pct}% off (
                {status.offers.anniversary.window})
              </li>
            )}
          </ul>
        </div>

        {done || !status.can_submit_dates ? (
          <div className="mt-6 space-y-2 text-sm">
            <p className="font-medium text-sea-700">
              {done?.message || "Profile updated. Dates are locked."}
            </p>
            {status.birthday_locked && (
              <p>
                Birthday locked: <strong>{status.birthday}</strong>
              </p>
            )}
            {status.anniversary_locked && status.anniversary && (
              <p>
                Anniversary locked: <strong>{status.anniversary}</strong>
              </p>
            )}
            {done?.coupons?.length ? (
              <p className="text-ink-500">
                Coupons created: {done.coupons.join(", ")}
              </p>
            ) : null}
            <p className="text-xs text-ink-400">
              These dates cannot be changed later. Only a Super Admin can unlock
              them with a logged reason.
            </p>
          </div>
        ) : (
          <form onSubmit={onSubmit} className="mt-6 space-y-4">
            <p className="text-sm text-ink-600">
              Complete your profile to receive birthday and anniversary discounts.
            </p>
            <label className="block text-xs text-ink-500">
              Birthday (YYYY-MM-DD)
              <input
                required
                type="date"
                value={birthday}
                onChange={(e) => setBirthday(e.target.value)}
                className="mt-1 w-full rounded-lg border border-ink-200 px-3 py-2 text-sm outline-none focus:border-sea-500"
              />
            </label>
            <label className="block text-xs text-ink-500">
              Anniversary (optional)
              <input
                type="date"
                value={anniversary}
                onChange={(e) => setAnniversary(e.target.value)}
                className="mt-1 w-full rounded-lg border border-ink-200 px-3 py-2 text-sm outline-none focus:border-sea-500"
              />
            </label>
            <label className="flex items-start gap-2 text-xs text-ink-600">
              <input
                type="checkbox"
                checked={confirm}
                onChange={(e) => setConfirm(e.target.checked)}
                className="mt-0.5"
                required
              />
              <span>
                I confirm these dates are correct. These dates cannot be changed
                later.
              </span>
            </label>
            {error && <p className="text-sm text-coral-600">{error}</p>}
            <Button type="submit" disabled={busy || !confirm} className="w-full">
              {busy ? "Saving…" : "Lock dates & create coupons"}
            </Button>
          </form>
        )}

        <p className="mt-8 text-center text-[11px] text-ink-400">
          Powered by {REVISIT.name} · {ARGUS.productLine}
        </p>
      </div>
    </div>
  );
}
