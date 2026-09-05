"""
Day 27 demo: runs build_communication_profile() over one candidate's
screening answers, deliberately mixing a confident/clean answer, a
hesitant/uncertain one, and a mildly negative one -- plus a reused
Day 26 consistency finding -- so every signal in this module has
something real to detect, not just a clean pass-through.

Answers below are hand-written, clearly-labeled examples standing in
for cleaned Day 24/25 output, not real candidate speech -- same
honesty stance as every prior demo script.
"""

import json
import logging
from pathlib import Path

from parsers.answer_intent_engine import understand_answer
from parsers.screening_scoring_engine import score_screening_call
from parsers.confidence_sentiment_engine import build_communication_profile

OUT_DIR = Path("data/results")
LOG_DIR = Path("logs")
OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "day27_communication_signal_run.log", mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("day27")

# (turn_id, expected_category, text, duration_seconds)
CANDIDATE_ANSWERS = [
    ("t000", "introduction", "Hi, I'm a developer with three years of experience, mostly working on React and Node.js. I really enjoy building things.", 14.0),
    ("t001", "experience", "Um, I think I've been working for around eight years now, probably, you know.", 9.0),  # hesitant + conflicts with t000
    ("t002", "skills", "I've used Docker quite a bit for containerizing our services.", 6.0),
    ("t003", "salary", "Honestly it's been a frustrating search, I'm a bit nervous about the negotiation.", 8.0),  # negative sentiment
]


def main():
    logger.info("=" * 70)
    logger.info("Day 27 -- Confidence & Sentiment Signal Analysis demo")
    logger.info("=" * 70)

    answers = [
        understand_answer(text, expected_category=category, turn_id=turn_id)
        for turn_id, category, text, _ in CANDIDATE_ANSWERS
    ]
    durations = {turn_id: dur for turn_id, _, _, dur in CANDIDATE_ANSWERS}

    # Reuse Day 26's consistency check -- not recomputed here.
    scoring_result = score_screening_call(answers)
    consistency_findings = scoring_result.consistency_findings

    profile = build_communication_profile(answers, consistency_findings, durations=durations)

    for signal in profile.answer_signals:
        logger.info("-" * 70)
        logger.info(f"[{signal.turn_id}]")
        h = signal.hesitation
        logger.info(f"  hesitation: filler_count={h.filler_count} phrases={h.filler_phrases_found} "
                     f"ambiguous_flagged={h.ambiguous_words_flagged} rate={h.hesitation_rate_per_100_words}/100w")
        lp = signal.length_pace
        logger.info(f"  length_pace: words={lp.word_count} wpm={lp.words_per_minute}" + (f"  ({lp.note})" if lp.note else ""))
        s = signal.sentiment
        logger.info(f"  sentiment: label={s.label} score={s.score} positive={s.positive_hits} negative={s.negative_hits}")
        u = signal.uncertainty
        logger.info(f"  uncertainty: markers={u.markers_found} rate={u.uncertainty_rate_per_100_words}/100w")

    logger.info("=" * 70)
    logger.info(f"Consistency findings (reused from Day 26): {profile.contradiction_findings}")
    logger.info(f"Component breakdown: {profile.component_breakdown}")
    logger.info(f"COMMUNICATION STRENGTH SCORE: {profile.communication_strength_score}")

    report = profile.to_dict()
    out_path = OUT_DIR / "day27_communication_signal_report.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info(f"Report written to {out_path}")


if __name__ == "__main__":
    main()
