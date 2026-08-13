"use client";

import { useScrollReveal } from "./useScrollReveal";
import { QuietIcon } from "./HospitalityIcons";

/**
 * The pace change after Return, per explicit direction: not another
 * cinematic scene, not icon cards either — a large editorial
 * typographic composition. Oversized numbers as visual anchors, one
 * sentence per outcome, no icons/cards/grid. No stats, no logos, no
 * testimonials (none are verified).
 */
const OUTCOMES = [
  {
    n: "01",
    title: "Better guest experiences",
    line: "Guests feel recognized instead of repeatedly explaining themselves.",
  },
  {
    n: "02",
    title: "Less repetitive work",
    line: "Your team spends less time answering the same questions.",
  },
  {
    n: "03",
    title: "More reason to return",
    line: "The next stay starts with context, not from zero.",
  },
];

function OutcomeRow({ n, title, line, delay }: { n: string; title: string; line: string; delay: string }) {
  const { ref, revealed } = useScrollReveal<HTMLDivElement>();
  return (
    <div
      ref={ref}
      className={`rv-outcome-row rv-reveal${revealed ? " in" : ""}`}
      style={{ transitionDelay: revealed ? delay : "0s" }}
    >
      <span className="rv-outcome-num">{n}</span>
      <div className="rv-outcome-copy">
        <h3>{title}</h3>
        <p>{line}</p>
      </div>
    </div>
  );
}

export function HotelOutcomes() {
  return (
    <section className="rv-section rv-editorial">
      <QuietIcon className="rv-editorial-mark" />
      <div className="rv-section-inner">
        <h2 className="rv-editorial-headline">What changes for the hotel?</h2>
        <div className="rv-outcomes-list">
          {OUTCOMES.map((o, i) => (
            <OutcomeRow key={o.n} {...o} delay={`${i * 0.12}s`} />
          ))}
        </div>
      </div>
    </section>
  );
}
