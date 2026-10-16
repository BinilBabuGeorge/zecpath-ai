"""
Day 48 demo -- runs a real HR interview session through the timed
tracker with deliberately varied pacing (one long pause, one filler-
heavy answer) to show the focus/distraction/hesitation signals
actually differentiate, and prints the full honesty-first report
including what's explicitly not implemented. Writes:
  - logs/day48_behavioral_signal_run.log
  - data/results/day48_behavioral_signal_report.json
"""

from __future__ import annotations

import json
import logging
import os
import time

from parsers.hr_interview_question_bank import InterviewSession, ExperienceLevel, RoleType
from parsers.behavioral_signal_engine import TimedSessionTracker, build_behavioral_insight_report

LOG_PATH = "logs/day48_behavioral_signal_run.log"
REPORT_PATH = "data/results/day48_behavioral_signal_report.json"

os.makedirs("logs", exist_ok=True)
os.makedirs("data/results", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, mode="w"), logging.StreamHandler()],
)
log = logging.getLogger("day48_demo")

# (answer, artificial delay before answering) -- one deliberate long
# pause and one filler-heavy answer, to exercise both signals for real.
ANSWERS = [
    ("For example, I led the migration project and delivered it two weeks early.", 0.08),
    ("I grew from junior to senior engineer over four years.", 0.09),
    ("Um, I think, uh, my strength is ownership, I guess.", 0.07),          # filler-heavy
    ("For example, I resolved a conflict between two teammates.", 0.6),      # deliberate long pause
    ("I want to grow into a tech lead role eventually.", 0.08),
    ("I'm available to start within two weeks.", 0.07),
]


def main() -> None:
    log.info("Starting Day 48 behavioral signal demo (non-invasive, timing + text only).")
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)
    tracker = TimedSessionTracker(session)

    for text, delay in ANSWERS:
        time.sleep(delay)
        record = tracker.submit_timed_response(text)
        log.info("Recorded %s: latency=%.3fs, text=%r", record.question_id, record.latency_seconds, text[:50])

    report = build_behavioral_insight_report(tracker)
    log.info("=" * 70)
    log.info(report.to_summary_text().replace("\n", " | "))
    print()
    print(report.to_summary_text())

    # Sanity checks the demo itself verifies, not just claims:
    assert "hr-q04" in report.distraction.spike_question_ids, "The deliberate long pause on hr-q04 should be flagged as a spike."
    log.info("Sanity check passed: deliberate long pause on hr-q04 was correctly flagged as a latency spike.")

    assert report.verbal_hesitation.average_hesitation_rate_per_100_words > 0.0, "The filler-heavy answer should raise the average hesitation rate above zero."
    log.info("Sanity check passed: filler-heavy answer raised the average verbal hesitation rate above zero.")

    assert set(report.not_implemented) == {"eye_movement_gaze_stability", "head_movement", "facial_engagement", "nervous_gestures_physical"}
    log.info("Sanity check passed: all four camera-dependent signals are explicitly listed as not implemented, not silently omitted.")

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2)
    log.info("Report written to %s", REPORT_PATH)


if __name__ == "__main__":
    main()
