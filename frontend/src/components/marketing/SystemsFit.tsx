"use client";

import { useScrollReveal } from "./useScrollReveal";
import { useTilt } from "./useTilt";

/**
 * Equation-style PMS positioning. Deliberately generic — a real
 * Cloudbeds integration exists in the backend, but naming a specific
 * PMS product here is a go-to-market claim, not a code-verification
 * question, so it stays unnamed unless that's an explicit decision
 * later.
 */
export function SystemsFit() {
  const { ref, revealed } = useScrollReveal<HTMLDivElement>();
  const revisitRef = useTilt<HTMLDivElement>(7);

  return (
    <section className="rv-section rv-systems-fit">
      <div className="rv-section-inner">
        <div ref={ref} className={`rv-reveal${revealed ? " in" : ""}`}>
          <span className="rv-section-eyebrow">Works with what you have</span>
          <div className="rv-systems-equation">
            <div className="rv-systems-block">
              <span className="rv-systems-block-label">Your existing hotel system</span>
              <p>Bookings, rooms, reservations.</p>
            </div>
            <span className="rv-systems-op">+</span>
            <div className="rv-systems-block rv-systems-block-accent rv-tilt-card" ref={revisitRef}>
              <span className="rv-systems-block-label">ReVisit</span>
              <p>Guest memory, context, and relationship.</p>
            </div>
            <span className="rv-systems-op">=</span>
            <div className="rv-systems-block rv-systems-block-result">
              <h2 className="rv-systems-block-label">A more personal stay</h2>
            </div>
          </div>
          <p className="rv-section-sub">
            ReVisit works alongside the systems your hotel already runs — it
            doesn&rsquo;t replace them.
          </p>
        </div>
      </div>
    </section>
  );
}
