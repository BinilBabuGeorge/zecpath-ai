"""
Edge Case & Failure Handling (Day 31)

SCOPE, STATED HONESTLY UP FRONT: this module handles exactly two new
detectable conditions -- poor/noisy audio and language mismatch -- plus
a generic crash-safety net. It does NOT add real noise-cancellation,
real language identification, or real code-switching (intra-sentence
language mixing) detection, because none of those exist anywhere in
this project to build on:

  - "Poor audio" and "background noise" are collapsed into ONE signal
    here: Day 24's mock STT confidence score. This project's STT layer
    has never modeled noise and audio quality as separate signals --
    both manifest as "confidence is low" in the only data this pipeline
    has ever produced, so treating them as one condition is honest,
    not a shortcut around a distinction that was never real to begin
    with.
  - "Language mixing" is handled ONLY at the whole-utterance level:
    Day 24's RawSTTResult.language is a single field describing the
    entire transcribed utterance. Real code-switching -- a candidate
    mixing Hindi words into an English sentence -- would require
    token-level language identification this project has never had and
    does not attempt here. What IS handled: the whole utterance being
    tagged in a different language than the call expects.
  - The pipeline is, and remains, English-only. Day 25's category
    keyword lexicons, Day 27's sentiment lexicon, and everything else
    downstream only understand English. A language-mismatch turn is
    handled by asking the candidate to switch to English, not by
    attempting to process what they said.

Reuse, not reimplementation: silence is still Day 25/29's job
(unchanged). Retry/clarification/polite-skip messaging follows the
same shape Day 29 established. The only change to Day 29's own file is
one small, additive public method (force_skip_current_category) for
crash/edge-case recovery -- documented and tested there, nothing else
in Day 29 touched.

Pipeline position -- this wraps Day 29's controller, sitting between
the raw STT result and Day 29's normal per-turn logic:

    RawSTTResult (Day 24)
        -> RobustConversationController.process_turn()  (Day 31, THIS module)
             -> edge case detected?  -> handle directly (retry/clarify/
                                         safety fallback), Day 29 never
                                         sees this turn
             -> no edge case?        -> clean_transcript() (Day 24)
                                         -> ConversationFlowController.
                                            process_turn()  (Day 29,
                                            unchanged)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from parsers.speech_to_text import RawSTTResult, clean_transcript, CleanStatus
from parsers.conversation_flow_engine import ConversationFlowController, NextAction

# ---------------------------------------------------------------------------
# Constants -- named, adjustable, reasonable-but-arbitrary, same stance
# as every prior day's thresholds
# ---------------------------------------------------------------------------

_POOR_AUDIO_CONFIDENCE_THRESHOLD = 0.4     # below this: too unreliable to score as-is
_UNUSABLE_AUDIO_CONFIDENCE_THRESHOLD = 0.15  # below this: essentially no signal at all
_MAX_EDGE_CASE_ATTEMPTS_PER_CATEGORY = 2    # retries before giving up on THIS question
_MAX_CONSECUTIVE_EDGE_CASES_PER_CALL = 3    # consecutive edge-case turns before ending the call
_EXPECTED_LANGUAGE = "en"                   # this project's entire pipeline is English-only


class EdgeCaseType(str, Enum):
    NONE = "none"
    POOR_AUDIO = "poor_audio"
    LANGUAGE_MISMATCH = "language_mismatch"


class EdgeCaseAction(str, Enum):
    RETRY_AUDIO = "retry_audio"
    CLARIFY_LANGUAGE = "clarify_language"
    SAFETY_FALLBACK_SKIP = "safety_fallback_skip"
    SAFETY_FALLBACK_END_CALL = "safety_fallback_end_call"
    CRASH_GUARD_SKIP = "crash_guard_skip"
    PASSTHROUGH = "passthrough"   # no edge case -- handled normally by Day 29


_POOR_AUDIO_RETRY_MESSAGE = "Sorry, I couldn't hear that clearly -- could you say that again, a little closer to the mic?"
_UNUSABLE_AUDIO_RETRY_MESSAGE = "I'm having real trouble hearing you at all -- could you check your connection and repeat that?"
_LANGUAGE_CLARIFY_MESSAGE = "I want to make sure I get this right -- could you answer that in English?"
_SAFETY_SKIP_MESSAGE = "No problem, let's move on to the next question."
_SAFETY_END_CALL_MESSAGE = "It looks like we're having trouble with the call quality. Let's stop here -- we'll be in touch to reschedule."
_CRASH_GUARD_MESSAGE = "Let's move on to the next question."   # deliberately identical in tone to a normal skip -- the candidate should never see an internal failure


@dataclass
class TurnOutcome:
    action: EdgeCaseAction
    message: str
    edge_case_type: EdgeCaseType
    call_ended: bool = False
    underlying_action: Optional[NextAction] = None   # Day 29's own NextAction, present only for PASSTHROUGH
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "action": self.action.value,
            "message": self.message,
            "edge_case_type": self.edge_case_type.value,
            "call_ended": self.call_ended,
            "underlying_action": self.underlying_action.to_dict() if self.underlying_action else None,
            "notes": self.notes,
        }


def classify_audio_quality(confidence: float) -> str:
    if confidence < _UNUSABLE_AUDIO_CONFIDENCE_THRESHOLD:
        return "unusable"
    if confidence < _POOR_AUDIO_CONFIDENCE_THRESHOLD:
        return "poor"
    return "good"


def detect_language_mismatch(raw_language: str, expected_language: str = _EXPECTED_LANGUAGE) -> bool:
    return raw_language.lower() != expected_language.lower()


@dataclass
class _EdgeCaseState:
    audio_attempts: int = 0
    language_attempts: int = 0


class RobustConversationController:
    """Wraps a Day 29 ConversationFlowController (by composition --
    Day 29's own file is untouched apart from one additive public
    method) with edge-case detection and a crash-safety net. Call
    process_turn() with each new RawSTTResult; internally this either
    handles an edge case directly, or hands clean text off to the
    wrapped Day 29 controller exactly as before.
    """

    def __init__(self, categories: Optional[List[str]] = None, expected_language: str = _EXPECTED_LANGUAGE):
        self._flow = ConversationFlowController(categories=categories)
        self._expected_language = expected_language
        self._edge_state: Dict[str, _EdgeCaseState] = {c: _EdgeCaseState() for c in self._flow.categories}
        self._consecutive_edge_cases = 0
        self.call_ended_early = False
        self.outcome_log: List[TurnOutcome] = []

    @property
    def current_category(self) -> Optional[str]:
        return self._flow.current_category

    @property
    def is_call_complete(self) -> bool:
        return self.call_ended_early or self._flow.is_call_complete

    def process_turn(self, raw: RawSTTResult) -> TurnOutcome:
        try:
            outcome = self._process_turn_inner(raw)
        except Exception as exc:  # the crash-safety net of last resort
            reason = f"Unexpected error while processing this turn, safely skipped: {type(exc).__name__}: {exc}"
            underlying = None
            if not self.is_call_complete:
                underlying = self._flow.force_skip_current_category(reason)
            outcome = TurnOutcome(
                EdgeCaseAction.CRASH_GUARD_SKIP, _CRASH_GUARD_MESSAGE, EdgeCaseType.NONE,
                call_ended=self.is_call_complete, underlying_action=underlying, notes=[reason],
            )
        self.outcome_log.append(outcome)
        return outcome

    def _process_turn_inner(self, raw: RawSTTResult) -> TurnOutcome:
        if self.is_call_complete:
            action = self._flow.process_turn("", is_silent=True)  # Day 29's own END_CALL path
            return TurnOutcome(EdgeCaseAction.PASSTHROUGH, action.message, EdgeCaseType.NONE,
                                call_ended=True, underlying_action=action)

        category = self._flow.current_category

        # Priority: unusable/poor audio is checked before language,
        # since garbled audio makes the detected language unreliable
        # too -- there is no point clarifying a language tag produced
        # from a signal too weak to trust in the first place.
        if not raw.is_silent:
            quality = classify_audio_quality(raw.confidence)
            if quality == "unusable":
                return self._handle_poor_audio(category, raw, severity="unusable")
            if quality == "poor":
                return self._handle_poor_audio(category, raw, severity="poor")
            if detect_language_mismatch(raw.language, self._expected_language):
                return self._handle_language_mismatch(category, raw)

        # No edge case (including genuine silence, which Day 25/29
        # already handle correctly) -- reset the streak and pass
        # through to Day 29 unchanged.
        self._consecutive_edge_cases = 0
        cleaned = clean_transcript(raw)
        is_silent_for_flow = cleaned.status == CleanStatus.SILENT
        action = self._flow.process_turn(cleaned.text, is_silent=is_silent_for_flow)
        return TurnOutcome(EdgeCaseAction.PASSTHROUGH, action.message, EdgeCaseType.NONE,
                            call_ended=self._flow.is_call_complete, underlying_action=action)

    def _handle_poor_audio(self, category: str, raw: RawSTTResult, severity: str) -> TurnOutcome:
        state = self._edge_state[category]
        state.audio_attempts += 1
        self._consecutive_edge_cases += 1

        if self._consecutive_edge_cases >= _MAX_CONSECUTIVE_EDGE_CASES_PER_CALL:
            return self._safety_end_call(f"{self._consecutive_edge_cases} consecutive edge-case turns -- likely a systemic call-quality issue, not per-question bad luck.")

        if state.audio_attempts < _MAX_EDGE_CASE_ATTEMPTS_PER_CATEGORY:
            message = _UNUSABLE_AUDIO_RETRY_MESSAGE if severity == "unusable" else _POOR_AUDIO_RETRY_MESSAGE
            return TurnOutcome(EdgeCaseAction.RETRY_AUDIO, message, EdgeCaseType.POOR_AUDIO,
                                notes=[f"Audio confidence {raw.confidence} classified '{severity}' (attempt {state.audio_attempts})."])

        underlying = self._flow.force_skip_current_category(f"Persistent poor audio on this question after {state.audio_attempts} attempts.")
        return TurnOutcome(EdgeCaseAction.SAFETY_FALLBACK_SKIP, _SAFETY_SKIP_MESSAGE, EdgeCaseType.POOR_AUDIO,
                            call_ended=self.is_call_complete, underlying_action=underlying,
                            notes=["Skipped this question after repeated poor-audio attempts."])

    def _handle_language_mismatch(self, category: str, raw: RawSTTResult) -> TurnOutcome:
        state = self._edge_state[category]
        state.language_attempts += 1
        self._consecutive_edge_cases += 1

        if self._consecutive_edge_cases >= _MAX_CONSECUTIVE_EDGE_CASES_PER_CALL:
            return self._safety_end_call(f"{self._consecutive_edge_cases} consecutive edge-case turns -- likely a systemic language/audio issue, not per-question bad luck.")

        if state.language_attempts < _MAX_EDGE_CASE_ATTEMPTS_PER_CATEGORY:
            return TurnOutcome(EdgeCaseAction.CLARIFY_LANGUAGE, _LANGUAGE_CLARIFY_MESSAGE, EdgeCaseType.LANGUAGE_MISMATCH,
                                notes=[f"Detected language '{raw.language}', expected '{self._expected_language}' (attempt {state.language_attempts})."])

        underlying = self._flow.force_skip_current_category(f"Candidate did not switch to {self._expected_language} after {state.language_attempts} attempts.")
        return TurnOutcome(EdgeCaseAction.SAFETY_FALLBACK_SKIP, _SAFETY_SKIP_MESSAGE, EdgeCaseType.LANGUAGE_MISMATCH,
                            call_ended=self.is_call_complete, underlying_action=underlying,
                            notes=["Skipped this question -- candidate did not switch to the expected language."])

    def _safety_end_call(self, reason: str) -> TurnOutcome:
        self.call_ended_early = True
        return TurnOutcome(EdgeCaseAction.SAFETY_FALLBACK_END_CALL, _SAFETY_END_CALL_MESSAGE, EdgeCaseType.NONE,
                            call_ended=True, notes=[reason])
