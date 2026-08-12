"use client";

import { FormEvent, useEffect, useState } from "react";
import { TopBar } from "@/components/TopBar";
import { Button, Panel } from "@/components/ui";
import {
  api,
  type Property,
  type PropertyKnowledgeBase,
  type PropertyKnowledgeBaseUpdate,
  type PropertyUpdate,
} from "@/lib/api";
import { REVISIT } from "@/lib/brand";

const emptyKbForm: PropertyKnowledgeBaseUpdate = {};

function kbFormFromKnowledgeBase(kb: PropertyKnowledgeBase): PropertyKnowledgeBaseUpdate {
  const { preview: _preview, ...fields } = kb;
  return fields;
}

// Grouped the same way PropertyKnowledgeBase's own fields are grouped
// in entities.py — one editor field per Knowledge Base fact, no new
// content architecture.
const KB_FIELD_GROUPS: {
  title: string;
  fields: { key: keyof PropertyKnowledgeBaseUpdate; label: string; multiline?: boolean }[];
}[] = [
  {
    title: "Practical info",
    fields: [
      { key: "wifi_password", label: "WiFi password" },
      { key: "breakfast_hours", label: "Breakfast hours" },
      { key: "pool_hours", label: "Pool hours" },
      { key: "gym_hours", label: "Gym hours" },
      { key: "spa_hours", label: "Spa hours" },
      { key: "checkin_time", label: "Check-in time" },
      { key: "checkout_time", label: "Check-out time" },
      { key: "room_service_hours", label: "Room service hours" },
      { key: "parking_info", label: "Parking", multiline: true },
      { key: "late_checkout_policy", label: "Late checkout policy", multiline: true },
      { key: "airport_transfer_info", label: "Airport transfer", multiline: true },
    ],
  },
  {
    title: "Policies",
    fields: [
      { key: "pet_policy", label: "Pet policy", multiline: true },
      { key: "house_rules", label: "House rules", multiline: true },
      { key: "policies", label: "Other policies", multiline: true },
    ],
  },
  {
    title: "Local recommendations",
    fields: [
      { key: "restaurants", label: "Restaurants", multiline: true },
      { key: "cafes", label: "Cafes", multiline: true },
      { key: "nearby_attractions", label: "Nearby attractions", multiline: true },
    ],
  },
  {
    title: "Services & emergency",
    fields: [
      { key: "services", label: "Services", multiline: true },
      { key: "emergency_contacts", label: "Emergency contacts", multiline: true },
    ],
  },
];

const emptyForm: PropertyUpdate = {
  name: "",
  city: "",
  country: "",
  currency: "",
  timezone: "",
  rooms: 1,
  brand_voice: "",
  address: "",
  google_review_url: "",
  whatsapp_phone_number_id: "",
};

function formFromProperty(property: Property): PropertyUpdate {
  return {
    name: property.name,
    city: property.city,
    country: property.country,
    currency: property.currency,
    timezone: property.timezone,
    rooms: property.rooms,
    brand_voice: property.brand_voice,
    address: property.address || "",
    google_review_url: property.google_review_url || "",
    // No input for this in Settings — it's provisioned by ReVisit under
    // its own WABA (CONCIERGE.md §3), not hotel self-serve in v1. Still
    // round-tripped through the form so an unrelated property save
    // (e.g. editing brand voice) doesn't silently wipe it back to null.
    whatsapp_phone_number_id: property.whatsapp_phone_number_id || "",
  };
}

