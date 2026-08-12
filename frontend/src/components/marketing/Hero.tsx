"use client";

import { useEffect, useRef } from "react";

/**
 * Act I — Arrival. Full-bleed licensed photo standing in for a future
 * commissioned arrival video (see public/images/marketing/CREDITS.md).
 * The image itself drifts almost imperceptibly on scroll via a direct
 * ref transform — deliberately not React state, since this updates on
 * every scroll frame and a re-render per frame would be wasteful.
 */
export function Hero() {
  const imgRef = useRef<HTMLImageElement>(null);

  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) return;

    const isMobile = window.innerWidth < 640;
    const mult = isMobile ? 0.01 : 0.02;
    const drift = isMobile ? -6 : -14;

    let ticking = false;
    function onScroll() {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        const progress = Math.min(Math.max(window.scrollY / window.innerHeight, 0), 1);
        if (imgRef.current) {
          imgRef.current.style.transform = `scale(${1.02 + progress * mult}) translateY(${progress * drift}px)`;
        }
        ticking = false;
      });
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <section className="rv-hero">
      <div className="rv-ground">
        {/* eslint-disable-next-line @next/next/no-img-element -- scroll-driven transform needs a plain img, not next/image */}
        <img ref={imgRef} src="/images/marketing/arrival.jpg" alt="" />
        <div className="rv-grade-dusk" />
        <div className="rv-vignette" />
        <svg className="rv-grain" width="100%" height="100%">
          <filter id="rv-grain-hero">
            <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves={3} stitchTiles="stitch" />
            <feColorMatrix type="saturate" values="0" />
          </filter>
          <rect width="100%" height="100%" filter="url(#rv-grain-hero)" opacity="0.05" />
        </svg>
      </div>

      <div className="rv-copy">
        <span className="rv-eyebrow">The hotel concierge</span>
        <h1>
          Every guest conversation
          <br />
          can become hotel action.
        </h1>
        <p className="rv-support">
          Guests ask. ReVisit understands. Your team acts. What follows is that
          transformation, once, in full.
        </p>
        <a href="/onboard" className="rv-cta">
          Discuss a pilot →
        </a>
      </div>

      <p className="rv-credit">Entrance, Amantaka — Basile Morin, CC BY-SA 4.0, Wikimedia Commons</p>
      <div className="rv-scroll-cue">
        <span className="rv-line" />
        Scroll
      </div>
    </section>
  );
}
