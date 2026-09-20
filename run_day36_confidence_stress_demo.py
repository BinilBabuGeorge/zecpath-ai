"""
Day 36 demo -- runs a full HR interview session through the
confidence & stress indicators engine and writes:
  - logs/day36_confidence_stress_run.log
  - data/results/day36_confidence_stress_report.json

Includes ONE calm/confident answer, ONE hesitant/stressed answer, and
a deliberate large sentiment swing between two answers to exercise the
cross-answer inconsistency flag -- not just "everything scores fine."
"""

from __future__ import annotations

import json
import logging
import os

from parsers.hr_interview_question_bank import ExperienceLevel, InterviewSession, RoleType
from parsers.confidence_stress_engine import build_confidence_profile

LOG_PATH = "logs/day36_confidence_stress_run.log"
REPORT_PATH = "data/results/day36_confidence_stress_report.json"

os.makedirs("logs", exist_ok=True)
os.makedirs("data/results", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, mode="w"), logging.StreamHandler()],
)
log = logging.getLogger("day36_demo")

RESPONSES = [
    # self_introduction -- calm, confident
    "I'm a backend engineer with four years of experience. I led the migration of our payments service and delivered it two weeks ahead of schedule.",

    # career_journey -- hesitant, uncertain, mildly stressed
    "Um, I think, uh, it was, I guess, kind of a hard time. I I was probably not sure what to do, honestly, it was frustrating.",

    # strengths_weaknesses -- strong positive sentiment (sets up the swing)
    "I'm genuinely excited and proud of how I handle challenges -- I love a good problem and feel confident tackling new things.",

    # teamwork_culture_fit -- strong negative sentiment right after (large swing)
    "Honestly it was difficult. I struggled, was frustrated, and felt pretty worried and afraid I'd let the team down.",
]

CATEGORY_NOTE = {
    0: "expected: calm/confident",
    1: "expected: hesitant/stressed",
    2: "expected: strong positive (swing setup)",
    3: "expected: strong negative (large swing from previous answer)",
}


def main() -> None:
    log.info("Starting Day 36 confidence & stress demo session (experienced, technical).")
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)

    for i, response_text in enumerate(RESPONSES):
        q = session.current_question
        log.info("Submitting response for %s (category=%s, %s)", q.question_id, q.category, CATEGORY_NOTE[i])
        session.submit_response(response_text)

    log.info("All responses submitted. Building confidence & stress profile.")
    profile = build_confidence_profile(session)

    for e in profile.answer_evaluations:
        log.info(
            "Evaluated %s [%s]: confidence=%s stress=%s sentiment=%s mixed_sentiment=%s "
            "(hesitation_rate=%s uncertainty_rate=%s repeated_words=%s)",
            e.question_id, e.category, e.behavioral_confidence_score, e.stress.stress_score,
            e.sentiment.label, e.mixed_sentiment_flag,
            e.hesitation_patterns.hesitation.hesitation_rate_per_100_words,
            e.hesitation_patterns.uncertainty.uncertainty_rate_per_100_words,
            len(e.hesitation_patterns.repeated_word_pairs),
        )

    log.info("Overall behavioral confidence score: %s", profile.overall_behavioral_confidence_score)
    log.info("Overall stress score: %s", profile.overall_stress_score)
    log.info("Cross-answer swings flagged: %s", profile.inconsistency_flags.cross_answer_swings)

    # Sanity checks the demo itself verifies, not just claims:
    scores = [e.behavioral_confidence_score for e in profile.answer_evaluations]
    assert scores[0] > scores[1], "Calm answer (idx0) should outscore hesitant answer (idx1) on confidence."
    log.info("Sanity check passed: calm answer (%s) outscored hesitant answer (%s).", scores[0], scores[1])
    assert len(profile.inconsistency_flags.cross_answer_swings) >= 1, "Expected the deliberate sentiment swing (idx2->idx3) to be flagged."
    log.info("Sanity check passed: deliberate sentiment swing (idx2->idx3) was flagged: %s", profile.inconsistency_flags.cross_answer_swings)

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(profile.to_dict(), f, indent=2)
    log.info("Report written to %s", REPORT_PATH)


if __name__ == "__main__":
    main()
