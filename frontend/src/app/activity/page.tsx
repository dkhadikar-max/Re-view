"use client";

import { useEffect, useState } from "react";
import { TopBar } from "@/components/TopBar";
import { Badge, Empty, Panel } from "@/components/ui";
import { api, type AIDecision, type EventItem } from "@/lib/api";

export default function ActivityPage() {
  const [events, setEvents] = useState<EventItem[]>([]);
  const [decisions, setDecisions] = useState<AIDecision[]>([]);

  useEffect(() => {
    Promise.all([api.events(), api.decisions()]).then(([e, d]) => {
      setEvents(e);
      setDecisions(d);
    });
  }, []);

  return (
    <div>
      <TopBar
        title="Event Stream"
        subtitle="Everything is event-driven — loosely coupled, nothing talks directly."
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Events" className="[animation-delay:80ms]">
          {events.length === 0 ? (
            <Empty>No events yet</Empty>
          ) : (
            <ul className="relative space-y-0 before:absolute before:bottom-2 before:left-[7px] before:top-2 before:w-px before:bg-ink-200">
              {events.slice(0, 40).map((e) => (
                <li key={e.id} className="relative flex gap-4 py-3 pl-6">
                  <span className="absolute left-0 top-4 h-3.5 w-3.5 rounded-full border-2 border-sea-500 bg-white" />
                  <div>
                    <p className="text-sm font-medium text-ink-900">
                      {e.event_type}
                    </p>
                    <p className="text-xs text-ink-400">
                      {e.source} ·{" "}
                      {new Date(e.created_at).toLocaleString()}
                      {e.processed && " · processed"}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="AI decisions" className="[animation-delay:120ms]">
          {decisions.length === 0 ? (
            <Empty>No decisions yet</Empty>
          ) : (
            <ul className="space-y-3">
              {decisions.map((d) => (
                <li
                  key={d.id}
                  className="rounded-xl border border-ink-100 bg-ink-50/50 p-3"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-ink-900">{d.action}</span>
                    {d.channel && <Badge>{d.channel}</Badge>}
                    {d.language && <Badge>{d.language}</Badge>}
                    <span className="text-xs text-ink-400">
                      {Math.round(d.confidence * 100)}%
                    </span>
                    {d.executed && <Badge tone="approved">executed</Badge>}
                  </div>
                  {d.offer && (
                    <p className="mt-1 text-xs text-sea-700">Offer: {d.offer}</p>
                  )}
                  {d.timing && (
                    <p className="text-xs text-ink-400">Timing: {d.timing}</p>
                  )}
                  {d.reasoning && (
                    <p className="mt-2 text-xs leading-relaxed text-ink-500">
                      {d.reasoning}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}
