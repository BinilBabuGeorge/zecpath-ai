"""
Runs the semantic matcher across every resume x JD pair (10 x 4 = 40
pairs), compares against a hand-labeled ground truth of which pairs
SHOULD be considered matches, and tunes the classification threshold to
maximize accuracy against that ground truth.
"""

import json
import logging
from pathlib import Path

from parsers.section_extractor import extract_resume_sections, extract_jd_sections
from parsers.semantic_matcher import SemanticMatcher, compare_resume_to_jd, classify_score

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
        logging.FileHandler(LOG_DIR / "matching_run.log", mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("semantic_matching")

# Ground truth: which (resume, jd) pairs are genuine matches.
# jd_03 is a differently-worded duplicate of jd_01's role (MERN dev),
# jd_04 is a differently-worded duplicate of jd_02's role (Sales exec) --
# both carried over from Day 6 specifically to test whether the matcher
# still recognizes the SAME underlying role despite different wording.
GROUND_TRUTH_MATCHES = {
    ("resume_01_mern_developer", "jd_01_mern_developer"),
    ("resume_01_mern_developer", "jd_03_frontend_engineer_mern"),
    ("resume_03_sales_executive", "jd_02_sales_executive"),
    ("resume_03_sales_executive", "jd_04_business_development_executive"),
}


def compute_all_scores(matcher, thresholds):
    resume_files = sorted(RESUME_DIR.glob("*.txt"))
    jd_files = sorted(JD_DIR.glob("*.txt"))

    results = []
    for resume_path in resume_files:
        resume_sections = extract_resume_sections(resume_path.read_text())
        for jd_path in jd_files:
            jd_sections = extract_jd_sections(jd_path.read_text())
            result = compare_resume_to_jd(resume_sections, jd_sections, matcher, thresholds)
            is_ground_truth_match = (resume_path.stem, jd_path.stem) in GROUND_TRUTH_MATCHES
            results.append({
                "resume": resume_path.stem,
                "jd": jd_path.stem,
                "overall_score": result.overall_score,
                "component_scores": result.component_scores,
                "classification": result.classification,
                "ground_truth_match": is_ground_truth_match,
            })
    return results


def tune_threshold(matcher):
    """Sweep candidate 'strong match' thresholds and pick the one that
    maximizes accuracy against ground truth (predicting a match if
    overall_score >= threshold)."""
    resume_files = sorted(RESUME_DIR.glob("*.txt"))
    jd_files = sorted(JD_DIR.glob("*.txt"))

    raw_scores = []
    for resume_path in resume_files:
        resume_sections = extract_resume_sections(resume_path.read_text())
        for jd_path in jd_files:
            jd_sections = extract_jd_sections(jd_path.read_text())
            score = compare_resume_to_jd(resume_sections, jd_sections, matcher, {"strong": 1.0, "moderate": 1.0}).overall_score
            is_match = (resume_path.stem, jd_path.stem) in GROUND_TRUTH_MATCHES
            raw_scores.append((score, is_match))

    candidate_thresholds = sorted(set(round(s, 4) for s, _ in raw_scores))
    best_threshold, best_accuracy = 0.0, 0.0

    for t in candidate_thresholds:
        correct = sum(1 for s, is_match in raw_scores if (s >= t) == is_match)
        accuracy = correct / len(raw_scores)
        if accuracy > best_accuracy:
            best_accuracy = accuracy
            best_threshold = t

    return best_threshold, best_accuracy, raw_scores


def run():
    resume_files = sorted(RESUME_DIR.glob("*.txt"))
    jd_files = sorted(JD_DIR.glob("*.txt"))
    corpus = [f.read_text() for f in resume_files + jd_files]
    matcher = SemanticMatcher(corpus)

    logger.info("=" * 70)
    logger.info("THRESHOLD TUNING")
    logger.info("=" * 70)
    best_threshold, best_accuracy, raw_scores = tune_threshold(matcher)
    logger.info("Best 'strong match' threshold found: %.4f (accuracy: %.1f%%)", best_threshold, best_accuracy * 100)

    moderate_threshold = round(best_threshold * 0.5, 4)
    thresholds = {"strong": best_threshold, "moderate": moderate_threshold}
    logger.info("Using thresholds: strong >= %.4f, moderate >= %.4f", thresholds["strong"], thresholds["moderate"])

    logger.info("")
    logger.info("=" * 70)
    logger.info("FULL SIMILARITY MATRIX (%d resumes x %d JDs = %d pairs)", len(resume_files), len(jd_files), len(resume_files) * len(jd_files))
    logger.info("=" * 70)

    results = compute_all_scores(matcher, thresholds)
    (OUT_DIR / "similarity_matrix.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    tp = fp = tn = fn = 0
    for r in results:
        predicted_match = r["overall_score"] >= thresholds["strong"]
        actual_match = r["ground_truth_match"]
        marker = "MATCH " if predicted_match else "      "
        gt_marker = "(ground truth: MATCH)" if actual_match else ""
        logger.info("%-28s vs %-32s  score=%.4f  %s%s", r["resume"], r["jd"], r["overall_score"], marker, gt_marker)

        if predicted_match and actual_match:
            tp += 1
        elif predicted_match and not actual_match:
            fp += 1
        elif not predicted_match and actual_match:
            fn += 1
        else:
            tn += 1

    logger.info("")
    logger.info("=" * 70)
    logger.info("ACCURACY REPORT (threshold = %.4f)", thresholds["strong"])
    logger.info("=" * 70)
    total = tp + fp + tn + fn
    accuracy = (tp + tn) / total
    precision = tp / (tp + fp) if (tp + fp) else 0
    recall = tp / (tp + fn) if (tp + fn) else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0

    logger.info("True Positives:  %d  (correctly predicted match)", tp)
    logger.info("False Positives: %d  (wrongly predicted match)", fp)
    logger.info("True Negatives:  %d  (correctly predicted no match)", tn)
    logger.info("False Negatives: %d  (missed an actual match)", fn)
    logger.info("")
    logger.info("Accuracy:  %.1f%%  (%d/%d pairs classified correctly)", accuracy * 100, tp + tn, total)
    logger.info("Precision: %.1f%%", precision * 100)
    logger.info("Recall:    %.1f%%", recall * 100)
    logger.info("F1 Score:  %.1f%%", f1 * 100)

    summary = {
        "threshold_used": thresholds["strong"],
        "true_positives": tp, "false_positives": fp,
        "true_negatives": tn, "false_negatives": fn,
        "accuracy": round(accuracy * 100, 1),
        "precision": round(precision * 100, 1),
        "recall": round(recall * 100, 1),
        "f1_score": round(f1 * 100, 1),
    }
    (OUT_DIR / "accuracy_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logger.info("\nDone. Results written to %s/", OUT_DIR)


if __name__ == "__main__":
    run()
