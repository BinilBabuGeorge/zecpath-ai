"""
Day 17 -- ATS System Testing.

Runs the full AI pipeline (Day 12 semantic matcher -> Day 13 scoring ->
Day 14 zone classification) against 12 resume/JD pairs whose CORRECT
outcome was judged independently by reading the resume/JD text (see
data/ground_truth_ats/day17_manual_review.json) -- not derived by running
the AI and copying its output. Comparing AI zone vs manual-review zone
produces genuine precision/recall/mismatch numbers, broken down by
category (tech/non-tech) and experience level (fresher/mid/senior) to
directly test role adaptability, per the Day 17 brief.
"""

import json
import logging
from collections import defaultdict
from pathlib import Path

from parsers.semantic_matcher import SemanticMatcher
from parsers.ats_scoring_engine import score_candidate
from parsers.ranking_engine import classify_zone

RESUME_DIR = Path("data/samples/resumes")
JD_DIR = Path("data/samples/jds")
GT_PATH = Path("data/ground_truth_ats/day17_manual_review.json")
OUT_DIR = Path("data/results")
LOG_DIR = Path("logs")

OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "day17_ats_testing.log", mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("day17")

ZONES = ["SHORTLIST", "REVIEW", "REJECT"]


def load_ground_truth():
    return json.loads(GT_PATH.read_text())["pairs"]


def run_pipeline(matcher, pair):
    resume_text = (RESUME_DIR / f"{pair['resume_id']}.txt").read_text()
    jd_text = (JD_DIR / f"{pair['jd_id']}.txt").read_text()
    result = score_candidate(resume_text, jd_text, matcher)
    zone = classify_zone(result.overall_score).upper()
    return result, zone


def precision_recall_f1(confusion):
    """confusion: {zone: {'tp':.., 'fp':.., 'fn':..}} -> adds precision/recall/f1."""
    metrics = {}
    for zone, c in confusion.items():
        p = c["tp"] / (c["tp"] + c["fp"]) if (c["tp"] + c["fp"]) else 0.0
        r = c["tp"] / (c["tp"] + c["fn"]) if (c["tp"] + c["fn"]) else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) else 0.0
        metrics[zone] = {"precision": round(p, 3), "recall": round(r, 3), "f1": round(f1, 3)}
    return metrics


def run():
    resume_files = sorted(RESUME_DIR.glob("*.txt"))
    jd_files = sorted(JD_DIR.glob("*.txt"))
    corpus = [f.read_text() for f in resume_files + jd_files]
    matcher = SemanticMatcher(corpus)
    logger.info("Fitted semantic matcher on %d documents (incl. new resume_16_senior_backend_lead)", len(corpus))
    logger.info("=" * 90)
    logger.info("DAY 17 -- ATS SYSTEM TESTING: AI OUTPUT vs MANUAL REVIEW")
    logger.info("=" * 90)

    pairs = load_ground_truth()
    confusion = {z: {"tp": 0, "fp": 0, "fn": 0} for z in ZONES}
    by_category = defaultdict(lambda: {"correct": 0, "total": 0})
    by_experience = defaultdict(lambda: {"correct": 0, "total": 0})
    mismatches = []
    rows = []

    for pair in pairs:
        result, ai_zone = run_pipeline(matcher, pair)
        expected = pair["expected_zone"]
        match = ai_zone == expected

        if match:
            confusion[expected]["tp"] += 1
        else:
            confusion[ai_zone]["fp"] += 1
            confusion[expected]["fn"] += 1
            mismatches.append({
                "resume_id": pair["resume_id"], "jd_id": pair["jd_id"],
                "category": pair["category"], "experience_level": pair["experience_level"],
                "expected_zone": expected, "ai_zone": ai_zone,
                "overall_score": result.overall_score,
                "manual_reasoning": pair["reasoning"],
                "ai_explanation": result.explanation,
            })

        by_category[pair["category"]]["total"] += 1
        by_category[pair["category"]]["correct"] += int(match)
        by_experience[pair["experience_level"]]["total"] += 1
        by_experience[pair["experience_level"]]["correct"] += int(match)

        rows.append({
            "resume_id": pair["resume_id"], "jd_id": pair["jd_id"],
            "category": pair["category"], "experience_level": pair["experience_level"],
            "expected_zone": expected, "ai_zone": ai_zone, "match": match,
            "overall_score": result.overall_score,
        })

        status = "MATCH" if match else "MISMATCH"
        logger.info("%-8s %-32s vs %-32s  expected=%-10s ai=%-10s score=%5.1f  [%s/%s]",
                     status, pair["resume_id"], pair["jd_id"], expected, ai_zone,
                     result.overall_score, pair["category"], pair["experience_level"])

    total = len(pairs)
    correct = sum(r["match"] for r in rows)
    overall_accuracy = round(100 * correct / total, 1)

    logger.info("-" * 90)
    logger.info("OVERALL ACCURACY: %d/%d = %.1f%%", correct, total, overall_accuracy)
    logger.info("-" * 90)

    metrics = precision_recall_f1(confusion)
    logger.info("%-12s %6s %6s %6s %10s %10s %10s", "Zone", "TP", "FP", "FN", "Precision", "Recall", "F1")
    for zone in ZONES:
        c = confusion[zone]
        m = metrics[zone]
        logger.info("%-12s %6d %6d %6d %10.3f %10.3f %10.3f", zone, c["tp"], c["fp"], c["fn"],
                     m["precision"], m["recall"], m["f1"])

    logger.info("-" * 90)
    logger.info("ACCURACY BY CATEGORY (role adaptability across tech/non-tech)")
    for cat, c in sorted(by_category.items()):
        logger.info("  %-12s %d/%d = %.1f%%", cat, c["correct"], c["total"], 100 * c["correct"] / c["total"])

    logger.info("ACCURACY BY EXPERIENCE LEVEL (role adaptability across fresher/mid/senior)")
    for level, c in sorted(by_experience.items()):
        logger.info("  %-12s %d/%d = %.1f%%", level, c["correct"], c["total"], 100 * c["correct"] / c["total"])

    logger.info("-" * 90)
    logger.info("MISMATCH CASES (%d)", len(mismatches))
    for m in mismatches:
        logger.info("  %s vs %s: expected %s, got %s (score %.1f)",
                     m["resume_id"], m["jd_id"], m["expected_zone"], m["ai_zone"], m["overall_score"])
        logger.info("    manual reasoning: %s", m["manual_reasoning"])
        logger.info("    ai explanation:   %s", m["ai_explanation"])
    logger.info("=" * 90)

    out = {
        "overall_accuracy_pct": overall_accuracy,
        "total_pairs": total,
        "correct": correct,
        "confusion_matrix": confusion,
        "metrics_by_zone": metrics,
        "accuracy_by_category": {k: {"correct": v["correct"], "total": v["total"],
                                       "pct": round(100 * v["correct"] / v["total"], 1)}
                                   for k, v in by_category.items()},
        "accuracy_by_experience_level": {k: {"correct": v["correct"], "total": v["total"],
                                               "pct": round(100 * v["correct"] / v["total"], 1)}
                                           for k, v in by_experience.items()},
        "mismatches": mismatches,
        "all_rows": rows,
    }
    out_path = OUT_DIR / "day17_ats_testing_report.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    logger.info("Structured report written to %s", out_path)
    return out


if __name__ == "__main__":
    run()
