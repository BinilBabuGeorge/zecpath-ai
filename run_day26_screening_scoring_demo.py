"""
Day 26 demo: runs score_screening_call() over one candidate's full set
of screening answers (Day 25's understand_answer() output) and writes
a structured JSON report plus a full run log.

The candidate's answers below are hand-written, clearly-labeled
examples standing in for a real screening call's Day 25 output -- not
real candidate speech -- same honesty stance as every prior demo
script. Deliberately includes one genuine experience-years conflict
(t000 says three years, t004 says eight) so the consistency
cross-check has something real to catch and penalize, not just a
clean pass-through.
"""

import json
import logging
from pathlib import Path

from parsers.answer_intent_engine import understand_answer
from parsers.screening_scoring_engine import score_screening_call

OUT_DIR = Path("data/results")
LOG_DIR = Path("logs")
OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "day26_screening_scoring_run.log", mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("day26")

# (turn_id, expected_category, text, is_silent)
CANDIDATE_ANSWERS = [
    ("t000", "introduction", "Hi, I'm a developer with about three years of experience, mostly working on React and Node.js.", False),
    ("t001", "education", "I completed my B.Tech in Computer Science from a college in Pune.", False),
    ("t002", "skills", "Yeah, I've used Docker quite a bit for containerizing our services.", False),
    ("t003", "location", "I'm currently based in Bengaluru and open to relocating.", False),
    ("t004", "experience", "I have eight years of experience in this field.", False),  # conflicts with t000's "three years"
    ("t005", "salary", "My current CTC is around eight lakhs and I'm expecting ten to twelve.", False),
    ("t006", "notice_period", "My notice period is two weeks.", False),
    ("t007", "salary", "I'm expecting a good package, it's negotiable.", False),  # OK, unparseable amount
    ("t008", "experience", "", True),  # missing
]


def main():
    logger.info("=" * 70)
    logger.info("Day 26 -- Screening Scoring Engine demo")
    logger.info("=" * 70)

    answers = [
        understand_answer(text, expected_category=category, turn_id=turn_id, is_silent=is_silent)
        for turn_id, category, text, is_silent in CANDIDATE_ANSWERS
    ]

    result = score_screening_call(answers)

    for qs in result.question_scores:
        logger.info("-" * 70)
        logger.info(f"[{qs.turn_id}] category={qs.question_category!r} quality={qs.quality.value} weighted_total={qs.weighted_total}")
        for name, comp in qs.components.items():
            note_str = f"  ({comp.note})" if comp.note else ""
            logger.info(f"  {name:<13} {comp.score:>5}{note_str}")
        if qs.notes:
            logger.info(f"  notes: {qs.notes}")

    logger.info("=" * 70)
    logger.info(f"Consistency findings: {result.consistency_findings}")
    logger.info(f"TOTAL SCREENING SCORE: {result.total_score}")

    report = result.to_dict()
    out_path = OUT_DIR / "day26_screening_scoring_report.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info(f"Report written to {out_path}")


if __name__ == "__main__":
    main()
