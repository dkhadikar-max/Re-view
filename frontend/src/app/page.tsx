import { MarketingNav } from "@/components/marketing/MarketingNav";
import { Hero } from "@/components/marketing/Hero";
import { SignatureSequence } from "@/components/marketing/SignatureSequence";
import { ArrivalScene } from "@/components/marketing/ArrivalScene";
import { StayScene } from "@/components/marketing/StayScene";
import { ReturnScene } from "@/components/marketing/ReturnScene";
import { HotelOutcomes } from "@/components/marketing/HotelOutcomes";
import { StaffExperience } from "@/components/marketing/StaffExperience";
import { SystemsFit } from "@/components/marketing/SystemsFit";
import { ClosingCTA } from "@/components/marketing/ClosingCTA";
import "@/components/marketing/marketing.css";

/**
 * Public marketing homepage — Direction B (Contemporary Hospitality) with
 * Direction A (Quiet Luxury) restraint in the hero and closing frame.
 *
 * Hero (Act I) and the Signature Sequence (Acts II–V + Final Frame) are the
 * original cinematic arc, unchanged in mechanics — Hero's copy was rewritten
 * to the locked positioning and its primary visual is now a staged CSS-3D
 * key-card scene (HeroScene), not a paragraph or an icon chain.
 *
 * Arrival / Stay / Return are three chapters of one narrative — the same
 * guest (Marie, already established in Hero and SignatureSequence)
 * traveling through a doorway scene, a service scene, and a second-arrival
 * scene, sharing one visual system (ChapterStage) rather than three
 * independent card sections. This replaced an earlier icon-grid/card-based
 * version of these sections entirely, not incrementally.
 *
 * HotelOutcomes/StaffExperience/SystemsFit/ClosingCTA follow as the
 * "why it matters / what your team sees / how it fits your PMS / close"
 * arc — StaffExperience resolves the previously-deferred "Act 08 · Product"
 * note (the operator-facing section).
 *
 * Photography is real but temporary: three commercially-licensed
 * Wikimedia Commons photos standing in for a future commissioned shoot,
 * not ReVisit's own. See public/images/marketing/CREDITS.md — flagged
 * explicitly there and in-page (small credit lines) since two of the
 * three depict a real, named, unaffiliated hotel.
 */
export default function HomePage() {
  return (
    <div className="rv-root rv-dusk">
      <MarketingNav />
      <Hero />
      <SignatureSequence />
      <ArrivalScene />
      <StayScene />
      <ReturnScene />
      <HotelOutcomes />
      <StaffExperience />
      <SystemsFit />
      <ClosingCTA />
    </div>
  );
}
