from parsers.speech_to_text import RawSTTResult
from parsers.edge_case_handler import (
    RobustConversationController, EdgeCaseAction, EdgeCaseType,
    classify_audio_quality, detect_language_mismatch,
)


def _controller(categories=None):
    return RobustConversationController(categories=categories or ["introduction", "experience"])


# ---------------------------------------------------------------------------
# classify_audio_quality / detect_language_mismatch
# ---------------------------------------------------------------------------

def test_classify_audio_quality_good():
    assert classify_audio_quality(0.9) == "good"


def test_classify_audio_quality_poor():
    assert classify_audio_quality(0.3) == "poor"


def test_classify_audio_quality_unusable():
    assert classify_audio_quality(0.05) == "unusable"


def test_detect_language_mismatch_true():
    assert detect_language_mismatch("hi", "en")


def test_detect_language_mismatch_false():
    assert not detect_language_mismatch("en", "en")


def test_detect_language_mismatch_case_insensitive():
    assert not detect_language_mismatch("EN", "en")


# ---------------------------------------------------------------------------
# Normal passthrough -- no edge case
# ---------------------------------------------------------------------------

def test_clean_high_confidence_turn_passes_through():
    c = _controller()
    outcome = c.process_turn(RawSTTResult(text="Hi, I'm a developer with three years of experience in React.", confidence=0.9))
    assert outcome.action == EdgeCaseAction.PASSTHROUGH
    assert outcome.underlying_action is not None
    assert c.current_category == "experience"


def test_silence_passes_through_to_day29_unchanged():
    c = _controller()
    outcome = c.process_turn(RawSTTResult(text="", confidence=0.0, is_silent=True))
    assert outcome.action == EdgeCaseAction.PASSTHROUGH
    assert outcome.underlying_action.action_type.value == "retry_silence"


# ---------------------------------------------------------------------------
# Poor / unusable audio handling
# ---------------------------------------------------------------------------

def test_poor_audio_first_attempt_retries():
    c = _controller(categories=["experience"])
    outcome = c.process_turn(RawSTTResult(text="garbled", confidence=0.3))
    assert outcome.action == EdgeCaseAction.RETRY_AUDIO
    assert outcome.edge_case_type == EdgeCaseType.POOR_AUDIO
    assert c.current_category == "experience"


def test_poor_audio_second_attempt_safety_skips():
    c = _controller(categories=["experience", "skills"])
    c.process_turn(RawSTTResult(text="garbled", confidence=0.3))
    outcome = c.process_turn(RawSTTResult(text="garbled", confidence=0.3))
    assert outcome.action == EdgeCaseAction.SAFETY_FALLBACK_SKIP
    assert c.current_category == "skills"


def test_unusable_audio_uses_stronger_message():
    c = _controller(categories=["experience"])
    outcome = c.process_turn(RawSTTResult(text="a", confidence=0.05))
    assert "trouble hearing you at all" in outcome.message


def test_audio_attempts_are_tracked_per_category():
    c = _controller(categories=["experience", "skills"])
    c.process_turn(RawSTTResult(text="garbled", confidence=0.3))   # experience attempt 1
    c.process_turn(RawSTTResult(text="garbled", confidence=0.3))   # experience attempt 2 -> skip to skills
    assert c._edge_state["experience"].audio_attempts == 2
    assert c._edge_state["skills"].audio_attempts == 0


# ---------------------------------------------------------------------------
# Language mismatch handling
# ---------------------------------------------------------------------------

def test_language_mismatch_first_attempt_clarifies():
    c = _controller(categories=["introduction"])
    outcome = c.process_turn(RawSTTResult(text="Namaste, main developer hoon", confidence=0.9, language="hi"))
    assert outcome.action == EdgeCaseAction.CLARIFY_LANGUAGE
    assert outcome.edge_case_type == EdgeCaseType.LANGUAGE_MISMATCH


def test_language_mismatch_second_attempt_safety_skips():
    c = _controller(categories=["introduction"])
    c.process_turn(RawSTTResult(text="Namaste", confidence=0.9, language="hi"))
    outcome = c.process_turn(RawSTTResult(text="Namaste", confidence=0.9, language="hi"))
    assert outcome.action == EdgeCaseAction.SAFETY_FALLBACK_SKIP
    assert c.is_call_complete  # only category, now skipped


