"use client";

import { useEffect, useRef, useState } from "react";
import { QuietIcon, PlateIcon, CalendarIcon } from "./HospitalityIcons";

/**
 * The signature ReVisit scene: a staged, physical hotel key card —
 * not an icon chain. Foreground (the card) tilts more under mouse
 * parallax than the background glow/room-number layer behind it,
 * which is how the brief's "foreground moves more than background"
 * depth cue is achieved with plain CSS perspective/translateZ, no
 * WebGL. Guest name and room number are printed on the card itself
 * (hotel signage, not a UI label); the preference tags, status line,
 * and welcome text stage in on mount via CSS animation-delay, not
 * scroll — the hero is already in view on load, so there's nothing to
 * scroll-trigger.
 */
export function HeroScene() {
  const sceneRef = useRef<HTMLDivElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const bgRef = useRef<HTMLDivElement>(null);
  const [started, setStarted] = useState(false);

  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    // Two rAFs so the initial (pre-animation) state has actually
    // painted once before the "in" class flips transitions on --
    // otherwise the browser can coalesce both states into one frame.
    if (reduced) {
      setStarted(true);
    } else {
      requestAnimationFrame(() => requestAnimationFrame(() => setStarted(true)));
    }

    const canTilt = window.matchMedia("(pointer: fine)").matches && window.innerWidth >= 900 && !reduced;
    if (!canTilt) return;

    const scene = sceneRef.current;
    if (!scene) return;

    let ticking = false;
    let pendingX = 0.5;
    let pendingY = 0.5;

    function onMove(e: PointerEvent) {
      const rect = scene!.getBoundingClientRect();
      pendingX = (e.clientX - rect.left) / rect.width;
      pendingY = (e.clientY - rect.top) / rect.height;
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        const rotateY = (pendingX - 0.5) * 8; // card: +/-4deg
        const rotateX = (0.5 - pendingY) * 6; // card: +/-3deg
        if (cardRef.current) {
          cardRef.current.style.transform = `perspective(1000px) rotateX(${-8 + rotateX}deg) rotateY(${-10 + rotateY}deg)`;
        }
        if (bgRef.current) {
          bgRef.current.style.transform = `translate3d(${(pendingX - 0.5) * -10}px, ${(pendingY - 0.5) * -8}px, -80px)`;
        }
        ticking = false;
      });
    }
    scene.addEventListener("pointermove", onMove);
    return () => scene.removeEventListener("pointermove", onMove);
  }, []);

  return (
    <div className={`rv-keycard-scene${started ? " in" : ""}`} ref={sceneRef}>
      <div className="rv-keycard-bg" ref={bgRef}>
        <span className="rv-keycard-room-number">407</span>
        <span className="rv-keycard-glow" />
      </div>

      <div className="rv-keycard-tags">
        <span className="rv-keycard-tag" style={{ animationDelay: "0.5s" }}>
          <QuietIcon className="rv-keycard-tag-icon" /> Quiet room
        </span>
        <span className="rv-keycard-tag" style={{ animationDelay: "0.75s" }}>
          <PlateIcon className="rv-keycard-tag-icon" /> Vegetarian
        </span>
        <span className="rv-keycard-tag" style={{ animationDelay: "1s" }}>
          <CalendarIcon className="rv-keycard-tag-icon" /> Anniversary
        </span>
      </div>

      <div className="rv-keycard" ref={cardRef}>
        <span className="rv-keycard-brand">ReVisit</span>
        <span className="rv-keycard-chip" />
        <span className="rv-keycard-guest">Marie Dupont</span>
        <span className="rv-keycard-room">Room 407</span>
      </div>

      <span className="rv-keycard-status">ReVisit — guest context ready</span>
      <span className="rv-keycard-welcome">Welcome back, Marie.</span>
      <p className="rv-keycard-line">The guest didn&rsquo;t have to ask.</p>
    </div>
  );
}
