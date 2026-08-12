import { MarketingNav } from "@/components/marketing/MarketingNav";
import { Hero } from "@/components/marketing/Hero";
import { SignatureSequence } from "@/components/marketing/SignatureSequence";
import "@/components/marketing/marketing.css";

/**
 * Public marketing homepage — Direction B (Contemporary Hospitality) with
 * Direction A (Quiet Luxury) restraint in the hero and closing frame.
 *
 * This implements Acts I–V + the Final Frame from the approved v8 design
 * (hero arrival → guest signal → intelligence reveal → hotel action →
 * experience fade → hospitality close). Act "08 · Product" (the operator
 * guest-intelligence screens) is a deliberate, separate follow-up — it
 * only earns its place once this arc has been reviewed live, per the
 * phased approach carried through the whole design process.
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
    </div>
  );
}
