"""
Screening System Finalization (Day 32)

WHAT THIS DAY ACTUALLY ADDS: everything Days 22-31 built has been
tested adjacent-pair by adjacent-pair (Day 25 against Day 24's output,
Day 26 against Day 25's, Day 29 against Day 25's, Day 31 wrapping
Day 29) -- but no single call has ever run start to finish through the
WHOLE chain: question bank -> robust conversation flow (with edge-case
handling) -> per-turn answer understanding -> screening score ->
communication profile -> final report. That gap is what this module
closes. Nothing here is new analysis logic -- it is integration only,
wiring real, already-tested pieces together for the first time.

Pipeline assembled:

    Day 22 CATEGORIES
        -> Day 31 RobustConversationController (wraps Day 29, which
           reuses Day 25 understand_answer() per turn)
        -> per-category final StructuredAnswer, collected as the call
           progresses
        -> Day 26 score_screening_call()
        -> Day 27 build_communication_profile()
        -> Day 28 generate_screening_report()

A question a candidate never gave a usable answer to -- because the
call ended early, or because an edge case (Day 31) exhausted its
retries without ever producing text Day 25 could evaluate -- is
represented as a synthesized MISSING StructuredAnswer with a note
explaining WHY it's missing (no answer at all, vs. skipped after
repeated poor audio, vs. skipped after a language mismatch). This
distinction is real and worth keeping: a recruiter reading the final
report should be able to tell "the candidate never got to this
question" apart from "the candidate refused/couldn't answer it,"
which is exactly the kind of honest bookkeeping this project has
maintained throughout.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from parsers.speech_to_text import RawSTTResult
from parsers.screening_question_bank import CATEGORIES
from parsers.answer_intent_engine import (
    StructuredAnswer, AnswerQuality, AnswerIntent, IntentClassification, ExtractedEntities,
)
from parsers.screening_scoring_engine import score_screening_call, ScreeningScoreResult
from parsers.confidence_sentiment_engine import build_communication_profile, CommunicationProfile
from parsers.screening_report_generator import generate_screening_report, ScreeningReport
from parsers.edge_case_handler import RobustConversationController, EdgeCaseAction


def _missing_placeholder(category: str, reason: str) -> StructuredAnswer:
    """A synthesized stand-in for a category the candidate never
    produced a usable answer for. Scores as MISSING throughout Day
    26/27/28 exactly like a real silent turn would -- the only
    difference is the note explaining why, which is real information
    (call ended early vs. edge case exhaustion vs. genuine silence)
    worth preserving for whoever reads the final report.
    """
    return StructuredAnswer(
        raw_text="", question_category=category,
        intent=IntentClassification(intent=AnswerIntent.UNKNOWN, confidence=0.0, category_scores={}, note="Not answered."),
        quality=AnswerQuality.MISSING, entities=ExtractedEntities(),
        notes=[reason], turn_id=None,
    )


_EDGE_CASE_SKIP_ACTIONS = {
    EdgeCaseAction.SAFETY_FALLBACK_SKIP, EdgeCaseAction.SAFETY_FALLBACK_END_CALL, EdgeCaseAction.CRASH_GUARD_SKIP,
}


@dataclass
class EndToEndCallResult:
    report: ScreeningReport
    scoring_result: ScreeningScoreResult
    communication_profile: CommunicationProfile
    controller: RobustConversationController
    categories_answered: List[str]
    categories_missing: List[str]


def run_screening_call(
    turns: List[RawSTTResult],
    categories: Optional[List[str]] = None,
    candidate_id: Optional[str] = None,
    job_role: Optional[str] = None,
) -> EndToEndCallResult:
    """Runs one full simulated candidate call through every layer built
    across Days 22-31 and returns the final, recruiter-facing report
    plus the intermediate results (for auditability -- nothing here is
    hidden behind the final report alone).
    """
    resolved_categories = list(categories) if categories is not None else list(CATEGORIES)
    controller = RobustConversationController(categories=resolved_categories)

    final_by_category: Dict[str, StructuredAnswer] = {}
    skip_reason_by_category: Dict[str, str] = {}

    for raw in turns:
        if controller.is_call_complete:
            break
        category_before = controller.current_category
        outcome = controller.process_turn(raw)

        underlying = outcome.underlying_action
        if underlying is not None and underlying.structured_answer is not None:
            final_by_category[category_before] = underlying.structured_answer
        elif outcome.action in _EDGE_CASE_SKIP_ACTIONS and category_before is not None:
            reason = outcome.notes[0] if outcome.notes else outcome.action.value
            skip_reason_by_category[category_before] = f"Skipped due to an edge case, not a genuine non-answer -- {reason}"

    all_answers: List[StructuredAnswer] = []
    categories_answered, categories_missing = [], []
    for category in resolved_categories:
        if category in final_by_category and final_by_category[category].quality != AnswerQuality.MISSING:
            all_answers.append(final_by_category[category])
            categories_answered.append(category)
        elif category in final_by_category:
            # Genuinely reached and genuinely silent -- Day 25/29's own
            # MISSING, not an edge-case skip. Kept as-is, not re-wrapped.
            all_answers.append(final_by_category[category])
            categories_missing.append(category)
        else:
            reason = skip_reason_by_category.get(category, "The call ended before this question was reached.")
            all_answers.append(_missing_placeholder(category, reason))
            categories_missing.append(category)

    scoring_result = score_screening_call(all_answers)
    communication_profile = build_communication_profile(all_answers, scoring_result.consistency_findings)
    report = generate_screening_report(
        all_answers, scoring_result, communication_profile,
        candidate_id=candidate_id, job_role=job_role,
    )

    return EndToEndCallResult(
        report=report, scoring_result=scoring_result, communication_profile=communication_profile,
        controller=controller, categories_answered=categories_answered, categories_missing=categories_missing,
    )