def test_switching_to_english_after_clarification_resumes_normally():
    c = _controller(categories=["introduction"])
    c.process_turn(RawSTTResult(text="Namaste", confidence=0.9, language="hi"))
    outcome = c.process_turn(RawSTTResult(text="Hi, I'm a developer with three years of experience.", confidence=0.9, language="en"))
    assert outcome.action == EdgeCaseAction.PASSTHROUGH


def test_poor_audio_checked_before_language_mismatch():
    # Both conditions present -- audio quality should be flagged first,
    # since a low-confidence language tag isn't trustworthy either.
    c = _controller(categories=["introduction"])
    outcome = c.process_turn(RawSTTResult(text="a", confidence=0.2, language="hi"))
    assert outcome.edge_case_type == EdgeCaseType.POOR_AUDIO


# ---------------------------------------------------------------------------
# Consecutive-failure call-ending safety fallback
# ---------------------------------------------------------------------------

def test_consecutive_edge_cases_across_categories_end_call():
    c = _controller(categories=["introduction", "education", "experience", "skills"])
    c.process_turn(RawSTTResult(text="garbled", confidence=0.3))
    c.process_turn(RawSTTResult(text="garbled", confidence=0.3))
    outcome = c.process_turn(RawSTTResult(text="garbled", confidence=0.3))
    assert outcome.action == EdgeCaseAction.SAFETY_FALLBACK_END_CALL
    assert outcome.call_ended
    assert c.is_call_complete


def test_clean_turn_resets_consecutive_edge_case_streak():
    c = _controller(categories=["introduction", "education", "experience", "skills"])
    c.process_turn(RawSTTResult(text="garbled", confidence=0.3))
    c.process_turn(RawSTTResult(text="Hi, I'm a developer with three years of experience.", confidence=0.9))  # clean -- resets streak
    c.process_turn(RawSTTResult(text="garbled", confidence=0.3))
    outcome = c.process_turn(RawSTTResult(text="garbled", confidence=0.3))
    # only 2 consecutive edge cases since the streak reset -- should
    # safety-skip the category, not end the whole call
    assert outcome.action == EdgeCaseAction.SAFETY_FALLBACK_SKIP


# ---------------------------------------------------------------------------
# Crash safety net
# ---------------------------------------------------------------------------

def test_crash_guard_catches_unexpected_exception():
    c = _controller(categories=["introduction", "experience"])
    outcome = c.process_turn(RawSTTResult(text=None, confidence=0.95))
    assert outcome.action == EdgeCaseAction.CRASH_GUARD_SKIP
    assert "AttributeError" in outcome.notes[0]


def test_crash_guard_advances_the_call_not_stuck():
    c = _controller(categories=["introduction", "experience"])
    c.process_turn(RawSTTResult(text=None, confidence=0.95))
    assert c.current_category == "experience"


def test_crash_guard_message_gives_no_internal_detail_to_candidate():
    c = _controller(categories=["introduction"])
    outcome = c.process_turn(RawSTTResult(text=None, confidence=0.95))
    assert "error" not in outcome.message.lower()
    assert "exception" not in outcome.message.lower()


def test_call_already_complete_short_circuits_before_touching_raw_fields():
    # Once complete, the controller returns Day 29's own END_CALL path
    # without ever reading raw.text/confidence/language -- so even a
    # malformed RawSTTResult can't cause a crash here. This is a
    # stronger safety property than routing it through the crash
    # guard: the risky fields are never touched at all.
    c = _controller(categories=["introduction"])
    c.process_turn(RawSTTResult(text="Hi, I'm a developer with three years of experience.", confidence=0.9))
    assert c.is_call_complete
    outcome = c.process_turn(RawSTTResult(text=None, confidence=0.95))
    assert outcome.action == EdgeCaseAction.PASSTHROUGH
    assert outcome.call_ended
    assert outcome.underlying_action.action_type.value == "end_call"


# ---------------------------------------------------------------------------
# Outcome log / to_dict
# ---------------------------------------------------------------------------

def test_outcome_log_records_every_turn():
    c = _controller(categories=["introduction"])
    c.process_turn(RawSTTResult(text="garbled", confidence=0.3))
    c.process_turn(RawSTTResult(text="Hi, I'm a developer with three years of experience.", confidence=0.9))
    assert len(c.outcome_log) == 2


def test_to_dict_round_trips_expected_keys():
    c = _controller(categories=["introduction"])
    outcome = c.process_turn(RawSTTResult(text="Hi, I'm a developer with three years of experience.", confidence=0.9))
    d = outcome.to_dict()
    for key in ["action", "message", "edge_case_type", "call_ended", "underlying_action", "notes"]:
        assert key in d
