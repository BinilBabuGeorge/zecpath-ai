"""
Day 30 -- Screening System Testing & Optimization.

Re-tests Day 25's answer-quality classification against a human-judged
ground truth (data/ground_truth_screening/day30_manual_review.json),
comparing the CURRENT engine (with this day's fix) against the
ORIGINAL (pre-Day-30) logic to quantify a real, found-and-fixed
false-rejection bug -- same evidence-based, before/after methodology
Day 20 used for the ATS engine.

THE BUG, FOUND BY TESTING, NOT ASSUMED: Day 25's _is_vague() flagged
ANY 1-2 word answer as vague unless it was a bare yes/no -- so "5
years", "Ten lakhs", "B.Tech CSE", "Immediately", and "Thirty days"
were all being wrongly rejected as vague, despite being complete,
confident, correct answers. This is exactly the kind of answer a real
screening call produces constantly.

THE FIX (in parsers/answer_intent_engine.py): a short answer is only
treated as vague if it ALSO carries no recognizable concrete content
-- no digit, no number-word, no category-keyword signal, and none of
a narrow set of genuinely unambiguous words (immediately/immediate/
asap). This is deliberately narrow: an earlier draft of this fix also
included "remote"/"hybrid"/"onsite", which testing (case c19 below)
caught as a real overcorrection -- those words don't correspond to any
of Day 22's 7 categories, so accepting them as universally "confident"
would have let through wrong-category short answers. That draft was
corrected before shipping -- see this script's case c19.

The OLD logic is reproduced verbatim below (not re-imported) purely so
this script can compute a genuine, side-by-side before/after
comparison against the SAME ground truth, in the SAME run.
"""

import json
import logging
import re
from pathlib import Path

from parsers.answer_intent_engine import (
    understand_answer, classify_intent, AnswerQuality, _HEDGE_PHRASES,
)
from parsers.screening_scoring_engine import score_answer
from parsers.conversation_flow_engine import ConversationFlowController

GT_PATH = Path("data/ground_truth_screening/day30_manual_review.json")
OUT_DIR = Path("data/results")
LOG_DIR = Path("logs")
OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "day30_screening_system_test.log", mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("day30")


# --- The ORIGINAL (pre-Day-30) _is_vague, reproduced verbatim for a
# genuine before/after comparison -- this is NOT the shipped function
# anymore; parsers/answer_intent_engine.py has the fixed version. ---
def _old_is_vague(text: str) -> bool:
    lowered = text.lower().strip()
    if any(re.search(rf"\b{re.escape(phrase)}\b", lowered) for phrase in _HEDGE_PHRASES):
        return True
    words = lowered.split()
    if 0 < len(words) <= 2 and lowered not in {"yes", "no", "yeah", "nope"}:
        return True
    return False


def old_predicted_quality(text: str, expected_category: str, is_silent: bool) -> str:
    """Reconstructs what Day 25 would have returned BEFORE the Day 30
    fix, using the real classify_intent() (unchanged by this fix) but
    the OLD vague check, for a fair, apples-to-apples comparison.
    Applies the same notice_period -> availability alias the real
    understand_answer() applies -- classify_intent()'s category_scores
    dict is always keyed "availability", never "notice_period", so
    skipping this alias here would produce a false off_topic reading
    for any longer notice_period answer purely from a lookup-key
    mismatch in THIS reconstruction, not a real defect in the shipped
    code. Caught and fixed before this report was finalized.
    """
    if expected_category == "notice_period":
        expected_category = "availability"
    if is_silent or not text.strip():
        return "missing"
    if _old_is_vague(text):
        return "vague"
    intent = classify_intent(text)
    expected_score = intent.category_scores.get(expected_category, 0.0)
    if expected_score == 0.0:
        other_hits = {c: s for c, s in intent.category_scores.items() if c != expected_category and s > 0}
        if other_hits:
            return "off_topic"
    return "ok"


