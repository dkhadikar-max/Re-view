"use client";

import { useScrollReveal } from "./useScrollReveal";

/**
 * Redesigned from the old three-box equation (system + ReVisit =
 * better stay) into a restrained conceptual flow diagram — the
 * product truth ("your systems stay, ReVisit adds memory across
 * them") shown as a shape rather than boxed panels with +/= signs,
 * which read as a SaaS architecture diagram. One markup for all
 * viewports; the flex-wrap rows collapse gracefully on narrow
 * screens without needing a separate mobile-only text fallback.
 *
 * Categories stay generic (no named PMS product) — a real Cloudbeds
 * integration exists in the backend, but naming a specific PMS here
 * is a go-to-market claim, not a code-verification question.
 */
export function SystemsFit() {
  const { ref, revealed } = useScrollReveal<HTMLDivElement>();

  return (
    <section className="rv-section rv-memory-layer" id="integrations">
      <div className="rv-section-inner">
        <div ref={ref} className={`rv-reveal${revealed ? " in" : ""}`}>
          <span className="rv-section-eyebrow">Works with what you have</span>
          <h2>Your systems stay. ReVisit adds memory.</h2>

          <div className="rv-memory-diagram">
            <div className="rv-memory-row rv-memory-systems">
              <span>PMS</span>
              <span>Guest messaging</span>
              <span>CRM</span>
              <span>Booking engine</span>
            </div>
            <span className="rv-memory-connector" aria-hidden="true" />
            <div className="rv-memory-core">ReVisit Memory Layer</div>
            <span className="rv-memory-connector" aria-hidden="true" />
            <div className="rv-memory-row rv-memory-outputs">
              <span>Guest profile</span>
              <span>Preferences</span>
              <span>Stay history</span>
              <span>Staff context</span>
              <span>Next arrival</span>
            </div>
          </div>

          <p className="rv-section-sub rv-memory-sub">
            ReVisit doesn&rsquo;t replace your hotel&rsquo;s systems — it adds memory across them.
          </p>
        </div>
      </div>
    </section>
  );
}
