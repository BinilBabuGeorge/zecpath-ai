"""
Day 49 demo -- runs four interview scenarios through the integrity
detection engine to show the risk tag actually differentiates, and that
behavioral signals alone never raise it. Also replays the "lookup"
scenario through the real-time IntegrityMonitor to show the alert
escalation ladder. Writes:
  - logs/day49_integrity_detection_run.log
  - data/results/day49_integrity_detection_report.json

HONESTY NOTE: a real interview takes many minutes, so the TIMELINE here is
synthetic -- realistic per-question latencies are assigned to the real
question IDs/answers of a real Day 33 HR session, and browser events are
placed on that timeline by hand. The detection logic consuming them is
100% real. No real browser client exists in this project yet.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import replace

from parsers.behavioral_signal_engine import TimedSessionTracker
from parsers.hr_interview_question_bank import ExperienceLevel, InterviewSession, RoleType
from parsers.integrity_detection_engine import (
    AlertLevel,
    BrowserEvent,
    BrowserEventType as T,
    IntegrityMonitor,
    IntegrityRiskTag,
    build_integrity_report,
    windows_from_records,
)

LOG_PATH = "logs/day49_integrity_detection_run.log"
REPORT_PATH = "data/results/day49_integrity_detection_report.json"

os.makedirs("logs", exist_ok=True)
os.makedirs("data/results", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, mode="w"), logging.StreamHandler()],
)
log = logging.getLogger("day49_demo")

ANSWERS = [
    "I have six years of experience in backend development.",
    "I led a migration project and delivered it two weeks early.",
    "My strength is ownership; I follow problems through to the end.",
    "I resolved a conflict between two teammates by agreeing shared goals.",
    "I want to grow into a tech lead role.",
    "I can start within two weeks.",
]


def base_records(latencies):
    """Real question IDs + answers from a real HR session, with synthetic realistic latencies."""
    tracker = TimedSessionTracker(InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL))
    for text in ANSWERS:
        tracker.submit_timed_response(text)
    return [replace(r, latency_seconds=lat) for r, lat in zip(tracker.records, latencies)]


def ev(kind, t):
    return BrowserEvent(kind, t)


def scenario_a_clean():
    records = base_records([50, 62, 55, 58, 48, 40])
    events = [ev(T.WINDOW_BLUR, 80.0), ev(T.WINDOW_FOCUS, 80.9)]   # 0.9s blip: ignored
    return "A. Clean candidate (one 0.9s notification blip)", records, events


def scenario_b_distracted():
    records = base_records([50, 62, 55, 58, 48, 40])
    w = windows_from_records(records)
    events = [
        ev(T.TAB_HIDDEN, w[1].start + 25), ev(T.TAB_VISIBLE, w[1].start + 31),   # 6s, mid-question
        ev(T.TAB_HIDDEN, w[4].start + 20), ev(T.TAB_VISIBLE, w[4].start + 24),   # 4s, mid-question
    ]
    return "B. Honest but distracted (two short mid-question switches)", records, events


def scenario_c_lookup():
    records = base_records([50, 62, 130, 58, 140, 40])
    w = windows_from_records(records)
    events = [
        ev(T.WINDOW_BLUR, w[2].start + 2), ev(T.TAB_HIDDEN, w[2].start + 2.1),
        ev(T.TAB_VISIBLE, w[2].end - 6), ev(T.WINDOW_FOCUS, w[2].end - 5.9),      # leaves at once, back before answering
        ev(T.WINDOW_BLUR, w[4].start + 3), ev(T.TAB_HIDDEN, w[4].start + 3.1),
        ev(T.TAB_VISIBLE, w[4].end - 4), ev(T.WINDOW_FOCUS, w[4].end - 3.9),
    ]
    return "C. Lookup behaviour (leaves right after two questions, returns just before answering)", records, events


def scenario_d_slow_only():
    records = base_records([50, 62, 55, 260, 48, 40])   # one huge pause, NO browser events
    return "D. Slow answer only (huge latency spike, no browser events)", records, []


def main() -> None:
    log.info("Starting Day 49 integrity detection demo (browser events only -- no camera, no audio).")
    results = {}
    reports = {}
    for build in (scenario_a_clean, scenario_b_distracted, scenario_c_lookup, scenario_d_slow_only):
        title, records, events = build()
        report = build_integrity_report(events, records=records)
        reports[build.__name__] = report
        log.info("-" * 70)
        log.info("%s", title)
        log.info("%s", report.to_summary_text().replace("\n", " | "))
        print(f"\n### {title}\n{report.to_summary_text()}")
        results[build.__name__] = {"title": title, **report.to_dict()}

    # Real-time replay of scenario C through the monitor, with synthetic timestamps.
    _, records, events = scenario_c_lookup()
    monitor = IntegrityMonitor(windows=windows_from_records(records))
    ladder = []
    for e in sorted(events, key=lambda x: x.timestamp):
        alert = monitor.record_event(e)
        if alert:
            ladder.append(alert)
            log.info("REAL-TIME ALERT at t=%.1fs: %s | candidate sees: %s | internal: %s",
                     alert.timestamp, alert.level.value.upper(), alert.candidate_message, alert.internal_note)
    results["scenario_c_realtime_alerts"] = [a.to_dict() for a in ladder]

    # Sanity checks the demo itself verifies, not just claims:
    assert reports["scenario_a_clean"].risk_tag is IntegrityRiskTag.CLEAR
    assert reports["scenario_a_clean"].signals.ignored_blips == 1
    log.info("Sanity check passed: a 0.9s focus blip was ignored (counted as a blip) and the candidate stayed CLEAR.")

    assert reports["scenario_b_distracted"].risk_tag is IntegrityRiskTag.LOW
    assert not reports["scenario_b_distracted"].human_review_required
    log.info("Sanity check passed: two short mid-question switches stayed LOW with no review required (false-positive guard).")

    c = reports["scenario_c_lookup"]
    assert c.risk_tag in (IntegrityRiskTag.MEDIUM, IntegrityRiskTag.HIGH) and c.human_review_required
    assert {"QUESTION_LOOKUP_PATTERN", "LATENCY_CORROBORATION"} <= {f.code for f in c.flags}
    log.info("Sanity check passed: the lookup behaviour was tagged %s via the pattern and Day 48 latency corroboration.", c.risk_tag.value.upper())

    d = reports["scenario_d_slow_only"]
    assert d.risk_tag is IntegrityRiskTag.CLEAR and d.flags == []
    log.info("Sanity check passed: a huge latency spike with no browser events did NOT raise integrity risk (slow != malpractice).")

    assert all(r.automated_action == "none" and r.scoring_impact == "none" for r in reports.values())
    log.info("Sanity check passed: every report has automated_action='none' and scoring_impact='none'.")

    assert all(set(r.not_implemented) == {"external_voice_detection", "repeated_looking_away", "secondary_device_or_mobile_usage"}
               for r in reports.values())
    log.info("Sanity check passed: external voice, looking away and secondary-device usage are explicitly listed as not implemented in every report.")

    levels = [a.level for a in ladder]
    assert levels[0] is AlertLevel.NOTICE and AlertLevel.WARNING in levels
    assert all(a.candidate_message is None for a in ladder if a.level is AlertLevel.FLAG)
    log.info("Sanity check passed: real-time monitor escalated NOTICE -> WARNING, and any FLAG stays internal-only.")

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    log.info("Report written to %s", REPORT_PATH)


if __name__ == "__main__":
    main()
