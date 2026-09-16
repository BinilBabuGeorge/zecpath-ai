"""
Day 33 demo: generates the full HR interview question set for all four
experience-level x role-type combinations (proving the role-based
generator genuinely differentiates where it should and stays identical
where it shouldn't), then runs one complete InterviewSession end to
end -- including a recorded follow-up on an eligible question and a
correctly-rejected follow-up attempt on an ineligible one.
"""

import json
import logging
from pathlib import Path

from parsers.hr_interview_question_bank import (
    ExperienceLevel, RoleType, InterviewPhase, generate_hr_interview_questions, InterviewSession,
)

OUT_DIR = Path("data/results")
LOG_DIR = Path("logs")
OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "day33_hr_interview_design_run.log", mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("day33")


def main():
    logger.info("=" * 90)
    logger.info("DAY 33 -- HR Interview Engine Design demo")
    logger.info("=" * 90)

    all_combinations = {}
    for exp in (ExperienceLevel.FRESHER, ExperienceLevel.EXPERIENCED):
        for role in (RoleType.TECHNICAL, RoleType.NON_TECHNICAL):
            key = f"{exp.value}_{role.value}"
            qs = generate_hr_interview_questions(exp, role)
            all_combinations[key] = [
                {"id": q.id, "category": q.category, "phase": q.phase.value, "text": q.text, "follow_up_eligible": q.follow_up_eligible}
                for q in qs
            ]
            logger.info("-" * 90)
            logger.info(f"COMBINATION: {key}")
            for q in qs:
                logger.info(f"  [{q.phase.value:22s}] {q.category:22s} follow_up={str(q.follow_up_eligible):5s} -- {q.text}")

    logger.info("=" * 90)
    logger.info("Verifying role-based differentiation is genuine, not padded:")
    career_journey_texts = {v[1]["text"] for v in all_combinations.values()}
    teamwork_texts_by_exp = {
        "fresher": all_combinations["fresher_technical"][3]["text"],
        "experienced": all_combinations["experienced_technical"][3]["text"],
    }
    logger.info(f"  career_journey: {len(career_journey_texts)} distinct texts across 4 combinations (expect 4)")
    logger.info(f"  teamwork_culture_fit differs by experience level: {teamwork_texts_by_exp['fresher'] != teamwork_texts_by_exp['experienced']}")
    logger.info(f"  self_introduction identical across all combinations: "
                 f"{len({v[0]['text'] for v in all_combinations.values()}) == 1}")

    logger.info("=" * 90)
    logger.info("Running one complete InterviewSession (fresher / technical):")
    session = InterviewSession.start(ExperienceLevel.FRESHER, RoleType.TECHNICAL)
    sample_answers = [
        "Hi, I'm a computer science graduate who just finished my degree, excited about backend development.",
        "I built a full-stack project for my final year and interned for two months doing API work.",
        "I'd say my strength is picking up new frameworks quickly; I'm working on my public speaking.",
        "In my final year project, we split the work across three people and I owned the backend.",
        "I'd like to grow into a backend specialist over the next few years.",
        "I'm very committed and can join within two weeks of an offer.",
    ]
    for answer in sample_answers:
        q = session.current_question
        logger.info(f"  [{q.phase.value}] {q.category}: answered.")
        session.submit_response(answer)
    logger.info(f"Session complete: {session.is_complete}")

    # Demonstrate the follow-up bookkeeping the state structure supports.
    intro_state = session.questions[0]
    intro_state.record_follow_up("What made you specifically interested in backend development?")
    logger.info(f"Follow-up recorded on '{intro_state.category}': {intro_state.follow_up_text!r}")

    goals_state = next(q for q in session.questions if q.category == "career_goals")
    try:
        goals_state.record_follow_up("This should be rejected.")
    except ValueError as e:
        logger.info(f"Follow-up correctly rejected on '{goals_state.category}' (not eligible): {e}")

    report = {
        "all_combinations": all_combinations,
        "session_demo": {
            "experience_level": session.experience_level.value,
            "role_type": session.role_type.value,
            "is_complete": session.is_complete,
            "questions": [
                {
                    "question_id": q.question_id, "category": q.category, "phase": q.phase.value,
                    "response_text": q.response_text, "follow_up_eligible": q.follow_up_eligible,
                    "follow_up_asked": q.follow_up_asked, "follow_up_text": q.follow_up_text,
                }
                for q in session.questions
            ],
        },
    }
    out_path = OUT_DIR / "day33_hr_interview_design_report.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info("=" * 90)
    logger.info(f"Report written to {out_path}")


if __name__ == "__main__":
    main()
