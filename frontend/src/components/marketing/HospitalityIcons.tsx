"use client";

import { useId } from "react";

/**
 * Shared hospitality objects — small physical-looking details (brass
 * key card, ceramic plate, leather luggage), not a generic icon
 * library. Each carries a subtle material gradient (brass, ceramic,
 * leather) plus a line-art structure on top, still pure SVG — no new
 * dependency, no WebGL. `useId()` scopes each instance's gradient IDs
 * so the same icon can render more than once on a page (e.g. the
 * plate appears in both the Hero card and the Stay moment) without
 * colliding `<defs>` ids.
 *
 * Kept deliberately small and quiet wherever they're used — these are
 * details a guest might notice in passing, not the visual subject.
 * The photograph carries the scene; these carry texture.
 *
 * Every usage across the site is decorative (paired with adjacent
 * visible text, or purely atmospheric) — `aria-hidden` is baked in
 * here once rather than repeated at each call site.
 */
type IconProps = { className?: string };

export function KeyCardIcon({ className }: IconProps) {
  const id = useId();
  return (
    <svg viewBox="0 0 40 40" className={className} fill="none" aria-hidden="true">
      <defs>
        <linearGradient id={`${id}-brass`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#e8caa0" />
          <stop offset="50%" stopColor="#b98a56" />
          <stop offset="100%" stopColor="#8a6438" />
        </linearGradient>
        <linearGradient id={`${id}-body`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="currentColor" stopOpacity="0.14" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0.02" />
        </linearGradient>
      </defs>
      <rect x="6" y="10" width="28" height="20" rx="3" fill={`url(#${id}-body)`} stroke="currentColor" strokeWidth="1.4" />
      {/* brass corner accents, like a real hotel key card's foil edge */}
      <path d="M8 12v-1a1 1 0 0 1 1-1h1" stroke={`url(#${id}-brass)`} strokeWidth="1.6" strokeLinecap="round" />
      <path d="M32 28v1a1 1 0 0 1-1 1h-1" stroke={`url(#${id}-brass)`} strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="14" cy="20" r="3.4" fill={`url(#${id}-brass)`} fillOpacity="0.28" stroke={`url(#${id}-brass)`} strokeWidth="1.4" />
      <path d="M20 17h9M20 20h9M20 23h6" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeOpacity="0.8" />
    </svg>
  );
}

export function PlateIcon({ className }: IconProps) {
  const id = useId();
  return (
    <svg viewBox="0 0 40 40" className={className} fill="none" aria-hidden="true">
      <defs>
        <radialGradient id={`${id}-ceramic`} cx="38%" cy="34%" r="70%">
          <stop offset="0%" stopColor="currentColor" stopOpacity="0.16" />
          <stop offset="70%" stopColor="currentColor" stopOpacity="0.04" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
        </radialGradient>
        <linearGradient id={`${id}-rim`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#e8caa0" />
          <stop offset="100%" stopColor="#a87d4c" />
        </linearGradient>
      </defs>
      <circle cx="20" cy="20" r="13" fill={`url(#${id}-ceramic)`} stroke="currentColor" strokeWidth="1.5" />
      <circle cx="20" cy="20" r="10.2" stroke={`url(#${id}-rim)`} strokeWidth="0.7" strokeOpacity="0.7" />
      <circle cx="20" cy="20" r="7.5" stroke="currentColor" strokeWidth="1.1" strokeOpacity="0.85" />
    </svg>
  );
}

export function QuietIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 40 40" className={className} fill="none" aria-hidden="true">
      <path
        d="M25 8a13 13 0 1 0 7 23.4A11 11 0 0 1 25 8z"
        fill="currentColor"
        fillOpacity="0.08"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function CalendarIcon({ className }: IconProps) {
  const id = useId();
  return (
    <svg viewBox="0 0 40 40" className={className} fill="none" aria-hidden="true">
      <defs>
        <linearGradient id={`${id}-mark`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#e8caa0" />
          <stop offset="100%" stopColor="#a87d4c" />
        </linearGradient>
      </defs>
      <rect x="7" y="9" width="26" height="23" rx="2.5" fill="currentColor" fillOpacity="0.05" stroke="currentColor" strokeWidth="1.5" />
      <path d="M7 16h26M13 6v6M27 6v6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeOpacity="0.85" />
      <circle cx="20" cy="23" r="2" fill={`url(#${id}-mark)`} />
    </svg>
  );
}

export function LuggageIcon({ className }: IconProps) {
  const id = useId();
  return (
    <svg viewBox="0 0 40 40" className={className} fill="none" aria-hidden="true">
      <defs>
        <linearGradient id={`${id}-leather`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="currentColor" stopOpacity="0.16" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0.02" />
        </linearGradient>
        <linearGradient id={`${id}-buckle`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#e8caa0" />
          <stop offset="100%" stopColor="#8a6438" />
        </linearGradient>
      </defs>
      <rect x="8" y="14" width="24" height="18" rx="3" fill={`url(#${id}-leather)`} stroke="currentColor" strokeWidth="1.5" />
      <path d="M16 14v-3a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v3" stroke="currentColor" strokeWidth="1.5" />
      <path d="M8 22h24" stroke="currentColor" strokeWidth="1" strokeOpacity="0.55" />
      {/* small brass corner buckles, the detail that reads "leather" not "flat icon" */}
      <rect x="10.5" y="24.5" width="3.4" height="3.4" rx="0.6" fill={`url(#${id}-buckle)`} fillOpacity="0.85" />
      <rect x="26.1" y="24.5" width="3.4" height="3.4" rx="0.6" fill={`url(#${id}-buckle)`} fillOpacity="0.85" />
    </svg>
  );
}
