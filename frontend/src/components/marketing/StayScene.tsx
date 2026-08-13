"use client";

import { ChapterStage } from "./ChapterStage";
import { PlateIcon, QuietIcon, CalendarIcon } from "./HospitalityIcons";

/**
 * Chapter 2 — Stay. A different composition from Arrival on purpose
 * (a service surface, not a doorway): one preference — vegetarian —
 * animates into a physical action (the amenity on the plate). Quiet
 * room and anniversary stay present as small, already-settled marks,
 * not a second and third card — this chapter is about one action,
 * not a feature list.
 */
export function StayScene() {
  return (
    <section className="rv-section rv-chapter">
      <div className="rv-section-inner">
        <span className="rv-section-eyebrow">Stay</span>
        <h2 className="rv-chapter-headline">The hotel acts.</h2>

        <ChapterStage
          background={<div className="rv-tray" />}
          foreground={
            <>
              <PlateIcon className="rv-chapter-icon rv-stay-plate" />
              <span className="rv-stay-tag">Vegetarian</span>
              <span className="rv-stay-mark rv-stay-mark-1">
                <QuietIcon className="rv-chapter-icon-xs" /> Quiet room
              </span>
              <span className="rv-stay-mark rv-stay-mark-2">
                <CalendarIcon className="rv-chapter-icon-xs" /> Anniversary
              </span>
            </>
          }
          texts={[{ text: "Ready for Marie", delay: "1.1s", variant: "status" }]}
        />

        <p className="rv-chapter-line">Turn guest context into better service.</p>
      </div>
    </section>
  );
}
