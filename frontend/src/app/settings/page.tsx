"use client";

import { useEffect, useState } from "react";
import { TopBar } from "@/components/TopBar";
import { Panel } from "@/components/ui";
import { api, type Property } from "@/lib/api";

export default function SettingsPage() {
  const [property, setProperty] = useState<Property | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .properties()
      .then((props) => setProperty(props[0] || null))
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
  }, []);

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
            {property.city}, {property.country} · {property.rooms} rooms ·{" "}
            {property.google_rating}★ Google
          </p>
          <p className="mt-4 max-w-2xl text-sm leading-relaxed text-ink-200">
            Brand voice: {property.brand_voice}
          </p>
        </div>
      )}

      <Panel title="Account" className="[animation-delay:80ms]">
        <p className="text-sm text-ink-600">
          Hotel staff use this workspace to approve messages, manage reviews,
          and track guest revenue. Guests interact over WhatsApp, email, and
          payment links — not this dashboard.
        </p>
      </Panel>
    </div>
  );
}
