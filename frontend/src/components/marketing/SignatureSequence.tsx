"use client";

import { useEffect, useRef, useState } from "react";

type BeatId =
  | "world"
  | "signal"
  | "intel"
  | "action-checkin"
  | "action-team"
  | "hosp1"
  | "hosp2"
  | "hosp3"
  | "hosp4";

const RANGES: [number, number, BeatId][] = [
  [0.0, 0.13, "world"],
  [0.13, 0.28, "signal"],
  [0.28, 0.48, "intel"],
  [0.48, 0.62, "action-checkin"],
  [0.62, 0.74, "action-team"],
  [0.74, 0.8, "hosp1"],
  [0.8, 0.87, "hosp2"],
  [0.87, 0.94, "hosp3"],
  [0.94, 1.01, "hosp4"],
];

const RAIL_IDS: BeatId[] = [
  "signal",
  "intel",
  "action-checkin",
  "action-team",
  "hosp1",
  "hosp2",
  "hosp3",
  "hosp4",
];

/**
 * Acts II–V + Final Frame — one continuous scroll-driven take. The guest
 * → intelligence → action → hospitality story approved through the v8
 * prototype, ported faithfully: same beats, same timing bands, same
 * asymmetric placement. Beat/act state is applied imperatively via refs
 * (not React state) because it updates on every scroll frame — routing
 * that through setState would mean a re-render per frame.
 */