export default function SettingsPage() {
  const [property, setProperty] = useState<Property | null>(null);
  const [error, setError] = useState("");
  const [pwMsg, setPwMsg] = useState("");
  const [pwError, setPwError] = useState("");
  const [busy, setBusy] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<PropertyUpdate>(emptyForm);
  const [propBusy, setPropBusy] = useState(false);
  const [propMsg, setPropMsg] = useState("");
  const [propError, setPropError] = useState("");

  const [kb, setKb] = useState<PropertyKnowledgeBase | null>(null);
  const [kbForm, setKbForm] = useState<PropertyKnowledgeBaseUpdate>(emptyKbForm);
  const [kbBusy, setKbBusy] = useState(false);
  const [kbMsg, setKbMsg] = useState("");
  const [kbError, setKbError] = useState("");

  useEffect(() => {
    api
      .properties()
      .then((props) => {
        const first = props[0] || null;
        setProperty(first);
        if (!first) return;
        return api.propertyKnowledgeBase(first.id).then((data) => {
          setKb(data);
          setKbForm(kbFormFromKnowledgeBase(data));
        });
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
  }, []);

  async function onSaveKnowledgeBase(e: FormEvent) {
    e.preventDefault();
    if (!property) return;
    setKbError("");
    setKbMsg("");
    setKbBusy(true);
    try {
      const updated = await api.updatePropertyKnowledgeBase(property.id, kbForm);
      setKb(updated);
      setKbForm(kbFormFromKnowledgeBase(updated));
      setKbMsg("Knowledge Base updated — the concierge will use this immediately.");
    } catch (err) {
      setKbError(err instanceof Error ? err.message : "Could not update Knowledge Base");
    } finally {
      setKbBusy(false);
    }
  }

  function startEditing() {
    if (!property) return;
    setForm(formFromProperty(property));
    setPropMsg("");
    setPropError("");
    setEditing(true);
  }

  function cancelEditing() {
    setEditing(false);
    setPropError("");
  }

  async function onSaveProperty(e: FormEvent) {
    e.preventDefault();
    if (!property) return;
    setPropError("");
    setPropMsg("");
    setPropBusy(true);
    try {
      const updated = await api.updateProperty(property.id, {
        ...form,
        name: form.name.trim(),
        city: form.city.trim(),
        country: form.country.trim(),
        currency: form.currency.trim().toUpperCase(),
        timezone: form.timezone.trim(),
        brand_voice: form.brand_voice.trim(),
        address: form.address?.trim() || null,
        google_review_url: form.google_review_url?.trim() || null,
      });
      setProperty(updated);
      setEditing(false);
      setPropMsg("Property updated");
    } catch (err) {
      setPropError(
        err instanceof Error ? err.message : "Could not update property"
      );
    } finally {
      setPropBusy(false);
    }
  }

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
        action={
          property && !editing ? (
            <Button variant="secondary" onClick={startEditing}>
              Edit property
            </Button>
          ) : undefined
        }
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
          {property.address && (
            <p className="mt-1 text-sm text-ink-300">{property.address}</p>
          )}
          <p className="mt-4 max-w-2xl text-sm leading-relaxed text-ink-200">
            Brand voice: {property.brand_voice}
          </p>
          {property.google_review_url && (
            <a
              href={property.google_review_url}
              target="_blank"
              rel="noreferrer"
              className="mt-2 inline-block text-xs text-sea-300 underline-offset-2 hover:underline"
            >
              Google review link →
            </a>
          )}
        </div>
      )}

      {editing && property && (
        <Panel title="Edit property" className="mb-6 [animation-delay:40ms]">
          <form onSubmit={onSaveProperty} className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="text-xs text-ink-500">
                Property name *
                <input
                  required
                  maxLength={255}
                  value={form.name}
                  onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                  className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-sea-500"
                />
              </label>
              <label className="text-xs text-ink-500">
                Room count *
                <input
                  type="number"
                  required
                  min={1}
                  max={20000}
                  value={form.rooms}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, rooms: Number(e.target.value) || 1 }))
                  }
                  className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-sea-500"
                />
              </label>
              <label className="text-xs text-ink-500">
                City *
                <input
                  required
                  maxLength={128}
                  value={form.city}
                  onChange={(e) => setForm((f) => ({ ...f, city: e.target.value }))}
                  className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-sea-500"
                />
              </label>
              <label className="text-xs text-ink-500">
                Country *
                <input
                  required
                  maxLength={128}
                  value={form.country}
                  onChange={(e) => setForm((f) => ({ ...f, country: e.target.value }))}
                  className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-sea-500"
                />
              </label>
              <label className="text-xs text-ink-500">
                Currency *
                <input
                  required
                  minLength={3}
                  maxLength={8}
                  placeholder="EUR"
                  value={form.currency}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, currency: e.target.value.toUpperCase() }))
                  }
                  className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm uppercase outline-none focus:border-sea-500"
                />
              </label>
              <label className="text-xs text-ink-500">
                Time zone *
                <input
                  required
                  placeholder="Europe/Berlin"
                  value={form.timezone}
                  onChange={(e) => setForm((f) => ({ ...f, timezone: e.target.value }))}
                  className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-sea-500"
                />
              </label>
              <label className="sm:col-span-2 text-xs text-ink-500">
                Address
                <input
                  maxLength={500}
                  placeholder="Optional"
                  value={form.address || ""}
                  onChange={(e) => setForm((f) => ({ ...f, address: e.target.value }))}
                  className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-sea-500"
                />
              </label>
              <label className="sm:col-span-2 text-xs text-ink-500">
                Google Review URL
                <input
                  type="url"
                  maxLength={512}
                  placeholder="https://g.page/r/..."
                  value={form.google_review_url || ""}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, google_review_url: e.target.value }))
                  }
                  className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-sea-500"
                />
              </label>
            </div>
            <label className="block text-xs text-ink-500">
              Brand voice *
              <textarea
                required
                rows={2}
                value={form.brand_voice}
                onChange={(e) => setForm((f) => ({ ...f, brand_voice: e.target.value }))}
                className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-sea-500"
              />
              <span className="mt-1 block text-[11px] text-ink-400">
                Used to set the tone of guest messages and review replies.
              </span>
            </label>
            {propError && (
              <p className="text-sm text-coral-600" role="alert">
                {propError}
              </p>
            )}
            <div className="flex items-center gap-2">
              <Button type="submit" disabled={propBusy}>
                {propBusy ? "Saving…" : "Save changes"}
              </Button>
              <Button
                type="button"
                variant="ghost"
                disabled={propBusy}
                onClick={cancelEditing}
              >
                Cancel
              </Button>
            </div>
          </form>
        </Panel>
      )}
      {!editing && propMsg && (
        <p className="mb-6 text-sm text-sea-700" role="status">
          {propMsg}
        </p>
      )}

      {property && (
        <Panel title="Knowledge Base" className="mb-6 [animation-delay:60ms]">
          <p className="mb-4 text-sm text-ink-600">
            The facts your AI Concierge answers guest questions from. Change a
            fact here and the concierge reflects it on the very next message
            — you own the truth, the AI only reads it.
          </p>
          <form onSubmit={onSaveKnowledgeBase} className="space-y-6">
            {KB_FIELD_GROUPS.map((group) => (
              <div key={group.title}>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-400">
                  {group.title}
                </h3>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  {group.fields.map(({ key, label, multiline }) => {
                    const preview = kb?.preview?.[key as string];
                    const value = (kbForm[key] as string | null | undefined) ?? "";
                    return (
                      <label
                        key={key}
                        className={`text-xs text-ink-500 ${multiline ? "sm:col-span-2" : ""}`}
                      >
                        {label}
                        {multiline ? (
                          <textarea
                            rows={2}
                            value={value}
                            onChange={(e) =>
                              setKbForm((f) => ({ ...f, [key]: e.target.value }))
                            }
                            className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-sea-500"
                          />
                        ) : (
                          <input
                            value={value}
                            onChange={(e) =>
                              setKbForm((f) => ({ ...f, [key]: e.target.value }))
                            }
                            className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-sea-500"
                          />
                        )}
                        {/* wifi_password is deliberately never in kb.preview
                            (a credential, not a fact echoed back anywhere but
                            a guest's own answer) — this line just never
                            renders for that field. */}
                        {preview && (
                          <span className="mt-1 block text-[11px] italic text-ink-400">
                            Guest hears: “{preview}”
                          </span>
                        )}
                      </label>
                    );
                  })}
                </div>
              </div>
            ))}
            {kbError && (
              <p className="text-sm text-coral-600" role="alert">
                {kbError}
              </p>
            )}
            {kbMsg && (
              <p className="text-sm text-sea-700" role="status">
                {kbMsg}
              </p>
            )}
            <Button type="submit" disabled={kbBusy}>
              {kbBusy ? "Saving…" : "Save Knowledge Base"}
            </Button>
          </form>
        </Panel>
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
