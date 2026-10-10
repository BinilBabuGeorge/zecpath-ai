"""
Day 45 live demo -- candidate interview simulation -> scoring
breakdown -> final hiring recommendation, end to end.

HONEST ABOUT WHAT'S LIVE AND WHAT'S REPRESENTATIVE (same environment
constraint as Days 41-44): the interview session, the demographic
scrubbing, and the follow-up decisions below are REAL -- computed by
running this project's actual Day 33/34/43/45 code. The communication,
confidence, and HR-interview-composite scores are REPRESENTATIVE
numbers, standing in for Day 35/36/37's engines, which this build
environment doesn't have local source for (see
docs/day45_manager_evaluation_feedback.md). The unified score and
final decision ARE live -- Day 41's real compute_unified_score(),
run on those three numbers (two representative, one real-labeled-as-
such) exactly as it would run on real ones.

Writes:
  - logs/day45_hr_interview_demo_run.log
  - data/results/day45_demo_dataset.json
"""

from __future__ import annotations

import json
import logging
import os

from parsers.hr_interview_question_bank import InterviewSession, ExperienceLevel, RoleType
from parsers.hr_interview_finalization import submit_scrubbed_response
from parsers.unified_scoring_engine import RoundScores, compute_unified_score

LOG_PATH = "logs/day45_hr_interview_demo_run.log"
REPORT_PATH = "data/results/day45_demo_dataset.json"

os.makedirs("logs", exist_ok=True)
os.makedirs("data/results", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, mode="w"), logging.StreamHandler()],
)
log = logging.getLogger("day45_demo")

# One deliberate demographic disclosure included, to demonstrate the
# scrubber actually firing inside a real interview flow, not just in isolation.
CANDIDATE_ANSWERS = [
    "For example, I led the migration project and delivered it two weeks ahead of schedule. "
    "I'm a single mother, so I've gotten very good at managing my time efficiently.",
    "I steadily grew from junior to senior engineer over four years, taking on more ownership each year.",
    "My strength is ownership; my weakness is I sometimes take on too much at once.",
    "For example, I resolved a conflict between two teammates by listening to both sides and proposing a compromise.",
    "For example, I want to grow into a tech lead role where I can mentor others and own architecture decisions.",
    "I'm available to start within two weeks of an offer and can work the standard team hours.",
]

# Representative scores standing in for Day 35 (communication), Day 36
# (confidence), and Day 37 (combined HR score) -- see module docstring.
REPRESENTATIVE_HR_INTERVIEW_SCORE = 85.8   # stands in for Day 37's overall_hr_score
REPRESENTATIVE_ATS_SCORE = 82.0
REPRESENTATIVE_SCREENING_SCORE = 74.0


def main() -> None:
    log.info("=" * 70)
    log.info("Day 45 LIVE DEMO: candidate interview simulation -> scoring -> recommendation")
    log.info("=" * 70)

    # --- Stage 1: candidate interview simulation (REAL) ---
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)
    log.info("Session started: experience=%s role=%s, %d questions queued.", session.experience_level.value, session.role_type.value, len(session.questions))

    demo_record = {"interview": [], "scoring_breakdown": {}, "final_recommendation": {}}

    for answer in CANDIDATE_ANSWERS:
        q = session.current_question
        log.info("-" * 70)
        log.info("Question [%s / %s]: (prompting candidate)", q.question_id, q.category)
        result = submit_scrubbed_response(session, answer)
        log.info("Candidate answered. Demographic categories scrubbed: %s", result.categories_detected or "none")
        log.info("Stored (post-scrub) text: %s", result.question.response_text)
        if result.follow_up and result.follow_up.should_follow_up:
            log.info("Follow-up triggered: [%s] %s", result.follow_up.follow_up_type.value, result.follow_up.follow_up_text)
        else:
            log.info("No follow-up needed (answer_quality=%s).", result.follow_up.answer_quality.value if result.follow_up else "n/a")

        demo_record["interview"].append({
            "question_id": q.question_id, "category": q.category,
            "stored_text": result.question.response_text,
            "demographic_categories_scrubbed": result.categories_detected,
            "follow_up_triggered": bool(result.follow_up and result.follow_up.should_follow_up),
            "answer_quality": result.follow_up.answer_quality.value if result.follow_up else None,
        })

    assert session.is_complete, "Demo interview should be complete after answering every queued question."
    log.info("-" * 70)
    log.info("Interview complete. Sanity check passed: session.is_complete is True.")

    # Confirm the demographic disclosure never made it into permanent storage.
    stored_texts = " ".join(q.response_text for q in session.questions)
    assert "single mother" not in stored_texts.lower(), "Demographic disclosure should have been scrubbed before storage."
    log.info("Sanity check passed: the demographic disclosure does not appear anywhere in stored session data.")

    # --- Stage 2: scoring breakdown ---
    log.info("=" * 70)
    log.info("SCORING BREAKDOWN")
    log.info("HR interview composite score: %s (representative -- see module docstring; Day 37 engine not present in this build environment)", REPRESENTATIVE_HR_INTERVIEW_SCORE)
    log.info("ATS score: %s (representative)", REPRESENTATIVE_ATS_SCORE)
    log.info("Screening score: %s (representative)", REPRESENTATIVE_SCREENING_SCORE)
    demo_record["scoring_breakdown"] = {
        "hr_interview_score": REPRESENTATIVE_HR_INTERVIEW_SCORE, "hr_interview_score_is_representative": True,
        "ats_score": REPRESENTATIVE_ATS_SCORE, "ats_score_is_representative": True,
        "screening_score": REPRESENTATIVE_SCREENING_SCORE, "screening_score_is_representative": True,
    }

    # --- Stage 3: final hiring recommendation (REAL -- Day 41's actual engine) ---
    log.info("=" * 70)
    log.info("FINAL HIRING RECOMMENDATION (live computation, Day 41's compute_unified_score)")
    round_scores = RoundScores(
        ats_score=REPRESENTATIVE_ATS_SCORE, screening_score=REPRESENTATIVE_SCREENING_SCORE,
        hr_interview_score=REPRESENTATIVE_HR_INTERVIEW_SCORE,
    )
    unified = compute_unified_score(round_scores, role_type=RoleType.TECHNICAL, candidate_id="DEMO-CANDIDATE-001")
    log.info(unified.to_summary_text().replace("\n", " | "))
    print()
    print(unified.to_summary_text())

    assert unified.decision in ("selected", "hold", "rejected")
    log.info("Sanity check passed: final recommendation is a valid decision (%s).", unified.decision)

    demo_record["final_recommendation"] = unified.to_dict()

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(demo_record, f, indent=2)
    log.info("Demo dataset written to %s", REPORT_PATH)


if __name__ == "__main__":
    main()
