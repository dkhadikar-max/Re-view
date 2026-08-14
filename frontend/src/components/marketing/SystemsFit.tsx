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

          {/* Desktop: the equation composition. Hidden on mobile via
              CSS -- a row of boxed panels + operators reads as a
              SaaS diagram on a phone, not the editorial/premium
              language the rest of the mobile page uses. */}
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
          <p className="rv-section-sub rv-systems-sub-desktop">
            ReVisit works alongside the systems your hotel already runs — it
            doesn&rsquo;t replace them.
          </p>

          {/* Mobile: the same fact as two short lines instead of an
              equation diagram. Same claim, no boxes. */}
          <p className="rv-systems-proof-mobile">
            Your existing hotel system stays exactly where it is.
            <br />
            ReVisit adds the memory layer.
          </p>
        </div>
      </div>
    </section>
  );
}
