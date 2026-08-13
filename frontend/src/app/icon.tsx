import { ImageResponse } from "next/og";

/**
 * SEO_AEO_GEO_AUDIT.md §6 — no favicon existed at all (public/ only
 * had the unmodified Next.js starter SVGs). This is a minimal,
 * on-brand placeholder — same dusk/signal colors as the marketing
 * site (marketing.css's .rv-dusk) — not a real logo mark. Same
 * "temporary, clearly a placeholder, not a design decision" spirit
 * as the licensed stand-in photography already on the homepage
 * (public/images/marketing/CREDITS.md).
 */
export const size = { width: 32, height: 32 };
export const contentType = "image/png";

export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#0c1a1f",
          borderRadius: 6,
          color: "#2ec4c4",
          fontSize: 20,
          fontWeight: 600,
        }}
      >
        R
      </div>
    ),
    { ...size }
  );
}
