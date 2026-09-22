"""
Day 37 demo -- runs a full HR interview session through the scoring
engine and writes:
  - logs/day37_hr_scoring_run.log
  - data/results/day37_hr_scoring_report.json

Includes a strong answer, a weak/hesitant answer, and a deliberate
sentiment swing -- so the demo exercises every scoring parameter
(relevance, communication, confidence, consistency), not just the
happy path. Also demonstrates the configurable weight system by
scoring the same session twice with different weights.
"""

from __future__ import annotations

import json
import logging
import os

from parsers.hr_interview_question_bank import ExperienceLevel, InterviewSession, RoleType
from parsers.hr_interview_scoring_engine import WeightConfig, score_hr_interview

LOG_PATH = "logs/day37_hr_scoring_run.log"
REPORT_PATH = "data/results/day37_hr_scoring_report.json"

os.makedirs("logs", exist_ok=True)
os.makedirs("data/results", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, mode="w"), logging.StreamHandler()],
)
log = logging.getLogger("day37_demo")

RESPONSES = [
    "For example, in my last role I led the migration of our payments service to a new queue system, "
    "which cut failed transactions significantly. I delivered it two weeks ahead of schedule.",

    "Um, I think, uh, it was, I guess, kind of a hard time. I I was probably not sure what to do, honestly, it was frustrating.",

    "I'm genuinely excited and proud of how I handle challenges -- I love a good problem and feel confident tackling new things.",

    "Honestly it was difficult. I struggled, was frustrated, and felt pretty worried and afraid I'd let the team down.",
]


def main() -> None:
    log.info("Starting Day 37 HR interview scoring demo session (experienced, technical).")
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)
    for i, text in enumerate(RESPONSES):
        q = session.current_question
        log.info("Submitting response for %s (category=%s)", q.question_id, q.category)
        session.submit_response(text)

    log.info("All responses submitted. Scoring with default weights.")
    default_report = score_hr_interview(session)
    log.info("Default weights: %s", vars(default_report.weights_used))
    log.info("Overall HR score (default weights): %s", default_report.overall_hr_score)
    log.info("Component averages: relevance=%s communication=%s confidence=%s",
              default_report.avg_relevance, default_report.avg_communication, default_report.avg_confidence)
    log.info("Consistency: issue_rate=%s penalty=%s findings=%s",
              default_report.consistency.issue_rate, default_report.consistency.consistency_penalty, default_report.consistency.findings)

    for a in default_report.answer_breakdowns:
        log.info(
            "  [%s] %s: relevance=%s (%s) communication=%s confidence=%s -> weighted=%s",
            a.question_id, a.category, a.relevance_score, a.relevance_quality,
            a.communication_score, a.confidence_score, a.weighted_positive_component,
        )

    # Demonstrate the configurable weight system: re-score the SAME
    # session with relevance weighted much more heavily.
    relevance_heavy_weights = WeightConfig(relevance=0.7, communication=0.1, confidence=0.1, consistency=0.1)
    relevance_heavy_report = score_hr_interview(session, weights=relevance_heavy_weights)
    log.info("Re-scored with relevance-heavy weights: %s", vars(relevance_heavy_weights))
    log.info("Overall HR score (relevance-heavy weights): %s", relevance_heavy_report.overall_hr_score)

    # Sanity checks the demo itself verifies, not just claims:
    assert default_report.overall_hr_score != relevance_heavy_report.overall_hr_score, "Different weights should produce a different overall score."
    log.info("Sanity check passed: default weights (%s) and relevance-heavy weights (%s) produced different scores.",
              default_report.overall_hr_score, relevance_heavy_report.overall_hr_score)
    assert default_report.consistency.consistency_penalty > 0.0, "Expected the deliberate sentiment swing to produce a nonzero consistency penalty."
    log.info("Sanity check passed: deliberate sentiment swing produced a nonzero consistency penalty (%s).", default_report.consistency.consistency_penalty)

    print()
    print(default_report.to_summary_text())

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "default_weights_report": default_report.to_dict(),
            "relevance_heavy_weights_report": relevance_heavy_report.to_dict(),
        }, f, indent=2)
    log.info("Report written to %s", REPORT_PATH)


if __name__ == "__main__":
    main()