export function SignatureSequence() {
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReducedMotion(mq.matches);
    const handler = (e: MediaQueryListEvent) => setReducedMotion(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  return reducedMotion ? <StaticFallback /> : <InteractiveSequence />;
}

function InteractiveSequence() {
  const wrapRef = useRef<HTMLDivElement>(null);
  const seqImgRef = useRef<HTMLImageElement>(null);
  const hospGroundRef = useRef<HTMLDivElement>(null);
  const hospImgRef = useRef<HTMLImageElement>(null);
  const hospL1 = useRef<HTMLDivElement>(null);
  const hospL2 = useRef<HTMLDivElement>(null);
  const hospL3 = useRef<HTMLDivElement>(null);
  const hospL4 = useRef<HTMLDivElement>(null);
  const railRef = useRef<HTMLDivElement>(null);
  const dotRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const creditRef = useRef<HTMLParagraphElement>(null);
  const panelRefs = useRef<Map<string, HTMLDivElement>>(new Map());

  const panelRef = (id: string) => (el: HTMLDivElement | null) => {
    if (el) panelRefs.current.set(id, el);
    else panelRefs.current.delete(id);
  };

  useEffect(() => {
    const isMobile = window.innerWidth < 640;
    let current: BeatId | null = null;
    let hospLoaded = false;

    // Perf patch (PERF_PATCH_PUBLIC_SITE.md, Patch A): geometry cached
    // here and only recomputed on mount + resize, not on every scroll
    // frame. `getBoundingClientRect()` was being called inside the
    // scroll RAF purely to read `stageTop`, which is exactly
    // `offsetTop - window.scrollY` for an element with no transform on
    // itself (true here) -- so caching `offsetTop`/`total` once and
    // using the already-free `window.scrollY` on every frame gives the
    // same numbers without the forced-layout-read cost repeated ~60x/s
    // during a scroll.
    let offsetTop = 0;
    let total = 0;
    function measure() {
      const wrap = wrapRef.current;
      if (!wrap) return;
      offsetTop = wrap.offsetTop;
      total = wrap.offsetHeight - window.innerHeight;
    }

    function pulse(el: HTMLImageElement | null, ms = 700) {
      if (!el) return;
      el.classList.add("rv-pulse");
      setTimeout(() => el.classList.remove("rv-pulse"), ms);
    }

    // Perf patch, Patch A: the hospitality image is kept unpainted
    // (no `src`) until the sequence is genuinely close to needing it,
    // rather than loading eagerly at mount alongside the signal image
    // it never overlaps with on screen. Triggered a beat early
    // (action-team, not hosp1) so it has time to fetch/decode before
    // its pulse-in transition -- and also whenever hospActive directly,
    // as a safety net for the rail's jumpTo() landing straight on a
    // later hosp beat without passing through action-team first.
    function ensureHospLoaded() {
      if (hospLoaded) return;
      if (hospImgRef.current && !hospImgRef.current.src) {
        hospImgRef.current.src = "/images/marketing/hospitality.jpg";
      }
      hospLoaded = true;
    }

    function setBeat(id: BeatId) {
      if (id === current) return;
      const prev = current;
      current = id;

      panelRefs.current.forEach((el, beatId) => {
        el.classList.toggle("on", beatId === id);
      });
      RAIL_IDS.forEach((railId, i) => {
        dotRefs.current[i]?.classList.toggle("on", railId === id);
      });

      const hospActive = id === "hosp1" || id === "hosp2" || id === "hosp3" || id === "hosp4";
      if (id === "action-team" || hospActive) ensureHospLoaded();
      if (hospGroundRef.current) hospGroundRef.current.style.opacity = hospActive ? "1" : "0";
      hospL1.current?.classList.toggle("on", id === "hosp1");
      hospL2.current?.classList.toggle("on", id === "hosp2");
      hospL3.current?.classList.toggle("on", id === "hosp3");
      hospL4.current?.classList.toggle("on", id === "hosp4");
      if (creditRef.current) creditRef.current.style.opacity = hospActive ? "0" : "1";

      if (prev === "world" && id === "signal") pulse(seqImgRef.current, 650);
      if (prev === "action-team" && id === "hosp1") pulse(hospImgRef.current, 950);
    }

    let ticking = false;
    function onScroll() {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        if (!wrapRef.current || total <= 0) {
          ticking = false;
          return;
        }
        const stageTop = offsetTop - window.scrollY;
        const inView = stageTop <= 0 && stageTop > -total;
        railRef.current?.classList.toggle("show", inView);

        if (!inView) {
          if (stageTop > 0 && hospGroundRef.current) {
            hospGroundRef.current.style.opacity = "0";
            hospL1.current?.classList.remove("on");
            hospL2.current?.classList.remove("on");
            hospL3.current?.classList.remove("on");
            hospL4.current?.classList.remove("on");
          }
          ticking = false;
          return;
        }

        const progress = Math.min(Math.max(-stageTop / total, 0), 1);
        const seqMult = isMobile ? 0.015 : 0.03;
        if (seqImgRef.current) {
          seqImgRef.current.style.transform = `scale(${1.02 + progress * seqMult}) translateY(${
            progress * (isMobile ? -10 : -22)
          }px)`;
        }
        if (hospImgRef.current) {
          hospImgRef.current.style.transform = `scale(${1.01 + progress * 0.01})`;
        }

        for (const [start, end, id] of RANGES) {
          if (progress >= start && progress < end) {
            setBeat(id);
            break;
          }
        }
        if (progress >= 0.999) setBeat("hosp4");
        ticking = false;
      });
    }

    measure();
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", onScroll, { passive: true });
    setBeat("world");
    onScroll();
    return () => {
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", onScroll);
    };
  }, []);

  function jumpTo(id: BeatId) {
    const idx = RANGES.findIndex((r) => r[2] === id);
    if (idx === -1 || !wrapRef.current) return;
    const frac = (RANGES[idx][0] + RANGES[idx][1]) / 2;
    const top = wrapRef.current.offsetTop;
    const total = wrapRef.current.offsetHeight - window.innerHeight;
    window.scrollTo({ top: top + total * frac, behavior: "smooth" });
  }

  return (
    <>
      <div className="rv-sequence-wrap" ref={wrapRef}>
        <div className="rv-sequence-stage">
          <div className="rv-ground">
            {/* eslint-disable-next-line @next/next/no-img-element -- scroll-driven transform needs a plain img */}
            <img ref={seqImgRef} src="/images/marketing/signal.jpg" alt="" />
            <div className="rv-grade-dusk" />
            <div className="rv-vignette" />
          </div>
          <div className="rv-ground" ref={hospGroundRef} style={{ opacity: 0 }}>
            {/* eslint-disable-next-line @next/next/no-img-element -- scroll-driven transform needs a plain img.
                No `src` here on purpose (perf patch, Patch A): this image is kept unpainted until
                `ensureHospLoaded()` sets it, near its own beat, not eagerly at mount. */}
            <img ref={hospImgRef} alt="" />
            <div className="rv-grade-warm" />
            <div className="rv-vignette" />
          </div>

          {/* Act II — signal */}
          <div className="rv-beat-panel rv-pos-guest" ref={panelRef("signal")}>
            <p className="rv-signal-text">
              &quot;Good to be back.&quot;
              <span className="rv-signal-source">Guest · at check-in</span>
            </p>
          </div>

          {/* Act III — intelligence */}
          <div className="rv-beat-panel rv-pos-intel" ref={panelRef("intel")}>
            <span className="rv-intel-eyebrow">ReVisit understands</span>
            <p className="rv-intel-sentence">A returning guest, on their third stay.</p>
            <p className="rv-intel-meta">
              Previously shared preference — <b>Vegetarian dining</b>
            </p>
            <p className="rv-intel-ready">Preference carried forward</p>
          </div>

          {/* Act IV — action, part 1: check-in */}
          <div className="rv-beat-panel rv-pos-action" ref={panelRef("action-checkin")}>
            <span className="rv-action-heading">Check-in</span>
            <div className="rv-action-glow">
              <p className="rv-action-room">Room 412</p>
              <p className="rv-action-title">Quiet-side room assigned</p>
              <span className="rv-action-status">
                <span className="rv-dot" />
                Preference carried forward
              </span>
            </div>
          </div>

          {/* Act IV — action, part 2: team informed */}
          <div className="rv-beat-panel rv-pos-action" ref={panelRef("action-team")}>
            <span className="rv-action-heading">Team informed</span>
            <div className="rv-action-glow">
              <p className="rv-action-title">Vegetarian dining preference</p>
              <p className="rv-action-sub">Restaurant &amp; service team informed</p>
              <span className="rv-action-status">
                <span className="rv-dot" />
                Applied
              </span>
            </div>
          </div>

          {/* Act V — experience, held over hospitality footage */}
          <div className="rv-hosp-line rv-stmt" ref={hospL1}>
            <p>They shouldn&apos;t have to tell you twice.</p>
          </div>
          <div className="rv-hosp-line rv-stmt" ref={hospL2}>
            <p>A stay that remembers you feels different.</p>
          </div>

          {/* Final frame */}
          <div className="rv-hosp-line rv-brand" ref={hospL3}>
            <p>Guest intelligence for hospitality.</p>
          </div>
          <div className="rv-hosp-line rv-close" ref={hospL4}>
            <span className="rv-word" style={{ fontFamily: "var(--font-display)" }}>
              ReVisit
            </span>
            <p>Turn every guest conversation into a better stay.</p>
          </div>

          <p className="rv-credit" ref={creditRef}>
            Lobby, Amantaka — Basile Morin, CC BY-SA 4.0, Wikimedia Commons
          </p>
        </div>

        <div className="rv-rail" ref={railRef}>
          {RAIL_IDS.map((id, i) => (
            <button
              key={id}
              ref={(el) => {
                dotRefs.current[i] = el;
              }}
              aria-label={`Jump to: ${id}`}
              onClick={() => jumpTo(id)}
            />
          ))}
        </div>
      </div>
    </>
  );
}

