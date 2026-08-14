"use client";

import { useEffect, useRef } from "react";
import { HeroScene } from "./HeroScene";

/**
 * Act I — Arrival. Full-bleed photo standing in for a future
 * commissioned arrival video (see public/images/marketing/CREDITS.md).
 * AI-generated (not a real named property — deliberately generic
 * European grand-hotel facade, checked against not resembling any
 * single recognizable real building/brand). The image itself drifts
 * almost imperceptibly on scroll via a direct ref transform —
 * deliberately not React state, since this updates on every scroll
 * frame and a re-render per frame would be wasteful.
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
        <img ref={imgRef} src="/images/marketing/facade-dusk.png" alt="" />
        <div className="rv-grade-dusk" />
        <div className="rv-vignette" />
        {/* Was a full-viewport SVG feTurbulence filter -- recomputed
            on every repaint, a real GPU/rendering cost for a static
            grain effect. Same visual treatment now comes from a
            precomputed, tiled noise PNG (marketing.css's .rv-grain) --
            see PERF_PATCH_PUBLIC_SITE.md. */}
        <div className="rv-grain" />
      </div>

      <div className="rv-copy">
        <span className="rv-eyebrow">ReVisit for hotels</span>
        <h1>
          Your hotel
          <br />
          remembers your guests.
        </h1>
        <p className="rv-support-short rv-support-desktop">
          Every preference. Every occasion. Every detail your team
          shouldn&rsquo;t have to ask twice.
        </p>
        {/* Mobile only (CSS-toggled, see marketing.css): the key-card
            scene is hidden below 980px, so mobile needs a specific,
            concrete cue in its place rather than a generic sentence —
            the photo should set the mood, not compete with the
            proposition. */}
        <p className="rv-support-short rv-support-mobile">
          Marie is returning. Her room, her preferences, even the
          occasion — already remembered.
        </p>
        <div className="rv-cta-row">
          <a href="/onboard" className="rv-cta">
            Start free trial →
          </a>
          <a href="#how-it-works" className="rv-cta-secondary">
            See how it works
          </a>
        </div>
      </div>

      <div className="rv-hero-scene-wrap">
        <HeroScene />
      </div>

      <div className="rv-scroll-cue">
        <span className="rv-line" />
        Scroll
      </div>
    </section>
  );
}
