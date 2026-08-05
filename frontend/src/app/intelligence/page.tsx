"use client";

import { useEffect, useState } from "react";
import { TopBar } from "@/components/TopBar";
import { Badge, Empty, Panel, Stat } from "@/components/ui";
import { api, type IntelligenceReport } from "@/lib/api";

export default function IntelligencePage() {
  const [report, setReport] = useState<IntelligenceReport | null>(null);

  useEffect(() => {
    api.intelligence().then(setReport).catch(console.error);
  }, []);

  if (!report) {
    return (
      <div className="flex h-64 items-center justify-center text-ink-400">
        Analyzing reviews…
      </div>
    );
  }

  const max = Math.max(...report.themes.map((t) => t.mentions), 1);

  return (
    <div>
      <TopBar
        title="Intelligence"
        subtitle="What guests talk about — extracted from every review, ready for monthly insight."
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <Stat label="Reviews analyzed" value={report.total_reviews} accent="sea" />
        <Stat
          label="Most praised"
          value={report.most_praised || "—"}
          accent="sand"
          delay={40}
        />
        <Stat
          label="Main complaint"
          value={report.main_complaint || "—"}
          accent="coral"
          delay={80}
        />
      </div>

      <Panel title="Theme mentions" className="mt-8 [animation-delay:120ms]">
        {report.themes.length === 0 ? (
          <Empty>No themes extracted yet</Empty>
        ) : (
          <ul className="space-y-4">
            {report.themes.map((t) => (
              <li key={t.theme}>
                <div className="mb-1.5 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="capitalize text-sm font-medium text-ink-900">
                      {t.theme}
                    </span>
                    <Badge tone={t.sentiment}>{t.sentiment}</Badge>
                  </div>
                  <span className="text-xs text-ink-400">
                    {t.mentions} mention{t.mentions === 1 ? "" : "s"}
                  </span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-ink-100">
                  <div
                    className={`h-full rounded-full transition-all ${
                      t.sentiment === "negative"
                        ? "bg-coral-500"
                        : t.sentiment === "positive"
                          ? "bg-sea-500"
                          : "bg-ink-400"
                    }`}
                    style={{ width: `${(t.mentions / max) * 100}%` }}
                  />
                </div>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
