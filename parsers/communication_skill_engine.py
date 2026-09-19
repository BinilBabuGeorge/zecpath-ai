"""
Communication Skill Evaluation (Day 35)

WHAT THIS DAY ADDS: `interview_ai/service.py` has carried a
`communication_score: 0` TODO placeholder since Day 2's original
architecture. Day 27 already built a real communication-signal engine
-- but it is scoped to the SCREENING call (Days 22-32): it takes
`StructuredAnswer` objects and reuses Day 26's contradiction findings,
neither of which exist in the HR-interview phase (Days 33-34), which
works directly with `InterviewSession` / `InterviewQuestionState` and
plain response text. This day is the HR-interview-phase counterpart:
it evaluates the FIVE things the brief actually asks for (fluency,
grammar, vocabulary, clarity, structure) that Day 27 never covered,
while reusing Day 27's filler-word detector as-is for the one thing
that overlaps.

REUSE, NOT REIMPLEMENTATION (same discipline as every prior day):
  - `detect_hesitation()` is imported directly from Day 27's
    `confidence_sentiment_engine` for "detect filler words" -- it is
    already a generic, transcript-text filler counter with nothing
    screening-specific in it, exactly the kind of function Day 34
    reused Day 29's `detect_repeated_answer()` for.
  - `has_concrete_example()` and `is_vague_behavioral_answer()` are
    imported directly from Day 34's `hr_followup_engine` for the
    "clarity of explanation" signal -- concreteness and hedging are
    exactly what "clarity" means for a spoken explanation, and Day 34
    already built both detectors for this exact answer population
    (HR-interview behavioral responses).

SCOPE, STATED HONESTLY UP FRONT:
  - Grammar checking here is a small, curated list of common error
    PATTERNS (subject-verb agreement, double negatives, a few
    irregular-plural mistakes) plus repeated-word detection -- not a
    real parser or a trained grammar model. No POS tagger or
    dependency parser is available in this project, the same
    constraint every prior "understanding" module (Day 25's intent
    engine, this one) has stated rather than faked.
  - Capitalization and terminal punctuation are DELIBERATELY EXCLUDED
    from grammar scoring. Day 24's STT layer is a documented mock with
    no real transcription behind it, and even a real ASR transcript
    commonly comes back lowercase/unpunctuated -- scoring a candidate
    down for something that is a transcription-layer property, not a
    communication-skill property, would be exactly the kind of hidden
    unfairness this project's fairness engine (Day 15) exists to catch
    elsewhere. Named explicitly so it isn't a silent gap.
  - "Fluency" and "answer structure" are measured from SENTENCE
    SEGMENTATION on punctuation. If the upstream transcript has no
    punctuation at all (a real risk per the point above), every answer
    degrades to "one long sentence" -- flagged in the result via
    `sentence_boundary_confidence`, not hidden.
  - Vocabulary range uses root type-token ratio (unique words /
    sqrt(total words)), not raw type-token ratio, specifically BECAUSE
    raw TTR shrinks mechanically as answers get longer, which would
    otherwise punish candidates for giving fuller answers -- see
    "Normalizing to reduce bias" below.

NORMALIZING TO REDUCE BIAS (the brief's explicit last bullet):
  1. Length bias: root TTR (not raw TTR) for vocabulary, so a longer,
     more substantive answer isn't mechanically scored as "less
     varied" than a short one that happens to avoid repeating itself.
  2. Short-answer noise: filler-word RATE (per 100 words) is
     statistically noisy on very short answers -- one filler word in a
     6-word answer is a 16.7 rate that would swamp the score the same
     way it would for a real problem in a 200-word answer. Below
     `_SHORT_ANSWER_WORD_THRESHOLD`, the filler penalty is halved and
     `sample_size_reliability` is marked "low" so the number is never
     presented with false precision.
  3. Component clamping: every component score is independently capped
     to 0-100 BEFORE averaging, so one badly-triggered heuristic (e.g.
     a false-positive grammar hit) cannot drag the composite below
     what the other four components independently support.
  4. Equal weighting: all five components are weighted identically
     (20% each) rather than hand-tuned, since there is no labeled data
     in this project to justify weighting one skill above another --
     an arbitrary weighting would be a hidden bias of its own.

KNOWN LIMITATION, STATED HONESTLY: none of this corrects for the
genuine bias risk that a non-native English speaker will naturally
produce shorter sentences, a smaller working vocabulary in a second
language, and a more literal explanation style than a native speaker
-- all of which this module's heuristics would still under-score. That
is a real fairness gap in a rule-based English-text approach, not
something a scoring-formula tweak can fix, and it is named here rather
than left implicit.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from parsers.confidence_sentiment_engine import HesitationResult, detect_hesitation
from parsers.hr_followup_engine import has_concrete_example, is_vague_behavioral_answer
from parsers.hr_interview_question_bank import InterviewQuestionState, InterviewSession

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SHORT_ANSWER_WORD_THRESHOLD = 12   # below this, filler-rate and TTR are statistically noisy
_RUN_ON_WORD_THRESHOLD = 40         # a single "sentence" this long is treated as a run-on
_FRAGMENT_WORD_THRESHOLD = 3        # a "sentence" this short (and not the whole answer) is a fragment
_ROOT_TTR_CEILING = 6.0             # root-TTR value treated as "full marks" -- an uncalibrated but reasonable ceiling, see module docstring
_FILLER_PENALTY_CAP = 20.0

_CONTINUITY_CONNECTORS = [
    "also", "then", "after that", "as a result", "therefore", "so", "because", "however",
    "in addition", "furthermore", "meanwhile", "next", "before that", "since then",
]

_CLARITY_CONNECTORS = [
    "which means", "in other words", "specifically", "the reason is", "so that", "to clarify", "that is to say",
]

_STRUCTURING_CONNECTORS = [
    "first", "firstly", "second", "secondly", "then", "after that", "next", "finally",
    "in conclusion", "overall", "as a result", "for example", "to summarize",
]

# A small, curated set of common grammar-error PATTERNS -- not a parser.
# See module docstring for why capitalization/punctuation are excluded.
_GRAMMAR_ERROR_PATTERNS = [
    "he don't", "she don't", "it don't", "they was", "we was", "i were", "he were", "she were",
    "don't have no", "can't hardly", "didn't never", "more better", "most best",
    "i has", "he have", "she have", "they has", "was went", "have went",
]

_REPEATED_WORD_RE = re.compile(r"\b(\w+)\s+\1\b", re.IGNORECASE)
_SENTENCE_SPLIT_RE = re.compile(r"[.!?]+")


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _split_sentences(text: str) -> List[str]:
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(text) if p.strip()]
    return parts if parts else ([text.strip()] if text.strip() else [])


# ---------------------------------------------------------------------------
# 1. Fluency (sentence continuity)
# ---------------------------------------------------------------------------

@dataclass
class FluencyResult:
    sentence_count: int
    avg_sentence_length: float
    run_on_count: int
    fragment_count: int
    continuity_connectors_found: List[str]
    sentence_boundary_confidence: str   # "normal" | "low" -- see module docstring
    fluency_score: float


def assess_fluency(text: str) -> FluencyResult:
    sentences = _split_sentences(text)
    word_count = len(text.split())
    sentence_count = len(sentences)
    avg_len = round(word_count / sentence_count, 1) if sentence_count else 0.0

    run_ons = sum(1 for s in sentences if len(s.split()) > _RUN_ON_WORD_THRESHOLD)
    fragments = sum(
        1 for s in sentences if len(s.split()) < _FRAGMENT_WORD_THRESHOLD
    ) if sentence_count > 1 else 0  # a single short answer isn't a "fragment", it's just short

    connectors_found = [c for c in _CONTINUITY_CONNECTORS if re.search(rf"\b{re.escape(c)}\b", text.lower())]

    # No punctuation at all on a longer answer means sentence
    # segmentation collapsed to one giant "sentence" -- a transcript
    # artifact, not necessarily a real run-on. Flagged, not scored as
    # if it were confidently measured.
    boundary_confidence = "low" if (sentence_count <= 1 and word_count > _RUN_ON_WORD_THRESHOLD) else "normal"

    score = 100.0
    if boundary_confidence == "normal":
        score -= min(40.0, run_ons * 20.0)
        score -= min(30.0, fragments * 15.0)
        if sentence_count > 1 and connectors_found:
            score += min(10.0, len(connectors_found) * 5.0)
    # When boundary confidence is low, don't apply the run-on/fragment
    # penalties at all -- there is nothing reliable to penalize yet.

    return FluencyResult(
        sentence_count=sentence_count, avg_sentence_length=avg_len, run_on_count=run_ons,
        fragment_count=fragments, continuity_connectors_found=connectors_found,
        sentence_boundary_confidence=boundary_confidence, fluency_score=round(_clamp(score), 1),
    )


# ---------------------------------------------------------------------------
# 2. Grammar quality
# ---------------------------------------------------------------------------

@dataclass
class GrammarResult:
    errors_found: List[str]
    repeated_word_pairs: List[str]
    grammar_score: float


def assess_grammar(text: str) -> GrammarResult:
    lowered = text.lower()
    errors = [p for p in _GRAMMAR_ERROR_PATTERNS if re.search(rf"\b{re.escape(p)}\b", lowered)]
    repeated = _REPEATED_WORD_RE.findall(lowered)

    score = 100.0 - min(40.0, len(errors) * 10.0) - min(20.0, len(repeated) * 10.0)
    return GrammarResult(errors_found=errors, repeated_word_pairs=repeated, grammar_score=round(_clamp(score), 1))


# ---------------------------------------------------------------------------
# 3. Vocabulary range
# ---------------------------------------------------------------------------

@dataclass
class VocabularyResult:
    total_words: int
    unique_words: int
    root_ttr: float
    vocabulary_score: float


def assess_vocabulary(text: str) -> VocabularyResult:
    words = re.findall(r"[a-zA-Z']+", text.lower())
    total = len(words)
    unique = len(set(words))
    root_ttr = round(unique / math.sqrt(total), 2) if total else 0.0
    score = _clamp((root_ttr / _ROOT_TTR_CEILING) * 100.0)
    return VocabularyResult(total_words=total, unique_words=unique, root_ttr=root_ttr, vocabulary_score=round(score, 1))


# ---------------------------------------------------------------------------
# 4. Clarity of explanation -- reuses Day 34's concreteness/hedge detectors
# ---------------------------------------------------------------------------

@dataclass
class ClarityResult:
    has_concrete_grounding: bool
    clarity_connectors_found: List[str]
    is_vague: bool
    clarity_score: float


def assess_clarity(text: str) -> ClarityResult:
    concrete = has_concrete_example(text)
    vague = is_vague_behavioral_answer(text)
    connectors = [c for c in _CLARITY_CONNECTORS if c in text.lower()]

    score = 60.0
    if concrete:
        score += 20.0
    if connectors:
        score += 20.0
    if vague:
        score -= 40.0
    return ClarityResult(
        has_concrete_grounding=concrete, clarity_connectors_found=connectors,
        is_vague=vague, clarity_score=round(_clamp(score), 1),
    )


# ---------------------------------------------------------------------------
# 5. Answer structure
# ---------------------------------------------------------------------------

@dataclass
class StructureResult:
    sentence_count: int
    structuring_connectors_found: List[str]
    structure_score: float


def assess_structure(text: str, sentence_count: Optional[int] = None) -> StructureResult:
    if sentence_count is None:
        sentence_count = len(_split_sentences(text))
    connectors = [c for c in _STRUCTURING_CONNECTORS if re.search(rf"\b{re.escape(c)}\b", text.lower())]

    score = 40.0 + min(30.0, sentence_count * 10.0) + min(30.0, len(connectors) * 10.0)
    return StructureResult(
        sentence_count=sentence_count, structuring_connectors_found=connectors, structure_score=round(_clamp(score), 1),
    )


# ---------------------------------------------------------------------------
# 6. Per-answer communication evaluation -- combines all five components,
#    applies the filler penalty (Day 27's detector, reused), and applies
#    the bias-normalization steps described in the module docstring.
# ---------------------------------------------------------------------------

@dataclass
class AnswerCommunicationEvaluation:
    question_id: Optional[str]
    category: Optional[str]
    word_count: int
    sample_size_reliability: str   # "normal" | "low"
    fluency: FluencyResult
    grammar: GrammarResult
    vocabulary: VocabularyResult
    clarity: ClarityResult
    structure: StructureResult
    filler: HesitationResult
    communication_score: float
    component_breakdown: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "question_id": self.question_id,
            "category": self.category,
            "word_count": self.word_count,
            "sample_size_reliability": self.sample_size_reliability,
            "communication_score": self.communication_score,
            "component_breakdown": self.component_breakdown,
            "fluency": vars(self.fluency),
            "grammar": vars(self.grammar),
            "vocabulary": vars(self.vocabulary),
            "clarity": vars(self.clarity),
            "structure": vars(self.structure),
            "filler": {
                "filler_count": self.filler.filler_count,
                "filler_phrases_found": self.filler.filler_phrases_found,
                "hesitation_rate_per_100_words": self.filler.hesitation_rate_per_100_words,
            },
        }


def evaluate_answer_communication(
    text: str, question_id: Optional[str] = None, category: Optional[str] = None,
) -> AnswerCommunicationEvaluation:
    word_count = len(text.split())
    reliability = "low" if word_count < _SHORT_ANSWER_WORD_THRESHOLD else "normal"

    fluency = assess_fluency(text)
    grammar = assess_grammar(text)
    vocabulary = assess_vocabulary(text)
    clarity = assess_clarity(text)
    structure = assess_structure(text, sentence_count=fluency.sentence_count)
    filler = detect_hesitation(text)

    base_score = (
        fluency.fluency_score + grammar.grammar_score + vocabulary.vocabulary_score
        + clarity.clarity_score + structure.structure_score
    ) / 5.0

    # Bias-normalization step 2 (see module docstring): halve the
    # filler penalty on short answers, where the per-100-word rate is
    # statistically noisy.
    filler_penalty = min(_FILLER_PENALTY_CAP, filler.hesitation_rate_per_100_words * 2.0)
    if reliability == "low":
        filler_penalty /= 2.0

    final_score = round(_clamp(base_score - filler_penalty), 1)

    breakdown = {
        "fluency_score": fluency.fluency_score,
        "grammar_score": grammar.grammar_score,
        "vocabulary_score": vocabulary.vocabulary_score,
        "clarity_score": clarity.clarity_score,
        "structure_score": structure.structure_score,
        "base_average": round(base_score, 1),
        "filler_penalty": round(-filler_penalty, 1),
    }

    return AnswerCommunicationEvaluation(
        question_id=question_id, category=category, word_count=word_count, sample_size_reliability=reliability,
        fluency=fluency, grammar=grammar, vocabulary=vocabulary, clarity=clarity, structure=structure,
        filler=filler, communication_score=final_score, component_breakdown=breakdown,
    )


# ---------------------------------------------------------------------------
# 7. Interview-level aggregate -- the "communication scoring model"
#    deliverable applied across a full InterviewSession
# ---------------------------------------------------------------------------

@dataclass
class InterviewCommunicationProfile:
    answer_evaluations: List[AnswerCommunicationEvaluation]
    overall_communication_score: float
    category_scores: Dict[str, float]
    low_reliability_answer_count: int

    def to_dict(self) -> Dict:
        return {
            "overall_communication_score": self.overall_communication_score,
            "category_scores": self.category_scores,
            "low_reliability_answer_count": self.low_reliability_answer_count,
            "answer_evaluations": [a.to_dict() for a in self.answer_evaluations],
        }


def build_interview_communication_profile(session: InterviewSession) -> InterviewCommunicationProfile:
    """Evaluates every ANSWERED question in the session. This is the
    HR-interview-phase counterpart to Day 27's
    `build_communication_profile()` -- same "call-level indicator from
    per-answer signals" shape, different input type
    (`InterviewSession` instead of a list of `StructuredAnswer`) and
    different component set (fluency/grammar/vocabulary/clarity/
    structure instead of hesitation/sentiment/uncertainty), because
    the brief asks for different things than Day 27 already covered.
    """
    answered: List[InterviewQuestionState] = [q for q in session.questions if q.response_captured and q.response_text]

    if not answered:
        return InterviewCommunicationProfile(
            answer_evaluations=[], overall_communication_score=0.0, category_scores={}, low_reliability_answer_count=0,
        )

    evaluations = [
        evaluate_answer_communication(q.response_text, question_id=q.question_id, category=q.category)
        for q in answered
    ]

    overall = round(sum(e.communication_score for e in evaluations) / len(evaluations), 1)

    by_category: Dict[str, List[float]] = {}
    for e in evaluations:
        by_category.setdefault(e.category, []).append(e.communication_score)
    category_scores = {cat: round(sum(scores) / len(scores), 1) for cat, scores in by_category.items()}

    low_reliability_count = sum(1 for e in evaluations if e.sample_size_reliability == "low")

    return InterviewCommunicationProfile(
        answer_evaluations=evaluations, overall_communication_score=overall,
        category_scores=category_scores, low_reliability_answer_count=low_reliability_count,
    )
