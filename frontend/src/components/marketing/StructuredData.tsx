import { ARGUS, REVISIT } from "@/lib/brand";
import { ANSWER_BLOCKS } from "./answerBlocksData";

/**
 * SEO_AEO_GEO_AUDIT.md §8 — no JSON-LD existed anywhere. Every claim
 * here is either a plain fact about the site itself (name, url) or
 * pulled from the same REVISIT.description / ANSWER_BLOCKS content
 * already rendered visibly on the page — nothing invented, no
 * ratings/reviews/pricing/customer counts/awards, per the Product
 * Truth Principle.
 *
 * Two types considered and deliberately left out, not just omitted by
 * oversight:
 * - BreadcrumbList — no real hierarchical page tree exists yet (one
 *   homepage + one signup form); a breadcrumb would be decorative.
 * - WebPage — reconsidered during review. It mostly re-stated what
 *   title/description/canonical already say, carries no Google
 *   rich-result behavior of its own, and its only distinct property
 *   (isPartOf -> WebSite) was thin value for the duplication cost.
 *   "More schema is not automatically better" — dropped rather than
 *   kept for the sake of having five types instead of four.
 *
 * Service is kept for entity/categorization clarity (the GEO goal —
 * an AI system extracting this page should see "Service, guest
 * intelligence platform, audience: hotels" as an explicit fact, not
 * something it has to infer from prose). Worth being explicit that
 * this does not produce a Google Search rich result on its own —
 * Service/SoftwareApplication schema isn't one of Google's supported
 * rich-result types the way FAQPage or Product is.
 *
 * FAQPage matches ANSWER_BLOCKS 1:1, genuinely visible in
 * AnswerBlocks.tsx. One caveat worth recording here, not glossed
 * over: Google restricted FAQPage rich-result eligibility in Search
 * (2023) to a narrow set of authoritative government/health sites —
 * this markup is still valid, honest, and useful for AI/GEO systems
 * that read structured data directly, but it should not be assumed to
 * produce a Google SERP rich snippet for this site.
 */
export function StructuredData() {
  const organization = {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: REVISIT.name,
    url: REVISIT.siteUrl,
    parentOrganization: {
      "@type": "Organization",
      name: ARGUS.productLine,
      url: ARGUS.siteUrl,
    },
  };

  const website = {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: REVISIT.name,
    url: REVISIT.siteUrl,
  };

  const service = {
    "@context": "https://schema.org",
    "@type": "Service",
    name: "Guest intelligence platform for hotels",
    serviceType: "Guest intelligence platform for hotels",
    description: REVISIT.description,
    provider: {
      "@type": "Organization",
      name: REVISIT.name,
      url: REVISIT.siteUrl,
    },
    audience: {
      "@type": "BusinessAudience",
      audienceType: "Hotels and hospitality operators",
    },
  };

  const faqPage = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: ANSWER_BLOCKS.map((qa) => ({
      "@type": "Question",
      name: qa.question,
      acceptedAnswer: {
        "@type": "Answer",
        text: qa.answer,
      },
    })),
  };

  const graph = [organization, website, service, faqPage];

  return (
    <script
      type="application/ld+json"
      // eslint-disable-next-line react/no-danger -- JSON-LD requires raw script content; the payload
      // above is built entirely from typed, non-user-supplied constants, not interpolated HTML.
      dangerouslySetInnerHTML={{ __html: JSON.stringify(graph) }}
    />
  );
}
