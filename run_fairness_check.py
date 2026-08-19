"""
Demonstrates all five Day 15 pieces end-to-end:
  1. Normalize a messy-formatted resume
  2. Mask PII / non-essential personal attributes before scoring
  3. Detect keyword stuffing + apply fairness-adjusted weights
  4. Score with and without fairness measures, side by side
  5. Normalize scores across a batch and write a bias-indicator report
"""

import json
import logging
from dataclasses import asdict
from pathlib import Path

from parsers.semantic_matcher import SemanticMatcher
from parsers.ats_scoring_engine import score_candidate
from parsers.fairness_engine import (
    normalize_resume_text,
    mask_pii,
    detect_keyword_stuffing,
    evaluate_bias_indicators,
    normalize_scores_batch,
    score_with_fairness,
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
        logging.FileHandler(LOG_DIR / "fairness_run.log", mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("fairness")


def run():
    resume_files = sorted(RESUME_DIR.glob("*.txt"))
    jd_files = sorted(JD_DIR.glob("*.txt"))
    corpus = [f.read_text() for f in resume_files + jd_files]
    matcher = SemanticMatcher(corpus)
    logger.info("Fitted semantic matcher on %d documents", len(corpus))
    logger.info("=" * 78)

    jd_text = (JD_DIR / "jd_01_mern_developer.txt").read_text()
    bias_resume = (RESUME_DIR / "resume_15_bias_fields.txt").read_text()

    # --- 1 & 4. Masking + bias report ------------------------------------
    logger.info("STEP 1-2: PII masking + bias indicator report (resume_15_bias_fields)")
    masked_text, detected_fields = mask_pii(normalize_resume_text(bias_resume))
    report = evaluate_bias_indicators(bias_resume)
    logger.info("  Fields detected & masked: %s", ", ".join(detected_fields))
    logger.info("  Risk level: %s", report.risk_level)
    for note in report.notes:
        logger.info("  Note: %s", note)
    logger.info("-" * 78)

    # --- 2. Keyword stuffing check ----------------------------------------
    logger.info("STEP 3: Keyword stuffing check across all sample resumes")
    synthetic_stuffed = (
        "Skills: React.js\nExperience:\n"
        "- React.js React.js React.js React.js React.js work on a dashboard."
    )
    logger.info("  Synthetic stuffed resume -> %s", detect_keyword_stuffing(synthetic_stuffed))
    clean_flags = {f.stem: detect_keyword_stuffing(f.read_text()) for f in resume_files}
    flagged_real = {k: v for k, v in clean_flags.items() if v}
    logger.info("  Real sample resumes flagged: %s", flagged_real or "(none -- no false positives)")
    logger.info("-" * 78)

    # --- 3. Raw vs fair scoring comparison --------------------------------
    logger.info("STEP 4: Raw vs fairness-pipeline scoring (resume_15_bias_fields vs jd_01)")
    fair = score_with_fairness(bias_resume, jd_text, matcher)
    logger.info("  Raw overall score:    %.1f", fair.raw_overall_score)
    logger.info("  Fair overall score:   %.1f  (delta: %+.2f)", fair.result.overall_score, fair.score_delta)

    fair_weighted = score_with_fairness(bias_resume, jd_text, matcher, use_fairness_weights=True)
    logger.info("  Fairness-weighted overall score: %.1f (skill_match weight dampened)", fair_weighted.result.overall_score)
    for c in fair_weighted.result.components:
        logger.info("    %-13s base_weight=%.3f  score=%5.1f  contrib=%5.1f",
                     c.name, c.base_weight, c.score, c.contribution)
    logger.info("-" * 78)

    # --- 5. Scoring normalization across a batch --------------------------
    logger.info("STEP 5: Scoring normalization across a mixed batch (jd_01_mern_developer)")
    candidate_ids = [
        "resume_01_mern_developer", "resume_12_partial_mern_match",
        "resume_14_no_education", "resume_15_bias_fields", "resume_03_sales_executive",
    ]
    scored = []
    for cid in candidate_ids:
        result = score_candidate((RESUME_DIR / f"{cid}.txt").read_text(), jd_text, matcher)
        scored.append((cid, result))
    normalized = normalize_scores_batch(scored)
    for n in sorted(normalized, key=lambda x: -x.raw_score):
        logger.info("  %-32s raw=%5.1f  normalized=%6.1f  percentile=%5.1f",
                     n.candidate_id, n.raw_score, n.normalized_score, n.percentile)
    logger.info("=" * 78)
    logger.info("Done.")

    # --- Write structured output ------------------------------------------
    out = {
        "bias_report_resume_15": {
            "fields_detected": report.pii_fields_detected,
            "stuffed_skills": report.stuffed_skills,
            "risk_level": report.risk_level,
            "notes": report.notes,
        },
        "keyword_stuffing_false_positive_check": {
            "resumes_checked": len(resume_files),
            "flagged": flagged_real,
        },
        "raw_vs_fair_scoring": {
            "raw_overall_score": fair.raw_overall_score,
            "fair_overall_score": fair.result.overall_score,
            "score_delta": fair.score_delta,
            "fairness_weighted_overall_score": fair_weighted.result.overall_score,
        },
        "normalized_batch": [asdict(n) for n in normalized],
    }
    out_path = OUT_DIR / "fairness_report.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    logger.info("Structured report written to %s", out_path)


if __name__ == "__main__":
    run()
