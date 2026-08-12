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
        <small>Argus OS</small>
      </div>
      <Link href="/login" className="sign-in">
        Sign in
      </Link>
    </nav>
  );
}
