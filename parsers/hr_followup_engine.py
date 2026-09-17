"""
Dynamic Follow-Up Logic (Day 34)

WHAT THIS DAY ADDS: Day 33 explicitly deferred the real decision logic
for HR interview follow-ups -- it built `InterviewQuestionState` with a
`follow_up_eligible` flag and a place to record one, but nothing that
actually decided WHEN to ask a follow-up or WHAT KIND. This is exactly
the "future day" Day 33's own docs named: the same relationship
Day 22's screening question bank had to Day 29's conversation flow
engine.

SCOPE, STATED HONESTLY UP FRONT: Day 25's `understand_answer()` cannot
be reused here -- it classifies FACTUAL screening answers (experience,
salary, skills) using category keyword lexicons that have no bearing
on behavioral content ("tell me about a time you disagreed with a
teammate" has no "salary" or "skills" vocabulary to score against).
This module builds its own, differently-scoped, rule-based classifier
for behavioral answers -- still deterministic and keyword/pattern-
based, still not a trained model, same honesty stance as every prior
classifier in this project.

Reuse, not reimplementation: `detect_repeated_answer()` is imported
directly from Day 29's `conversation_flow_engine` -- it's a generic
word-overlap check with no screening-specific logic in it, so reusing
it here for "prevent repetitive questioning" is exactly the right call
rather than duplicating that function.

The mapping this day implements, reconciling the brief's two lists
(follow-up trigger types, and difficulty-adaptation rules) into one
coherent 3-way decision:

    Behavioral answer quality  ->  Follow-up type       ->  What it does
    ------------------------------------------------------------------
    VAGUE (hedged/non-answer)  ->  CLARIFICATION         ->  ask them to restate what they mean
    THIN  (short, no concrete  ->  DEEPENING              ->  "simple responses -> deeper probe"
           example given)
    CONFIDENT (substantive,    ->  EXAMPLE_BASED          ->  "confident responses -> scenario-
           concrete example)                                  based follow-up" / example-based prompt

Every answer quality gets exactly one follow-up TYPE suited to it --
adaptivity here means the NATURE of the follow-up changes with the
answer, not that only "bad" answers get followed up on. A confident,
complete answer to "tell me about your strengths" still benefits from
a scenario-based probe ("how would you apply that in a high-pressure
situation?") -- that's genuine interview practice, not a consolation
prize for a good answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from parsers.conversation_flow_engine import detect_repeated_answer
from parsers.hr_interview_question_bank import InterviewQuestionState, InterviewSession

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_FOLLOW_UPS_PER_QUESTION = 1   # a real interview probes once, not repeatedly -- see "prevent repetitive questioning"
_THIN_ANSWER_WORD_THRESHOLD = 20   # behavioral answers run longer than factual ones; this is NOT Day 29's factual 5-word threshold

_VAGUE_HEDGE_PHRASES = [
    "i don't really have an example", "i dont really have an example", "nothing comes to mind",
    "i'm not sure", "im not sure", "not really sure", "i don't know", "i dont know",
    "i can't think of anything", "i cant think of anything", "hard to say", "depends",
]

# Presence of ANY of these is treated as "this answer contains a
# concrete example," regardless of raw length -- a genuinely different
# signal than Day 25/26/29's word-count-based thinness, because a long
# but entirely generic answer ("I'm hardworking, a team player, and a
# fast learner...") should still be flagged thin in the behavioral
# sense, and a short-but-specific one shouldn't be penalized just for
# brevity.
_CONCRETE_EXAMPLE_MARKERS = [
    "for example", "for instance", "one time", "once,", "when i", "i remember",
    "in my previous role", "in my last job", "specifically", "let me give an example",
    "there was a situation", "a time when", "i recall",
]


class BehavioralAnswerQuality(str, Enum):
    MISSING = "missing"
    VAGUE = "vague"
    THIN = "thin"
    CONFIDENT = "confident"


class FollowUpType(str, Enum):
    CLARIFICATION = "clarification"
    DEEPENING = "deepening"
    EXAMPLE_BASED = "example_based"


# ---------------------------------------------------------------------------
# Behavioral answer quality assessment -- deliberately separate from
# Day 25's understand_answer(), which is scoped to factual content
# ---------------------------------------------------------------------------

def has_concrete_example(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _CONCRETE_EXAMPLE_MARKERS)


def is_vague_behavioral_answer(text: str) -> bool:
    lowered = text.lower().strip()
    return any(re.search(rf"\b{re.escape(phrase)}\b", lowered) for phrase in _VAGUE_HEDGE_PHRASES)


def assess_behavioral_answer(text: str, is_silent: bool = False) -> BehavioralAnswerQuality:
    if is_silent or not text.strip():
        return BehavioralAnswerQuality.MISSING
    if is_vague_behavioral_answer(text):
        return BehavioralAnswerQuality.VAGUE
    word_count = len(text.split())
    if word_count < _THIN_ANSWER_WORD_THRESHOLD and not has_concrete_example(text):
        return BehavioralAnswerQuality.THIN
    if not has_concrete_example(text) and word_count < _THIN_ANSWER_WORD_THRESHOLD * 2:
        # Long-ish but still no concrete marker -- generic padding
        # rather than a real answer. Still THIN, not CONFIDENT, since
        # length alone doesn't establish concreteness.
        return BehavioralAnswerQuality.THIN
    return BehavioralAnswerQuality.CONFIDENT


# ---------------------------------------------------------------------------
# Follow-up prompt templates -- 6 categories x 3 types, hand-written
# and category-appropriate, same discipline as Day 29's per-category
# templates. Never freely generated.
# ---------------------------------------------------------------------------

_FOLLOW_UP_TEMPLATES: Dict[str, Dict[FollowUpType, str]] = {
    "self_introduction": {
        FollowUpType.CLARIFICATION: "Could you clarify -- what's the one thing you'd most want me to know about you?",
        FollowUpType.DEEPENING: "Could you tell me a bit more -- what's your background in a bit more detail?",
        FollowUpType.EXAMPLE_BASED: "That's helpful -- can you give me a specific example of a project or moment that shaped who you are professionally?",
    },
    "career_journey": {
        FollowUpType.CLARIFICATION: "Just to clarify -- could you walk me through that in a bit more order, from where you started?",
        FollowUpType.DEEPENING: "Could you go a bit deeper -- what specifically did you do in that role?",
        FollowUpType.EXAMPLE_BASED: "Can you walk me through one specific project or milestone from that journey in detail?",
    },
    "strengths_weaknesses": {
        FollowUpType.CLARIFICATION: "Could you clarify what you mean by that -- how does that strength show up day to day?",
        FollowUpType.DEEPENING: "Could you say more about that -- why do you see it as a strength or weakness?",
        FollowUpType.EXAMPLE_BASED: "Can you give me a specific example of a time that strength (or weakness) played out at work?",
    },
    "teamwork_culture_fit": {
        FollowUpType.CLARIFICATION: "Could you clarify -- what does working well in a team actually look like for you?",
        FollowUpType.DEEPENING: "Could you tell me more about that -- what was your specific role in the team?",
        FollowUpType.EXAMPLE_BASED: "Can you walk me through a specific situation where teamwork mattered, including any disagreement you navigated?",
    },
    "career_goals": {
        FollowUpType.CLARIFICATION: "Could you clarify -- what does that goal look like concretely, a year or two from now?",
        FollowUpType.DEEPENING: "Could you say more about why that direction appeals to you?",
        FollowUpType.EXAMPLE_BASED: "If you were already in that position, what's one specific thing you'd want to be working on?",
    },
    "availability_commitment": {
        FollowUpType.CLARIFICATION: "Just to clarify -- what would affect your ability to commit to that timeline?",
        FollowUpType.DEEPENING: "Could you say a bit more about your current situation and what's driving that timeline?",
        FollowUpType.EXAMPLE_BASED: "If we needed you to start sooner for the right opportunity, how would you think through that?",
    },
}


def _follow_up_text_for(category: str, follow_up_type: FollowUpType) -> str:
    return _FOLLOW_UP_TEMPLATES[category][follow_up_type]


_QUALITY_TO_FOLLOW_UP_TYPE = {
    BehavioralAnswerQuality.VAGUE: FollowUpType.CLARIFICATION,
    BehavioralAnswerQuality.THIN: FollowUpType.DEEPENING,
    BehavioralAnswerQuality.CONFIDENT: FollowUpType.EXAMPLE_BASED,
}


# ---------------------------------------------------------------------------
# The decision tree -- the "adaptive questioning framework" / "decision
# tree logic" deliverable
# ---------------------------------------------------------------------------

@dataclass
class FollowUpDecision:
    should_follow_up: bool
    follow_up_type: Optional[FollowUpType]
    follow_up_text: Optional[str]
    answer_quality: BehavioralAnswerQuality
    reason: str

    def to_dict(self) -> Dict:
        return {
            "should_follow_up": self.should_follow_up,
            "follow_up_type": self.follow_up_type.value if self.follow_up_type else None,
            "follow_up_text": self.follow_up_text,
            "answer_quality": self.answer_quality.value,
            "reason": self.reason,
        }


def decide_follow_up(
    question: InterviewQuestionState, response_text: str, is_silent: bool = False,
    previous_responses_on_this_question: Optional[List[str]] = None,
) -> FollowUpDecision:
    """The core decision tree. Checks, in order:
    1. Is this question even eligible for a follow-up at all? (Day 33's flag)
    2. Has the repetition cap already been hit? ("prevent repetitive questioning")
    3. Is the candidate just repeating what they already said? (reuses Day 29's detector)
    4. What quality is this specific answer, and what follow-up type does that call for?
    Silence is explicitly NOT handled here -- see module docstring:
    retry logic for missing answers is a different concern, out of
    this day's scope, the same way Day 33 deferred it.
    """
    quality = assess_behavioral_answer(response_text, is_silent=is_silent)

    if quality == BehavioralAnswerQuality.MISSING:
        return FollowUpDecision(False, None, None, quality, "No answer given -- a follow-up doesn't address silence; that's retry-logic scope, not this day's.")

    if not question.follow_up_eligible:
        return FollowUpDecision(False, None, None, quality, f"'{question.category}' is not eligible for a follow-up by design (see Day 33's category defaults).")

    if question.follow_up_asked:
        return FollowUpDecision(False, None, None, quality, f"Already asked one follow-up on this question -- capped at {_MAX_FOLLOW_UPS_PER_QUESTION} to prevent repetitive questioning.")

    if previous_responses_on_this_question and detect_repeated_answer(response_text, previous_responses_on_this_question):
        return FollowUpDecision(False, None, None, quality, "This response closely repeats an earlier one on the same question -- asking again would not surface new information.")

    follow_up_type = _QUALITY_TO_FOLLOW_UP_TYPE[quality]
    text = _follow_up_text_for(question.category, follow_up_type)
    reason = {
        BehavioralAnswerQuality.VAGUE: "Answer was vague/hedged -- asking for clarification.",
        BehavioralAnswerQuality.THIN: "Answer was thin/generic with no concrete example -- probing deeper.",
        BehavioralAnswerQuality.CONFIDENT: "Answer was confident and concrete -- following up with a scenario-based probe.",
    }[quality]
    return FollowUpDecision(True, follow_up_type, text, quality, reason)


def process_response_with_follow_up(session: InterviewSession, response_text: str, is_silent: bool = False) -> FollowUpDecision:
    """Convenience wrapper tying the decision tree to a live
    InterviewSession: evaluates the CURRENT question's response,
    records the follow-up on the state (Day 33's InterviewQuestionState)
    if warranted, and returns the decision for the caller to act on
    (e.g. actually asking the follow-up text before advancing).
    Does NOT call session.submit_response() itself -- advancing past
    the question is the caller's decision (e.g. only after the
    follow-up, if any, has also been captured), kept separate so this
    function has exactly one responsibility.
    """
    question = session.current_question
    if question is None:
        return FollowUpDecision(False, None, None, BehavioralAnswerQuality.MISSING, "Interview already complete -- no current question.")

    previous = [question.response_text] if question.response_text else None
    decision = decide_follow_up(question, response_text, is_silent=is_silent, previous_responses_on_this_question=previous)
    if decision.should_follow_up:
        question.record_follow_up(decision.follow_up_text, follow_up_type=decision.follow_up_type.value)
    return decision
