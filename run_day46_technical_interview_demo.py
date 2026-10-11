"""
Day 46 demo -- runs three candidates (junior MERN, mid-level Java,
senior DevOps) through the technical interview system to show the
experience-based difficulty logic actually selecting different
questions, not just computing a different label. Writes:
  - logs/day46_technical_interview_run.log
  - data/results/day46_technical_interview_report.json
"""

from __future__ import annotations

import json
import logging
import os

from parsers.technical_interview_question_bank import TechnicalDomain, TechnicalInterviewSession

LOG_PATH = "logs/day46_technical_interview_run.log"
REPORT_PATH = "data/results/day46_technical_interview_report.json"

os.makedirs("logs", exist_ok=True)
os.makedirs("data/results", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, mode="w"), logging.StreamHandler()],
)
log = logging.getLogger("day46_demo")

CANDIDATES = [
    ("Junior MERN candidate", TechnicalDomain.MERN, 1),
    ("Mid-level Java candidate", TechnicalDomain.JAVA, 4),
    ("Senior DevOps candidate", TechnicalDomain.DEVOPS, 9),
]


def main() -> None:
    log.info("Starting Day 46 technical interview system demo (3 candidates, 3 domains, 3 tiers).")
    report_data = {}

    for name, domain, years in CANDIDATES:
        log.info("=" * 70)
        log.info("%s -- domain=%s, years_of_experience=%s", name, domain.value, years)
        session = TechnicalInterviewSession.start(domain, years)
        log.info("Selected tier: %s (%d questions queued)", session.tier.value, len(session.questions))

        record = {"name": name, "domain": domain.value, "years_of_experience": years, "tier": session.tier.value, "questions": []}

        while not session.is_complete:
            q = session.current_question
            log.info("  [%s] %s", q.phase.value, q.question.prompt_text)
            session.submit_response(f"({name}'s answer)")
            record["questions"].append({"phase": q.phase.value, "question_id": q.question.question_id, "prompt": q.question.prompt_text})

        followed = [p.value for p in session.phase_sequence_followed()]
        log.info("Phase sequence followed: %s", followed)
        assert followed == ["introduction", "experience_based", "conceptual", "scenario_based"], f"Unexpected phase sequence for {name}: {followed}"
        record["phase_sequence_followed"] = followed
        report_data[name] = record

    log.info("=" * 70)
    log.info("Sanity check passed: all 3 candidates followed the exact designed phase order (introduction -> experience_based -> conceptual -> scenario_based).")

    tiers_seen = {report_data[name]["tier"] for name, _, _ in CANDIDATES}
    assert tiers_seen == {"basics", "intermediate", "advanced"}, f"Expected all three tiers represented across candidates, got {tiers_seen}"
    log.info("Sanity check passed: all three difficulty tiers (basics/intermediate/advanced) were actually selected across the 3 candidates, not just one tier reused.")

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)
    log.info("Report written to %s", REPORT_PATH)


if __name__ == "__main__":
    main()
