"use client";

import { useEffect, useState } from "react";
import { TopBar } from "@/components/TopBar";
import { Badge, Button, Empty, Panel } from "@/components/ui";
import { api, type Review } from "@/lib/api";

export default function ReviewsPage() {
  const [reviews, setReviews] = useState<Review[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [invite, setInvite] = useState("");

  async function load() {
    setReviews(await api.reviews());
  }

  useEffect(() => {
    load().catch(console.error);
  }, []);

  async function publish(id: string) {
    setBusy(id);
    try {
      await api.publishReviewResponse(id);
      await load();
    } finally {
      setBusy(null);
    }
  }

  async function unlockCelebrate(guestId: string, reviewId: string) {
    setBusy(reviewId);
    try {
      const res = await api.unlockCelebrateFromReview(guestId, reviewId);
      setInvite(`${window.location.origin}${res.invite_path}`);
      await load();
    } catch (e) {
      setInvite(e instanceof Error ? e.message : "Unlock failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div>
      <TopBar
        title="Review Engine"
        subtitle="Encourage authentic feedback. Draft replies. Never fabricate reviews. Verified reviewers unlock Rewards."
      />
      {invite && (
        <p className="mb-4 break-all rounded-xl bg-sea-500/10 px-3 py-2 text-xs text-sea-700">
          {invite}
        </p>
      )}

      <div className="space-y-4">
        {reviews.length === 0 ? (
          <Panel title="Reviews">
            <Empty>No reviews yet</Empty>
          </Panel>
        ) : (
          reviews.map((r, i) => {
            const themes: string[] = Array.isArray(r.themes)
              ? r.themes
              : typeof r.themes === "string"
                ? (() => {
                    try {
                      return JSON.parse(r.themes);
                    } catch {
                      return [];
                    }
                  })()
                : [];
            return (
              <article
                key={r.id}
                style={{ animationDelay: `${80 + i * 40}ms` }}
                className="animate-fade-up opacity-0 rounded-2xl border border-ink-200/60 bg-white/70 p-5 backdrop-blur"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="font-display text-xl text-ink-900">
                        {r.guest_name}
                      </h2>
                      <span className="font-display text-lg text-sand-400">
                        {"★".repeat(r.rating)}
                        <span className="text-ink-200">
                          {"★".repeat(5 - r.rating)}
                        </span>
                      </span>
                      <Badge tone={r.sentiment}>{r.sentiment}</Badge>
                      <Badge>{r.platform}</Badge>
                    </div>
                    {r.title && (
                      <p className="mt-1 text-sm font-medium text-ink-700">
                        {r.title}
                      </p>
                    )}
                  </div>
                  {r.responded ? (
                    <Badge tone="approved">Responded</Badge>
                  ) : (
                    <Badge tone="pending">Needs response</Badge>
                  )}
                </div>

                <p className="mt-3 text-sm leading-relaxed text-ink-700">
                  {r.body}
                </p>

                {themes.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {themes.map((t) => (
                      <Badge key={t}>{t}</Badge>
                    ))}
                  </div>
                )}

                {r.ai_draft_response && (
                  <div className="mt-4 rounded-xl border border-dashed border-sea-400/40 bg-sea-500/5 p-4">
                    <p className="text-xs font-medium uppercase tracking-wider text-sea-700">
                      Suggested reply
                    </p>
                    <pre className="mt-2 whitespace-pre-wrap font-sans text-sm text-ink-800">
                      {r.ai_draft_response}
                    </pre>
                    {!r.responded && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        <Button
                          disabled={busy === r.id}
                          onClick={() => publish(r.id)}
                        >
                          Publish response
                        </Button>
                        {r.guest_id && (
                          <Button
                            variant="secondary"
                            disabled={busy === r.id}
                            onClick={() => unlockCelebrate(r.guest_id!, r.id)}
                          >
                            Unlock Rewards
                          </Button>
                        )}
                      </div>
                    )}
                    {r.responded && r.guest_id && (
                      <div className="mt-3">
                        <Button
                          variant="secondary"
                          disabled={busy === r.id}
                          onClick={() => unlockCelebrate(r.guest_id!, r.id)}
                        >
                          Unlock / invite Rewards
                        </Button>
                      </div>
                    )}
                  </div>
                )}

                {r.published_response && r.responded && (
                  <div className="mt-4 rounded-xl bg-ink-50 p-4">
                    <p className="text-xs font-medium uppercase tracking-wider text-ink-400">
                      Published
                    </p>
                    <pre className="mt-2 whitespace-pre-wrap font-sans text-sm text-ink-700">
                      {r.published_response}
                    </pre>
                  </div>
                )}
              </article>
            );
          })
        )}
      </div>
    </div>
  );
}
