"use client";

import { useScrollReveal } from "./useScrollReveal";
import { useTilt } from "./useTilt";

/**
 * What the hotel team actually sees. Reuses Marie Dupont (already
 * established in SignatureSequence.tsx and GuestExamples.tsx) rather
 * than inventing a third persona — one consistent guest, reinforced
 * across the page. Never says "AI dashboard" — "Guest context" /
 * "What matters now" only. The caption is phrased as information
 * surfacing, not automated action: EvidenceChain.tsx's own code
 * comment notes no restaurant/PMS notification integration actually
 * exists yet, and this copy shouldn't overclaim past that.
 */
const GUEST_CONTEXT = [
  { label: "Marie Dupont", value: "3rd stay · Anniversary" },
  { label: "Preferences", value: "Vegetarian dining, quiet room" },
  { label: "Last stay", value: "Requested late checkout" },
];

const WHAT_MATTERS_NOW = [
  "Prepare room preference",
  "Follow up on previous request",
  "Remember the occasion",
];

export function StaffExperience() {
  const { ref, revealed } = useScrollReveal<HTMLDivElement>();
  const panelRef = useTilt<HTMLDivElement>(6);

  return (
    <section className="rv-section rv-staff-section">
      <div className="rv-section-inner">
        <div ref={ref} className={`rv-reveal${revealed ? " in" : ""}`}>
          <h2>What your team sees</h2>
          <p className="rv-section-sub">Guest context, not another dashboard to learn.</p>

          <div className="rv-staff-panel rv-tilt-card" ref={panelRef}>
            <div className="rv-staff-col">
              <span className="rv-staff-col-label">Guest context</span>
              <dl>
                {GUEST_CONTEXT.map((item) => (
                  <div className="rv-staff-row" key={item.label}>
                    <dt>{item.label}</dt>
                    <dd>{item.value}</dd>
                  </div>
                ))}
              </dl>
            </div>
            <div className="rv-staff-col rv-staff-col-now">
              <span className="rv-staff-col-label">What matters now</span>
              <ul>
                {WHAT_MATTERS_NOW.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          </div>
          <p className="rv-staff-caption">
            ReVisit surfaces this so your team doesn&rsquo;t have to dig for it.
          </p>
        </div>
      </div>
    </section>
  );
}
