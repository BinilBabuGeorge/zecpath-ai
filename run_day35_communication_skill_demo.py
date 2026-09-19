"""
Day 35 demo -- runs a full HR interview session through the
communication skill evaluation engine and writes:
  - logs/day35_communication_skill_run.log
  - data/results/day35_communication_skill_report.json

Deliberately includes ONE clearly strong answer, ONE clearly weak
answer (fillers, grammar errors, vague, unstructured), and remaining
answers of ordinary quality -- so the demo actually exercises score
differentiation, not just "everything scores fine."
"""

from __future__ import annotations

import json
import logging
import os

from parsers.hr_interview_question_bank import ExperienceLevel, InterviewSession, RoleType
from parsers.communication_skill_engine import build_interview_communication_profile

LOG_PATH = "logs/day35_communication_skill_run.log"
REPORT_PATH = "data/results/day35_communication_skill_report.json"

os.makedirs("logs", exist_ok=True)
os.makedirs("data/results", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, mode="w"), logging.StreamHandler()],
)
log = logging.getLogger("day35_demo")

RESPONSES = [
    # self_introduction -- strong: fluent, structured, concrete
    "First, I'll introduce myself. I'm a backend engineer with four years of experience, mostly in Python. "
    "For example, in my last role I led the migration of our payments service to a new queue system, which cut failed transactions significantly. "
    "As a result, I'm now looking for a role where I can keep owning end-to-end systems.",

    # career_journey -- weak: filler-heavy, vague, grammar error, unstructured
    "Um, so, like, I don't really know, it was, uh, you know, kind of okay I guess. He don't really explain the the process to me either.",

    # strengths_weaknesses -- ordinary: clean grammar, decent structure, but plain vocabulary
    "My biggest strength is that I finish what I start. My weakness is that I sometimes take on too much work at once.",

    # teamwork_culture_fit -- ordinary-to-strong: concrete, clear, slightly informal
    "I once resolved a disagreement between two teammates by listening to both sides first. Then I proposed a compromise that both agreed to. It worked out well.",
]

CATEGORY_QUALITY_NOTE = {
    0: "expected: strong",
    1: "expected: weak",
    2: "expected: ordinary",
    3: "expected: ordinary-to-strong",
}


def main() -> None:
    log.info("Starting Day 35 communication-skill demo session (experienced, technical).")
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)

    for i, response_text in enumerate(RESPONSES):
        q = session.current_question
        log.info("Submitting response for %s (category=%s, %s)", q.question_id, q.category, CATEGORY_QUALITY_NOTE[i])
        session.submit_response(response_text)

    log.info("All responses submitted. Building communication profile.")
    profile = build_interview_communication_profile(session)

    for e in profile.answer_evaluations:
        log.info(
            "Evaluated %s [%s]: score=%s reliability=%s (fluency=%s grammar=%s vocab=%s clarity=%s structure=%s filler_penalty=%s)",
            e.question_id, e.category, e.communication_score, e.sample_size_reliability,
            e.fluency.fluency_score, e.grammar.grammar_score, e.vocabulary.vocabulary_score,
            e.clarity.clarity_score, e.structure.structure_score, e.component_breakdown["filler_penalty"],
        )

    log.info("Overall communication score: %s", profile.overall_communication_score)
    log.info("Category scores: %s", profile.category_scores)
    log.info("Low-reliability answers: %s", profile.low_reliability_answer_count)

    # Sanity checks the demo itself verifies, not just claims:
    scores_by_index = [e.communication_score for e in profile.answer_evaluations]
    assert scores_by_index[0] > scores_by_index[1], "Strong answer (idx0) should outscore weak answer (idx1)."
    log.info("Sanity check passed: strong answer (%s) outscored weak answer (%s).", scores_by_index[0], scores_by_index[1])

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(profile.to_dict(), f, indent=2)
    log.info("Report written to %s", REPORT_PATH)


if __name__ == "__main__":
    main()
