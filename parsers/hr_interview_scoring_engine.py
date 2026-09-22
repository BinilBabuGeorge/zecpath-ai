"""
HR Interview Scoring Engine (Day 37)

WHAT THIS DAY ADDS: Days 34-36 built three independent signal
engines for the HR-interview phase -- follow-up/answer-quality
classification (34), communication skill (35), and confidence/stress
(36) -- but nothing that combines them into the one structured,
explainable HR score an actual hiring decision needs. This day is
that combination layer: it defines the four scoring parameters the
brief asks for, a configurable weightage system, and an explainable
breakdown -- reusing all three prior engines' outputs rather than
recomputing anything.

REUSE, NOT REIMPLEMENTATION -- ALL FOUR SCORING PARAMETERS MAP
DIRECTLY ONTO EXISTING, ALREADY-TESTED WORK:

    Scoring parameter    ->  Reused from
    -------------------------------------------------------------
    Answer relevance      ->  Day 34's assess_behavioral_answer()
                               (MISSING/VAGUE/THIN/CONFIDENT tiers)
    Communication score    ->  Day 35's evaluate_answer_communication()
    Confidence score       ->  Day 36's evaluate_answer_confidence()
    Consistency            ->  Day 36's cross-answer sentiment-swing
                               and mixed-sentiment flags

Nothing here re-derives a signal that already exists -- this module's
only new code is the WEIGHTING, COMBINATION, and NORMALIZATION logic,
which is exactly what Day 37's brief actually asks for and none of
Days 34-36 built (each was deliberately scoped to its own signal).

ANSWER RELEVANCE, STATED HONESTLY: Day 34's four-tier classifier
(MISSING/VAGUE/THIN/CONFIDENT) is an answer-QUALITY signal, not a
semantic relevance-to-the-question checker -- this project has no NLP
model to verify an answer actually addresses what was asked versus
just being long and concrete about something else. Mapping quality
tiers to a relevance score (CONFIDENT=100, THIN=60, VAGUE=30,
MISSING=0) is a reasoned proxy: an answer with a concrete, substantive
example is far more likely to be relevant than a vague hedge, but this
does not verify topical relevance directly. Named here rather than
implied by the field name alone.

WEIGHTAGE SYSTEM: unlike Days 34-36's equal-weighting default (used
there because the components were of equal, unknown reliability),
this day's four parameters differ in what they actually verify --
so the default weights are REASONED, not equal, and are fully
configurable via `WeightConfig` for anyone who disagrees with the
reasoning:

    - Relevance:      35% -- the most direct measure of whether the
                             candidate actually answered the question,
                             the core purpose of interview scoring.
    - Communication:   25% -- a real, independently useful skill signal.
    - Confidence:       25% -- useful, but Day 36 itself flags this as
                             more heuristic than the other two (text-only
                             disfluency detection, no audio).
    - Consistency:      15% -- weighted lowest because Day 36 explicitly
                             labels its own contradiction signals
                             `possible_`, not confirmed -- the least
                             certain of the four inputs gets the
                             smallest say in the final score.

This weighting is a reasoned default, NOT calibrated against labeled
hiring outcomes -- no such data exists in this project. Anyone
integrating this can supply their own `WeightConfig`.

NORMALIZING ACROSS DIFFERENT INTERVIEW LENGTHS (the brief's explicit
last task): relevance/communication/confidence are combined as
PER-ANSWER AVERAGES, not sums, so a 4-question and a 10-question
interview land on the same 0-100 scale. The consistency penalty is
computed from an ISSUE RATE (swing flags + mixed-sentiment answers,
divided by the number of answers/pairs), not a raw count -- Day 36's
own aggregate capped the raw swing count, which would have under-
penalized a long interview with the same proportion of issues as a
short one just because the cap saturates at a lower rate. Rate-based
normalization fixes that at this aggregation layer without needing to
change Day 36's module itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from parsers.hr_followup_engine import assess_behavioral_answer, BehavioralAnswerQuality
from parsers.communication_skill_engine import evaluate_answer_communication
from parsers.confidence_stress_engine import evaluate_answer_confidence
from parsers.hr_interview_question_bank import InterviewQuestionState, InterviewSession

_RELEVANCE_SCORE_BY_QUALITY = {
    BehavioralAnswerQuality.CONFIDENT: 100.0,
    BehavioralAnswerQuality.THIN: 60.0,
    BehavioralAnswerQuality.VAGUE: 30.0,
    BehavioralAnswerQuality.MISSING: 0.0,
}


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


# ---------------------------------------------------------------------------
# 1. Weightage system -- the "weight configuration system" deliverable
# ---------------------------------------------------------------------------

@dataclass
class WeightConfig:
    relevance: float = 0.35
    communication: float = 0.25
    confidence: float = 0.25
    consistency: float = 0.15

    def validate(self) -> None:
        total = self.relevance + self.communication + self.confidence + self.consistency
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"WeightConfig must sum to 1.0, got {total}")
        for name, value in vars(self).items():
            if value < 0:
                raise ValueError(f"WeightConfig.{name} must be >= 0, got {value}")

    @property
    def positive_component_total(self) -> float:
        """Relevance + communication + confidence -- everything except
        the subtractive consistency penalty. Used to renormalize the
        positive components back onto a 0-100 scale before the
        consistency penalty is applied. See module docstring."""
        return self.relevance + self.communication + self.confidence


# ---------------------------------------------------------------------------
# 2. Per-answer breakdown -- reuses Day 34/35/36 outputs, does not
#    recompute any of them.
# ---------------------------------------------------------------------------

@dataclass
class AnswerScoreBreakdown:
    question_id: Optional[str]
    category: Optional[str]
    relevance_quality: str          # BehavioralAnswerQuality value, from Day 34
    relevance_score: float
    communication_score: float      # from Day 35
    confidence_score: float         # from Day 36
    weighted_positive_component: float   # relevance/communication/confidence combined, renormalized to 0-100

    def to_dict(self) -> Dict:
        return {
            "question_id": self.question_id,
            "category": self.category,
            "relevance_quality": self.relevance_quality,
            "relevance_score": self.relevance_score,
            "communication_score": self.communication_score,
            "confidence_score": self.confidence_score,
            "weighted_positive_component": self.weighted_positive_component,
        }


def _score_answer(q: InterviewQuestionState, weights: WeightConfig) -> AnswerScoreBreakdown:
    quality = assess_behavioral_answer(q.response_text)
    relevance_score = _RELEVANCE_SCORE_BY_QUALITY[quality]
    communication_score = evaluate_answer_communication(q.response_text, question_id=q.question_id, category=q.category).communication_score
    confidence_score = evaluate_answer_confidence(q.response_text, question_id=q.question_id, category=q.category).behavioral_confidence_score

    weighted_sum = relevance_score * weights.relevance + communication_score * weights.communication + confidence_score * weights.confidence
    weighted_positive_component = round(weighted_sum / weights.positive_component_total, 1) if weights.positive_component_total else 0.0

    return AnswerScoreBreakdown(
        question_id=q.question_id, category=q.category, relevance_quality=quality.value,
        relevance_score=relevance_score, communication_score=communication_score,
        confidence_score=confidence_score, weighted_positive_component=weighted_positive_component,
    )


# ---------------------------------------------------------------------------
# 3. Consistency -- reuses Day 36's cross-answer swing / mixed-sentiment
#    flags, normalized to a RATE (see module docstring on length bias)
# ---------------------------------------------------------------------------

@dataclass
class ConsistencyAssessment:
    swing_count: int
    mixed_sentiment_count: int
    issue_rate: float          # 0-1, normalized by answer/pair count -- NOT a raw count
    consistency_penalty: float   # 0 to weights.consistency * 100
    findings: List[str] = field(default_factory=list)


def _assess_consistency(session: InterviewSession, weights: WeightConfig) -> ConsistencyAssessment:
    from parsers.confidence_stress_engine import build_confidence_profile  # local import: avoids recomputation elsewhere in module

    confidence_profile = build_confidence_profile(session)
    answered_count = len(confidence_profile.answer_evaluations)
    pair_count = max(1, answered_count - 1)

    swing_count = len(confidence_profile.inconsistency_flags.cross_answer_swings)
    mixed_count = sum(1 for e in confidence_profile.answer_evaluations if e.mixed_sentiment_flag)

    # Rate-based, not raw-count-based -- see "Normalizing across
    # different interview lengths" in the module docstring.
    swing_rate = swing_count / pair_count
    mixed_rate = mixed_count / max(1, answered_count)
    issue_rate = _clamp((swing_rate + mixed_rate) / 2.0, 0.0, 1.0)

    penalty = round(issue_rate * (weights.consistency * 100.0), 1)

    findings = list(confidence_profile.inconsistency_flags.cross_answer_swings)
    if mixed_count:
        findings.append(f"{mixed_count} answer(s) with strongly mixed sentiment within a single response.")

    return ConsistencyAssessment(
        swing_count=swing_count, mixed_sentiment_count=mixed_count,
        issue_rate=round(issue_rate, 3), consistency_penalty=penalty, findings=findings,
    )


# ---------------------------------------------------------------------------
# 4. Full interview score report -- the "HR interview scoring engine"
#    and "candidate HR score report format" deliverables
# ---------------------------------------------------------------------------

@dataclass
class HRInterviewScoreReport:
    overall_hr_score: float
    weights_used: WeightConfig
    answer_breakdowns: List[AnswerScoreBreakdown]
    avg_relevance: float
    avg_communication: float
    avg_confidence: float
    consistency: ConsistencyAssessment
    num_questions_answered: int

    def to_dict(self) -> Dict:
        return {
            "overall_hr_score": self.overall_hr_score,
            "weights_used": vars(self.weights_used),
            "num_questions_answered": self.num_questions_answered,
            "component_averages": {
                "avg_relevance": self.avg_relevance,
                "avg_communication": self.avg_communication,
                "avg_confidence": self.avg_confidence,
            },
            "consistency": {
                "swing_count": self.consistency.swing_count,
                "mixed_sentiment_count": self.consistency.mixed_sentiment_count,
                "issue_rate": self.consistency.issue_rate,
                "consistency_penalty": self.consistency.consistency_penalty,
                "findings": self.consistency.findings,
            },
            "answer_breakdowns": [a.to_dict() for a in self.answer_breakdowns],
        }

    def to_summary_text(self) -> str:
        """The 'candidate HR score report format' deliverable as a
        plain-text human-readable summary -- explainable by design:
        every number here traces back to a specific, named component.
        """
        lines = [
            f"HR Interview Score Report",
            f"{'=' * 40}",
            f"Overall HR Score: {self.overall_hr_score}/100",
            f"Questions answered: {self.num_questions_answered}",
            "",
            f"Component averages (0-100):",
            f"  Relevance:      {self.avg_relevance}",
            f"  Communication:  {self.avg_communication}",
            f"  Confidence:     {self.avg_confidence}",
            "",
            f"Weights used: relevance={self.weights_used.relevance}, communication={self.weights_used.communication}, "
            f"confidence={self.weights_used.confidence}, consistency={self.weights_used.consistency}",
            "",
            f"Consistency penalty: -{self.consistency.consistency_penalty} (issue rate: {self.consistency.issue_rate})",
        ]
        if self.consistency.findings:
            lines.append("Consistency findings:")
            for f_ in self.consistency.findings:
                lines.append(f"  - {f_}")
        else:
            lines.append("No consistency issues flagged.")
        lines.append("")
        lines.append("Per-question breakdown:")
        for a in self.answer_breakdowns:
            lines.append(
                f"  [{a.question_id}] {a.category}: relevance={a.relevance_score} ({a.relevance_quality}), "
                f"communication={a.communication_score}, confidence={a.confidence_score} "
                f"-> weighted={a.weighted_positive_component}"
            )
        return "\n".join(lines)


def score_hr_interview(session: InterviewSession, weights: Optional[WeightConfig] = None) -> HRInterviewScoreReport:
    weights = weights or WeightConfig()
    weights.validate()

    answered: List[InterviewQuestionState] = [q for q in session.questions if q.response_captured and q.response_text]

    if not answered:
        return HRInterviewScoreReport(
            overall_hr_score=0.0, weights_used=weights, answer_breakdowns=[],
            avg_relevance=0.0, avg_communication=0.0, avg_confidence=0.0,
            consistency=ConsistencyAssessment(0, 0, 0.0, 0.0, []), num_questions_answered=0,
        )

    breakdowns = [_score_answer(q, weights) for q in answered]

    avg_relevance = round(sum(b.relevance_score for b in breakdowns) / len(breakdowns), 1)
    avg_communication = round(sum(b.communication_score for b in breakdowns) / len(breakdowns), 1)
    avg_confidence = round(sum(b.confidence_score for b in breakdowns) / len(breakdowns), 1)
    avg_weighted_positive = round(sum(b.weighted_positive_component for b in breakdowns) / len(breakdowns), 1)

    consistency = _assess_consistency(session, weights)

    overall = round(_clamp(avg_weighted_positive - consistency.consistency_penalty), 1)

    return HRInterviewScoreReport(
        overall_hr_score=overall, weights_used=weights, answer_breakdowns=breakdowns,
        avg_relevance=avg_relevance, avg_communication=avg_communication, avg_confidence=avg_confidence,
        consistency=consistency, num_questions_answered=len(answered),
    )
