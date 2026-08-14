"use client";

import { ChapterStage } from "./ChapterStage";
import { KeyCardIcon, LuggageIcon } from "./HospitalityIcons";

/**
 * Chapter 1 — Arrival. A doorway scene: Marie's previous context
 * (the same guest as the hero, not a new persona) quietly arrives
 * with her. Calm and anticipatory, not busy — one door, one key, one
 * small luggage mark, three staged words.
 */
export function ArrivalScene() {
  return (
    <section className="rv-section rv-chapter" id="how-it-works">
      <div className="rv-section-inner">
        <span className="rv-section-eyebrow">Arrival</span>
        <h2 className="rv-chapter-headline">ReVisit remembers.</h2>

        <ChapterStage
          background={
            <div className="rv-door">
              <span className="rv-door-glow" />
              <span className="rv-door-number">407</span>
            </div>
          }
          foreground={
            <>
              <LuggageIcon className="rv-chapter-icon rv-arrival-luggage" />
              <div className="rv-arrival-key">
                <KeyCardIcon className="rv-chapter-icon" />
              </div>
            </>
          }
          texts={[
            { text: "Marie Dupont", delay: "0.3s", variant: "name" },
            { text: "Room 407", delay: "0.7s", variant: "room" },
            { text: "Welcome back.", delay: "1.15s", variant: "welcome" },
          ]}
        />

        <p className="rv-chapter-line">Know what matters before they arrive.</p>
      </div>
    </section>
  );
}
