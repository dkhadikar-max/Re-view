import { ImageResponse } from "next/og";
import { REVISIT } from "@/lib/brand";

/**
 * SEO_AEO_GEO_AUDIT.md §9 — no Open Graph image existed; sharing the
 * homepage link showed a bare fallback. This is a typography-only
 * card using the site's own tokens (marketing.css's .rv-dusk palette)
 * — no photography decision made here, no new logo asset, nothing
 * that touches the approved cinematic visual direction.
 */
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: "80px",
          background: "#0c1a1f",
          color: "#eef4f5",
        }}
      >
        <div
          style={{
            fontSize: 22,
            letterSpacing: 4,
            textTransform: "uppercase",
            color: "#2ec4c4",
            marginBottom: 24,
          }}
        >
          {REVISIT.name}
        </div>
        <div style={{ fontSize: 64, fontWeight: 600, lineHeight: 1.15, maxWidth: 900 }}>
          Guest intelligence for hospitality.
        </div>
        <div style={{ fontSize: 28, color: "rgba(238,244,245,0.75)", marginTop: 32, maxWidth: 820 }}>
          {REVISIT.description}
        </div>
      </div>
    ),
    { ...size }
  );
}