/** prefers-reduced-motion: every beat rendered in normal document flow, no scroll-linked animation. */
function StaticFallback() {
  return (
    <div>
      <div className="rv-rm-beat">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/images/marketing/signal.jpg" alt="" />
        <div className="rv-beat-panel rv-pos-guest on" style={{ position: "relative", right: "auto", bottom: "auto" }}>
          <p className="rv-signal-text">
            &quot;Good to be back.&quot;
            <span className="rv-signal-source">Guest · at check-in</span>
          </p>
        </div>
      </div>
      <div className="rv-rm-beat">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/images/marketing/signal.jpg" alt="" />
        <div className="rv-beat-panel rv-pos-intel on" style={{ position: "relative", left: "auto", top: "auto" }}>
          <span className="rv-intel-eyebrow">ReVisit understands</span>
          <p className="rv-intel-sentence">A returning guest, on their third stay.</p>
          <p className="rv-intel-meta">
            Previously shared preference — <b>Vegetarian dining</b>
          </p>
          <p className="rv-intel-ready">Preference carried forward</p>
        </div>
      </div>
      <div className="rv-rm-beat">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/images/marketing/signal.jpg" alt="" />
        <div className="rv-beat-panel rv-pos-action on" style={{ position: "relative", left: "auto", top: "auto", transform: "none" }}>
          <span className="rv-action-heading">Check-in</span>
          <div className="rv-action-glow">
            <p className="rv-action-room">Room 412</p>
            <p className="rv-action-title">Quiet-side room assigned</p>
            <span className="rv-action-status">
              <span className="rv-dot" />
              Preference carried forward
            </span>
          </div>
        </div>
      </div>
      <div className="rv-rm-beat">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/images/marketing/signal.jpg" alt="" />
        <div className="rv-beat-panel rv-pos-action on" style={{ position: "relative", left: "auto", top: "auto", transform: "none" }}>
          <span className="rv-action-heading">Team informed</span>
          <div className="rv-action-glow">
            <p className="rv-action-title">Vegetarian dining preference</p>
            <p className="rv-action-sub">Restaurant &amp; service team informed</p>
            <span className="rv-action-status">
              <span className="rv-dot" />
              Applied
            </span>
          </div>
        </div>
      </div>
      <div className="rv-rm-beat">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/images/marketing/hospitality.jpg" alt="" />
        <div className="rv-hosp-line rv-stmt on" style={{ position: "relative", left: "auto", bottom: "auto", transform: "none" }}>
          <p>They shouldn&apos;t have to tell you twice.</p>
        </div>
      </div>
      <div className="rv-rm-beat">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/images/marketing/hospitality.jpg" alt="" />
        <div className="rv-hosp-line rv-stmt on" style={{ position: "relative", left: "auto", bottom: "auto", transform: "none" }}>
          <p>A stay that remembers you feels different.</p>
        </div>
      </div>
      <div className="rv-rm-beat">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/images/marketing/hospitality.jpg" alt="" />
        <div className="rv-hosp-line rv-brand on" style={{ position: "relative", left: "auto", bottom: "auto", transform: "none" }}>
          <p>Guest intelligence for hospitality.</p>
        </div>
      </div>
      <div className="rv-rm-beat">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/images/marketing/hospitality.jpg" alt="" />
        <div className="rv-hosp-line rv-close on" style={{ position: "relative", left: "auto", bottom: "auto", transform: "none" }}>
          <span className="rv-word" style={{ fontFamily: "var(--font-display)" }}>
            ReVisit
          </span>
          <p>Turn every guest conversation into a better stay.</p>
        </div>
      </div>
    </div>
  );
}
