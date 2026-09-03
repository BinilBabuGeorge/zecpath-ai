"""
Screening Scoring Engine (Day 26)

SCOPE, STATED HONESTLY UP FRONT: scoring here is rule-based and
explainable -- deterministic formulas over Day 25's StructuredAnswer
output -- not a trained scoring model. Same reasoning as every prior
day: no labeled "good answer" training data exists in this project,
so a claimed ML scorer would be fabricated. What's real: a genuine,
independently-tested, four-parameter scoring formula (Clarity,
Relevance, Completeness, Consistency) with every component visible in
the output, not collapsed into an opaque single number.

Pipeline position:

    audio -> STTProvider.transcribe()   (Day 24)
          -> clean_transcript()          (Day 24)
          -> understand_answer()         (Day 25) -> StructuredAnswer
          -> score_screening_call()      (Day 26, THIS module)
          -> ScreeningScoreResult

The four scoring parameters, and why each is computed the way it is:

  - Clarity: how well-formed the answer was, independent of whether it
    was even on-topic. Derived from Day 25's intent-classification
    confidence and quality bucket -- a confident classification means
    the answer's content was unambiguous; a VAGUE/MISSING answer is
    definitionally unclear.
  - Relevance: how much of the answer's content was actually about
    what was asked. Computed as the expected category's keyword/entity
    score as a share of everything the answer scored on -- an answer
    that's 90% skills-talk and 10% intro-phrasing when asked to
    introduce themselves is graded as mostly-relevant, not a flat
    pass/fail.
  - Completeness: for questions expecting a concrete extractable value
    (experience/salary/availability), did Day 25 actually manage to
    pull one out? For open-ended categories (introduction/skills/
    education/location), completeness tracks whether a substantive
    on-topic answer was given at all.
  - Consistency: CANNOT be judged from a single answer in isolation --
    honestly requires comparing every answer a candidate gave across
    the whole call (e.g. "three years" in one answer vs "five years"
    in another). score_answer() defaults this to a neutral placeholder;
    the real check runs in score_screening_call() once every answer is
    available, and only then are affected questions' scores updated.
    This two-pass design is a deliberate, documented consequence of an
    honest constraint, not an oversight.

Per-category weighting reuses the same pattern as Day 13's
WEIGHT_PROFILES: a "structured" question (experience/salary/
availability) is asking for a fact, so completeness matters more; an
"open_ended" question (introduction/skills/education/location) is
asking for description, so clarity matters more.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from parsers.answer_intent_engine import AnswerQuality, StructuredAnswer

# ---------------------------------------------------------------------------
# Weight profiles -- same reasoning/shape as Day 13's WEIGHT_PROFILES
# ---------------------------------------------------------------------------

_STRUCTURED_CATEGORIES = {"experience", "salary", "availability"}
_OPEN_ENDED_CATEGORIES = {"introduction", "skills", "education", "location"}

WEIGHT_PROFILES: Dict[str, Dict[str, float]] = {
    "structured":  {"clarity": 0.15, "relevance": 0.30, "completeness": 0.40, "consistency": 0.15},
    "open_ended":  {"clarity": 0.35, "relevance": 0.35, "completeness": 0.20, "consistency": 0.10},
    "default":     {"clarity": 0.25, "relevance": 0.25, "completeness": 0.25, "consistency": 0.25},
}


def _weight_profile_for(category: str) -> Dict[str, float]:
    if category in _STRUCTURED_CATEGORIES:
        return WEIGHT_PROFILES["structured"]
    if category in _OPEN_ENDED_CATEGORIES:
        return WEIGHT_PROFILES["open_ended"]
    return WEIGHT_PROFILES["default"]


@dataclass
class ScoreComponent:
    score: float                  # 0-100
    note: Optional[str] = None


@dataclass
class QuestionScore:
    turn_id: Optional[str]
    question_category: str
    quality: AnswerQuality
    components: Dict[str, ScoreComponent]   # keys: clarity, relevance, completeness, consistency
    weighted_total: float                   # 0-100, this question's normalized score
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "turn_id": self.turn_id,
            "question_category": self.question_category,
            "quality": self.quality.value,
            "components": {k: {"score": v.score, "note": v.note} for k, v in self.components.items()},
            "weighted_total": self.weighted_total,
            "notes": self.notes,
        }


@dataclass
class ScreeningScoreResult:
    total_score: float                      # 0-100, average of all question weighted_totals
    question_scores: List[QuestionScore]
    consistency_findings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "total_score": self.total_score,
            "consistency_findings": self.consistency_findings,
            "question_scores": [q.to_dict() for q in self.question_scores],
        }


# ---------------------------------------------------------------------------
# 1. Per-question component scoring
# ---------------------------------------------------------------------------

def _clarity_score(answer: StructuredAnswer) -> ScoreComponent:
    if answer.quality == AnswerQuality.MISSING:
        return ScoreComponent(0.0, "No speech to assess clarity of.")
    if answer.quality == AnswerQuality.VAGUE:
        return ScoreComponent(25.0, "Hedged/non-committal answer -- inherently unclear.")
    # OK or OFF_TOPIC: the candidate said something unambiguous (even if
    # about the wrong topic) -- clarity tracks HOW confidently that
    # content classified, not WHETHER it was the right content.
    confidence_score = round(answer.intent.confidence * 100, 1)
    floored = max(confidence_score, 40.0)   # they clearly said *something* substantive
    note = None if confidence_score >= 40.0 else "Low classification confidence -- answer content was ambiguous across categories."
    return ScoreComponent(floored, note)


def _relevance_score(answer: StructuredAnswer) -> ScoreComponent:
    if answer.quality == AnswerQuality.MISSING:
        return ScoreComponent(0.0, "No answer given.")
    if answer.quality == AnswerQuality.OFF_TOPIC:
        return ScoreComponent(0.0, "Answer's content matched a different category entirely.")
    if answer.quality == AnswerQuality.VAGUE:
        return ScoreComponent(20.0, "Too thin to judge relevance beyond 'attempted to engage'.")

    scores = answer.intent.category_scores
    total = sum(scores.values())
    expected_score = scores.get(answer.question_category, 0.0)
    if total == 0.0:
        return ScoreComponent(60.0, "On-topic by quality gate, but no category scored -- moderate default credit.")
    pct = round(expected_score / total * 100, 1)
    note = None if pct >= 60 else "Answer touched the expected topic but was mostly about something else."
    return ScoreComponent(pct, note)


def _completeness_score(answer: StructuredAnswer) -> ScoreComponent:
    if answer.quality == AnswerQuality.MISSING:
        return ScoreComponent(0.0, "No answer to extract anything from.")
    if answer.quality == AnswerQuality.OFF_TOPIC:
        return ScoreComponent(0.0, "Didn't address what was actually asked.")
    if answer.quality == AnswerQuality.VAGUE:
        return ScoreComponent(10.0, "Non-answer -- nothing concrete was said.")

    category = answer.question_category
    if category in _STRUCTURED_CATEGORIES:
        field_map = {
            "experience": answer.entities.experience_years,
            "salary": answer.entities.salary_expectation,
            "availability": answer.entities.availability,
        }
        extracted = field_map.get(category)
        if extracted is not None:
            return ScoreComponent(100.0, None)
        return ScoreComponent(40.0, "On-topic, but Day 25 could not extract a concrete value from it.")

    # Open-ended categories: a substantive on-topic answer IS the
    # complete deliverable -- there's no single field to check for.
    return ScoreComponent(100.0, None)


def score_answer(answer: StructuredAnswer) -> QuestionScore:
    """Scores one answer on Clarity, Relevance, and Completeness.
    Consistency is deliberately left at a neutral placeholder here --
    see module docstring -- and is only meaningfully computed by
    score_screening_call() once every answer from the call is
    available for cross-checking.
    """
    clarity = _clarity_score(answer)
    relevance = _relevance_score(answer)
    completeness = _completeness_score(answer)
    consistency = ScoreComponent(100.0, "Not yet cross-checked against the candidate's other answers.")

    components = {
        "clarity": clarity, "relevance": relevance,
        "completeness": completeness, "consistency": consistency,
    }
    weighted_total = _weighted_total(components, answer.question_category)

    return QuestionScore(
        turn_id=answer.turn_id, question_category=answer.question_category,
        quality=answer.quality, components=components, weighted_total=weighted_total,
        notes=list(answer.notes),
    )


def _weighted_total(components: Dict[str, ScoreComponent], category: str) -> float:
    weights = _weight_profile_for(category)
    total = sum(components[name].score * weight for name, weight in weights.items())
    return round(total, 1)


# ---------------------------------------------------------------------------
# 2. Cross-answer consistency check -- the honest reason this is a
#    two-pass design (see module docstring)
# ---------------------------------------------------------------------------

_EXPERIENCE_TOLERANCE_YEARS = 1.0


def _check_consistency(answers: List[StructuredAnswer], scores: List[QuestionScore]) -> List[str]:
    findings: List[str] = []
    by_turn = {qs.turn_id: qs for qs in scores}

    # -- Experience years, mentioned in any answer, not just "experience"-category ones
    exp_mentions = [(a.turn_id, a.entities.experience_years) for a in answers if a.entities.experience_years is not None]
    if len(exp_mentions) >= 2:
        values = [v for _, v in exp_mentions]
        if max(values) - min(values) > _EXPERIENCE_TOLERANCE_YEARS:
            turn_ids = [t for t, _ in exp_mentions]
            findings.append(
                f"Experience-years mismatch across answers {turn_ids}: values {values} disagree by more than "
                f"{_EXPERIENCE_TOLERANCE_YEARS} year(s)."
            )
            for turn_id in turn_ids:
                qs = by_turn.get(turn_id)
                if qs is not None:
                    qs.components["consistency"] = ScoreComponent(
                        40.0, f"Experience-years conflicts with another answer in this call: {values}."
                    )
        else:
            for turn_id, _ in exp_mentions:
                qs = by_turn.get(turn_id)
                if qs is not None:
                    qs.components["consistency"] = ScoreComponent(100.0, "Experience-years confirmed consistent with other answers.")

    # -- Salary expectations: only directly comparable when units match;
    # differing units is an honest "cannot verify," not a penalty --
    # same "don't guess a conversion" stance as Day 25's extractor.
    salary_mentions = [(a.turn_id, a.entities.salary_expectation) for a in answers if a.entities.salary_expectation is not None]
    if len(salary_mentions) >= 2:
        units = {s["unit"] for _, s in salary_mentions}
        if len(units) == 1:
            amounts = [s["amount"] for _, s in salary_mentions]
            unit = next(iter(units))
            # A candidate stating a range (current vs. expected) is normal,
            # not a conflict -- only flag genuinely far-apart figures.
            spread_ratio = (max(amounts) - min(amounts)) / max(amounts) if max(amounts) else 0
            if spread_ratio > 0.6:
                turn_ids = [t for t, _ in salary_mentions]
                findings.append(f"Salary figures across answers {turn_ids} vary widely ({amounts} {unit}) -- worth a follow-up.")
        else:
            findings.append(
                f"Salary mentioned with different units across answers ({units}) -- cannot verify consistency "
                "without guessing a conversion, so not penalized."
            )

    # -- Availability: "immediate" in one answer vs. a specific non-zero
    # notice period in another is a direct contradiction.
    availability_mentions = [(a.turn_id, a.entities.availability) for a in answers if a.entities.availability is not None]
    if len(availability_mentions) >= 2:
        immediate_flags = {av.get("immediate", False) for _, av in availability_mentions}
        nonzero_amounts = [av.get("amount", 0) for _, av in availability_mentions if not av.get("immediate", False)]
        if True in immediate_flags and any(a and a > 0 for a in nonzero_amounts):
            turn_ids = [t for t, _ in availability_mentions]
            findings.append(f"Availability conflict across answers {turn_ids}: 'immediate' stated alongside a non-zero notice period.")
            for turn_id in turn_ids:
                qs = by_turn.get(turn_id)
                if qs is not None:
                    qs.components["consistency"] = ScoreComponent(40.0, "Availability conflicts with another answer in this call.")

    return findings


# ---------------------------------------------------------------------------
# 3. Aggregate entry point -- the "screening scoring engine" deliverable
# ---------------------------------------------------------------------------

def score_screening_call(answers: List[StructuredAnswer]) -> ScreeningScoreResult:
    """Scores every answer from one candidate's screening call and
    returns the aggregated, explainable result -- the Day 26
    deliverable's three parts: per-question score breakdown
    (QuestionScore list), the final screening score object
    (ScreeningScoreResult), and every component visible for audit.
    """
    if not answers:
        return ScreeningScoreResult(total_score=0.0, question_scores=[], consistency_findings=["No answers to score."])

    question_scores = [score_answer(a) for a in answers]
    consistency_findings = _check_consistency(answers, question_scores)

    # Recompute weighted_total for any question whose consistency
    # component changed during the cross-check above. Questions not
    # involved in any cross-check keep their neutral default -- there
    # was nothing to compare them against, which is different from
    # "checked and found consistent," so the note is corrected here to
    # say so honestly rather than leave the pre-check wording in place.
    for qs in question_scores:
        if qs.components["consistency"].note == "Not yet cross-checked against the candidate's other answers.":
            qs.components["consistency"] = ScoreComponent(
                100.0, "No comparable field in another answer to cross-check against."
            )
        qs.weighted_total = _weighted_total(qs.components, qs.question_category)

    total_score = round(sum(qs.weighted_total for qs in question_scores) / len(question_scores), 1)

    return ScreeningScoreResult(
        total_score=total_score, question_scores=question_scores,
        consistency_findings=consistency_findings,
    )
