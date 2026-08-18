"""
Runs the ATS scoring engine across a set of resume-JD pairs, including
the two missing-data cases, and saves the full explainable output.
"""

import json
import logging
from dataclasses import asdict
from pathlib import Path

from parsers.semantic_matcher import SemanticMatcher
from parsers.ats_scoring_engine import score_candidate

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
        logging.FileHandler(LOG_DIR / "ats_scoring_run.log", mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("ats_scoring")

# (resume_stem, jd_stem) pairs to score, chosen to cover: a clean match,
# a cross-domain mismatch, and both missing-data scenarios.
PAIRS_TO_SCORE = [
    ("resume_01_mern_developer", "jd_01_mern_developer"),
    ("resume_03_sales_executive", "jd_02_sales_executive"),
    ("resume_01_mern_developer", "jd_02_sales_executive"),      # cross-domain mismatch
    ("resume_13_fresher_no_experience", "jd_01_mern_developer"),  # missing experience
    ("resume_14_no_education", "jd_01_mern_developer"),           # missing education
]


def result_to_dict(result):
    return {
        "overall_score": result.overall_score,
        "role_category": result.role_category,
        "explanation": result.explanation,
        "missing_data_notes": result.missing_data_notes,
        "components": [asdict(c) for c in result.components],
    }


def run():
    resume_files = sorted(RESUME_DIR.glob("*.txt"))
    jd_files = sorted(JD_DIR.glob("*.txt"))
    corpus = [f.read_text() for f in resume_files + jd_files]
    matcher = SemanticMatcher(corpus)

    logger.info("Fitted semantic matcher on %d documents", len(corpus))
    logger.info("=" * 70)

    for resume_stem, jd_stem in PAIRS_TO_SCORE:
        resume_text = (RESUME_DIR / f"{resume_stem}.txt").read_text()
        jd_text = (JD_DIR / f"{jd_stem}.txt").read_text()

        result = score_candidate(resume_text, jd_text, matcher)

        out_path = OUT_DIR / f"{resume_stem}__vs__{jd_stem}.json"
        out_path.write_text(json.dumps(result_to_dict(result), indent=2), encoding="utf-8")

        logger.info("%s  vs  %s", resume_stem, jd_stem)
        logger.info("  Overall score: %.1f/100  (role category: %s)", result.overall_score, result.role_category)
        for c in result.components:
            flag = "" if c.available else "  [MISSING DATA]"
            logger.info("    %-13s score=%6.1f  weight=%.2f->%.2f  contrib=%5.1f%s",
                        c.name, c.score, c.base_weight, c.effective_weight, c.contribution, flag)
        if result.missing_data_notes:
            for note in result.missing_data_notes:
                logger.info("    NOTE: %s", note)
        logger.info("-" * 70)

    logger.info("Done. Results written to %s/", OUT_DIR)


if __name__ == "__main__":
    run()
