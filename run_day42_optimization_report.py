"""
Day 42 demo -- demonstrates the concrete-example detector fix
(Finding 1 from Day 40) with the exact before/after evidence, plus the
regression guards confirming nothing else moved. Writes:
  - logs/day42_optimization_report_run.log
  - data/results/day42_optimization_report.json

Findings 2 and 3 from Day 40 are NOT addressed here -- the files they
live in (confidence_stress_engine.py, interview_summary_generator.py)
aren't available in this build environment. See
docs/day42_optimization_stability.md for the full explanation and
what's needed to close them out.
"""

from __future__ import annotations

import json
import logging
import os

from parsers.hr_followup_engine import has_concrete_example, assess_behavioral_answer

LOG_PATH = "logs/day42_optimization_report_run.log"
REPORT_PATH = "data/results/day42_optimization_report.json"

os.makedirs("logs", exist_ok=True)
os.makedirs("data/results", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, mode="w"), logging.StreamHandler()],
)
log = logging.getLogger("day42_demo")

# The exact Day 40 Hesitant-persona sentences that were mis-classified.
FIXED_CASES = [
    "So, um, I started as an intern, and then, uh, I think I became a full-time developer after that, and, um, I have been growing since then I think.",
    "Um, I think, uh, I have been working as a developer for about three years, I guess, and, um, I worked on a couple of projects.",
]

# Cases that must NOT change behavior -- the regression guard.
UNCHANGED_VAGUE = ["Honestly, nothing comes to mind right now.", "I'm not sure, hard to say."]
UNCHANGED_THIN = "I am hardworking, a team player, and a fast learner who is dedicated and motivated to succeed in every situation I encounter."
UNCHANGED_FALSE_MATCH = "It took quite a while to finish, honestly."


def main() -> None:
    log.info("Starting Day 42 optimization report -- Finding 1 fix verification.")
    report_data = {"finding_1_fixed_cases": [], "regression_guards": []}

    log.info("=" * 60)
    log.info("Finding 1 fix: broadened has_concrete_example() for narrative/quantity signals.")
    for text in FIXED_CASES:
        concrete = has_concrete_example(text)
        quality = assess_behavioral_answer(text).value
        log.info("Text: %s...", text[:60])
        log.info("  -> concrete=%s, quality=%s (previously: concrete=False, quality=thin)", concrete, quality)
        assert concrete is True, f"Expected this previously-false-negative case to now be concrete: {text}"
        assert quality == "confident", f"Expected this case to now classify as confident: {text}"
        report_data["finding_1_fixed_cases"].append({"text": text, "concrete": concrete, "quality": quality})

    log.info("=" * 60)
    log.info("Regression guards -- confirming the fix did NOT change other classifications.")
    for text in UNCHANGED_VAGUE:
        quality = assess_behavioral_answer(text).value
        log.info("Vague case unaffected: %s -> %s", text, quality)
        assert quality == "vague"
        report_data["regression_guards"].append({"text": text, "expected": "vague", "actual": quality})

    thin_quality = assess_behavioral_answer(UNCHANGED_THIN).value
    log.info("Generic-padding case unaffected: -> %s", thin_quality)
    assert thin_quality == "thin"
    report_data["regression_guards"].append({"text": UNCHANGED_THIN, "expected": "thin", "actual": thin_quality})

    false_match = has_concrete_example(UNCHANGED_FALSE_MATCH)
    log.info("'Quite a while' false-match guard: concrete=%s (expected False)", false_match)
    assert false_match is False
    report_data["regression_guards"].append({"text": UNCHANGED_FALSE_MATCH, "expected_concrete": False, "actual_concrete": false_match})

    log.info("=" * 60)
    log.info("Sanity check passed: both Day 40 Finding-1 false negatives are now fixed.")
    log.info("Sanity check passed: all regression guards held -- vague/thin/false-match behavior unchanged.")
    log.info("Findings 2 and 3 (confidence_stress_engine.py, interview_summary_generator.py) NOT addressed -- files unavailable in this environment. See docs/day42_optimization_stability.md.")

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)
    log.info("Report written to %s", REPORT_PATH)


if __name__ == "__main__":
    main()
