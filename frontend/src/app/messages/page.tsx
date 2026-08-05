"use client";

import { useEffect, useState } from "react";
import { TopBar } from "@/components/TopBar";
import { Badge, Empty, Panel } from "@/components/ui";
import { api, type Message } from "@/lib/api";

export default function MessagesPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [selected, setSelected] = useState<Message | null>(null);

  useEffect(() => {
    api.messages().then((m) => {
      setMessages(m);
      setSelected(m[0] || null);
    });
  }, []);

  return (
    <div>
      <TopBar
        title="Messaging"
        subtitle="AI writes. The messaging engine delivers. You approve when confidence is low."
      />

      <div className="grid gap-6 lg:grid-cols-[1fr_420px]">
        <Panel title="Outbound queue" className="[animation-delay:80ms]">
          {messages.length === 0 ? (
            <Empty>No messages</Empty>
          ) : (
            <ul className="divide-y divide-ink-50">
              {messages.map((m) => (
                <li
                  key={m.id}
                  onClick={() => setSelected(m)}
                  className={`cursor-pointer py-3 transition hover:bg-sea-500/5 ${
                    selected?.id === m.id ? "bg-sea-500/8" : ""
                  }`}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-medium text-ink-900">{m.guest_name}</p>
                    <Badge tone={m.status}>{m.status.replace("_", " ")}</Badge>
                    <Badge>{m.channel}</Badge>
                    <Badge>{m.message_type}</Badge>
                  </div>
                  <p className="mt-1 text-xs text-ink-500">
                    {m.subject} · {m.language.toUpperCase()}
                    {m.confidence != null &&
                      ` · ${Math.round(m.confidence * 100)}% confidence`}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        {selected && (
          <div className="animate-fade-up opacity-0 [animation-delay:120ms]">
            <div className="rounded-2xl border border-ink-200/60 bg-white/80 p-5 backdrop-blur">
              <div className="flex items-center justify-between gap-2">
                <h2 className="font-display text-xl text-ink-900">
                  {selected.subject}
                </h2>
                <Badge tone={selected.status}>
                  {selected.status.replace("_", " ")}
                </Badge>
              </div>
              <p className="mt-1 text-xs text-ink-400">
                To {selected.guest_name} via {selected.channel}
              </p>
              <pre className="mt-5 whitespace-pre-wrap rounded-xl bg-ink-50 p-4 font-sans text-sm leading-relaxed text-ink-800">
                {selected.body}
              </pre>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
