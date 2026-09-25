"""
Day 40 demo -- runs all four personas through the full HR-interview
pipeline, prints each result against its hand-written manual
expectation, and writes:
  - logs/day40_hr_interview_simulation_run.log
  - data/results/day40_hr_interview_test_report.json

This IS the "compare AI output vs manual evaluation" and "identify
scoring inconsistencies" tasks, executed for real -- the findings
below were discovered by running this script, not written first and
then confirmed.
"""

from __future__ import annotations

import json
import logging
import os

from parsers.hr_interview_simulation import run_all_personas

LOG_PATH = "logs/day40_hr_interview_simulation_run.log"
REPORT_PATH = "data/results/day40_hr_interview_test_report.json"

os.makedirs("logs", exist_ok=True)
os.makedirs("data/results", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, mode="w"), logging.StreamHandler()],
)
log = logging.getLogger("day40_demo")


def main() -> None:
    log.info("Starting Day 40 HR interview simulation across 4 personas.")
    results = run_all_personas()

    report_data = {}
    for r in results:
        log.info("=" * 60)
        log.info("Persona: %s -- %s", r.persona.name, r.persona.description)
        log.info("Manual expectation: %s", r.persona.manual_expectation)
        log.info(
            "AI scores -- relevance=%.1f communication=%.1f confidence=%.1f stress=%.1f",
            r.hr_report.avg_relevance, r.hr_report.avg_communication, r.hr_report.avg_confidence,
            r.confidence_profile.overall_stress_score,
        )
        log.info("Combined score: %s (%s) | Risk flags: %d", r.summary.combined_overall_score, r.summary.performance_band, len(r.summary.risk_flags))
        print()
        print(r.summary.to_narrative())

        report_data[r.persona.name] = {
            "description": r.persona.description,
            "manual_expectation": r.persona.manual_expectation,
            "ai_summary": r.summary.to_dict(),
            "hr_component_averages": {
                "relevance": r.hr_report.avg_relevance, "communication": r.hr_report.avg_communication,
                "confidence": r.hr_report.avg_confidence,
            },
            "stress_score": r.confidence_profile.overall_stress_score,
        }

    # Sanity checks the demo itself verifies, not just claims:
    band_by_name = {r.persona.name: r.summary.performance_band for r in results}
    assert band_by_name["Confident"] in ("Strong", "Good"), "Confident persona should land in a top band."
    log.info("Sanity check passed: Confident persona landed in band %s.", band_by_name["Confident"])

    inexperienced = next(r for r in results if r.persona.name == "Inexperienced")
    assert inexperienced.hr_report.consistency.findings == [], "Inexperienced persona should NOT be flagged inconsistent (weak != risky)."
    log.info("Sanity check passed: Inexperienced persona correctly shows no consistency findings.")

    hesitant = next(r for r in results if r.persona.name == "Hesitant")
    assert hesitant.hr_report.avg_relevance != hesitant.hr_report.avg_confidence, "Hesitant persona's content and delivery scores should differ, not collapse together."
    log.info("Sanity check passed: Hesitant persona's relevance (%.1f) and confidence (%.1f) scores differ.", hesitant.hr_report.avg_relevance, hesitant.hr_report.avg_confidence)

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)
    log.info("Report written to %s", REPORT_PATH)


if __name__ == "__main__":
    main()
