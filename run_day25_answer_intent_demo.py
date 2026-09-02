"""
Day 25 demo: runs understand_answer() over a set of realistic candidate
answers -- clean, multi-entity, vague, off-topic, and silent -- and
writes a structured JSON report plus a full run log.

Answers below are hand-written, clearly-labeled examples standing in
for cleaned Day 24 output (i.e. what clean_transcript() would hand this
module), not real candidate speech -- same honesty stance as Day 23's
and Day 24's demo scripts.
"""

import json
import logging
from pathlib import Path

from parsers.answer_intent_engine import understand_answer

OUT_DIR = Path("data/results")
LOG_DIR = Path("logs")
OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "day25_answer_intent_run.log", mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("day25")

# (turn_id, expected_category, text, is_silent) -- covers every quality
# bucket (OK / multi-entity OK / VAGUE / OFF_TOPIC / MISSING) plus every
# entity extractor (skills, experience, availability, salary).
SAMPLE_ANSWERS = [
    ("t000", "introduction", "Hi, I'm a full stack developer with about three years of experience, mostly working on React and Node.js.", False),
    ("t001", "experience", "I've been working professionally for around three years now.", False),
    ("t002", "skills", "Yeah, I've used Docker quite a bit for containerizing our services.", False),
    ("t003", "education", "I completed my B.Tech in Computer Science from a college in Pune.", False),
    ("t004", "location", "I'm currently based in Bengaluru and open to relocating.", False),
    ("t005", "salary", "My current CTC is around eight lakhs and I'm expecting ten to twelve.", False),
    ("t006", "salary", "I'm expecting a good package, it's negotiable.", False),  # OK intent, unparseable amount
    ("t007", "notice_period", "My notice period is thirty days but I can negotiate.", False),
    ("t008", "notice_period", "I can join immediately, I'm not serving any notice.", False),
    ("t009", "salary", "I'm not really sure, maybe around that range I guess.", False),  # VAGUE
    ("t010", "location", "My current CTC is around twelve lakhs.", False),  # OFF_TOPIC (salary vocab, location expected)
    ("t011", "experience", "", True),  # MISSING (silent)
]


def main():
    logger.info("=" * 70)
    logger.info("Day 25 -- Answer Intent & Understanding Engine demo")
    logger.info("=" * 70)

    results = []
    quality_counts = {}

    for turn_id, category, text, is_silent in SAMPLE_ANSWERS:
        structured = understand_answer(text, expected_category=category, turn_id=turn_id, is_silent=is_silent)
        d = structured.to_dict()
        results.append(d)

        quality_counts[d["quality"]] = quality_counts.get(d["quality"], 0) + 1

        logger.info("-" * 70)
        logger.info(f"[{turn_id}] expected_category={category!r}  is_silent={is_silent}")
        logger.info(f"  raw_text: {text!r}")
        logger.info(f"  predicted_intent={d['intent']['predicted']} confidence={d['intent']['confidence']} quality={d['quality']}")
        if d["notes"]:
            logger.info(f"  notes: {d['notes']}")
        entities = d["entities"]
        if any(entities.values()):
            logger.info(f"  entities: {entities}")

    report = {
        "total_answers": len(results),
        "quality_distribution": quality_counts,
        "results": results,
    }
    out_path = OUT_DIR / "day25_answer_intent_report.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    logger.info("=" * 70)
    logger.info(f"Quality distribution: {quality_counts}")
    logger.info(f"Report written to {out_path}")


if __name__ == "__main__":
    main()
