"""
Confidence & Stress Indicators (Day 36)

WHAT THIS DAY ADDS: Day 27 already built hesitation detection,
sentiment analysis, and uncertainty-marker detection -- but scoped to
the SCREENING call phase (Days 22-32), consuming `StructuredAnswer`
objects and reusing Day 26's contradiction findings. Neither exists in
the HR-interview phase (Days 33-35), which works with
`InterviewSession` / `InterviewQuestionState` and plain response text
-- the same phase/input-type gap Day 35 filled for communication
skill, and Day 34 filled for follow-up logic. This day is the
HR-interview-phase counterpart for CONFIDENCE AND STRESS specifically.

REUSE, NOT REIMPLEMENTATION:
  - `detect_hesitation()`, `analyze_sentiment()`, and
    `detect_uncertainty()` are imported DIRECTLY from Day 27's
    `confidence_sentiment_engine`, unchanged. All three already take
    plain `text: str` with nothing screening-specific in their
    signature or logic -- they were only ever *called* from a
    screening-scoped pipeline, not *built* for one. This is a stronger
    case for reuse than Day 34/35's, where the reused functions were
    generic but still needed a new caller; here the functions apply
    with zero adaptation.
  - `assess_grammar()` is imported from Day 35's
    `communication_skill_engine` for its `repeated_word_pairs` field
    -- built there to catch a grammar error, reused here for a
    different purpose: consecutive word repetition ("I I want to...")
    is also a classic verbal disfluency / hesitation marker. Same
    function, two legitimate uses, not two implementations.

SCOPE, STATED HONESTLY UP FRONT:
  - **"Long pauses" are NOT computed.** Day 24's speech-to-text layer
    is a documented mock with no real audio pipeline behind it -- pause
    timing requires audio, which does not exist here. Every result
    reports `long_pauses_detected: None` with a note, the same honest
    "not computed" pattern Day 27 used for words-per-minute pace,
    rather than silently omitting the field or faking a value.
  - **"Stress indicators" are a LINGUISTIC PROXY, not a physiological
    measurement.** Real stress detection would use vocal pitch, galvanic
    skin response, or similar biometric signals -- none of which is
    available. What this module actually measures is a combination of
    hesitation rate, uncertainty density, disfluent repetition, and
    negative/mixed sentiment: a reasonable, explainable stand-in, named
    as such rather than oversold as detecting real physiological stress.
  - **"Contradiction patterns" for behavioral answers are NOT the same
    kind of check as Day 26's.** Day 26 compares literal factual claims
    (stated years of experience vs. stated graduation year) for logical
    inconsistency -- that has no equivalent for behavioral answers
    ("tell me about a time you led a team"), which have no factual
    payload to cross-check. What this module does instead: (1) flags
    single answers with strongly mixed sentiment (both several positive
    and several negative words), and (2) flags large sentiment swings
    between consecutive answers as *possible* inconsistency. Both are
    coarse heuristic proxies, explicitly labeled `possible_` rather than
    asserted as confirmed contradictions -- a real semantic entailment
    check is out of scope for a rule-based, pattern-matching project.

NORMALIZING TO REDUCE BIAS (consistent with Days 34/35): every
component score is independently clamped to 0-100 before combining,
and the behavioral confidence score's penalties are individually
capped (see `_*_PENALTY_CAP` constants) so no single heuristic can
sink the whole score by itself. The same known limitation from Day 27
still applies and is not re-solved here: filler-word and disfluency
detection on text alone is weaker than on audio, and a candidate
answering in a second language may show more hesitation markers and
repeated words for reasons that have nothing to do with confidence or
stress -- flagged, not corrected for, since no rule-based text fix
exists for that gap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from parsers.confidence_sentiment_engine import (
    HesitationResult, SentimentResult, UncertaintyResult,
    detect_hesitation, analyze_sentiment, detect_uncertainty,
)
from parsers.communication_skill_engine import assess_grammar
from parsers.hr_interview_question_bank import InterviewQuestionState, InterviewSession

_HESITATION_PENALTY_CAP = 30.0
_UNCERTAINTY_PENALTY_CAP = 30.0
_REPEATED_WORD_PENALTY_CAP = 20.0
_INCONSISTENCY_PENALTY_CAP = 20.0
_INCONSISTENCY_PENALTY_PER_FLAG = 10.0
_SENTIMENT_ADJUSTMENT_SCALE = 0.2

_MIXED_SENTIMENT_MIN_HITS = 2          # both polarities need >= this many hits to flag "mixed"
_SENTIMENT_SWING_THRESHOLD = 40.0      # |delta| between consecutive answers' sentiment scores

_STRESS_HESITATION_WEIGHT = 1.5
_STRESS_UNCERTAINTY_WEIGHT = 1.5
_STRESS_REPEATED_WORD_WEIGHT = 10.0
_STRESS_NEGATIVE_SENTIMENT_BONUS = 15.0
_STRESS_MIXED_SENTIMENT_BONUS = 10.0


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


# ---------------------------------------------------------------------------
# 1. Per-answer hesitation bundle -- fillers (Day 27) + uncertainty (Day 27)
#    + repeated words (Day 35's grammar checker, reused for a new purpose)
# ---------------------------------------------------------------------------

@dataclass
class HesitationPatternResult:
    hesitation: HesitationResult
    uncertainty: UncertaintyResult
    repeated_word_pairs: List[str]
    long_pauses_detected: Optional[bool]   # always None -- see module docstring
    long_pauses_note: str


def detect_hesitation_patterns(text: str) -> HesitationPatternResult:
    return HesitationPatternResult(
        hesitation=detect_hesitation(text),
        uncertainty=detect_uncertainty(text),
        repeated_word_pairs=assess_grammar(text).repeated_word_pairs,
        long_pauses_detected=None,
        long_pauses_note="Not computed -- pause timing requires real audio, and Day 24's STT layer is a documented mock with no timing output.",
    )


# ---------------------------------------------------------------------------
# 2. Contradiction / inconsistency patterns -- explicitly a coarse proxy,
#    not the factual cross-check Day 26 does for screening answers.
# ---------------------------------------------------------------------------

@dataclass
class InconsistencyFlags:
    mixed_sentiment_within_answer: bool
    cross_answer_swings: List[str]   # human-readable descriptions, e.g. "hr-q01 -> hr-q02: +65"


def _detect_mixed_sentiment(sentiment: SentimentResult) -> bool:
    return len(sentiment.positive_hits) >= _MIXED_SENTIMENT_MIN_HITS and len(sentiment.negative_hits) >= _MIXED_SENTIMENT_MIN_HITS


def _detect_cross_answer_swings(question_ids: List[str], sentiment_scores: List[float]) -> List[str]:
    swings = []
    for i in range(1, len(sentiment_scores)):
        delta = sentiment_scores[i] - sentiment_scores[i - 1]
        if abs(delta) >= _SENTIMENT_SWING_THRESHOLD:
            swings.append(f"{question_ids[i-1]} -> {question_ids[i]}: {delta:+.1f} (possible inconsistency, not confirmed)")
    return swings


# ---------------------------------------------------------------------------
# 3. Stress indicators -- a linguistic proxy, not a physiological measurement
# ---------------------------------------------------------------------------

@dataclass
class StressIndicatorResult:
    stress_score: float   # 0-100, higher = more stress-indicative language
    component_breakdown: Dict[str, float]


def measure_stress_indicators(
    hesitation_patterns: HesitationPatternResult, sentiment: SentimentResult,
) -> StressIndicatorResult:
    mixed = _detect_mixed_sentiment(sentiment)

    score = 0.0
    score += hesitation_patterns.hesitation.hesitation_rate_per_100_words * _STRESS_HESITATION_WEIGHT
    score += hesitation_patterns.uncertainty.uncertainty_rate_per_100_words * _STRESS_UNCERTAINTY_WEIGHT
    score += len(hesitation_patterns.repeated_word_pairs) * _STRESS_REPEATED_WORD_WEIGHT
    if sentiment.label == "negative":
        score += _STRESS_NEGATIVE_SENTIMENT_BONUS
    if mixed:
        score += _STRESS_MIXED_SENTIMENT_BONUS

    breakdown = {
        "hesitation_contribution": round(hesitation_patterns.hesitation.hesitation_rate_per_100_words * _STRESS_HESITATION_WEIGHT, 1),
        "uncertainty_contribution": round(hesitation_patterns.uncertainty.uncertainty_rate_per_100_words * _STRESS_UNCERTAINTY_WEIGHT, 1),
        "repeated_word_contribution": round(len(hesitation_patterns.repeated_word_pairs) * _STRESS_REPEATED_WORD_WEIGHT, 1),
        "negative_sentiment_bonus": _STRESS_NEGATIVE_SENTIMENT_BONUS if sentiment.label == "negative" else 0.0,
        "mixed_sentiment_bonus": _STRESS_MIXED_SENTIMENT_BONUS if mixed else 0.0,
    }
    return StressIndicatorResult(stress_score=round(_clamp(score), 1), component_breakdown=breakdown)


# ---------------------------------------------------------------------------
# 4. Per-answer confidence evaluation
# ---------------------------------------------------------------------------

@dataclass
class AnswerConfidenceEvaluation:
    question_id: Optional[str]
    category: Optional[str]
    hesitation_patterns: HesitationPatternResult
    sentiment: SentimentResult
    stress: StressIndicatorResult
    mixed_sentiment_flag: bool
    behavioral_confidence_score: float
    component_breakdown: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "question_id": self.question_id,
            "category": self.category,
            "behavioral_confidence_score": self.behavioral_confidence_score,
            "component_breakdown": self.component_breakdown,
            "mixed_sentiment_flag": self.mixed_sentiment_flag,
            "stress": {"stress_score": self.stress.stress_score, "breakdown": self.stress.component_breakdown},
            "sentiment": {"label": self.sentiment.label, "score": self.sentiment.score},
            "hesitation": {
                "filler_count": self.hesitation_patterns.hesitation.filler_count,
                "hesitation_rate_per_100_words": self.hesitation_patterns.hesitation.hesitation_rate_per_100_words,
                "uncertainty_rate_per_100_words": self.hesitation_patterns.uncertainty.uncertainty_rate_per_100_words,
                "repeated_word_pairs": self.hesitation_patterns.repeated_word_pairs,
                "long_pauses_note": self.hesitation_patterns.long_pauses_note,
            },
        }


def evaluate_answer_confidence(text: str, question_id: Optional[str] = None, category: Optional[str] = None) -> AnswerConfidenceEvaluation:
    hesitation_patterns = detect_hesitation_patterns(text)
    sentiment = analyze_sentiment(text)
    stress = measure_stress_indicators(hesitation_patterns, sentiment)
    mixed = _detect_mixed_sentiment(sentiment)

    hesitation_penalty = min(_HESITATION_PENALTY_CAP, hesitation_patterns.hesitation.hesitation_rate_per_100_words * 2)
    uncertainty_penalty = min(_UNCERTAINTY_PENALTY_CAP, hesitation_patterns.uncertainty.uncertainty_rate_per_100_words * 2)
    repeated_word_penalty = min(_REPEATED_WORD_PENALTY_CAP, len(hesitation_patterns.repeated_word_pairs) * 10.0)
    mixed_penalty = 10.0 if mixed else 0.0
    sentiment_adjustment = round(sentiment.score * _SENTIMENT_ADJUSTMENT_SCALE, 1)

    raw_score = 100.0 - hesitation_penalty - uncertainty_penalty - repeated_word_penalty - mixed_penalty + sentiment_adjustment
    score = round(_clamp(raw_score), 1)

    breakdown = {
        "base": 100.0,
        "hesitation_penalty": -round(hesitation_penalty, 1),
        "uncertainty_penalty": -round(uncertainty_penalty, 1),
        "repeated_word_penalty": -round(repeated_word_penalty, 1),
        "mixed_sentiment_penalty": -mixed_penalty,
        "sentiment_adjustment": sentiment_adjustment,
    }

    return AnswerConfidenceEvaluation(
        question_id=question_id, category=category, hesitation_patterns=hesitation_patterns,
        sentiment=sentiment, stress=stress, mixed_sentiment_flag=mixed,
        behavioral_confidence_score=score, component_breakdown=breakdown,
    )


# ---------------------------------------------------------------------------
# 5. Interview-level aggregate -- the "confidence analyzer module" +
#    "behavioral signal logic" deliverables applied across a full session
# ---------------------------------------------------------------------------

@dataclass
class InterviewConfidenceProfile:
    answer_evaluations: List[AnswerConfidenceEvaluation]
    overall_behavioral_confidence_score: float
    overall_stress_score: float
    inconsistency_flags: InconsistencyFlags

    def to_dict(self) -> Dict:
        return {
            "overall_behavioral_confidence_score": self.overall_behavioral_confidence_score,
            "overall_stress_score": self.overall_stress_score,
            "inconsistency_flags": {
                "mixed_sentiment_within_answer_count": sum(1 for e in self.answer_evaluations if e.mixed_sentiment_flag),
                "cross_answer_swings": self.inconsistency_flags.cross_answer_swings,
            },
            "answer_evaluations": [e.to_dict() for e in self.answer_evaluations],
        }


def build_confidence_profile(session: InterviewSession) -> InterviewConfidenceProfile:
    """HR-interview-phase counterpart to Day 27's
    `build_communication_profile()` -- same "aggregate from per-answer
    signals" shape, different input type (`InterviewSession`) and a
    different, honestly-scoped contradiction mechanism (cross-answer
    sentiment-swing flags instead of Day 26's factual cross-check,
    which has no behavioral-answer equivalent -- see module docstring).
    """
    answered: List[InterviewQuestionState] = [q for q in session.questions if q.response_captured and q.response_text]

    if not answered:
        return InterviewConfidenceProfile(
            answer_evaluations=[], overall_behavioral_confidence_score=0.0, overall_stress_score=0.0,
            inconsistency_flags=InconsistencyFlags(mixed_sentiment_within_answer=False, cross_answer_swings=[]),
        )

    evaluations = [
        evaluate_answer_confidence(q.response_text, question_id=q.question_id, category=q.category)
        for q in answered
    ]

    question_ids = [e.question_id for e in evaluations]
    sentiment_scores = [e.sentiment.score for e in evaluations]
    swings = _detect_cross_answer_swings(question_ids, sentiment_scores)

    overall_confidence = round(sum(e.behavioral_confidence_score for e in evaluations) / len(evaluations), 1)
    overall_stress = round(sum(e.stress.stress_score for e in evaluations) / len(evaluations), 1)

    # Cross-answer swings additionally pull down the overall confidence
    # score (a per-answer score can't reflect a pattern that only shows
    # up across answers), capped the same way every other penalty here is.
    swing_penalty = min(_INCONSISTENCY_PENALTY_CAP, len(swings) * _INCONSISTENCY_PENALTY_PER_FLAG)
    overall_confidence = round(_clamp(overall_confidence - swing_penalty), 1)

    return InterviewConfidenceProfile(
        answer_evaluations=evaluations, overall_behavioral_confidence_score=overall_confidence,
        overall_stress_score=overall_stress,
        inconsistency_flags=InconsistencyFlags(
            mixed_sentiment_within_answer=any(e.mixed_sentiment_flag for e in evaluations), cross_answer_swings=swings,
        ),
    )
