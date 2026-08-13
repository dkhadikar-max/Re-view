import Link from "next/link";
import { ANSWER_BLOCKS } from "./answerBlocksData";

/**
 * SEO_AEO_GEO_AUDIT.md §3/§5/§6/§8 — a static, always-rendered
 * section beneath the cinematic sequence. Deliberately separate from
 * SignatureSequence.tsx/Hero.tsx/marketing.css: the animated sequence
 * stays exactly as approved (PR #45, PR #50's performance work), and
 * the site's real semantic meaning — what ReVisit is, is it a
 * chatbot, how it remembers preferences — lives here as genuine,
 * crawlable HTML with real heading structure, not retrofitted into
 * the animation's own copy.
 *
 * This is the page's only H2/H3 content. One H2 section title, one
 * H3 per question — real content an AI system or search engine can
 * extract in isolation and still have the right answer, per the
 * brief's GEO framing (§5: "understandable if a system extracts only
 * fragments").
 */
export function AnswerBlocks() {
  return (
    <section className="rv-answers" aria-labelledby="rv-answers-heading">
      <div className="rv-answers-inner">
        <h2 id="rv-answers-heading">About ReVisit</h2>
        <dl>
          {ANSWER_BLOCKS.map((qa) => (
            <div className="rv-answer" key={qa.question}>
              <dt>
                <h3>{qa.question}</h3>
              </dt>
              <dd>{qa.answer}</dd>
            </div>
          ))}
        </dl>
        <p className="rv-answers-cta">
          <Link href="/onboard">Start a hotel trial with ReVisit →</Link>
        </p>
      </div>
    </section>
  );
}
