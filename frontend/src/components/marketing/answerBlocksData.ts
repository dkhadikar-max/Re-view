/**
 * SEO_AEO_GEO_AUDIT.md §7/§8 (AEO content) — the single source of
 * truth for the homepage's visible Q&A section (AnswerBlocks.tsx) and
 * its matching FAQPage JSON-LD (StructuredData.tsx). One array, two
 * renderers, so the structured data can never claim something the
 * visible page doesn't actually say.
 *
 * Named answerBlocksData.ts, not answerBlocks.ts -- the latter
 * collided with AnswerBlocks.tsx on Windows' case-insensitive
 * filesystem (a real `next build` failure, not a flaky one: two
 * files differing only by the first letter's case are the same file
 * on disk there, even though git and macOS/Linux treat them as
 * distinct).
 *
 * Every answer is grounded in real, shipped capability — the same
 * discipline as GUEST_MEMORY_EVIDENCE_CHAIN.md and
 * PHASE4_PRODUCT_REVIEW.md's Product Truth Principle: confirmed-only
 * memory (no inference), no autonomous actions, no chatbot framing,
 * no claims about capabilities (WhatsApp specifics, cross-hotel
 * memory, predictive scoring) that haven't been verified as real,
 * user-facing, launched behavior.
 */
export type AnswerBlock = {
  question: string;
  answer: string;
};

export const ANSWER_BLOCKS: AnswerBlock[] = [
  {
    question: "What is ReVisit?",
    answer:
      "ReVisit is a guest intelligence platform for hotels. It turns relevant guest conversations and confirmed guest history into intelligence hotel teams can act on — helping them recognize returning guests, remember stated preferences, and carry that context into every stay.",
  },
  {
    question: "Is ReVisit an AI chatbot?",
    answer:
      "No. ReVisit is a guest intelligence and experience tool. It uses guest information and conversation history to help hotels understand returning guests and act on relevant information; it is not positioned as a guest-facing AI chatbot.",
  },
  {
    question: "How does ReVisit remember guest preferences?",
    answer:
      "When a guest explicitly shares a preference — a dietary need, a room preference — ReVisit records it together with the guest's own words as evidence, so hotel staff can see not just what was recorded but exactly what the guest said and when.",
  },
  {
    question: "What is guest intelligence in hospitality?",
    answer:
      "Guest intelligence is the practice of turning what guests have explicitly told a hotel into organized, evidence-backed information hotel teams can act on, instead of relying on staff memory or notes scattered across systems.",
  },
  {
    question: "What is the difference between guest intelligence and a hotel chatbot?",
    answer:
      "A chatbot is built to hold a conversation. Guest intelligence is built to remember and organize what guests have already said — with evidence — so hotel teams, not just a bot, can act on it at the next stay.",
  },
  {
    question: "What can hotel teams see in ReVisit?",
    answer:
      "Hotel teams see confirmed guest preferences — such as dietary needs or room preferences — alongside the guest's own words as evidence, for any preference the guest explicitly and directly stated.",
  },
];
