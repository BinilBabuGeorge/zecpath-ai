"""
Runs section_classifier.py against every labeled resume in
data/labeled_resumes/, compares the result to the independently-authored
ground truth in data/ground_truth/, and computes:
  - overall line-level accuracy
  - per-section precision / recall / F1
  - per-resume accuracy (to see which edge cases are hardest)

Writes a summary to logs/accuracy_report.log and predictions to
data/predictions/ for manual inspection.
"""

import json
import logging
from collections import defaultdict
from pathlib import Path

from parsers.section_classifier import classify_resume, TARGET_SECTIONS

RESUME_DIR = Path("data/labeled_resumes")
GROUND_TRUTH_DIR = Path("data/ground_truth")
PREDICTIONS_DIR = Path("data/predictions")
LOG_DIR = Path("logs")

PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "accuracy_report.log", mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("accuracy")

ALL_LABELS = TARGET_SECTIONS + ["Other"]


def evaluate():
    resume_files = sorted(RESUME_DIR.glob("*.txt"))
    logger.info("=" * 70)
    logger.info("SECTION CLASSIFIER ACCURACY REPORT")
    logger.info("=" * 70)
    logger.info("Resumes evaluated: %d\n", len(resume_files))

    # Confusion counts for precision/recall: {label: {"tp":.., "fp":.., "fn":..}}
    confusion = {label: {"tp": 0, "fp": 0, "fn": 0} for label in ALL_LABELS}

    total_lines = 0
    total_correct = 0
    per_resume_results = []

    for resume_path in resume_files:
        name = resume_path.stem
        gt_path = GROUND_TRUTH_DIR / f"{name}.json"
        if not gt_path.exists():
            logger.warning("SKIP %s -- no ground truth file found", name)
            continue

        ground_truth = json.loads(gt_path.read_text())
        raw_text = resume_path.read_text(encoding="utf-8")
        predicted = classify_resume(raw_text)

        predictions_out = [{"line": p.line, "predicted": p.section, "method": p.method} for p in predicted]
        (PREDICTIONS_DIR / f"{name}.json").write_text(json.dumps(predictions_out, indent=2), encoding="utf-8")

        if len(predicted) != len(ground_truth):
            logger.warning(
                "%s -- line count mismatch: predicted %d, ground truth %d (comparing by min length)",
                name, len(predicted), len(ground_truth),
            )

        n = min(len(predicted), len(ground_truth))
        resume_correct = 0
        for i in range(n):
            pred_label = predicted[i].section
            true_label = ground_truth[i]["section"]

            if pred_label == true_label:
                confusion[true_label]["tp"] += 1
                resume_correct += 1
            else:
                confusion[pred_label]["fp"] += 1
                confusion[true_label]["fn"] += 1

        total_lines += n
        total_correct += resume_correct
        accuracy = 100 * resume_correct / n if n else 0
        per_resume_results.append((name, resume_correct, n, accuracy))
        logger.info("%-38s %2d/%2d correct  (%.1f%%)", name, resume_correct, n, accuracy)

    logger.info("")
    logger.info("-" * 70)
    logger.info("OVERALL LINE-LEVEL ACCURACY: %d/%d = %.1f%%", total_correct, total_lines,
                 100 * total_correct / total_lines if total_lines else 0)
    logger.info("-" * 70)
    logger.info("")
    logger.info("%-16s %8s %8s %8s %10s", "Section", "TP", "FP", "FN", "F1")
    for label in ALL_LABELS:
        c = confusion[label]
        precision = c["tp"] / (c["tp"] + c["fp"]) if (c["tp"] + c["fp"]) else 0
        recall = c["tp"] / (c["tp"] + c["fn"]) if (c["tp"] + c["fn"]) else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0
        logger.info("%-16s %8d %8d %8d %9.1f%%", label, c["tp"], c["fp"], c["fn"], f1 * 100)

    logger.info("")
    logger.info("Hardest cases (lowest per-resume accuracy):")
    for name, correct, n, acc in sorted(per_resume_results, key=lambda r: r[3]):
        logger.info("  %-38s %.1f%%", name, acc)


if __name__ == "__main__":
    evaluate()
