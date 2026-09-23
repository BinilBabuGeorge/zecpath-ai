"""
Day 38 demo -- runs a full aptitude session (3 logical-reasoning +
3 situational-judgment questions) through the scoring engine and writes:
  - logs/day38_aptitude_logic_run.log
  - data/results/day38_aptitude_logic_report.json

Includes a mix of strong, partial, and weak/vague answers so the demo
exercises real score differentiation, not just the happy path.
"""

from __future__ import annotations

import json
import logging
import os

from parsers.aptitude_logic_engine import AptitudeSession, build_aptitude_profile

LOG_PATH = "logs/day38_aptitude_logic_run.log"
REPORT_PATH = "data/results/day38_aptitude_logic_report.json"

os.makedirs("logs", exist_ok=True)
os.makedirs("data/results", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, mode="w"), logging.StreamHandler()],
)
log = logging.getLogger("day38_demo")

RESPONSES = [
    # apt-lr01 -- strong
    "Since all labels are wrong, I would pick one fruit from the box labeled Mixed. Whatever "
    "fruit I draw tells me its true contents, so I can then deduce the other two boxes and "
    "relabel everything correctly.",

    # apt-lr02 -- strong
    "First take the chicken across, because leaving it with the fox is unsafe. Then go back "
    "alone. Bring the grain across next since the fox and grain are safe together. Then bring "
    "the chicken back so it doesn't eat the grain, take the fox across, and finally return for the chicken.",

    # apt-lr03 -- weak/vague
    "I'm not sure, maybe yes, hard to say.",

    # apt-sj01 -- strong
    "For example, I would talk to them privately to understand why they are missing deadlines, "
    "and offer to help if they are stuck. If it continues after that, I would escalate to the manager.",

    # apt-sj02 -- partial
    "I would explain my concern about the risk.",

    # apt-sj03 -- weak/vague
    "Honestly, nothing comes to mind, I'm not sure.",
]

EXPECTED_NOTE = {
    0: "expected: strong", 1: "expected: strong", 2: "expected: weak/vague",
    3: "expected: strong", 4: "expected: partial", 5: "expected: weak/vague",
}


def main() -> None:
    log.info("Starting Day 38 aptitude logic demo session.")
    session = AptitudeSession.start()

    for i, text in enumerate(RESPONSES):
        q = session.current_question.question
        log.info("Submitting response for %s (type=%s, %s)", q.question_id, q.question_type.value, EXPECTED_NOTE[i])
        session.submit_response(text)

    log.info("All responses submitted. Building aptitude profile.")
    profile = build_aptitude_profile(session)

    for e in profile.answer_evaluations:
        log.info(
            "Evaluated %s [%s]: overall=%s reasoning=%s (coverage=%s, matched=%d/%d) clarity=%s",
            e.question_id, e.question_type, e.overall_aptitude_score, e.reasoning.logical_reasoning_score,
            e.reasoning.coverage_ratio, len(e.reasoning.matched_elements),
            len(e.reasoning.matched_elements) + len(e.reasoning.missing_elements), e.clarity.clarity_score,
        )

    log.info("Overall aptitude score: %s", profile.overall_aptitude_score)
    log.info("Logical reasoning avg: %s", profile.logical_reasoning_avg)
    log.info("Situational judgment avg: %s", profile.situational_judgment_avg)

    # Sanity checks the demo itself verifies, not just claims:
    scores_by_id = {e.question_id: e.overall_aptitude_score for e in profile.answer_evaluations}
    assert scores_by_id["apt-lr01"] > scores_by_id["apt-lr03"], "Strong logical-reasoning answer should outscore the weak/vague one."
    log.info("Sanity check passed: strong apt-lr01 (%s) outscored weak apt-lr03 (%s).", scores_by_id["apt-lr01"], scores_by_id["apt-lr03"])
    assert scores_by_id["apt-sj01"] > scores_by_id["apt-sj03"], "Strong situational-judgment answer should outscore the weak/vague one."
    log.info("Sanity check passed: strong apt-sj01 (%s) outscored weak apt-sj03 (%s).", scores_by_id["apt-sj01"], scores_by_id["apt-sj03"])

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(profile.to_dict(), f, indent=2)
    log.info("Report written to %s", REPORT_PATH)


if __name__ == "__main__":
    main()
