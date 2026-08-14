"use client";

import type { ReactNode } from "react";
import { useScrollReveal } from "./useScrollReveal";

export type ChapterText = {
  text: string;
  delay: string;
  variant?: "name" | "room" | "welcome" | "status";
};

/**
 * Shared staging for the three narrative chapters (Arrival/Stay/
 * Return) — one component so all three genuinely share the same
 * perspective, reveal mechanism, and text rhythm rather than being
 * three independently-built components that happen to look similar.
 * Each call site supplies its own background/foreground content, so
 * the compositions stay visually distinct (a different camera scene
 * each time) while the system underneath — timing, easing, palette,
 * the one-shot scroll reveal — is identical.
 */
export function ChapterStage({
  background,
  foreground,
  texts,
}: {
  background: ReactNode;
  foreground: ReactNode;
  texts: ChapterText[];
}) {
  const { ref, revealed } = useScrollReveal<HTMLDivElement>();

  return (
    <div ref={ref} className={`rv-chapter-stage${revealed ? " in" : ""}`}>
      <div className="rv-chapter-bg">{background}</div>
      <div className="rv-chapter-fg">{foreground}</div>
      <div className="rv-chapter-text">
        {texts.map((t) => (
          <span
            key={t.text}
            className={`rv-chapter-text-line rv-chapter-text-${t.variant ?? "line"}`}
            style={{ transitionDelay: t.delay }}
          >
            {t.text}
          </span>
        ))}
      </div>
    </div>
  );
}
