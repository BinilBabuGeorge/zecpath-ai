"""
Day 21 -- Eligibility Decision Engine demo.

Loads three real rule configs (data/eligibility_rules/*.json) and runs
every relevant candidate through evaluate_eligibility(), showing how the
same ATS score can produce different eligibility tags depending on a
job's specific hard requirements -- and validates every config on load
to catch the exact class of silent-typo bug this module's own example
config had at one point (see validate_rules_against_dictionary's
docstring).
"""

import json
import logging
from pathlib import Path

from parsers.semantic_matcher import SemanticMatcher
from parsers.ats_scoring_engine import score_candidate
from parsers.eligibility_engine import (
    EligibilityRules,
    evaluate_eligibility,
    validate_rules_against_dictionary,
)

RESUME_DIR = Path("data/samples/resumes")
JD_DIR = Path("data/samples/jds")
RULES_DIR = Path("data/eligibility_rules")
OUT_DIR = Path("data/results")
LOG_DIR = Path("logs")

OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "day21_eligibility_run.log", mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("day21")

# Which candidates to check against each config -- deliberately includes
# edge cases (fresher, senior, wrong-stack) for each relevant job.
CONFIG_CANDIDATES = {
    "jd_01_mern_developer.json": [
        "resume_01_mern_developer", "resume_13_fresher_no_experience",
        "resume_16_senior_backend_lead", "resume_11_python_backend_dev",
    ],
    "jd_01_junior_track.json": [
        "resume_01_mern_developer", "resume_13_fresher_no_experience",
    ],
    "jd_02_sales_executive.json": [
        "resume_03_sales_executive", "resume_05_hr_executive",
    ],
}


def run():
    resume_files = sorted(RESUME_DIR.glob("*.txt"))
    jd_files = sorted(JD_DIR.glob("*.txt"))
    corpus = [f.read_text() for f in resume_files + jd_files]
    matcher = SemanticMatcher(corpus)
    logger.info("Fitted semantic matcher on %d documents", len(corpus))
    logger.info("=" * 90)

    all_results = []

    for config_file, candidate_ids in CONFIG_CANDIDATES.items():
        config_path = RULES_DIR / config_file
        raw = json.loads(config_path.read_text())
        rules = EligibilityRules.from_dict(raw)

        # Validate on load -- exactly the step that would have caught
        # this module's own original "Salesforce CRM" typo before it
        # ever reached evaluate_eligibility().
        warnings = validate_rules_against_dictionary(rules)
        logger.info("CONFIG: %s  (job_id=%s)", config_file, rules.job_id)
        if warnings:
            for w in warnings:
                logger.info("  CONFIG WARNING: %s", w)
        else:
            logger.info("  Config validated clean -- all mandatory_skills match canonical names.")

        jd_text = (JD_DIR / f"{rules.job_id}.txt").read_text()

        for cid in candidate_ids:
            text = (RESUME_DIR / f"{cid}.txt").read_text()
            result = score_candidate(text, jd_text, matcher)
            elig = evaluate_eligibility(cid, text, result, rules)
            logger.info("  %-32s -> %-9s (score=%.1f, zone=%s)", cid, elig.tag, elig.overall_score, elig.score_zone)
            for reason in elig.reasons:
                logger.info("      %s", reason)
            all_results.append({
                "config": config_file, "candidate_id": cid, "job_id": rules.job_id,
                "tag": elig.tag, "overall_score": elig.overall_score,
                "score_zone": elig.score_zone, "reasons": elig.reasons,
                "gates_applied": elig.gates_applied,
            })
        logger.info("-" * 90)

    out_path = OUT_DIR / "day21_eligibility_results.json"
    out_path.write_text(json.dumps(all_results, indent=2), encoding="utf-8")
    logger.info("Structured results written to %s", out_path)


if __name__ == "__main__":
    run()