def run():
    cases = json.loads(GT_PATH.read_text())["cases"]
    logger.info("=" * 90)
    logger.info("DAY 30 -- Screening System Testing & Optimization")
    logger.info(f"Ground truth: {len(cases)} human-labeled cases")
    logger.info("=" * 90)

    old_correct = new_correct = 0
    old_false_rejections = []   # human said ok, engine said vague/off_topic/missing
    new_false_rejections = []
    rows = []

    for c in cases:
        is_silent = c["text"] == ""
        old_q = old_predicted_quality(c["text"], c["category"], is_silent)
        structured = understand_answer(c["text"], expected_category=c["category"], is_silent=is_silent)
        new_q = structured.quality.value

        old_ok = old_q == c["human_expected_quality"]
        new_ok = new_q == c["human_expected_quality"]
        old_correct += old_ok
        new_correct += new_ok

        if c["human_expected_quality"] == "ok" and old_q != "ok":
            old_false_rejections.append(c["id"])
        if c["human_expected_quality"] == "ok" and new_q != "ok":
            new_false_rejections.append(c["id"])

        rows.append({
            "id": c["id"], "category": c["category"], "text": c["text"],
            "human_expected": c["human_expected_quality"],
            "old_predicted": old_q, "old_correct": old_ok,
            "new_predicted": new_q, "new_correct": new_ok,
        })

        logger.info("-" * 90)
        logger.info(f"[{c['id']}] category={c['category']:14s} text={c['text']!r}")
        logger.info(f"  human_expected={c['human_expected_quality']:10s} old={old_q:10s}({'OK' if old_ok else 'WRONG'})  new={new_q:10s}({'OK' if new_ok else 'WRONG'})")

    total = len(cases)
    old_acc = round(old_correct / total * 100, 1)
    new_acc = round(new_correct / total * 100, 1)

    logger.info("=" * 90)
    logger.info(f"OLD accuracy: {old_correct}/{total} ({old_acc}%)")
    logger.info(f"NEW accuracy: {new_correct}/{total} ({new_acc}%)")
    logger.info(f"OLD false rejections (human=ok, engine!=ok): {old_false_rejections} ({len(old_false_rejections)})")
    logger.info(f"NEW false rejections (human=ok, engine!=ok): {new_false_rejections} ({len(new_false_rejections)})")

    # --- Downstream scoring impact (Day 26) -- quantify what the false
    # rejections actually cost in the final screening score, not just
    # a classification label change.
    logger.info("-" * 90)
    logger.info("Downstream Day 26 scoring impact on the originally-misclassified cases:")
    import dataclasses
    scoring_deltas = []
    for c in cases:
        if c["id"] not in old_false_rejections:
            continue
        structured = understand_answer(c["text"], expected_category=c["category"])
        new_score = score_answer(structured).weighted_total
        old_structured = dataclasses.replace(structured, quality=AnswerQuality.VAGUE if old_predicted_quality(c["text"], c["category"], False) == "vague" else structured.quality)
        old_score = score_answer(old_structured).weighted_total
        scoring_deltas.append({"id": c["id"], "text": c["text"], "old_score": old_score, "new_score": new_score})
        logger.info(f"  [{c['id']}] {c['text']!r}: old_score={old_score}  new_score={new_score}  (+{round(new_score - old_score, 1)})")

    # --- Cross-day consequence check (Day 29) -- confirm the fix also
    # improves live conversation flow, not just offline scoring.
    logger.info("-" * 90)
    logger.info("Cross-day check: Day 29 conversation flow on the same fixed cases:")
    flow_results = []
    for c in cases:
        if c["id"] not in old_false_rejections:
            continue
        controller = ConversationFlowController(categories=[c["category"]])
        action = controller.process_turn(c["text"])
        flow_results.append({"id": c["id"], "text": c["text"], "action": action.action_type.value})
        if c["id"] in new_false_rejections:
            logger.info(f"  [{c['id']}] {c['text']!r}: Day 29 still takes action={action.action_type.value!r} -- "
                         f"UNCHANGED, since this case's classification is still wrong (see known limitation).")
        else:
            logger.info(f"  [{c['id']}] {c['text']!r}: Day 29 now takes action={action.action_type.value!r} on first attempt "
                         f"(previously would have been 'ask_fallback', consuming a retry on a perfectly good answer)")

    report = {
        "total_cases": total,
        "old_accuracy_pct": old_acc, "new_accuracy_pct": new_acc,
        "old_false_rejections": old_false_rejections, "new_false_rejections": new_false_rejections,
        "case_results": rows,
        "downstream_scoring_impact": scoring_deltas,
        "conversation_flow_impact": flow_results,
    }
    out_path = OUT_DIR / "day30_screening_system_test_report.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info("=" * 90)
    logger.info(f"Report written to {out_path}")


if __name__ == "__main__":
    run()
