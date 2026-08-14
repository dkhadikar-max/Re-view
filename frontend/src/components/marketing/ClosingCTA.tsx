"use client";

import { useScrollReveal } from "./useScrollReveal";

/**
 * A quiet premium close — per explicit direction, a single statement
 * and one CTA, no feature list or secondary information underneath.
 * `/onboard` is confirmed instant self-serve trial signup, not a
 * sales/contact flow, so "Start free" (not "Start a pilot") stays
 * accurate to what actually happens next.
 */
export function ClosingCTA() {
  const { ref, revealed } = useScrollReveal<HTMLDivElement>();

  return (
    <section className="rv-section rv-closing">
      <div className="rv-section-inner">
        <div ref={ref} className={`rv-reveal${revealed ? " in" : ""}`}>
          <p className="rv-closing-line">
            Your next guest
            <br />
            should not have to
            <br />
            start over.
          </p>
          <a href="/onboard" className="rv-cta">
            Start free →
          </a>
        </div>
      </div>
    </section>
  );
}
