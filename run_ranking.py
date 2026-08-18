"""
Runs Day 13's ATS scoring engine across every candidate applying to a
single job, then Day 14's ranking engine to sort, zone, and shortlist
them -- producing the recruiter-facing output (ranked table + JSON).
"""

import json
import logging
from pathlib import Path

from parsers.semantic_matcher import SemanticMatcher
from parsers.ats_scoring_engine import score_candidate
from parsers.ranking_engine import (
    rank_candidates,
    top_candidates,
    filter_by_zone,
    zone_counts,
    to_recruiter_view,
)

RESUME_DIR = Path("data/samples/resumes")
JD_DIR = Path("data/samples/jds")
OUT_DIR = Path("data/results")
LOG_DIR = Path("logs")

OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "ranking_run.log", mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("ranking")

# One job, several applicants -- a strong domain match, a couple of
# adjacent/partial-fit candidates, and clear mismatches (one of which
# also has a missing-data component), so shortlist, review, and reject
# all get exercised in a single run.
JD_TO_SCORE = "jd_02_sales_executive"
CANDIDATES = [
    "resume_03_sales_executive",       # strong domain match -> shortlist
    "resume_10_customer_support",      # adjacent field -> review
    "resume_05_hr_executive",          # adjacent field -> review
    "resume_08_digital_marketer",      # adjacent field -> review
    "resume_01_mern_developer",        # cross-domain mismatch -> reject
    "resume_14_no_education",          # mismatch + missing education -> reject
]


def run():
    resume_files = sorted(RESUME_DIR.glob("*.txt"))
    jd_files = sorted(JD_DIR.glob("*.txt"))
    corpus = [f.read_text() for f in resume_files + jd_files]
    matcher = SemanticMatcher(corpus)
    logger.info("Fitted semantic matcher on %d documents", len(corpus))

    jd_text = (JD_DIR / f"{JD_TO_SCORE}.txt").read_text()

    scored = []
    for candidate_id in CANDIDATES:
        resume_text = (RESUME_DIR / f"{candidate_id}.txt").read_text()
        result = score_candidate(resume_text, jd_text, matcher)
        scored.append((candidate_id, JD_TO_SCORE, result))

    ranked = rank_candidates(scored)

    logger.info("=" * 78)
    logger.info("RANKED CANDIDATES for %s", JD_TO_SCORE)
    logger.info("=" * 78)
    for row in to_recruiter_view(ranked):
        logger.info(
            "#%-2d %-32s score=%5.1f  zone=%-9s strongest=%-13s flags=%s",
            row["rank"], row["candidate"], row["score"], row["zone"],
            row["strongest_factor"], row["flags"],
        )

    counts = zone_counts(ranked)
    logger.info("-" * 78)
    logger.info(
        "Zone summary: %d shortlisted, %d in review, %d rejected",
        counts["shortlist"], counts["review"], counts["reject"],
    )

    top3 = top_candidates(ranked, n=3)
    logger.info("Top 3 overall: %s", ", ".join(f"{c.candidate_id} ({c.overall_score})" for c in top3))

    shortlisted = filter_by_zone(ranked, "shortlist")
    logger.info("Auto-shortlisted: %s", ", ".join(c.candidate_id for c in shortlisted) or "(none)")

    out_path = OUT_DIR / f"ranking__{JD_TO_SCORE}.json"
    out_path.write_text(json.dumps({
        "jd_id": JD_TO_SCORE,
        "zone_counts": counts,
        "candidates": to_recruiter_view(ranked),
    }, indent=2), encoding="utf-8")
    logger.info("Done. Ranked output written to %s", out_path)


if __name__ == "__main__":
    run()
