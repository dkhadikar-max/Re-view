"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Fires once when the attached element enters the viewport, then
 * disconnects — a single boolean state update, not a per-frame one,
 * so this doesn't carry the same "avoid React state" constraint as
 * the scroll-linked parallax in Hero.tsx/SignatureSequence.tsx (those
 * update every scroll frame; this updates once, ever, per element).
 *
 * Under prefers-reduced-motion, skips the observer entirely and
 * reports revealed immediately. marketing.css's own reduced-motion
 * block also forces `.rv-reveal` visible via `!important` — this is
 * belt-and-suspenders, not the only safeguard.
 */
export function useScrollReveal<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [revealed, setRevealed] = useState(false);

  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      setRevealed(true);
      return;
    }

    const el = ref.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setRevealed(true);
          observer.disconnect();
        }
      },
      { threshold: 0.15, rootMargin: "0px 0px -10% 0px" }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return { ref, revealed };
}
