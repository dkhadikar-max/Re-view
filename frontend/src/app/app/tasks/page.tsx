"use client";

import { useEffect, useState } from "react";
import { TopBar } from "@/components/TopBar";
import { Badge, Button, Empty, Panel } from "@/components/ui";
import { api, type Task } from "@/lib/api";

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  async function load() {
    setTasks(await api.tasks());
  }

  useEffect(() => {
    load().catch(console.error);
  }, []);

  async function complete(id: string) {
    setBusy(id);
    try {
      await api.completeTask(id);
      await load();
    } finally {
      setBusy(null);
    }
  }

  return (
    <div>
      <TopBar
        title="Tasks"
        subtitle="Priority-based routing for negative reviews, escalations, and ops follow-ups."
      />

      <Panel title="Task board" className="[animation-delay:80ms]">
        {tasks.length === 0 ? (
          <Empty>No tasks</Empty>
        ) : (
          <ul className="space-y-3">
            {tasks.map((t) => (
              <li
                key={t.id}
                className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-ink-100 bg-ink-50/40 p-4"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-medium text-ink-900">{t.title}</h3>
                    <Badge tone={t.priority}>{t.priority}</Badge>
                    <Badge tone={t.status}>{t.status.replace("_", " ")}</Badge>
                  </div>
                  {t.description && (
                    <p className="mt-2 whitespace-pre-line text-xs text-ink-500 line-clamp-4">
                      {t.description}
                    </p>
                  )}
                  <p className="mt-2 text-xs text-ink-400">
                    {t.assignee || "Unassigned"}
                  </p>
                </div>
                {t.status === "open" && (
                  <Button
                    variant="secondary"
                    disabled={busy === t.id}
                    onClick={() => complete(t.id)}
                  >
                    Complete
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
