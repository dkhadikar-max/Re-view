"use client";

import { useScrollReveal } from "./useScrollReveal";

/**
 * A quiet premium close — per explicit direction, a single statement
 * and one CTA, no feature list underneath. "A stay that remembers you
 * feels different." still lives once, mid-page, in
 * SignatureSequence.tsx's Act V — this doesn't need to repeat it, it
 * has its own, more direct closing line. `/onboard` is confirmed
 * instant self-serve trial signup, not a sales/contact flow, so one
 * CTA, accurate to what actually happens, is correct here.
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
            See ReVisit with your property →
          </a>
        </div>
      </div>
    </section>
  );
}
