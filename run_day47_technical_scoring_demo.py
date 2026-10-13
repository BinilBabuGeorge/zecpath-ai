"""
Day 47 demo -- runs a full technical interview session (Java,
advanced tier) through the new scoring engine with a mix of a deep,
grounded answer, a moderate textbook-style answer, and a shallow
non-answer, to show real score differentiation. Writes:
  - logs/day47_technical_scoring_run.log
  - data/results/day47_technical_scoring_report.json
"""

from __future__ import annotations

import json
import logging
import os

from parsers.technical_interview_question_bank import TechnicalDomain, TechnicalInterviewSession
from parsers.technical_skill_scoring_engine import build_technical_evaluation_report

LOG_PATH = "logs/day47_technical_scoring_run.log"
REPORT_PATH = "data/results/day47_technical_scoring_report.json"

os.makedirs("logs", exist_ok=True)
os.makedirs("data/results", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, mode="w"), logging.StreamHandler()],
)
log = logging.getLogger("day47_demo")

# intro, experience-based, 2 conceptual (advanced Java), 1 scenario (advanced Java)
ANSWERS = [
    "I've been working with backend systems for about eight years now, mostly in Java.",
    "I led the redesign of a payments processing service that needed strict consistency guarantees.",
    # Deep, grounded conceptual answer:
    "A thread-safe singleton can use double-checked locking with a synchronized block, because that avoids "
    "the overhead of synchronizing on every call. An enum singleton is often simpler and inherently thread-safe. "
    "In my last project, we chose eager initialization since the singleton was lightweight and always needed.",
    # Moderate, textbook conceptual answer:
    "The JVM heap stores objects, the stack stores method calls and local variables, and metaspace stores class metadata.",
    # Shallow scenario answer:
    "I'd probably just look into it and figure out what's wrong.",
]

EXPECTED_NOTE = {2: "expected: deep", 3: "expected: moderate", 4: "expected: shallow"}


def main() -> None:
    log.info("Starting Day 47 technical scoring demo (Java, advanced tier).")
    session = TechnicalInterviewSession.start(TechnicalDomain.JAVA, 8)
    log.info("Session tier selected: %s", session.tier.value)

    for i, answer in enumerate(ANSWERS):
        q = session.current_question
        note = EXPECTED_NOTE.get(i, "")
        log.info("Submitting answer for [%s] %s %s", q.phase.value, q.question.question_id, f"({note})" if note else "")
        session.submit_response(answer)

    report = build_technical_evaluation_report(session)

    for e in report.answer_evaluations:
        log.info(
            "Evaluated %s: overall=%s (%s) accuracy=%s depth=%s reasoning=%s real_world=%s",
            e.question_id, e.overall_technical_score, e.classification.value,
            e.accuracy.accuracy_score, e.depth.depth_score, e.logical_reasoning.logical_reasoning_score, e.real_world.real_world_score,
        )

    log.info("Overall technical score: %s", report.overall_score)
    log.info("Skill breakdown: %s", report.skill_breakdown)

    # Sanity checks the demo itself verifies, not just claims:
    scores_by_id = {e.question_id: e.overall_technical_score for e in report.answer_evaluations}
    conceptual_scores = [scores_by_id[e.question_id] for e in report.answer_evaluations if e.question_id.endswith("c01") or e.question_id.endswith("c02")]
    scenario_scores = [scores_by_id[e.question_id] for e in report.answer_evaluations if "s01" in e.question_id]
    assert max(conceptual_scores) > min(scenario_scores), "The deep conceptual answer should outscore the shallow scenario answer."
    log.info("Sanity check passed: deep answer (%s) outscored shallow answer (%s).", max(conceptual_scores), min(scenario_scores))

    classifications = {e.classification.value for e in report.answer_evaluations}
    assert len(classifications) >= 2, "Expected more than one shallow/moderate/deep classification across these deliberately varied answers."
    log.info("Sanity check passed: multiple classifications represented (%s), not all answers lumped into one band.", classifications)

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2)
    log.info("Report written to %s", REPORT_PATH)


if __name__ == "__main__":
    main()
