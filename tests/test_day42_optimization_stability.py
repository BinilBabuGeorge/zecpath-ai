"""
Day 42 tests -- covers the scoring-anomaly fix to
parsers.hr_followup_engine.has_concrete_example(), found during Day 40's
HR interview simulation (Finding 1: "Relevance scoring is sensitive to
marker phrasing") and fixed here. See docs/day42_optimization_stability.md
for the full before/after evidence this fix is based on.
"""

from parsers.hr_followup_engine import has_concrete_example, assess_behavioral_answer, BehavioralAnswerQuality


# ---------------------------------------------------------------------------
# The exact false negatives Day 40 found, now fixed -- verified against
# the real Hesitant-persona sentences from day40_hr_interview_test_report.json
# ---------------------------------------------------------------------------

def test_narrative_transition_without_marker_phrase_now_concrete():
    text = (
        "So, um, I started as an intern, and then, uh, I think I became a full-time "
        "developer after that, and, um, I have been growing since then I think."
    )
    assert has_concrete_example(text) is True
    assert assess_behavioral_answer(text) == BehavioralAnswerQuality.CONFIDENT


def test_specific_quantity_without_marker_phrase_now_concrete():
    text = (
        "Um, I think, uh, I have been working as a developer for about three years, "
        "I guess, and, um, I worked on a couple of projects."
    )
    assert has_concrete_example(text) is True


def test_digit_quantity_also_recognized():
    assert has_concrete_example("I managed 2 teammates on that project.") is True


def test_word_number_quantity_reuses_day16_vocabulary():
    # "three" comes from transcript_schema's _WORD_NUMBERS, not a
    # second duplicated list -- this confirms the reuse actually works,
    # not just that the digit path does.
    assert has_concrete_example("I spent five months on that initiative.") is True


def test_approximate_word_number_also_recognized():
    # "couple" comes from transcript_schema's _APPROXIMATE_WORD_NUMBERS.
    assert has_concrete_example("I worked with a couple of teammates on it.") is True


# ---------------------------------------------------------------------------
# Regression guards -- the fix must NOT change these existing behaviors
# ---------------------------------------------------------------------------

def test_vague_hedge_answers_still_vague_not_concrete():
    assert assess_behavioral_answer("Honestly, nothing comes to mind right now.") == BehavioralAnswerQuality.VAGUE
    assert assess_behavioral_answer("I'm not sure, hard to say.") == BehavioralAnswerQuality.VAGUE


def test_generic_padding_without_any_signal_still_thin():
    text = (
        "I am hardworking, a team player, and a fast learner who is dedicated and "
        "motivated to succeed in every situation I encounter."
    )
    assert has_concrete_example(text) is False
    assert assess_behavioral_answer(text) == BehavioralAnswerQuality.THIN


def test_article_a_still_excluded_from_quantity_matching():
    # Mirrors transcript_schema's own documented "a"/"an" exclusion
    # (see its _WORD_NUMBERS comment) -- "quite a while" must not
    # false-match as a quantity.
    assert has_concrete_example("It took quite a while to finish, honestly.") is False


def test_original_marker_phrases_still_work_unchanged():
    assert has_concrete_example("For example, I led a major migration.") is True
    assert has_concrete_example("I remember handling a similar situation once.") is True
