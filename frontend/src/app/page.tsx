import { MarketingNav } from "@/components/marketing/MarketingNav";
import { Hero } from "@/components/marketing/Hero";
import { GuestJourney } from "@/components/marketing/GuestJourney";
import { HotelValue } from "@/components/marketing/HotelValue";
import { SystemsFit } from "@/components/marketing/SystemsFit";
import { ClosingCTA } from "@/components/marketing/ClosingCTA";
import "@/components/marketing/marketing.css";

/**
 * Public marketing homepage — final narrative-consolidation pass.
 *
 * Structure: Hero → Guest Journey → Hotel Value → Systems Fit (Memory
 * Layer) → Closing CTA. Five sections, ~5-6 viewports total, down
 * from the previous nine-section/~10-12-viewport version. The
 * objective of this pass was compression, not addition — every prior
 * section either got folded into one of the five above or stopped
 * rendering:
 *
 * - `SignatureSequence` no longer renders. It was the ~4-5 viewport
 *   scroll-hijacked cinematic sequence between Hero and Arrival; its
 *   story (guest arrives, memory surfaces, hotel acts) is now told
 *   once, compactly, in `GuestJourney`. The component itself is kept
 *   in the repo, unrendered, for easy rollback — not deleted.
 * - `ArrivalScene` / `StayScene` / `ReturnScene` no longer render as
 *   three independent full-viewport sections. `GuestJourney` is a
 *   fresh composition reusing their visual language (ChapterStage,
 *   the door/tray/key motifs) as three compact moments of one
 *   section instead. Also kept in the repo, unrendered.
 * - `HotelOutcomes` + `StaffExperience` no longer render separately.
 *   `HotelValue` consolidates them into one editorial section —
 *   StaffExperience's two-column "Guest context / What matters now"
 *   panel is deliberately not carried forward (it read as a dashboard
 *   dropped into a hospitality site). Both original files kept,
 *   unrendered.
 * - `SystemsFit` is redesigned in place (same file, same slot in the
 *   flow) from a three-box equation into a restrained flow diagram.
 *
 * Photography is real but temporary: three commercially-licensed
 * Wikimedia Commons photos standing in for a future commissioned
 * shoot. See public/images/marketing/CREDITS.md.
 */
export default function HomePage() {
  return (
    <div className="rv-root rv-dusk">
      <MarketingNav />
      <Hero />
      <GuestJourney />
      <HotelValue />
      <SystemsFit />
      <ClosingCTA />
    </div>
  );
}
