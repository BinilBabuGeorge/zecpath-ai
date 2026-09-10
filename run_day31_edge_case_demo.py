"""
Day 31 demo: drives RobustConversationController through a simulated
call engineered to hit every edge case this module handles -- clean
turns, poor audio (retry then safety-skip), unusable audio, a
language-mismatch turn that resolves after clarification, a genuine
caught exception (crash guard), and a consecutive-failure run that
triggers the call-ending safety fallback in a separate, isolated run
(so it doesn't cut the main demo call short).

Turns below are hand-written, clearly-labeled examples simulating a
live call turn-by-turn, including deliberately malformed input for the
crash-guard case -- not real candidate speech or real audio, same
honesty stance as every prior demo script.
"""

import json
import logging
from pathlib import Path

from parsers.speech_to_text import RawSTTResult
from parsers.edge_case_handler import RobustConversationController

OUT_DIR = Path("data/results")
LOG_DIR = Path("logs")
OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "day31_edge_case_run.log", mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("day31")


def describe(raw: RawSTTResult) -> str:
    if raw.text is None:
        return "<malformed input: text=None>"
    if raw.is_silent:
        return "<silence>"
    return f"{raw.text!r} (confidence={raw.confidence}, language={raw.language})"


def run_main_call():
    logger.info("=" * 90)
    logger.info("DAY 31 -- Edge Case & Failure Handling demo -- MAIN CALL")
    logger.info("=" * 90)

    controller = RobustConversationController(categories=["introduction", "education", "experience", "skills", "location"])

    turns = [
        RawSTTResult(text="Hi, I'm a developer based in Pune with three years of experience.", confidence=0.9),  # introduction: clean -> advance
        RawSTTResult(text="mumble mumble", confidence=0.3),        # education: poor audio -> retry
        RawSTTResult(text="I completed my B.Tech in Computer Science from a college in Pune.", confidence=0.9),  # education: clean, substantial -> advance
        RawSTTResult(text="Namaste, teen saal ka experience hai", confidence=0.9, language="hi"),  # experience: language mismatch -> clarify
        RawSTTResult(text="Sorry, I have three years of experience in backend development.", confidence=0.9, language="en"),  # experience: resolved, on-topic -> advance
        RawSTTResult(text=None, confidence=0.95),                  # skills: malformed input -> crash guard, safely skipped
        RawSTTResult(text="I'm based in Bengaluru and open to relocating.", confidence=0.9),  # location: clean -> advance -> call complete
    ]

    for raw in turns:
        category_before = controller.current_category
        outcome = controller.process_turn(raw)
        logger.info("-" * 90)
        logger.info(f"[{category_before}] input={describe(raw)}")
        logger.info(f"  -> {outcome.action.value}: {outcome.message!r}")
        if outcome.notes:
            logger.info(f"  notes: {outcome.notes}")

    logger.info("=" * 90)
    logger.info(f"Main call complete: {controller.is_call_complete}")
    logger.info(f"Total turns processed: {len(controller.outcome_log)}")
    action_counts = {}
    for o in controller.outcome_log:
        action_counts[o.action.value] = action_counts.get(o.action.value, 0) + 1
    logger.info(f"Action distribution: {action_counts}")
    return controller


def run_consecutive_failure_call():
    logger.info("=" * 90)
    logger.info("DAY 31 -- Edge Case & Failure Handling demo -- ISOLATED CONSECUTIVE-FAILURE CALL")
    logger.info("(run separately so it doesn't cut the main demo call short)")
    logger.info("=" * 90)

    controller = RobustConversationController(categories=["introduction", "education", "experience", "skills"])
    turns = [
        RawSTTResult(text="mumble", confidence=0.3),
        RawSTTResult(text="mumble", confidence=0.3),
        RawSTTResult(text="mumble", confidence=0.3),
    ]
    for raw in turns:
        category_before = controller.current_category
        outcome = controller.process_turn(raw)
        logger.info("-" * 90)
        logger.info(f"[{category_before}] input={describe(raw)}")
        logger.info(f"  -> {outcome.action.value}: {outcome.message!r}  call_ended={outcome.call_ended}")
        if outcome.notes:
            logger.info(f"  notes: {outcome.notes}")

    logger.info(f"Consecutive-failure call ended early: {controller.call_ended_early}")
    return controller


def main():
    main_controller = run_main_call()
    consec_controller = run_consecutive_failure_call()

    report = {
        "main_call": {
            "call_complete": main_controller.is_call_complete,
            "outcome_log": [o.to_dict() for o in main_controller.outcome_log],
        },
        "consecutive_failure_call": {
            "call_ended_early": consec_controller.call_ended_early,
            "outcome_log": [o.to_dict() for o in consec_controller.outcome_log],
        },
    }
    out_path = OUT_DIR / "day31_edge_case_report.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info("=" * 90)
    logger.info(f"Report written to {out_path}")


if __name__ == "__main__":
    main()
