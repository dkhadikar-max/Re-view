"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { REVISIT } from "@/lib/brand";

/** Transparent over the hero, solidifying once the visitor scrolls past it. */
export function MarketingNav() {
  const [solid, setSolid] = useState(false);

  useEffect(() => {
    function onScroll() {
      setSolid(window.scrollY > window.innerHeight * 0.7);
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <nav className={`rv-nav${solid ? " solid" : ""}`}>
      <div className="rv-word" style={{ fontFamily: "var(--font-display)" }}>
        {REVISIT.name}
      </div>
      {/* Anchors to sections on this same page — no new routes, per
          explicit direction not to expand information architecture
          for this pass. Hidden on mobile (see marketing.css) to keep
          the small nav bar minimal there. */}
      <div className="rv-nav-links">
        <a href="#how-it-works">How it works</a>
        <a href="#for-hotels">For Hotels</a>
        <a href="#integrations">Integrations</a>
      </div>
      <div className="rv-nav-actions">
        <Link href="/login" className="sign-in">
          Sign in
        </Link>
        {/* "Start free", not "Start a pilot" — /onboard is instant
            self-serve trial signup, not a managed pilot engagement. */}
        <a href="/onboard" className="rv-nav-cta">
          Start free →
        </a>
      </div>
    </nav>
  );
}
