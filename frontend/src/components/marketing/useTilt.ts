"use client";

import { useEffect, useRef } from "react";

/**
 * Mouse-follow tilt for a card/panel: writes `transform` directly on
 * the ref via rAF-batched pointermove handling — the same
 * no-React-state-per-frame discipline as Hero.tsx's and
 * SignatureSequence.tsx's scroll transforms.
 *
 * Never attaches on touch devices, narrow viewports, or under
 * prefers-reduced-motion — "3D gracefully degrades on mobile" is
 * satisfied by not running at all there, not by running a reduced
 * version of it.
 */
export function useTilt<T extends HTMLElement>(maxDeg = 6) {
  const ref = useRef<T>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const canTilt = window.matchMedia("(pointer: fine)").matches && window.innerWidth >= 640;
    if (reduced || !canTilt) return;

    let rect: DOMRect | null = null;
    let ticking = false;
    let pendingX = 0;
    let pendingY = 0;

    function onEnter() {
      rect = el!.getBoundingClientRect();
    }

    function onMove(e: PointerEvent) {
      if (!rect) rect = el!.getBoundingClientRect();
      pendingX = (e.clientX - rect.left) / rect.width;
      pendingY = (e.clientY - rect.top) / rect.height;
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        const rotateY = (pendingX - 0.5) * maxDeg * 2;
        const rotateX = (0.5 - pendingY) * maxDeg * 2;
        el!.style.transform = `perspective(800px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateZ(6px)`;
        ticking = false;
      });
    }

    function onLeave() {
      el!.style.transform = "";
    }

    el.addEventListener("pointerenter", onEnter);
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerleave", onLeave);
    return () => {
      el.removeEventListener("pointerenter", onEnter);
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerleave", onLeave);
    };
  }, [maxDeg]);

  return ref;
}
