"""
Confidence & Sentiment Signal Analysis (Day 27)

SCOPE, STATED HONESTLY UP FRONT: every signal here is a deterministic,
lexicon/pattern-based heuristic -- not a trained sentiment/confidence
model. Same reasoning as every prior day: no labeled sentiment or
confidence training data exists in this project. What's real: a
genuinely useful set of rule-based communication signals, each one
independently visible and explainable, built on top of Day 25/26's
already-tested output rather than duplicating their logic.

A specific, honestly-flagged limitation worth stating before anything
else: hesitation/filler detection on TEXT ALONE is fundamentally
weaker than on audio. A real disfluency detector would use pause
timing, pitch, and speech rate from the audio signal -- none of which
exists here, because Day 24's speech-to-text layer is a documented
mock with no real audio pipeline behind it (see Day 24's docs). This
module can only count word-level filler patterns in the transcribed
text, and several common filler words ("like", "actually", "basically",
"well") are also ordinary content words ("I like React" vs. "it's,
like, really hard to explain") -- this is called out explicitly below,
not smoothed over.

Pipeline position:

    audio -> STTProvider.transcribe()      (Day 24)
          -> clean_transcript()             (Day 24)
          -> understand_answer()            (Day 25) -> StructuredAnswer
          -> score_screening_call()         (Day 26) -> ScreeningScoreResult
          -> build_communication_profile()  (Day 27, THIS module)
          -> CommunicationProfile

Contradiction detection is NOT re-implemented here -- Day 26's
score_screening_call() already cross-checks every answer in a call
against every other and produces consistency_findings. Day 27 reuses
that list as-is for its "detect uncertainty and contradictions" task
rather than duplicating the comparison logic, exactly the same reuse
discipline Day 25/26 applied to Day 23's normalize_answer().

This module's output (communication_strength_score) is the concrete,
finally-real implementation of the `communication_score` field that
`interview_ai/service.py` and `scoring/service.py` (Day 2's original
architecture) have carried as a `0`/`TODO` placeholder since Day 2 --
though wiring it into those services is out of Day 27's stated scope
and is left as a clearly-flagged follow-on, not silently done here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from parsers.answer_intent_engine import StructuredAnswer

# ---------------------------------------------------------------------------
# 1. Hesitation pattern detection
# ---------------------------------------------------------------------------

# Unambiguous fillers -- interjections that are essentially never used
# as ordinary content words, so counting them directly is safe.
_UNAMBIGUOUS_FILLERS = ["um", "umm", "uh", "uhh", "erm", "hmm"]

# Multi-word filler phrases -- also low-ambiguity, since these specific
# word sequences are rarely meant literally in a screening-call answer.
_FILLER_PHRASES = ["you know", "i mean", "sort of", "kind of", "or something", "or whatever"]

# Deliberately EXCLUDED from the hesitation count: "like", "actually",
# "basically", "well" -- each is a common filler in speech but is
# equally common as an ordinary content word ("I like React", "it
# actually works", "the basically approach" -- well, not that one, but
# "well, that's a good question" vs. "I did well"). Counting these
# blindly would produce false positives this project isn't willing to
# silently absorb into a candidate-facing score. They're tracked
# separately, unscored, so the gap is visible rather than hidden.
_AMBIGUOUS_FILLER_CANDIDATES = ["like", "actually", "basically", "well"]


@dataclass
class HesitationResult:
    filler_count: int                        # unambiguous fillers + filler phrases only
    filler_phrases_found: List[str]
    ambiguous_words_flagged: Dict[str, int]   # NOT included in filler_count -- see module docstring
    hesitation_rate_per_100_words: float


def detect_hesitation(text: str) -> HesitationResult:
    lowered = text.lower()
    word_count = max(len(lowered.split()), 1)

    filler_count = 0
    for filler in _UNAMBIGUOUS_FILLERS:
        filler_count += len(re.findall(rf"\b{filler}\b", lowered))

    phrases_found = []
    for phrase in _FILLER_PHRASES:
        hits = len(re.findall(rf"\b{re.escape(phrase)}\b", lowered))
        if hits:
            phrases_found.extend([phrase] * hits)
            filler_count += hits

    ambiguous_flagged = {}
    for word in _AMBIGUOUS_FILLER_CANDIDATES:
        hits = len(re.findall(rf"\b{word}\b", lowered))
        if hits:
            ambiguous_flagged[word] = hits

    rate = round(filler_count / word_count * 100, 1)
    return HesitationResult(
        filler_count=filler_count, filler_phrases_found=phrases_found,
        ambiguous_words_flagged=ambiguous_flagged, hesitation_rate_per_100_words=rate,
    )


# ---------------------------------------------------------------------------
# 2. Response length & pace
# ---------------------------------------------------------------------------

@dataclass
class LengthPaceResult:
    word_count: int
    duration_seconds: Optional[float]
    words_per_minute: Optional[float]
    note: Optional[str] = None


def measure_length_and_pace(text: str, duration_seconds: Optional[float] = None) -> LengthPaceResult:
    """Pace (words per minute) requires real audio duration. Day 24's
    STT layer is a documented mock with no real timing output, so pace
    can only be computed when the caller explicitly supplies a
    duration -- otherwise this honestly reports "not computed" rather
    than guessing a duration from word count.
    """
    word_count = len(text.split())
    if duration_seconds is None or duration_seconds <= 0:
        return LengthPaceResult(
            word_count=word_count, duration_seconds=None, words_per_minute=None,
            note="Pace not computed -- no real audio duration available (Day 24's STT layer is mocked).",
        )
    wpm = round(word_count / (duration_seconds / 60.0), 1)
    return LengthPaceResult(word_count=word_count, duration_seconds=duration_seconds, words_per_minute=wpm)


# ---------------------------------------------------------------------------
# 3. Sentiment (positive / negative / neutral)
# ---------------------------------------------------------------------------

_POSITIVE_WORDS = [
    "excited", "passionate", "enjoy", "enjoyed", "love", "loved", "confident", "great",
    "good", "happy", "motivated", "eager", "comfortable", "strong", "proud", "interested",
]
_NEGATIVE_WORDS = [
    "difficult", "struggle", "struggled", "hate", "hated", "worried", "nervous",
    "frustrated", "frustrating", "bad", "poor", "concerned", "concern", "weak", "afraid", "stressed",
]


@dataclass
class SentimentResult:
    positive_hits: List[str]
    negative_hits: List[str]
    label: str          # "positive" | "neutral" | "negative"
    score: float         # -100..100, net sentiment scaled by word count


def analyze_sentiment(text: str) -> SentimentResult:
    lowered = text.lower()
    word_count = max(len(lowered.split()), 1)

    positive_hits = [w for w in _POSITIVE_WORDS if re.search(rf"\b{w}\b", lowered)]
    negative_hits = [w for w in _NEGATIVE_WORDS if re.search(rf"\b{w}\b", lowered)]

    net = len(positive_hits) - len(negative_hits)
    score = round(max(-100.0, min(100.0, net / word_count * 100 * 5)), 1)  # x5: lexicon hits are sparse relative to word count

    if score > 5:
        label = "positive"
    elif score < -5:
        label = "negative"
    else:
        label = "neutral"

    return SentimentResult(positive_hits=positive_hits, negative_hits=negative_hits, label=label, score=score)


# ---------------------------------------------------------------------------
# 4. Uncertainty marker density
#
# Deliberately a DIFFERENT lexicon and purpose from Day 25's
# _HEDGE_PHRASES: Day 25 used a short hedge list as a binary gate
# ("is this whole answer too vague to score?"). Day 27 measures
# uncertainty-language DENSITY across any answer, including
# substantive ones ("I think it was around three years, probably")
# is a confident-sounding, complete, ON-topic answer that still
# carries real uncertainty markers worth surfacing as a behavioral
# signal -- not duplicated logic, a different question being asked
# of the same text.
# ---------------------------------------------------------------------------

_UNCERTAINTY_MARKERS = [
    "i think", "i guess", "i believe", "probably", "maybe", "perhaps", "not sure",
    "not certain", "might be", "could be", "i suppose", "possibly", "not 100%", "kind of unsure",
]


@dataclass
class UncertaintyResult:
    markers_found: List[str]
    uncertainty_rate_per_100_words: float


def detect_uncertainty(text: str) -> UncertaintyResult:
    lowered = text.lower()
    word_count = max(len(lowered.split()), 1)

    found = []
    for marker in _UNCERTAINTY_MARKERS:
        hits = len(re.findall(rf"\b{re.escape(marker)}\b", lowered))
        if hits:
            found.extend([marker] * hits)

    rate = round(len(found) / word_count * 100, 1)
    return UncertaintyResult(markers_found=found, uncertainty_rate_per_100_words=rate)


# ---------------------------------------------------------------------------
# 5. Per-answer signal bundle
# ---------------------------------------------------------------------------

@dataclass
class AnswerCommunicationSignals:
    turn_id: Optional[str]
    hesitation: HesitationResult
    length_pace: LengthPaceResult
    sentiment: SentimentResult
    uncertainty: UncertaintyResult

    def to_dict(self) -> Dict:
        return {
            "turn_id": self.turn_id,
            "hesitation": {
                "filler_count": self.hesitation.filler_count,
                "filler_phrases_found": self.hesitation.filler_phrases_found,
                "ambiguous_words_flagged": self.hesitation.ambiguous_words_flagged,
                "hesitation_rate_per_100_words": self.hesitation.hesitation_rate_per_100_words,
            },
            "length_pace": {
                "word_count": self.length_pace.word_count,
                "duration_seconds": self.length_pace.duration_seconds,
                "words_per_minute": self.length_pace.words_per_minute,
                "note": self.length_pace.note,
            },
            "sentiment": {
                "positive_hits": self.sentiment.positive_hits,
                "negative_hits": self.sentiment.negative_hits,
                "label": self.sentiment.label,
                "score": self.sentiment.score,
            },
            "uncertainty": {
                "markers_found": self.uncertainty.markers_found,
                "uncertainty_rate_per_100_words": self.uncertainty.uncertainty_rate_per_100_words,
            },
        }


def analyze_answer_communication(
    text: str, turn_id: Optional[str] = None, duration_seconds: Optional[float] = None,
) -> AnswerCommunicationSignals:
    return AnswerCommunicationSignals(
        turn_id=turn_id,
        hesitation=detect_hesitation(text),
        length_pace=measure_length_and_pace(text, duration_seconds),
        sentiment=analyze_sentiment(text),
        uncertainty=detect_uncertainty(text),
    )


# ---------------------------------------------------------------------------
# 6. Call-level communication strength indicator -- the Day 27
#    "behavioral indicators report" deliverable
# ---------------------------------------------------------------------------

_HESITATION_PENALTY_CAP = 30.0
_UNCERTAINTY_PENALTY_CAP = 30.0
_CONTRADICTION_PENALTY_CAP = 30.0
_CONTRADICTION_PENALTY_PER_FINDING = 15.0
_SENTIMENT_ADJUSTMENT_SCALE = 0.2   # sentiment score range -100..100 -> adjustment -20..20


@dataclass
class CommunicationProfile:
    answer_signals: List[AnswerCommunicationSignals]
    contradiction_count: int
    contradiction_findings: List[str]
    communication_strength_score: float           # 0-100
    component_breakdown: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "communication_strength_score": self.communication_strength_score,
            "component_breakdown": self.component_breakdown,
            "contradiction_count": self.contradiction_count,
            "contradiction_findings": self.contradiction_findings,
            "answer_signals": [a.to_dict() for a in self.answer_signals],
        }


def build_communication_profile(
    answers: List[StructuredAnswer],
    consistency_findings: List[str],
    durations: Optional[Dict[str, float]] = None,
) -> CommunicationProfile:
    """Builds the call-level communication strength indicator.
    contradiction_findings is Day 26's score_screening_call() output,
    passed in as-is -- reused, not recomputed. durations is an
    optional {turn_id: seconds} map for real pace calculation; without
    it every answer's pace honestly reports "not computed."
    """
    durations = durations or {}
    signals = [
        analyze_answer_communication(a.raw_text, turn_id=a.turn_id, duration_seconds=durations.get(a.turn_id))
        for a in answers
    ]

    if not signals:
        return CommunicationProfile(
            answer_signals=[], contradiction_count=0, contradiction_findings=[],
            communication_strength_score=0.0, component_breakdown={"note": "No answers to analyze."},
        )

    avg_hesitation_rate = round(sum(s.hesitation.hesitation_rate_per_100_words for s in signals) / len(signals), 1)
    avg_uncertainty_rate = round(sum(s.uncertainty.uncertainty_rate_per_100_words for s in signals) / len(signals), 1)
    avg_sentiment_score = round(sum(s.sentiment.score for s in signals) / len(signals), 1)

    hesitation_penalty = min(_HESITATION_PENALTY_CAP, avg_hesitation_rate * 2)
    uncertainty_penalty = min(_UNCERTAINTY_PENALTY_CAP, avg_uncertainty_rate * 2)
    contradiction_penalty = min(_CONTRADICTION_PENALTY_CAP, len(consistency_findings) * _CONTRADICTION_PENALTY_PER_FINDING)
    sentiment_adjustment = round(avg_sentiment_score * _SENTIMENT_ADJUSTMENT_SCALE, 1)

    raw_score = 100.0 - hesitation_penalty - uncertainty_penalty - contradiction_penalty + sentiment_adjustment
    communication_strength_score = round(max(0.0, min(100.0, raw_score)), 1)

    breakdown = {
        "base": 100.0,
        "avg_hesitation_rate_per_100_words": avg_hesitation_rate,
        "hesitation_penalty": -hesitation_penalty,
        "avg_uncertainty_rate_per_100_words": avg_uncertainty_rate,
        "uncertainty_penalty": -uncertainty_penalty,
        "contradiction_count": len(consistency_findings),
        "contradiction_penalty": -contradiction_penalty,
        "avg_sentiment_score": avg_sentiment_score,
        "sentiment_adjustment": sentiment_adjustment,
    }

    return CommunicationProfile(
        answer_signals=signals, contradiction_count=len(consistency_findings),
        contradiction_findings=list(consistency_findings),
        communication_strength_score=communication_strength_score, component_breakdown=breakdown,
    )
