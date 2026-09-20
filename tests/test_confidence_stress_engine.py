from parsers.hr_interview_question_bank import (
    InterviewQuestionState, InterviewPhase, InterviewSession, ExperienceLevel, RoleType,
)
from parsers.confidence_stress_engine import (
    detect_hesitation_patterns, measure_stress_indicators, evaluate_answer_confidence,
    build_confidence_profile, _detect_mixed_sentiment, _detect_cross_answer_swings,
)
from parsers.confidence_sentiment_engine import analyze_sentiment


# ---------------------------------------------------------------------------
# Hesitation patterns -- fillers (Day 27), uncertainty (Day 27), repeated
# words (Day 35's grammar checker, reused), long pauses (honestly N/A)
# ---------------------------------------------------------------------------

def test_hesitation_patterns_detects_fillers():
    result = detect_hesitation_patterns("Um, I think it was, uh, a good experience.")
    assert result.hesitation.filler_count > 0


def test_hesitation_patterns_detects_uncertainty_markers():
    result = detect_hesitation_patterns("I think it was probably around three years, maybe.")
    assert result.uncertainty.markers_found


def test_hesitation_patterns_detects_repeated_words():
    result = detect_hesitation_patterns("I I was really surprised by the the outcome.")
    assert len(result.repeated_word_pairs) == 2


def test_hesitation_patterns_long_pauses_not_computed():
    result = detect_hesitation_patterns("This is a normal answer with no issues.")
    assert result.long_pauses_detected is None
    assert "audio" in result.long_pauses_note.lower()


def test_hesitation_patterns_clean_answer_has_no_signals():
    result = detect_hesitation_patterns("I led the migration and delivered it two weeks early.")
    assert result.hesitation.filler_count == 0
    assert not result.uncertainty.markers_found
    assert not result.repeated_word_pairs


# ---------------------------------------------------------------------------
# Mixed-sentiment / cross-answer swing detection (contradiction proxy)
# ---------------------------------------------------------------------------

def test_mixed_sentiment_flagged_when_both_polarities_strong():
    sentiment = analyze_sentiment("I loved it, I was excited and happy, but also hated it, frustrated and worried.")
    assert _detect_mixed_sentiment(sentiment) is True


def test_mixed_sentiment_not_flagged_for_single_polarity():
    sentiment = analyze_sentiment("I was excited and happy about the opportunity.")
    assert _detect_mixed_sentiment(sentiment) is False


def test_cross_answer_swing_detected_on_large_delta():
    swings = _detect_cross_answer_swings(["q1", "q2"], [80.0, -20.0])
    assert len(swings) == 1
    assert "q1 -> q2" in swings[0]


def test_cross_answer_swing_not_detected_on_small_delta():
    swings = _detect_cross_answer_swings(["q1", "q2"], [10.0, 5.0])
    assert swings == []


# ---------------------------------------------------------------------------
# Stress indicators -- linguistic proxy, not physiological
# ---------------------------------------------------------------------------

def test_stress_score_higher_for_hesitant_negative_answer():
    calm = detect_hesitation_patterns("I handled the project well and delivered on time.")
    calm_sentiment = analyze_sentiment("I handled the project well and delivered on time.")
    stressed_text = "Um, uh, I I was really worried, frustrated, and nervous about it, honestly."
    stressed = detect_hesitation_patterns(stressed_text)
    stressed_sentiment = analyze_sentiment(stressed_text)

    calm_result = measure_stress_indicators(calm, calm_sentiment)
    stressed_result = measure_stress_indicators(stressed, stressed_sentiment)
    assert stressed_result.stress_score > calm_result.stress_score


def test_stress_score_bounded_0_to_100():
    text = "Um uh um I I I was was worried nervous frustrated afraid stressed concerned bad poor."
    hesitation = detect_hesitation_patterns(text)
    sentiment = analyze_sentiment(text)
    result = measure_stress_indicators(hesitation, sentiment)
    assert 0.0 <= result.stress_score <= 100.0


# ---------------------------------------------------------------------------
# Per-answer confidence evaluation
# ---------------------------------------------------------------------------

def test_confident_clean_answer_scores_high():
    result = evaluate_answer_confidence("I led the migration project and delivered it two weeks ahead of schedule.")
    assert result.behavioral_confidence_score > 80.0


def test_hesitant_answer_scores_lower_than_confident_one():
    confident = evaluate_answer_confidence("I led the project and delivered it on time.")
    hesitant = evaluate_answer_confidence("Um, I think, uh, maybe I sort of helped with the project, I guess.")
    assert hesitant.behavioral_confidence_score < confident.behavioral_confidence_score


def test_mixed_sentiment_answer_flagged_and_penalized():
    result = evaluate_answer_confidence("I loved it, was excited and happy, but also hated it, frustrated and worried.")
    assert result.mixed_sentiment_flag is True
    assert result.component_breakdown["mixed_sentiment_penalty"] < 0


# ---------------------------------------------------------------------------
# Interview-level aggregate
# ---------------------------------------------------------------------------

def test_build_confidence_profile_empty_session():
    session = InterviewSession.start(ExperienceLevel.FRESHER, RoleType.TECHNICAL)
    profile = build_confidence_profile(session)
    assert profile.overall_behavioral_confidence_score == 0.0
    assert profile.answer_evaluations == []


def test_build_confidence_profile_skips_unanswered_questions():
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)
    session.submit_response("I led a migration project that reduced downtime significantly.")
    profile = build_confidence_profile(session)
    assert len(profile.answer_evaluations) == 1


def test_build_confidence_profile_detects_cross_answer_swing():
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.NON_TECHNICAL)
    session.submit_response("I was excited, happy, and proud of the great outcome we achieved.")
    session.submit_response("Honestly it was difficult, I struggled, was frustrated and afraid the whole time.")
    profile = build_confidence_profile(session)
    assert len(profile.inconsistency_flags.cross_answer_swings) >= 1


def test_build_confidence_profile_overall_score_bounded():
    session = InterviewSession.start(ExperienceLevel.FRESHER, RoleType.NON_TECHNICAL)
    session.submit_response("Um, I think, uh, it was okay I guess, nothing special.")
    session.submit_response("I organized the event and it went smoothly.")
    profile = build_confidence_profile(session)
    assert 0.0 <= profile.overall_behavioral_confidence_score <= 100.0
    assert 0.0 <= profile.overall_stress_score <= 100.0
