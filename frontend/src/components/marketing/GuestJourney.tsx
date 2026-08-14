"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { useScrollReveal } from "./useScrollReveal";

/**
 * A compact 3D card-stack carousel — Arrival/Stay/Return as three
 * cards staged with CSS `perspective`/`translateZ`/`rotateY` (no
 * WebGL, no new dependency), one visibly in front, the other two
 * receded and blurred behind it. Click a nav dot or a label to jump;
 * otherwise it auto-advances every 5s and resets that timer on
 * interaction.
 *
 * Originated as a design exploration in Kimi (a separate AI tool) for
 * this exact ReVisit narrative — reusing the site's own locked copy
 * ("She doesn't start over.", "The next stay starts with context, not
 * from zero.") — and ported here as a proper React component rather
 * than the original vanilla-JS/onclick markup: state lives in
 * `current`, and each panel set is `key`-ed by `current` so React
 * remounts them on every switch, which is what re-triggers the
 * `rv-jc-fade-in` entrance animations (replacing the original's
 * manual reflow-and-reset trick).
 *
 * The z transform deliberately does NOT match the original Kimi math
 * (`z = offset * -140`, which pushed the *previous* panel toward the
 * camera): because `.rv-jc-scene` uses real `transform-style:
 * preserve-3d`, the browser depth-sorts by actual 3D position rather
 * than CSS z-index, so that dimmed/blurred "previous" panel rendered
 * in front of the sharp active one. Using `Math.abs(offset)` instead
 * ensures any inactive panel always recedes, regardless of which side
 * it's on.
 *
 * Replaces the previous ChapterStage-based Arrival/Stay/Return
 * treatment for this section. ChapterStage itself, and
 * ArrivalScene.tsx/StayScene.tsx/ReturnScene.tsx, stay in the repo
 * unrendered rather than deleted — same policy as SignatureSequence.
 */
type Panel = { number: string; title: string; body: ReactNode };

const PANELS: Panel[] = [
  {
    number: "01 / Arrival",
    title: "ReVisit remembers.",
    body: (
      <>
        <div className="rv-jc-guest-card rv-jc-fade-in">
          <div className="rv-jc-guest-name">Marie Dupont</div>
          <div className="rv-jc-guest-meta">3rd stay · Anniversary</div>
          <div className="rv-jc-room-badge">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
              <polyline points="9 22 9 12 15 12 15 22" />
            </svg>
            Room 407
          </div>
        </div>
        <div className="rv-jc-chip-row">
          <span className="rv-jc-chip vegetarian rv-jc-fade-in rv-jc-delay-1">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
              <path d="M20 12V8H6a2 2 0 0 1-2-2c0-1.1.9-2 2-2h12v4" />
              <path d="M4 6v12a2 2 0 0 0 2 2h14v-4" />
              <path d="M18 12a2 2 0 0 0-2 2c0 1.1.9 2 2 2h4v-4h-4z" />
            </svg>
            Vegetarian
          </span>
          <span className="rv-jc-chip quiet rv-jc-fade-in rv-jc-delay-2">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
              <path d="M3 18v-6a9 9 0 0 1 18 0v6" />
              <path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3zM3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z" />
            </svg>
            Quiet room
          </span>
          <span className="rv-jc-chip anniversary rv-jc-fade-in rv-jc-delay-3">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
              <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
            </svg>
            Anniversary
          </span>
        </div>
        <div className="rv-jc-quote rv-jc-fade-in rv-jc-delay-3">Know what matters before they arrive.</div>
      </>
    ),
  },
  {
    number: "02 / Stay",
    title: "The hotel acts.",
    body: (
      <>
        <CheckItem delay="">Quiet-side room assigned</CheckItem>
        <CheckItem delay="rv-jc-delay-1">Restaurant team informed — vegetarian dining</CheckItem>
        <CheckItem delay="rv-jc-delay-2">Service team briefed on anniversary</CheckItem>
        <CheckItem delay="rv-jc-delay-3">Late checkout remembered from last stay</CheckItem>
        <div className="rv-jc-flow-arrow">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 5v14M5 12l7 7 7-7" />
          </svg>
        </div>
        <div className="rv-jc-quote">Dinner is already right. She didn&rsquo;t have to ask.</div>
      </>
    ),
  },
  {
    number: "03 / Return",
    title: "She doesn't start over.",
    body: (
      <>
        <div className="rv-jc-guest-card rv-jc-fade-in">
          <div className="rv-jc-guest-name">Welcome back, Marie.</div>
          <div className="rv-jc-guest-meta">Every preference, carried forward.</div>
        </div>
        <div style={{ marginTop: 18 }}>
          <CheckItem delay="rv-jc-delay-1">Quiet room ready</CheckItem>
          <CheckItem delay="rv-jc-delay-2">Vegetarian dining noted</CheckItem>
          <CheckItem delay="rv-jc-delay-3">Anniversary on file</CheckItem>
        </div>
        <div className="rv-jc-quote rv-jc-fade-in rv-jc-delay-3">
          The next stay starts with context, not from zero.
        </div>
      </>
    ),
  },
];

