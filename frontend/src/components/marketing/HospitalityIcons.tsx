/**
 * Shared line-art hospitality objects — deliberately simple geometry
 * (a handful of primitives each, no traced illustration paths) styled
 * with the site's teal/warm palette. Not literal 3D renders (no
 * WebGL is installed and the brief explicitly prefers CSS 3D over a
 * new dependency) — these are staged with perspective/translateZ in
 * the components that use them to read as objects in space, not flat
 * icons.
 *
 * Every usage across the site is decorative (paired with adjacent
 * visible text, or purely atmospheric) — `aria-hidden` is baked in
 * here once rather than repeated at each call site.
 */
type IconProps = { className?: string };

export function KeyCardIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 40 40" className={className} fill="none" aria-hidden="true">
      <rect x="6" y="10" width="28" height="20" rx="3" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="14" cy="20" r="3.4" stroke="currentColor" strokeWidth="1.6" />
      <path d="M20 17h9M20 20h9M20 23h6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

export function PlateIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 40 40" className={className} fill="none" aria-hidden="true">
      <circle cx="20" cy="20" r="13" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="20" cy="20" r="7.5" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  );
}

export function QuietIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 40 40" className={className} fill="none" aria-hidden="true">
      <path d="M25 8a13 13 0 1 0 7 23.4A11 11 0 0 1 25 8z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
    </svg>
  );
}

export function CalendarIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 40 40" className={className} fill="none" aria-hidden="true">
      <rect x="7" y="9" width="26" height="23" rx="2.5" stroke="currentColor" strokeWidth="1.6" />
      <path d="M7 16h26M13 6v6M27 6v6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="20" cy="23" r="2" fill="currentColor" />
    </svg>
  );
}

export function LuggageIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 40 40" className={className} fill="none" aria-hidden="true">
      <rect x="8" y="14" width="24" height="18" rx="3" stroke="currentColor" strokeWidth="1.6" />
      <path d="M16 14v-3a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v3" stroke="currentColor" strokeWidth="1.6" />
      <path d="M8 22h24" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  );
}
