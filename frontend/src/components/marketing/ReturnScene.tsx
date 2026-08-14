"use client";

import { ChapterStage } from "./ChapterStage";
import { KeyCardIcon } from "./HospitalityIcons";

/**
 * Chapter 3 — Return. The emotional payoff: a second arrival, the
 * same key/guest identity from the hero traveling forward. Deliberately
 * echoes Arrival's doorway (this one *should* rhyme with chapter 1 —
 * it's the same guest returning) but simpler, since the context is
 * already established rather than being introduced.
 */
export function ReturnScene() {
  return (
    <section className="rv-section rv-chapter">
      <div className="rv-section-inner">
        <span className="rv-section-eyebrow">Return</span>
        <h2 className="rv-chapter-headline">She doesn&rsquo;t start over.</h2>

        <ChapterStage
          background={
            <div className="rv-door rv-door-return">
              <span className="rv-door-glow" />
            </div>
          }
          foreground={
            <div className="rv-return-key">
              <KeyCardIcon className="rv-chapter-icon" />
            </div>
          }
          texts={[
            { text: "Marie Dupont", delay: "0.3s", variant: "name" },
            { text: "Welcome back.", delay: "0.75s", variant: "welcome" },
            { text: "Quiet room ready.", delay: "1.2s", variant: "status" },
          ]}
        />

        <p className="rv-chapter-line">Every preference, carried forward.</p>
      </div>
    </section>
  );
}
