"""
AI Conversation Flow Design (Day 29)

SCOPE, STATED HONESTLY UP FRONT: this is a deterministic decision
tree / state machine over Day 25's already-tested quality gating --
not an LLM-driven conversational agent. Every message the AI would
say is a fixed template filled from the current category and attempt
number, exactly the same "template, not generated prose" discipline
Day 28 applied to report bullets. A real conversational AI would want
natural, varied phrasing generated per-turn; this module deliberately
does not claim that, since nothing here has been tested against real
candidate speech patterns, only against the same kind of hand-written
example text every prior demo has used.

Reuse, not reimplementation: SILENCE and off-topic/vague detection
are NOT redone here -- Day 25's understand_answer() already produces
AnswerQuality.MISSING/VAGUE/OFF_TOPIC/OK for exactly this purpose, and
this module calls it directly. Only two genuinely new detectors are
needed for what Day 25 doesn't cover: CONFUSION (a candidate asking
the AI to repeat/clarify, which is a reaction to the question, not a
property of an answer's content) and REPEATED ANSWERS (comparing a
turn's text against everything said earlier in the SAME call, which
requires call-level state Day 25 never had -- it works one answer at
a time).

Pipeline position -- this sits BESIDE Day 25-28, not after them. Those
days evaluate a call's answers after the call is transcribed. This
module decides, live, what the AI should ask/say next while the call
is still happening:

    (existing) audio -> STT -> clean -> understand_answer() -> scoring/report
    (this day) ConversationFlowController.process_turn() -- decides
               the NEXT prompt the AI plays, turn by turn, during the
               call itself
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from parsers.answer_intent_engine import AnswerQuality, StructuredAnswer, understand_answer
from parsers.screening_question_bank import CATEGORIES

# ---------------------------------------------------------------------------
# Constants -- named, adjustable, reasonable-but-arbitrary (same stance
# as every prior day's thresholds)
# ---------------------------------------------------------------------------

_MAX_ATTEMPTS_PER_CATEGORY = 2        # initial ask + 1 retry before giving up
_THIN_ANSWER_WORD_THRESHOLD = 5       # OK answers at or below this word count get one follow-up probe
_REPEATED_ANSWER_WORD_OVERLAP = 0.8   # Jaccard word-overlap ratio treated as "the same answer again"

_CONFUSION_PHRASES = [
    "what do you mean", "can you repeat", "could you repeat", "sorry, what",
    "sorry what", "i don't understand", "i dont understand", "didn't understand",
    "didnt understand", "come again", "pardon", "say that again", "not clear", "can you clarify",
]


class FlowAction(str, Enum):
    RETRY_SILENCE = "retry_silence"
    CLARIFY_CONFUSION = "clarify_confusion"
    REDIRECT_OFF_TOPIC = "redirect_off_topic"
    ASK_FALLBACK = "ask_fallback"
    ACKNOWLEDGE_REPEATED = "acknowledge_repeated"
    ASK_FOLLOW_UP = "ask_follow_up"
    ADVANCE = "advance"
    POLITE_SKIP = "polite_skip"
    END_CALL = "end_call"


# ---------------------------------------------------------------------------
# Templated messages -- filled from category name only, never freely
# generated. Fallback/clarification intentionally share one simplified-
# restatement bank: both situations need the same thing -- a shorter,
# plainer version of the same question -- so one bank serves both
# rather than maintaining two near-duplicate sets of phrasing.
# ---------------------------------------------------------------------------

_SIMPLIFIED_RESTATEMENT: Dict[str, str] = {
    "introduction": "No problem -- in short, what's your name and current role?",
    "education": "Just to simplify -- what degree did you complete, and from where?",
    "experience": "In short -- how many years of relevant experience do you have?",
    "skills": "Simply put -- what are the main technical skills you'd like to highlight?",
    "location": "Just to confirm -- which city are you currently based in?",
    "salary": "In short -- what salary are you currently expecting?",
    "notice_period": "Simply -- how soon could you join if selected?",
}

_FOLLOW_UP_PROBE: Dict[str, str] = {
    "introduction": "Thanks -- could you tell me a bit more about your background?",
    "education": "Got it -- any specific specialization or achievements worth mentioning?",
    "experience": "Understood -- what did that experience mainly involve?",
    "skills": "Great -- which of those would you say you're strongest in?",
    "location": "Thanks -- would you be open to relocating if needed?",
    "salary": "Understood -- is that figure negotiable?",
    "notice_period": "Got it -- is that notice period flexible?",
}

_POLITE_SKIP_MESSAGE = "That's alright, let's move on to the next question."
_REPEATED_ACK_MESSAGE = "I think you've mentioned that already -- let's continue."
_END_CALL_MESSAGE = "Thank you, that's everything I needed. We'll be in touch with next steps."


@dataclass
class NextAction:
    action_type: FlowAction
    message: str
    category: str
    attempt_number: int
    reason: str
    structured_answer: Optional[StructuredAnswer] = None

    def to_dict(self) -> Dict:
        return {
            "action_type": self.action_type.value,
            "message": self.message,
            "category": self.category,
            "attempt_number": self.attempt_number,
            "reason": self.reason,
            "quality": self.structured_answer.quality.value if self.structured_answer else None,
        }


# ---------------------------------------------------------------------------
# The two genuinely new detectors Day 25 doesn't provide
# ---------------------------------------------------------------------------

def detect_confusion(text: str) -> bool:
    """A candidate reaction to the QUESTION, not a property of an
    answer's content -- distinct from Day 25's quality gate, which
    only ever judges the substance of what was said.
    """
    lowered = text.lower()
    return any(re.search(rf"\b{re.escape(phrase)}\b", lowered) for phrase in _CONFUSION_PHRASES)


def _word_set(text: str) -> set:
    return set(re.findall(r"[a-z0-9']+", text.lower()))


def detect_repeated_answer(text: str, previous_texts: List[str]) -> bool:
    """Lexical-overlap check only -- NOT semantic. Two answers that say
    the same thing in different words will NOT be caught; this is a
    stated limitation, not a silent gap, consistent with this
    project's honesty stance on every other rule-based detector.
    """
    current_words = _word_set(text)
    if not current_words:
        return False
    for prev in previous_texts:
        prev_words = _word_set(prev)
        if not prev_words:
            continue
        overlap = len(current_words & prev_words) / len(current_words | prev_words)
        if overlap >= _REPEATED_ANSWER_WORD_OVERLAP:
            return True
    return False


# ---------------------------------------------------------------------------
# The conversation state machine -- the "conversation state machine"
# and "AI call flow logic" deliverables
# ---------------------------------------------------------------------------

@dataclass
class _CategoryState:
    attempts: int = 0
    fallback_used: bool = False
    follow_up_used: bool = False


class ConversationFlowController:
    """Drives one candidate's screening call, one turn at a time.
    Call process_turn() with each new (possibly silent) response;
    it returns the NextAction the AI should take, and advances its own
    internal state accordingly. Every action taken is kept in
    self.action_log for the "error-handling flow design" audit trail.
    """

    def __init__(self, categories: Optional[List[str]] = None):
        self.categories: List[str] = list(categories) if categories is not None else list(CATEGORIES)
        self._index: int = 0
        self._state: Dict[str, _CategoryState] = {c: _CategoryState() for c in self.categories}
        self._all_raw_texts: List[Tuple[str, str]] = []   # (category, text) across the WHOLE call
        self.action_log: List[NextAction] = []

    @property
    def current_category(self) -> Optional[str]:
        if self._index >= len(self.categories):
            return None
        return self.categories[self._index]

    @property
    def is_call_complete(self) -> bool:
        return self._index >= len(self.categories)

    def _advance(self) -> None:
        self._index += 1

    def process_turn(self, text: str, is_silent: bool = False) -> NextAction:
        if self.is_call_complete:
            action = NextAction(FlowAction.END_CALL, _END_CALL_MESSAGE, category="", attempt_number=0,
                                 reason="Call already complete -- no more categories to ask.")
            self.action_log.append(action)
            return action

        category = self.current_category
        state = self._state[category]
        state.attempts += 1

        structured = understand_answer(text, expected_category=category, turn_id=None, is_silent=is_silent)

        # Priority order, documented: confusion is checked first because
        # it's a reaction to the QUESTION and should be resolved before
        # judging the (non-)answer that came with it; silence next since
        # there's nothing else to evaluate; repeated-answer next since a
        # copy-pasted answer shouldn't be scored as if it were new content
        # for THIS category; quality-based branches last.
        if not is_silent and detect_confusion(text):
            action = self._handle_confusion(category, state, structured)
        elif is_silent:
            action = self._handle_silence(category, state, structured)
        elif detect_repeated_answer(text, [t for c, t in self._all_raw_texts]):
            action = self._handle_repeated(category, state, structured)
        elif structured.quality == AnswerQuality.OFF_TOPIC:
            action = self._handle_off_topic(category, state, structured)
        elif structured.quality == AnswerQuality.VAGUE:
            action = self._handle_vague(category, state, structured)
        else:  # OK
            action = self._handle_ok(category, state, text, structured)

        if not is_silent:
            self._all_raw_texts.append((category, text))
        self.action_log.append(action)
        return action

    # -- individual handlers, one per condition, each a short, testable unit --

    def _handle_confusion(self, category: str, state: _CategoryState, structured: StructuredAnswer) -> NextAction:
        if state.attempts >= _MAX_ATTEMPTS_PER_CATEGORY:
            return self._polite_skip(category, state, structured, "Repeated confusion after max attempts.")
        return NextAction(FlowAction.CLARIFY_CONFUSION, _SIMPLIFIED_RESTATEMENT[category], category, state.attempts,
                           "Candidate signaled confusion about the question.", structured)

    def _handle_silence(self, category: str, state: _CategoryState, structured: StructuredAnswer) -> NextAction:
        if state.attempts < _MAX_ATTEMPTS_PER_CATEGORY:
            return NextAction(FlowAction.RETRY_SILENCE, f"Are you still there? {_SIMPLIFIED_RESTATEMENT[category]}",
                               category, state.attempts, "No speech detected -- re-prompting.", structured)
        if not state.fallback_used:
            state.fallback_used = True
            return NextAction(FlowAction.ASK_FALLBACK, _SIMPLIFIED_RESTATEMENT[category], category, state.attempts,
                               "Still silent after max retries -- one simplified fallback attempt.", structured)
        return self._polite_skip(category, state, structured, "Silent after retries and fallback.")

    def _handle_repeated(self, category: str, state: _CategoryState, structured: StructuredAnswer) -> NextAction:
        action = NextAction(FlowAction.ACKNOWLEDGE_REPEATED, _REPEATED_ACK_MESSAGE, category, state.attempts,
                             "Answer's wording closely matches something said earlier in the call.", structured)
        self._advance()
        return action

    def _handle_off_topic(self, category: str, state: _CategoryState, structured: StructuredAnswer) -> NextAction:
        if state.attempts < _MAX_ATTEMPTS_PER_CATEGORY:
            return NextAction(FlowAction.REDIRECT_OFF_TOPIC,
                               f"That's helpful, but I actually wanted to ask about your {category}. {_SIMPLIFIED_RESTATEMENT[category]}",
                               category, state.attempts, "Answer matched a different category's content.", structured)
        return self._polite_skip(category, state, structured, "Still off-topic after max attempts.")

    def _handle_vague(self, category: str, state: _CategoryState, structured: StructuredAnswer) -> NextAction:
        if not state.fallback_used and state.attempts < _MAX_ATTEMPTS_PER_CATEGORY:
            state.fallback_used = True
            return NextAction(FlowAction.ASK_FALLBACK, _SIMPLIFIED_RESTATEMENT[category], category, state.attempts,
                               "Answer was too vague/hedged to score -- one simplified fallback attempt.", structured)
        return self._polite_skip(category, state, structured, "Still vague after fallback attempt.")

    def _handle_ok(self, category: str, state: _CategoryState, text: str, structured: StructuredAnswer) -> NextAction:
        word_count = len(text.split())
        if word_count <= _THIN_ANSWER_WORD_THRESHOLD and not state.follow_up_used:
            state.follow_up_used = True
            return NextAction(FlowAction.ASK_FOLLOW_UP, _FOLLOW_UP_PROBE[category], category, state.attempts,
                               f"Answer was on-topic but thin ({word_count} words) -- probing once for more detail.", structured)
        action = NextAction(FlowAction.ADVANCE, "Thanks, that's helpful.", category, state.attempts,
                             "Answer was complete and on-topic.", structured)
        self._advance()
        return action

    def _polite_skip(self, category: str, state: _CategoryState, structured: StructuredAnswer, reason: str) -> NextAction:
        action = NextAction(FlowAction.POLITE_SKIP, _POLITE_SKIP_MESSAGE, category, state.attempts, reason, structured)
        self._advance()
        return action
