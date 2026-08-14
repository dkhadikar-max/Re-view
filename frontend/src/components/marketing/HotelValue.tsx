"use client";

import { useScrollReveal } from "./useScrollReveal";
import { QuietIcon } from "./HospitalityIcons";

/**
 * Consolidates the old HotelOutcomes + StaffExperience into one
 * editorial section. StaffExperience's two-column "Guest context /
 * What matters now" panel is deliberately not carried forward here —
 * it read as a dashboard dropped into a hospitality site, which is
 * exactly the language this pass removes. The same idea (staff sees
 * context, acts on it) is now three short editorial lines instead of
 * a data panel. Reuses the numbered-row visual language from the old
 * HotelOutcomes.tsx (see git history), swapping numerals for phase
 * words since the content is genuinely a sequence (before/during/
 * after a stay) — the ordering carries real meaning here.
 */
const PHASES = [
  {
    phase: "Before",
    title: "Check-in",
    line: "The team knows what matters before the guest arrives.",
  },
  {
    phase: "During",
    title: "The stay",
    line: "Staff act on context instead of asking the guest to repeat it.",
  },
  {
    phase: "After",
    title: "The stay ends",
    line: "The relationship continues into the next visit.",
  },
];

function PhaseRow({
  phase,
  title,
  line,
  delay,
}: {
  phase: string;
  title: string;
  line: string;
  delay: string;
}) {
  const { ref, revealed } = useScrollReveal<HTMLDivElement>();
  return (
    <div
      ref={ref}
      className={`rv-outcome-row rv-reveal${revealed ? " in" : ""}`}
      style={{ transitionDelay: revealed ? delay : "0s" }}
    >
      <span className="rv-outcome-phase">{phase}</span>
      <div className="rv-outcome-copy">
        <h3>{title}</h3>
        <p>{line}</p>
      </div>
    </div>
  );
}

export function HotelValue() {
  return (
    <section className="rv-section rv-editorial" id="for-hotels">
      <QuietIcon className="rv-editorial-mark" />
      <div className="rv-section-inner">
        <h2 className="rv-editorial-headline">Better stays. Stronger relationships.</h2>
        <p className="rv-section-sub">Turn guest memory into meaningful actions your team can use.</p>
        <div className="rv-outcomes-list">
          {PHASES.map((p, i) => (
            <PhaseRow key={p.phase} {...p} delay={`${i * 0.12}s`} />
          ))}
        </div>
      </div>
    </section>
  );
}
