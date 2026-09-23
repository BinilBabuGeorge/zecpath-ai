"""
Aptitude Logic Design (Day 38)

WHAT THIS DAY IS: the foundation for a genuinely NEW phase of this
project -- cognitive/situational evaluation -- distinct from both the
factual screening phase (Days 22-32) and the behavioral HR-interview
phase (Days 33-37). Screening asks WHAT a candidate has done;
HR-interview asks HOW they communicate and present themselves; this
phase asks HOW THEY THINK -- logical reasoning puzzles and workplace
situational-judgment scenarios, each with a hand-mapped "ideal answer
structure" to score against. Same DESIGN-day discipline as Day 33:
real, tested, runnable code, not a diagram -- a question bank, a
session structure, and (since scoring is inseparable from what "ideal
answer structure" even means) a scoring model, all in one day because
the brief bundles design and scoring tasks together this time, unlike
Days 33/34/35 which spread an equivalent scope across three days.

REUSE, NOT REIMPLEMENTATION: "detect problem-solving clarity" is
conceptually the same thing Day 35 already built for behavioral
answers -- concrete grounding, clarity connectors, vagueness. Rather
than re-deriving a second clarity heuristic, this day imports Day 35's
`assess_clarity()` directly and applies it to aptitude responses
unchanged. The session/question-bank SHAPE (a linear sequence of
question states, captured one response at a time) follows Day 33's
pattern -- but the pattern is reused, not the code, since aptitude
questions (fixed logic puzzles/scenarios with hand-mapped ideal
elements) are structurally nothing like Day 33's role-varied
behavioral question generator. A new, small `AptitudeSession` is built
rather than stretching Day 33's `InterviewSession` to fit a domain it
wasn't designed for.

IDEAL ANSWER STRUCTURES, STATED HONESTLY: "mapping an ideal answer
structure" here means a hand-written list of the KEY REASONING
ELEMENTS a strong answer would touch on (e.g., for the classic
fox/chicken/grain puzzle: taking the chicken across first, leaving
fox+grain safely together, then bringing the chicken back) --
matched by keyword/phrase presence, the same deterministic,
non-ML-model approach every classifier in this project uses. This is
NOT a formal logical-proof checker or a semantic answer grader --
it cannot tell a correct answer phrased unusually from a wrong one
that happens to use the right words. Named here rather than implied
by "scoring model."

SCORING MODEL: for each answer, `logical_reasoning_score` combines (1)
how many of the ideal answer's key elements were matched, weighted
most heavily since that's the actual reasoning content, and (2) the
density of logical/causal connectors ("because", "therefore", "if...
then"), a weaker but real signal that the candidate is reasoning
through steps rather than asserting a conclusion. `clarity_score`
reuses Day 35 unchanged. `overall_aptitude_score` weights reasoning
content over clarity of expression (60/40) -- reasoned, not
data-calibrated (no labeled data exists in this project, the same
caveat as every prior scoring day), and kept as named constants so the
weighting is easy to find and change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from parsers.communication_skill_engine import assess_clarity, ClarityResult

_LOGICAL_REASONING_SCORE_WEIGHT = 0.6
_CLARITY_SCORE_WEIGHT = 0.4

_COVERAGE_SCORE_WEIGHT = 70.0   # of the 100-point logical_reasoning_score
_CONNECTOR_SCORE_CAP = 30.0     # remaining points available from connector usage
_CONNECTOR_POINTS_PER_HIT = 10.0

_LOGICAL_CONNECTORS = [
    "because", "therefore", "since", "thus", "hence", "if", "then", "as a result",
    "which means", "so that", "given that", "in order to", "consequently", "so,",
]


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


class AptitudeQuestionType(str, Enum):
    LOGICAL_REASONING = "logical_reasoning"
    SITUATIONAL_JUDGMENT = "situational_judgment"


@dataclass
class IdealAnswerElement:
    """One key reasoning element an ideal answer would touch on,
    matched by ANY of its phrases being present (case-insensitive
    substring match) -- deterministic, not semantic."""
    label: str
    match_phrases: List[str]

    def matches(self, lowered_text: str) -> bool:
        return any(phrase in lowered_text for phrase in self.match_phrases)


@dataclass
class AptitudeQuestion:
    question_id: str
    question_type: AptitudeQuestionType
    prompt_text: str
    ideal_answer_elements: List[IdealAnswerElement]


# ---------------------------------------------------------------------------
# The question bank -- "design reasoning-based questions" +
# "build situational judgment scenarios" + "map ideal answer
# structures", all hand-written, same discipline as every other
# question bank in this project (Days 22, 29, 33, 34).
# ---------------------------------------------------------------------------

APTITUDE_QUESTION_BANK: List[AptitudeQuestion] = [
    AptitudeQuestion(
        question_id="apt-lr01", question_type=AptitudeQuestionType.LOGICAL_REASONING,
        prompt_text=(
            "You have three boxes labeled 'Apples', 'Oranges', and 'Mixed', but all three "
            "labels are wrong. You may pick one fruit from ONE box without looking inside. "
            "How do you correctly relabel all three boxes?"
        ),
        ideal_answer_elements=[
            IdealAnswerElement("identifies the mixed-labeled box as the one to pick from", ["mixed box", "labeled mixed", "the box labeled mixed"]),
            IdealAnswerElement("recognizes every label is wrong (the key constraint)", ["all labels are wrong", "every label is incorrect", "none of the labels are correct", "all three labels are wrong"]),
            IdealAnswerElement("describes drawing one fruit as the deciding action", ["pick one fruit", "draw one fruit", "take one fruit", "pick a fruit"]),
            IdealAnswerElement("states the resulting deduction for the other two boxes", ["relabel", "deduce the other two", "figure out the remaining", "the other two boxes"]),
        ],
    ),
    AptitudeQuestion(
        question_id="apt-lr02", question_type=AptitudeQuestionType.LOGICAL_REASONING,
        prompt_text=(
            "A farmer must cross a river with a fox, a chicken, and a bag of grain. The boat "
            "carries only the farmer and one item at a time. Left unattended, the fox eats the "
            "chicken, and the chicken eats the grain. How does the farmer get everything across safely?"
        ),
        ideal_answer_elements=[
            IdealAnswerElement("takes the chicken across first", ["take the chicken first", "bring the chicken across first", "chicken first"]),
            IdealAnswerElement("returns alone for the next item", ["goes back alone", "returns alone", "comes back empty", "goes back for"]),
            IdealAnswerElement("recognizes fox and grain are safe together", ["fox and grain", "grain and fox", "fox with the grain"]),
            IdealAnswerElement("brings the chicken back at some point (the key trick)", ["bring the chicken back", "take the chicken back", "return with the chicken", "brings the chicken back"]),
        ],
    ),
    AptitudeQuestion(
        question_id="apt-lr03", question_type=AptitudeQuestionType.LOGICAL_REASONING,
        prompt_text=(
            "All Zorgs are Blips. Some Blips are Trons. Can you conclude that some Zorgs are "
            "Trons? Explain your reasoning."
        ),
        ideal_answer_elements=[
            IdealAnswerElement("concludes it cannot be determined", ["cannot conclude", "not necessarily", "no, we cannot", "can't be certain", "cannot be determined"]),
            IdealAnswerElement("notes the Trons might be a different subset of Blips than the Zorgs", ["different subset", "not the same blips", "might not overlap", "may not include"]),
            IdealAnswerElement("references the overlap/subset relationship explicitly", ["overlap", "subset", "some blips"]),
            IdealAnswerElement("offers or implies a counterexample style justification", ["example", "counterexample", "for instance", "imagine if"]),
        ],
    ),
    AptitudeQuestion(
        question_id="apt-sj01", question_type=AptitudeQuestionType.SITUATIONAL_JUDGMENT,
        prompt_text=(
            "You notice a teammate consistently missing deadlines, which is affecting the "
            "whole team's delivery. What would you do?"
        ),
        ideal_answer_elements=[
            IdealAnswerElement("talks to the teammate directly/privately", ["talk to them", "speak with", "have a conversation", "approach them privately", "talk to him", "talk to her"]),
            IdealAnswerElement("tries to understand the underlying cause", ["understand why", "find out the reason", "ask what's going on", "ask what is going on"]),
            IdealAnswerElement("offers support or help", ["offer help", "support them", "see if i can help", "help them"]),
            IdealAnswerElement("considers escalation only if it continues", ["escalate", "involve the manager", "if it continues", "if the issue persists"]),
        ],
    ),
    AptitudeQuestion(
        question_id="apt-sj02", question_type=AptitudeQuestionType.SITUATIONAL_JUDGMENT,
        prompt_text=(
            "Your manager asks you to complete a task in a way you believe is technically "
            "wrong, but they insist. What do you do?"
        ),
        ideal_answer_elements=[
            IdealAnswerElement("raises the concern rather than staying silent", ["explain my concern", "raise the issue", "share my perspective", "raise my concern"]),
            IdealAnswerElement("backs the concern with reasoning/evidence", ["provide reasoning", "explain why", "give evidence", "explain the risk"]),
            IdealAnswerElement("ultimately respects the manager's final call", ["respect their decision", "follow their decision", "defer to them", "go with their decision"]),
            IdealAnswerElement("documents the disagreement for the record", ["document", "note it", "in writing", "put it in writing"]),
        ],
    ),
    AptitudeQuestion(
        question_id="apt-sj03", question_type=AptitudeQuestionType.SITUATIONAL_JUDGMENT,
        prompt_text=(
            "You're given two urgent tasks with the same deadline by two different "
            "stakeholders. How do you handle it?"
        ),
        ideal_answer_elements=[
            IdealAnswerElement("assesses relative priority/impact first", ["prioritize", "assess priority", "determine which is more urgent", "assess which is more important"]),
            IdealAnswerElement("communicates proactively with both stakeholders", ["communicate", "talk to both", "inform them", "let them know"]),
            IdealAnswerElement("negotiates timeline where possible", ["negotiate", "ask for extension", "renegotiate", "push back the deadline"]),
            IdealAnswerElement("weighs business impact of each task", ["impact", "business impact", "consequences", "what matters more to the business"]),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Session -- reuses Day 33's LINEAR-SEQUENCE PATTERN, not its code
# (see module docstring for why a new, small container is warranted)
# ---------------------------------------------------------------------------

@dataclass
class AptitudeQuestionState:
    question: AptitudeQuestion
    response_text: Optional[str] = None
    response_captured: bool = False

    def capture_response(self, text: str) -> None:
        self.response_text = text
        self.response_captured = True


@dataclass
class AptitudeSession:
    questions: List[AptitudeQuestionState]
    current_index: int = 0

    @classmethod
    def start(cls) -> "AptitudeSession":
        return cls(questions=[AptitudeQuestionState(question=q) for q in APTITUDE_QUESTION_BANK])

    @property
    def current_question(self) -> Optional[AptitudeQuestionState]:
        if self.current_index >= len(self.questions):
            return None
        return self.questions[self.current_index]

    @property
    def is_complete(self) -> bool:
        return self.current_index >= len(self.questions)

    def submit_response(self, text: str) -> None:
        q = self.current_question
        if q is None:
            raise ValueError("Aptitude session already complete -- no current question.")
        q.capture_response(text)
        self.current_index += 1


# ---------------------------------------------------------------------------
# Scoring model -- "score logical thinking ability" + "detect
# problem-solving clarity" (the latter reused from Day 35 unchanged)
# ---------------------------------------------------------------------------

@dataclass
class LogicalReasoningResult:
    matched_elements: List[str]
    missing_elements: List[str]
    coverage_ratio: float
    connector_hits: List[str]
    logical_reasoning_score: float


def assess_logical_reasoning(text: str, question: AptitudeQuestion) -> LogicalReasoningResult:
    lowered = text.lower()
    matched = [e.label for e in question.ideal_answer_elements if e.matches(lowered)]
    missing = [e.label for e in question.ideal_answer_elements if e.label not in matched]
    coverage_ratio = round(len(matched) / len(question.ideal_answer_elements), 3) if question.ideal_answer_elements else 0.0

    connector_hits = [c for c in _LOGICAL_CONNECTORS if c in lowered]
    connector_score = min(_CONNECTOR_SCORE_CAP, len(connector_hits) * _CONNECTOR_POINTS_PER_HIT)

    score = round(_clamp(coverage_ratio * _COVERAGE_SCORE_WEIGHT + connector_score), 1)

    return LogicalReasoningResult(
        matched_elements=matched, missing_elements=missing, coverage_ratio=coverage_ratio,
        connector_hits=connector_hits, logical_reasoning_score=score,
    )


@dataclass
class AptitudeAnswerEvaluation:
    question_id: str
    question_type: str
    reasoning: LogicalReasoningResult
    clarity: ClarityResult
    overall_aptitude_score: float

    def to_dict(self) -> Dict:
        return {
            "question_id": self.question_id,
            "question_type": self.question_type,
            "overall_aptitude_score": self.overall_aptitude_score,
            "logical_reasoning": {
                "score": self.reasoning.logical_reasoning_score,
                "coverage_ratio": self.reasoning.coverage_ratio,
                "matched_elements": self.reasoning.matched_elements,
                "missing_elements": self.reasoning.missing_elements,
                "connector_hits": self.reasoning.connector_hits,
            },
            "problem_solving_clarity": {
                "score": self.clarity.clarity_score,
                "has_concrete_grounding": self.clarity.has_concrete_grounding,
                "is_vague": self.clarity.is_vague,
            },
        }


def evaluate_aptitude_answer(text: str, question: AptitudeQuestion) -> AptitudeAnswerEvaluation:
    reasoning = assess_logical_reasoning(text, question)
    clarity = assess_clarity(text)   # reused directly from Day 35, unchanged
    overall = round(
        reasoning.logical_reasoning_score * _LOGICAL_REASONING_SCORE_WEIGHT
        + clarity.clarity_score * _CLARITY_SCORE_WEIGHT, 1,
    )
    return AptitudeAnswerEvaluation(
        question_id=question.question_id, question_type=question.question_type.value,
        reasoning=reasoning, clarity=clarity, overall_aptitude_score=overall,
    )


# ---------------------------------------------------------------------------
# Session-level aggregate -- the "scenario evaluation framework"
# deliverable applied across a full AptitudeSession
# ---------------------------------------------------------------------------

@dataclass
class AptitudeProfile:
    answer_evaluations: List[AptitudeAnswerEvaluation]
    overall_aptitude_score: float
    logical_reasoning_avg: float
    situational_judgment_avg: float

    def to_dict(self) -> Dict:
        return {
            "overall_aptitude_score": self.overall_aptitude_score,
            "logical_reasoning_avg": self.logical_reasoning_avg,
            "situational_judgment_avg": self.situational_judgment_avg,
            "answer_evaluations": [e.to_dict() for e in self.answer_evaluations],
        }


def build_aptitude_profile(session: AptitudeSession) -> AptitudeProfile:
    answered = [q for q in session.questions if q.response_captured and q.response_text]

    if not answered:
        return AptitudeProfile(answer_evaluations=[], overall_aptitude_score=0.0, logical_reasoning_avg=0.0, situational_judgment_avg=0.0)

    evaluations = [evaluate_aptitude_answer(q.response_text, q.question) for q in answered]

    overall = round(sum(e.overall_aptitude_score for e in evaluations) / len(evaluations), 1)

    lr_scores = [e.overall_aptitude_score for e in evaluations if e.question_type == AptitudeQuestionType.LOGICAL_REASONING.value]
    sj_scores = [e.overall_aptitude_score for e in evaluations if e.question_type == AptitudeQuestionType.SITUATIONAL_JUDGMENT.value]
    lr_avg = round(sum(lr_scores) / len(lr_scores), 1) if lr_scores else 0.0
    sj_avg = round(sum(sj_scores) / len(sj_scores), 1) if sj_scores else 0.0

    return AptitudeProfile(
        answer_evaluations=evaluations, overall_aptitude_score=overall,
        logical_reasoning_avg=lr_avg, situational_judgment_avg=sj_avg,
    )
