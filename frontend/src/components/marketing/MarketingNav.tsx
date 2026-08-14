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
        {/* "Start free trial", not "Start a pilot" (implies a managed
            engagement /onboard doesn't support) and not bare "Start
            free" (the product itself isn't free — only the trial
            period is, and today nothing charges since billing isn't
            built yet; "trial" keeps that accurate either way). */}
        <a href="/onboard" className="rv-nav-cta">
          Start free trial →
        </a>
      </div>
    </nav>
  );
}
