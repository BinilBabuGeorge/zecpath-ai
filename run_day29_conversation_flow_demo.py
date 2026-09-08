"""
Day 29 demo: drives a full ConversationFlowController call across
every branch of the decision tree -- silence + retry + fallback,
confusion + clarification, off-topic + redirect, vague + fallback,
a repeated answer, a thin answer triggering a follow-up, and a clean
straight-through answer -- so every FlowAction this module can emit
appears at least once in the log.

Turns below are hand-written, clearly-labeled examples simulating a
live call turn-by-turn, not real candidate speech -- same honesty
stance as every prior demo script.
"""

import json
import logging
from pathlib import Path

from parsers.conversation_flow_engine import ConversationFlowController

OUT_DIR = Path("data/results")
LOG_DIR = Path("logs")
OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "day29_conversation_flow_run.log", mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("day29")

# (text, is_silent) -- fed turn by turn; the controller decides which
# category each one lands on internally. Every FlowAction this module
# can emit appears at least once in this sequence, verified turn by
# turn before finalizing (see docs/day29_conversation_flow_design.md).
SIMULATED_TURNS = [
    ("", True),                                                                              # introduction: silence -> retry
    ("Hi, I'm a developer based in Pune with a background in web development and cloud systems.", False),  # introduction: OK -> advance
    ("", True),                                                                              # education: silence -> retry
    ("", True),                                                                              # education: silence again -> fallback
    ("I completed my B.Tech in Computer Science from a college in Pune.", False),             # education: OK -> advance
    ("Sorry, what do you mean?", False),                                                      # experience: confusion -> clarify
    ("About four years of experience.", False),                                               # experience: thin OK -> follow-up
    ("Mostly backend systems and some DevOps work over the last few years.", False),           # experience: OK -> advance
    ("My current CTC is around eight lakhs and I am expecting more.", False),                  # skills expected, salary content -> off-topic redirect
    ("My CTC expectation is around ten lakhs actually.", False),                               # skills: still off-topic -> polite skip
    ("I'm not sure, maybe.", False),                                                           # location: vague -> fallback
    ("I am currently based in Bengaluru and open to relocating for the right opportunity.", False),  # location: OK -> advance
    ("My current CTC is around eight lakhs and I am expecting more.", False),                  # salary: repeated (matches earlier off-topic turn) -> acknowledge + advance
    ("My notice period is immediate, I can join within a few days.", False),                   # notice_period: OK -> advance -> call complete
    ("hello?", False),                                                                         # after completion -> end_call
]


def main():
    logger.info("=" * 70)
    logger.info("Day 29 -- AI Conversation Flow Design demo")
    logger.info("=" * 70)

    controller = ConversationFlowController()  # defaults to Day 22's 7 categories

    for text, is_silent in SIMULATED_TURNS:
        category_before = controller.current_category
        already_complete = controller.is_call_complete
        action = controller.process_turn(text, is_silent=is_silent)
        logger.info("-" * 70)
        logger.info(f"[{category_before if not already_complete else 'CALL COMPLETE'}] input={'<silence>' if is_silent else text!r}")
        logger.info(f"  -> {action.action_type.value}: {action.message!r}")
        logger.info(f"  reason: {action.reason}")

    logger.info("=" * 70)
    logger.info(f"Call complete: {controller.is_call_complete}")
    logger.info(f"Total actions taken: {len(controller.action_log)}")
    action_counts = {}
    for a in controller.action_log:
        action_counts[a.action_type.value] = action_counts.get(a.action_type.value, 0) + 1
    logger.info(f"Action type distribution: {action_counts}")

    report = {
        "call_complete": controller.is_call_complete,
        "action_type_distribution": action_counts,
        "action_log": [a.to_dict() for a in controller.action_log],
    }
    out_path = OUT_DIR / "day29_conversation_flow_report.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info(f"Report written to {out_path}")


if __name__ == "__main__":
    main()
