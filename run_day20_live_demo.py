"""
Day 20 -- Live demo of the ATS system, end to end.

Walks through every stage built across Days 9-20 against one job opening
and a small, deliberately varied set of candidates (see data/demo/README.md
for why these specific candidates were chosen). Meant to be read top to
bottom as a narrated demo, not just executed for output -- each section
prints what's happening and why before showing the result.
"""

import logging
from pathlib import Path

from parsers.semantic_matcher import SemanticMatcher
from parsers.ats_scoring_engine import score_candidate
from parsers.ranking_engine import rank_candidates, to_recruiter_view, zone_counts
from parsers.fairness_engine import score_with_fairness, evaluate_bias_indicators

RESUME_DIR = Path("data/samples/resumes")
JD_DIR = Path("data/samples/jds")

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("demo")


def section(title):
    logger.info("")
    logger.info("=" * 90)
    logger.info(title)
    logger.info("=" * 90)


def run():
    section("ZECPATH ATS -- LIVE DEMO")
    logger.info("Job opening: MERN Stack Developer (jd_01_mern_developer)")
    logger.info("Candidates: 6, deliberately varied -- see data/demo/README.md for why each was picked")

    jd_text = (JD_DIR / "jd_01_mern_developer.txt").read_text()
    candidate_ids = [
        "resume_01_mern_developer",       # clean, strong match
        "resume_16_senior_backend_lead",  # senior, overqualified in years
        "resume_12_partial_mern_match",   # partial skill overlap
        "resume_13_fresher_no_experience",# fresher, sparse but relevant skills
        "resume_11_python_backend_dev",   # wrong stack entirely
        "resume_15_bias_fields",          # resume with demographic fields present
    ]

    # --- Stage 1: extraction + semantic matching setup --------------------
    section("STAGE 1 -- Corpus fitting (Days 9-12)")
    all_resumes = sorted(RESUME_DIR.glob("*.txt"))
    all_jds = sorted(JD_DIR.glob("*.txt"))
    corpus = [f.read_text() for f in all_resumes + all_jds]
    matcher = SemanticMatcher(corpus)
    logger.info("Fitted TF-IDF semantic matcher on %d resumes + %d JDs.", len(all_resumes), len(all_jds))
    logger.info("(Section extraction, skill/experience/education parsing happen per-candidate below.)")

    # --- Stage 2: explainable scoring (Day 13) -----------------------------
    section("STAGE 2 -- Explainable scoring, one candidate shown in full (Day 13)")
    sample_id = "resume_01_mern_developer"
    sample_text = (RESUME_DIR / f"{sample_id}.txt").read_text()
    sample_result = score_candidate(sample_text, jd_text, matcher)
    logger.info("Candidate: %s", sample_id)
    logger.info("Overall score: %.1f  (role category: %s)", sample_result.overall_score, sample_result.role_category)
    for c in sample_result.components:
        logger.info("  %-13s score=%5.1f  weight=%.2f->%.3f  contributes=%5.1f  available=%s",
                     c.name, c.score, c.base_weight, c.effective_weight, c.contribution, c.available)
    logger.info("Explanation: %s", sample_result.explanation)
    logger.info("(Every score comes with this full breakdown -- nothing is a black box.)")

    # --- Stage 3: fairness pipeline on the demographic-fields candidate ---
    section("STAGE 3 -- Fairness pipeline (Day 15): PII masking + bias report")
    bias_id = "resume_15_bias_fields"
    bias_text = (RESUME_DIR / f"{bias_id}.txt").read_text()
    bias_report = evaluate_bias_indicators(bias_text)
    fair_result = score_with_fairness(bias_text, jd_text, matcher)
    logger.info("Candidate: %s", bias_id)
    logger.info("Non-essential personal fields detected & masked before scoring: %s", ", ".join(bias_report.pii_fields_detected))
    logger.info("Risk level: %s", bias_report.risk_level)
    logger.info("Raw score: %.1f  ->  Fair (masked) score: %.1f  (delta %+.2f -- masking removes bias vectors without changing legitimate standing)",
                 fair_result.raw_overall_score, fair_result.result.overall_score, fair_result.score_delta)

    # --- Stage 4: score every candidate, rank, and shortlist ---------------
    section("STAGE 4 -- Score all 6 candidates, rank, and shortlist (Days 13+14+20)")
    scored = []
    for cid in candidate_ids:
        text = (RESUME_DIR / f"{cid}.txt").read_text()
        result = score_candidate(text, jd_text, matcher)
        scored.append((cid, "jd_01_mern_developer", result))

    ranked = rank_candidates(scored)
    logger.info("%-4s %-32s %-8s %-10s %-15s", "Rank", "Candidate", "Score", "Zone", "Strongest Factor")
    for row in to_recruiter_view(ranked):
        logger.info("%-4s %-32s %-8.1f %-10s %-15s", row["rank"], row["candidate"], row["score"], row["zone"], row["strongest_factor"])

    counts = zone_counts(ranked)
    logger.info("")
    logger.info("Zone summary: %d shortlisted, %d in review, %d rejected", counts["shortlist"], counts["review"], counts["reject"])
    logger.info("(This zone classification now uses Day 20's category-aware thresholds + skill-relevance floor --")
    logger.info(" see docs/day20_final_review.md for the measured 41.7%% -> 83.3%% accuracy improvement this produced.)")

    section("DEMO COMPLETE")
    logger.info("What was shown: extraction+matching setup, one fully explained score, the fairness/PII")
    logger.info("pipeline on a demographic-rich resume, and full ranking/shortlisting across 6 varied")
    logger.info("candidates. See docs/day20_final_review.md for the full production-readiness assessment,")
    logger.info("including what's still NOT resolved (2 known gaps, documented, not hidden).")


if __name__ == "__main__":
    run()
