"""
Day 39 demo -- generates interview summary reports for THREE different
candidate profiles (strong, weak, mixed) to show real differentiation,
not just one happy-path report. Writes:
  - logs/day39_summary_generator_run.log
  - data/results/day39_sample_hr_summary_reports.json
"""

from __future__ import annotations

import json
import logging
import os

from parsers.hr_interview_question_bank import InterviewSession, ExperienceLevel, RoleType
from parsers.hr_interview_scoring_engine import score_hr_interview
from parsers.aptitude_logic_engine import AptitudeSession, build_aptitude_profile
from parsers.confidence_stress_engine import build_confidence_profile
from parsers.interview_summary_generator import generate_interview_summary

LOG_PATH = "logs/day39_summary_generator_run.log"
REPORT_PATH = "data/results/day39_sample_hr_summary_reports.json"

os.makedirs("logs", exist_ok=True)
os.makedirs("data/results", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, mode="w"), logging.StreamHandler()],
)
log = logging.getLogger("day39_demo")


def _strong_candidate():
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)
    for text in [
        "For example, I led the migration project and delivered it two weeks ahead of schedule.",
        "I steadily grew from junior to senior engineer over four years, taking on more ownership each year.",
        "My strength is ownership; my weakness is I sometimes take on too much.",
        "For example, I resolved a conflict between two teammates by listening to both sides and proposing a compromise.",
    ]:
        session.submit_response(text)
    apt_session = AptitudeSession.start()
    for text in [
        "Since all labels are wrong, I would pick from the box labeled Mixed, then deduce the other two and relabel correctly.",
        "First take the chicken across, then go back alone, bring the grain, then bring the chicken back, take the fox, then return for the chicken.",
        "No, we cannot conclude that, because the blips that are trons might be a different subset than the zorgs.",
        "For example, I would talk to them privately to understand why, and offer to help. If it continues, I would escalate.",
        "I would explain my concern with reasoning, but respect their decision and document it in writing.",
        "I would assess business impact, communicate with both stakeholders, and negotiate the deadline.",
    ]:
        apt_session.submit_response(text)
    return session, apt_session


def _weak_candidate():
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.NON_TECHNICAL)
    for text in [
        "I was excited, happy, proud, confident, and motivated about it.",
        "Honestly, nothing comes to mind, not sure.",
        "It was difficult, I struggled, was frustrated, afraid, and stressed the whole time.",
        "I guess it was okay, not sure really.",
    ]:
        session.submit_response(text)
    apt_session = AptitudeSession.start()
    for _ in range(6):
        apt_session.submit_response("I'm not sure, maybe, hard to say.")
    return session, apt_session


def _mixed_candidate():
    session = InterviewSession.start(ExperienceLevel.FRESHER, RoleType.NON_TECHNICAL)
    for text in [
        "I'm a recent graduate excited to start my career in software.",
        "Um, I think, uh, it was, I guess, kind of a hard time honestly.",
        "My strength is that I learn quickly; my weakness is I lack real-world experience.",
        "For example, I organized a college event and made sure everyone had a clear role.",
    ]:
        session.submit_response(text)
    apt_session = AptitudeSession.start()
    for text in [
        "I would pick from the mixed box since all labels are wrong.",
        "Not sure about this one, hard to say.",
        "No, we cannot conclude that for sure.",
        "For example, I would talk to them to understand why.",
        "I would raise my concern first.",
        "I would try to prioritize based on impact.",
    ]:
        apt_session.submit_response(text)
    return session, apt_session


def _run_profile(name: str, session, apt_session):
    hr_report = score_hr_interview(session)
    apt_profile = build_aptitude_profile(apt_session)
    confidence_profile = build_confidence_profile(session)
    summary = generate_interview_summary(hr_report, aptitude_profile=apt_profile, confidence_profile=confidence_profile)

    log.info("--- %s candidate ---", name)
    log.info("Combined overall score: %s (%s)", summary.combined_overall_score, summary.performance_band)
    log.info("Strengths: %d, Weaknesses: %d, Risk flags: %d", len(summary.strengths), len(summary.weaknesses), len(summary.risk_flags))
    print()
    print(summary.to_narrative())
    return summary


def main() -> None:
    log.info("Starting Day 39 interview summary generator demo (3 candidate profiles).")

    strong_summary = _run_profile("Strong", *_strong_candidate())
    weak_summary = _run_profile("Weak", *_weak_candidate())
    mixed_summary = _run_profile("Mixed", *_mixed_candidate())

    # Sanity checks the demo itself verifies, not just claims:
    assert strong_summary.combined_overall_score > weak_summary.combined_overall_score, "Strong candidate should outscore weak candidate overall."
    log.info("Sanity check passed: strong candidate (%s) outscored weak candidate (%s).", strong_summary.combined_overall_score, weak_summary.combined_overall_score)
    assert strong_summary.performance_band != weak_summary.performance_band, "Strong and weak candidates should land in different performance bands."
    log.info("Sanity check passed: performance bands differ (%s vs %s).", strong_summary.performance_band, weak_summary.performance_band)
    assert len(weak_summary.risk_flags) > len(strong_summary.risk_flags), "Weak candidate should surface more risk flags than the strong candidate."
    log.info("Sanity check passed: weak candidate had more risk flags (%d) than strong candidate (%d).", len(weak_summary.risk_flags), len(strong_summary.risk_flags))

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "strong_candidate": strong_summary.to_dict(),
            "weak_candidate": weak_summary.to_dict(),
            "mixed_candidate": mixed_summary.to_dict(),
        }, f, indent=2)
    log.info("Report written to %s", REPORT_PATH)


if __name__ == "__main__":
    main()
