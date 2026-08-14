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
 *
 * Below 640px the "Vegetarian" pill and the quiet-room/anniversary
 * text labels are CSS-hidden (see marketing.css) in favor of a plain
 * story-beat line ("Dinner is already right. / Vegetarian, as
 * remembered.") -- the pill and the bordered tray read as a UI
 * component displaying guest attributes on a phone, which is exactly
 * the SaaS-dashboard language the rest of the mobile page is free of.
 * The plate icon itself (the physical object) stays as the visual
 * carrier; quiet room/anniversary reduce to small unlabeled icons --
 * environmental detail, not a data row. Desktop keeps the full pill +
 * label treatment, unchanged.
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
                <QuietIcon className="rv-chapter-icon-xs" />
                <span className="rv-stay-mark-text"> Quiet room</span>
              </span>
              <span className="rv-stay-mark rv-stay-mark-2">
                <CalendarIcon className="rv-chapter-icon-xs" />
                <span className="rv-stay-mark-text"> Anniversary</span>
              </span>
            </>
          }
          texts={[{ text: "Ready for Marie", delay: "1.1s", variant: "status" }]}
        />

        <p className="rv-stay-beat-mobile">
          Dinner is already right.
          <br />
          Vegetarian, as remembered.
        </p>

        <p className="rv-chapter-line">Turn guest context into better service.</p>
      </div>
    </section>
  );
}
