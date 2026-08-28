"""
Day 22 -- generates the HR screening question dataset for real JDs, both
generic (JD-only) and personalized (JD + candidate + ATS result), and
writes it as the "HR screening question dataset" / "AI conversation-ready
question objects" deliverables.
"""

import json
import logging
from dataclasses import asdict
from pathlib import Path

from parsers.semantic_matcher import SemanticMatcher
from parsers.ats_scoring_engine import score_candidate
from parsers.screening_question_bank import (
    generate_screening_questions,
    QUESTION_TEMPLATES,
    CATEGORY_METADATA,
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
        logging.FileHandler(LOG_DIR / "day22_question_bank_run.log", mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("day22")

# One tech JD, one business JD -- shows the templates + JD-derived
# personalization working across role categories, not just one.
JD_ONLY_TARGETS = ["jd_01_mern_developer", "jd_02_sales_executive"]

# A clean match, a missing-education case, and a wrong-stack case --
# exercises every ats_followup branch (education missing, skill missing,
# skill matched) in one run.
PERSONALIZED_TARGETS = [
    ("resume_01_mern_developer", "jd_01_mern_developer"),
    ("resume_14_no_education", "jd_01_mern_developer"),
    ("resume_11_python_backend_dev", "jd_01_mern_developer"),
]


def run():
    resume_files = sorted(RESUME_DIR.glob("*.txt"))
    jd_files = sorted(JD_DIR.glob("*.txt"))
    corpus = [f.read_text() for f in resume_files + jd_files]
    matcher = SemanticMatcher(corpus)
    logger.info("Fitted semantic matcher on %d documents", len(corpus))
    logger.info("=" * 90)
    logger.info("CATEGORY MAPPING (%d categories)", len(CATEGORY_METADATA))
    for cat, meta in CATEGORY_METADATA.items():
        logger.info("  %-14s mandatory=%-5s importance=%-6s roles=%s",
                     cat, meta["default_mandatory"], meta["default_scoring_importance"], meta["applicable_roles"])
    logger.info("REUSABLE TEMPLATES: %d defined across all categories", len(QUESTION_TEMPLATES))
    logger.info("=" * 90)

    dataset = {"jd_only": {}, "personalized": {}}

    for jd_id in JD_ONLY_TARGETS:
        jd_text = (JD_DIR / f"{jd_id}.txt").read_text()
        qs = generate_screening_questions(jd_text, jd_id)
        logger.info("JD-ONLY: %s (%d questions)", jd_id, len(qs))
        for q in qs:
            logger.info("  [%-13s|%-10s] %s", q.category, q.source, q.text)
        logger.info("-" * 90)
        dataset["jd_only"][jd_id] = [asdict(q) for q in qs]

    for resume_id, jd_id in PERSONALIZED_TARGETS:
        resume_text = (RESUME_DIR / f"{resume_id}.txt").read_text()
        jd_text = (JD_DIR / f"{jd_id}.txt").read_text()
        result = score_candidate(resume_text, jd_text, matcher)
        qs = generate_screening_questions(jd_text, jd_id, resume_text=resume_text, ats_result=result)
        followups = [q for q in qs if q.source == "ats_followup"]
        logger.info("PERSONALIZED: %s vs %s (%d questions, %d ATS-driven follow-ups)",
                     resume_id, jd_id, len(qs), len(followups))
        for q in qs:
            logger.info("  [%-13s|%-14s] %s", q.category, q.source, q.text)
        logger.info("-" * 90)
        dataset["personalized"][f"{resume_id}__vs__{jd_id}"] = [asdict(q) for q in qs]

    out_path = OUT_DIR / "day22_screening_question_dataset.json"
    out_path.write_text(json.dumps(dataset, indent=2), encoding="utf-8")
    logger.info("Full dataset written to %s", out_path)


if __name__ == "__main__":
    run()
