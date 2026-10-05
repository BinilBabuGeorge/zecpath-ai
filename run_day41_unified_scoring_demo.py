"""
Day 41 demo -- computes unified hiring-fit scores for three candidates
(a full candidate with all 3 rounds, a candidate missing the screening
round, and a weak candidate), across both role types, to show the
weighting and missing-round redistribution actually change the
result. Writes:
  - logs/day41_unified_scoring_run.log
  - data/results/day41_unified_scoring_report.json
"""

from __future__ import annotations

import json
import logging
import os

from parsers.hr_interview_question_bank import RoleType
from parsers.unified_scoring_engine import RoundScores, compute_unified_score

LOG_PATH = "logs/day41_unified_scoring_run.log"
REPORT_PATH = "data/results/day41_unified_scoring_report.json"

os.makedirs("logs", exist_ok=True)
os.makedirs("data/results", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, mode="w"), logging.StreamHandler()],
)
log = logging.getLogger("day41_demo")


def main() -> None:
    log.info("Starting Day 41 unified scoring demo.")
    report_data = {}

    log.info("=" * 60)
    log.info("Candidate A -- strong, all three rounds completed, technical role.")
    scores_a = RoundScores(ats_score=82.0, screening_score=74.0, hr_interview_score=88.0)
    result_a = compute_unified_score(scores_a, role_type=RoleType.TECHNICAL, candidate_id="CAND-A")
    log.info(result_a.to_summary_text().replace("\n", " | "))
    print()
    print(result_a.to_summary_text())
    report_data["candidate_a_full_technical"] = result_a.to_dict()

    log.info("=" * 60)
    log.info("Candidate A, same scores, but as a NON_TECHNICAL role -- weighting should shift.")
    result_a_nontech = compute_unified_score(scores_a, role_type=RoleType.NON_TECHNICAL, candidate_id="CAND-A")
    log.info("Technical weighting score: %s | Non-technical weighting score: %s", result_a.hiring_fit_percentage, result_a_nontech.hiring_fit_percentage)
    report_data["candidate_a_full_non_technical"] = result_a_nontech.to_dict()

    log.info("=" * 60)
    log.info("Candidate B -- screening round not yet completed.")
    scores_b = RoundScores(ats_score=82.0, screening_score=None, hr_interview_score=88.0)
    result_b = compute_unified_score(scores_b, role_type=RoleType.TECHNICAL, candidate_id="CAND-B")
    print()
    print(result_b.to_summary_text())
    report_data["candidate_b_missing_screening"] = result_b.to_dict()

    log.info("=" * 60)
    log.info("Candidate C -- weak across all three rounds.")
    scores_c = RoundScores(ats_score=35.0, screening_score=30.0, hr_interview_score=40.0)
    result_c = compute_unified_score(scores_c, role_type=RoleType.TECHNICAL, candidate_id="CAND-C")
    print()
    print(result_c.to_summary_text())
    report_data["candidate_c_weak"] = result_c.to_dict()

    # Sanity checks the demo itself verifies, not just claims:
    assert result_a.hiring_fit_percentage != result_a_nontech.hiring_fit_percentage, "Role-based weighting should change the score for the same raw inputs."
    log.info("Sanity check passed: technical (%s%%) and non-technical (%s%%) weighting produced different scores for identical raw inputs.", result_a.hiring_fit_percentage, result_a_nontech.hiring_fit_percentage)

    assert result_b.missing_rounds == ["screening"], "Candidate B should have screening flagged as missing."
    log.info("Sanity check passed: Candidate B correctly flags screening as missing.")

    assert result_a.decision == "selected" and result_c.decision == "rejected", "Strong and weak candidates should land in different decision bands."
    log.info("Sanity check passed: Candidate A (%s) and Candidate C (%s) landed in different decisions.", result_a.decision, result_c.decision)

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)
    log.info("Report written to %s", REPORT_PATH)


if __name__ == "__main__":
    main()
