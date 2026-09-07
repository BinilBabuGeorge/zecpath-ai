"""
Day 28 demo: runs the full Day 25 -> 26 -> 27 -> 28 pipeline over one
candidate's screening call and produces the actual exportable report
artifacts -- a recruiter-facing Markdown file and a machine-readable
JSON file -- which ARE the "sample screening reports" deliverable,
not just log output describing them.

Answers below are hand-written, clearly-labeled examples standing in
for a real screening call, not real candidate speech -- same honesty
stance as every prior demo script. Deliberately mixes a strong answer,
a hesitant/conflicting one, an unparseable-salary answer, and a
missing answer so every report section (strengths, risks, missing
data, highlights) has something real to show.
"""

import logging
from pathlib import Path

from parsers.answer_intent_engine import understand_answer
from parsers.screening_scoring_engine import score_screening_call
from parsers.confidence_sentiment_engine import build_communication_profile
from parsers.screening_report_generator import generate_screening_report

OUT_DIR = Path("data/results")
REPORTS_DIR = Path("data/reports")
LOG_DIR = Path("logs")
OUT_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "day28_screening_report_run.log", mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("day28")

# (turn_id, expected_category, text, duration_seconds)
CANDIDATE_ANSWERS = [
    ("t000", "introduction", "Hi, I'm a developer with three years of experience, mostly working on React and Node.js. I really enjoy building things.", 14.0),
    ("t001", "experience", "Um, I think I've been working for around eight years now, probably, you know.", 9.0),  # hesitant + conflicts with t000
    ("t002", "skills", "I've used Docker quite a bit for containerizing our services.", 6.0),
    ("t003", "salary", "I'm expecting a good package, it's negotiable.", 7.0),  # unparseable amount
    ("t004", "availability", "My notice period is immediate.", 4.0),
    ("t005", "education", "", None),  # missing / silent
]


def main():
    logger.info("=" * 70)
    logger.info("Day 28 -- AI Screening Report Generator demo")
    logger.info("=" * 70)

    answers = [
        understand_answer(text, expected_category=category, turn_id=turn_id, is_silent=(text == ""))
        for turn_id, category, text, _ in CANDIDATE_ANSWERS
    ]
    durations = {turn_id: dur for turn_id, _, _, dur in CANDIDATE_ANSWERS if dur is not None}

    scoring_result = score_screening_call(answers)
    communication_profile = build_communication_profile(answers, scoring_result.consistency_findings, durations=durations)

    report = generate_screening_report(
        answers, scoring_result, communication_profile,
        candidate_id="CAND-2026-0142", job_role="MERN Stack Developer",
    )

    logger.info(f"Total Screening Score: {report.total_score}")
    logger.info(f"Communication Strength Score: {report.communication_strength_score}")
    logger.info("-" * 70)
    logger.info("Strengths:")
    for s in report.strengths:
        logger.info(f"  - {s}")
    logger.info("Risks:")
    for r in report.risks:
        logger.info(f"  - {r}")
    logger.info("Missing Data:")
    for m in report.missing_data:
        logger.info(f"  - {m}")
    logger.info(f"Highlights: {report.highlights.to_dict()}")

    md_path = REPORTS_DIR / "sample_screening_report_CAND-2026-0142.md"
    json_path = REPORTS_DIR / "sample_screening_report_CAND-2026-0142.json"
    md_path.write_text(report.to_markdown(), encoding="utf-8")
    json_path.write_text(report.to_json(), encoding="utf-8")

    logger.info("=" * 70)
    logger.info(f"Sample report written to {md_path} and {json_path}")


if __name__ == "__main__":
    main()
