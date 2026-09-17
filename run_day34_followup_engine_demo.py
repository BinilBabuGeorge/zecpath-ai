"""
Day 34 demo: runs one complete HR interview session where every answer
is deliberately engineered to a different quality tier -- vague, thin,
and confident -- so all three follow-up types (clarification, deepening,
example_based) fire at least once, plus the repetition cap and the
ineligible-category skip both get exercised for real.
"""

import json
import logging
from pathlib import Path

from parsers.hr_interview_question_bank import InterviewSession, ExperienceLevel, RoleType
from parsers.hr_followup_engine import process_response_with_follow_up

OUT_DIR = Path("data/results")
LOG_DIR = Path("logs")
OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "day34_followup_engine_run.log", mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("day34")

# (initial_answer, follow_up_answer) -- one pair per category, in
# CATEGORIES order (self_introduction, career_journey,
# strengths_weaknesses, teamwork_culture_fit, career_goals,
# availability_commitment). career_goals and availability_commitment
# are NOT follow-up eligible (Day 33 defaults), so their second slot
# is unused but harmless to provide.
ANSWER_PAIRS = [
    ("I really can't think of anything to say, nothing comes to mind.", "Okay -- I'm a computer science graduate excited about backend development."),  # vague -> clarification
    ("I did some coursework and a couple of small projects.", "For example, in my final year I built a full-stack app and once debugged a production issue during a demo."),  # thin -> deepening
    ("For instance, I once took full ownership of a failing project and turned it around within a month.", "not used"),  # confident -> example_based
    ("I worked with people on group projects sometimes.", "not used"),  # thin -> deepening
    ("I'd like to grow into a senior engineering role eventually.", "not used"),  # NOT follow-up eligible
    ("I can join within two weeks of an offer.", "not used"),  # NOT follow-up eligible
]


def main():
    logger.info("=" * 90)
    logger.info("DAY 34 -- Dynamic Follow-Up Logic demo")
    logger.info("=" * 90)

    session = InterviewSession.start(ExperienceLevel.FRESHER, RoleType.TECHNICAL)
    decisions_log = []

    for initial_answer, follow_up_answer in ANSWER_PAIRS:
        q = session.current_question
        logger.info("-" * 90)
        logger.info(f"[{q.phase.value}] {q.category} (follow_up_eligible={q.follow_up_eligible})")
        logger.info(f"  candidate: {initial_answer!r}")

        decision = process_response_with_follow_up(session, initial_answer)
        logger.info(f"  -> quality={decision.answer_quality.value}  should_follow_up={decision.should_follow_up}")
        logger.info(f"     reason: {decision.reason}")
        decisions_log.append(decision.to_dict())

        if decision.should_follow_up:
            logger.info(f"  AI follow-up ({decision.follow_up_type.value}): {decision.follow_up_text!r}")
            logger.info(f"  candidate (to follow-up): {follow_up_answer!r}")
            second_decision = process_response_with_follow_up(session, follow_up_answer)
            logger.info(f"  -> second attempt correctly capped: should_follow_up={second_decision.should_follow_up} ({second_decision.reason})")
            decisions_log.append(second_decision.to_dict())

        session.submit_response(initial_answer)

    logger.info("=" * 90)
    logger.info(f"Interview complete: {session.is_complete}")
    follow_up_types_used = [q.follow_up_type for q in session.questions if q.follow_up_type]
    logger.info(f"Follow-up types used across the interview: {follow_up_types_used}")
    logger.info(f"All three trigger types exercised: {set(follow_up_types_used) == {'clarification', 'deepening', 'example_based'}}")

    report = {
        "decisions": decisions_log,
        "follow_up_types_used": follow_up_types_used,
        "session_summary": [
            {"category": q.category, "follow_up_asked": q.follow_up_asked, "follow_up_type": q.follow_up_type, "follow_up_text": q.follow_up_text}
            for q in session.questions
        ],
    }
    out_path = OUT_DIR / "day34_followup_engine_report.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info(f"Report written to {out_path}")


if __name__ == "__main__":
    main()
