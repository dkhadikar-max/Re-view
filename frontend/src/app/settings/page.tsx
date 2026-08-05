"use client";

import { FormEvent, useEffect, useState } from "react";
import { TopBar } from "@/components/TopBar";
import { Button, Panel } from "@/components/ui";
import { api, type Property } from "@/lib/api";
import { REVISIT } from "@/lib/brand";

export default function SettingsPage() {
  const [property, setProperty] = useState<Property | null>(null);
  const [error, setError] = useState("");
  const [pwMsg, setPwMsg] = useState("");
  const [pwError, setPwError] = useState("");
  const [busy, setBusy] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  useEffect(() => {
    api
      .properties()
      .then((props) => setProperty(props[0] || null))
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
  }, []);

  async function onChangePassword(e: FormEvent) {
    e.preventDefault();
    setPwMsg("");
    setPwError("");
    if (newPassword !== confirmPassword) {
      setPwError("New passwords do not match");
      return;
    }
    setBusy(true);
    try {
      const res = await api.changePassword(currentPassword, newPassword);
      setPwMsg(res.message);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      setPwError(err instanceof Error ? err.message : "Could not update password");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <TopBar
        title="Settings"
        subtitle="Your property profile and brand voice."
      />

      {error && (
        <p className="mb-4 rounded-lg border border-coral-200 bg-coral-50 px-3 py-2 text-sm text-coral-800">
          {error}
        </p>
      )}

      {property && (
        <div className="mb-6 animate-fade-up rounded-2xl border border-ink-200/60 bg-gradient-to-br from-ink-950 via-ink-900 to-sea-700 p-6 text-white opacity-0">
          <p className="text-xs uppercase tracking-wider text-ink-300">
            Property
          </p>
          <h2 className="mt-2 font-display text-3xl">{property.name}</h2>
          <p className="mt-1 text-ink-300">
            {property.city}, {property.country} · {property.currency || "EUR"} ·{" "}
            {property.rooms} rooms · {property.google_rating}★ Google
          </p>
          <p className="mt-4 max-w-2xl text-sm leading-relaxed text-ink-200">
            Brand voice: {property.brand_voice}
          </p>
        </div>
      )}

      <Panel title="Account" className="[animation-delay:80ms]">
        <p className="text-sm text-ink-600">
          This is your {REVISIT.name} workspace ({REVISIT.tagline}). Staff approve
          messages, manage reviews, and track guest revenue here. Guests interact
          over WhatsApp, email, and payment links — not this dashboard.
        </p>
        <p className="mt-3 text-xs text-ink-400">{REVISIT.productOf}</p>
      </Panel>

      <Panel title="Change password" className="mt-6 [animation-delay:120ms]">
        <form onSubmit={onChangePassword} className="max-w-md space-y-3">
          <label className="block text-xs text-ink-500">
            Current password
            <input
              type="password"
              required
              minLength={8}
              autoComplete="current-password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-sea-500"
            />
          </label>
          <label className="block text-xs text-ink-500">
            New password
            <input
              type="password"
              required
              minLength={8}
              autoComplete="new-password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-sea-500"
            />
          </label>
          <label className="block text-xs text-ink-500">
            Confirm new password
            <input
              type="password"
              required
              minLength={8}
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-sea-500"
            />
          </label>
          {pwError && (
            <p className="text-sm text-coral-600" role="alert">
              {pwError}
            </p>
          )}
          {pwMsg && (
            <p className="text-sm text-sea-700" role="status">
              {pwMsg}
            </p>
          )}
          <Button type="submit" disabled={busy}>
            {busy ? "Saving…" : "Store new password"}
          </Button>
          <p className="text-[11px] text-ink-400">
            Passwords are stored as secure hashes — never in plain text.
          </p>
        </form>
      </Panel>
    </div>
  );
}