function CheckItem({ children, delay }: { children: ReactNode; delay: string }) {
  return (
    <div className={`rv-jc-check-item rv-jc-fade-in ${delay}`}>
      <svg className="rv-jc-check-icon" viewBox="0 0 24 24" fill="currentColor">
        <path d="M19.3 5.9l1.3 1.3L9.7 18.1l-5-5 1.3-1.3 3.7 3.7z" />
      </svg>
      <span>{children}</span>
    </div>
  );
}

const LABELS = ["Arrival", "Stay", "Return"];

export function GuestJourney() {
  const { ref, revealed } = useScrollReveal<HTMLDivElement>();
  const [current, setCurrent] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) return;
    intervalRef.current = setInterval(() => setCurrent((c) => (c + 1) % 3), 5000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  function goTo(idx: number) {
    setCurrent(idx);
    if (intervalRef.current) clearInterval(intervalRef.current);
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!reduced) {
      intervalRef.current = setInterval(() => setCurrent((c) => (c + 1) % 3), 5000);
    }
  }

  return (
    <section className="rv-section rv-journey" id="how-it-works">
      {/* The section's own atmosphere shifts with the story, not just
          the card. One consistent color (the platform's own brass
          warmth) whose position drifts across the three states, so
          it reads as one continuous atmosphere following the story
          rather than three different scenes swapping in. */}
      <div className="rv-journey-mood">
        {["arrival", "stay", "return"].map((mood, i) => (
          <div key={mood} className={`rv-journey-mood-layer rv-journey-mood-${mood}${i === current ? " active" : ""}`} />
        ))}
      </div>
      <div className="rv-section-inner">
        <div ref={ref} className={`rv-reveal${revealed ? " in" : ""}`}>
          <span className="rv-section-eyebrow">The guest journey</span>
          <h2>One story, from arrival to return.</h2>
        </div>

        <div className="rv-jc" onClick={() => goTo((current + 1) % 3)}>
          <div className="rv-jc-scene">
            {PANELS.map((panel, i) => {
              const offset = i - current;
              // z always recedes (negative) for any non-active panel,
              // regardless of which side it's on -- the original math
              // (z = offset * -140) pushed the *previous* panel
              // toward the camera instead, and because the scene uses
              // real `transform-style: preserve-3d`, the browser
              // depth-sorts by actual 3D position rather than
              // z-index, so that dimmed/blurred panel rendered in
              // front of the sharp active one. x/rotation keep using
              // the signed offset so left/right ordering still reads.
              const transform = `translateZ(${Math.abs(offset) * -140}px) translateX(${offset * 70}px) rotateY(${offset * -28}deg)`;
              const isActive = i === current;
              return (
                <div
                  key={`${i}-${current}`}
                  className={`rv-jc-panel${isActive ? " active" : " inactive"}`}
                  style={{ transform }}
                  onClick={(e) => {
                    e.stopPropagation();
                    goTo(i);
                  }}
                >
                  <div className="rv-jc-panel-number">{panel.number}</div>
                  <div className="rv-jc-panel-title">{panel.title}</div>
                  <div className="rv-jc-panel-body">{panel.body}</div>
                </div>
              );
            })}
          </div>

          <div className="rv-jc-nav">
            {LABELS.map((_, i) => (
              <button
                key={i}
                type="button"
                className={`rv-jc-nav-btn${i === current ? " active" : ""}`}
                aria-label={`Show ${LABELS[i]}`}
                onClick={(e) => {
                  e.stopPropagation();
                  goTo(i);
                }}
              />
            ))}
          </div>

          <div className="rv-jc-labels">
            {LABELS.map((label, i) => (
              <div
                key={label}
                className={`rv-jc-label${i === current ? " active" : ""}`}
                onClick={(e) => {
                  e.stopPropagation();
                  goTo(i);
                }}
              >
                {label}
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
