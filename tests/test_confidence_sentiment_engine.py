from parsers.answer_intent_engine import understand_answer
from parsers.confidence_sentiment_engine import (
    detect_hesitation, measure_length_and_pace, analyze_sentiment, detect_uncertainty,
    analyze_answer_communication, build_communication_profile,
)


def _answer(text, category, turn_id="t000"):
    return understand_answer(text, expected_category=category, turn_id=turn_id)


# ---------------------------------------------------------------------------
# detect_hesitation
# ---------------------------------------------------------------------------

def test_unambiguous_fillers_counted():
    result = detect_hesitation("Um, I think, uh, it was around three years.")
    assert result.filler_count >= 2


def test_filler_phrases_counted():
    result = detect_hesitation("It was, you know, kind of a tough project.")
    assert "you know" in result.filler_phrases_found
    assert "kind of" in result.filler_phrases_found


def test_ambiguous_words_flagged_but_not_counted_in_filler_count():
    result = detect_hesitation("I like React and I actually enjoy it.")
    assert result.filler_count == 0
    assert result.ambiguous_words_flagged.get("like") == 1
    assert result.ambiguous_words_flagged.get("actually") == 1


def test_no_fillers_gives_zero_rate():
    result = detect_hesitation("I completed my degree in Computer Science.")
    assert result.filler_count == 0
    assert result.hesitation_rate_per_100_words == 0.0


def test_hesitation_rate_scales_with_word_count():
    short = detect_hesitation("Um, three years.")
    long_text = detect_hesitation("Um, " + "word " * 100 + "three years.")
    assert short.hesitation_rate_per_100_words > long_text.hesitation_rate_per_100_words


# ---------------------------------------------------------------------------
# measure_length_and_pace
# ---------------------------------------------------------------------------

def test_word_count_correct():
    result = measure_length_and_pace("I have three years of experience.")
    assert result.word_count == 6


def test_pace_not_computed_without_duration():
    result = measure_length_and_pace("I have three years of experience.")
    assert result.words_per_minute is None
    assert "not computed" in result.note


def test_pace_computed_with_duration():
    result = measure_length_and_pace("word " * 30, duration_seconds=15.0)
    assert result.words_per_minute == 120.0
    assert result.note is None


def test_pace_not_computed_with_zero_duration():
    result = measure_length_and_pace("word " * 10, duration_seconds=0)
    assert result.words_per_minute is None


# ---------------------------------------------------------------------------
# analyze_sentiment
# ---------------------------------------------------------------------------

def test_positive_sentiment_detected():
    result = analyze_sentiment("I'm really excited and passionate about this role, I love the challenge.")
    assert result.label == "positive"
    assert "excited" in result.positive_hits


def test_negative_sentiment_detected():
    result = analyze_sentiment("Honestly it was a frustrating and difficult experience, I felt quite nervous.")
    assert result.label == "negative"
    assert "frustrating" in result.negative_hits


def test_neutral_sentiment_when_no_lexicon_hits():
    result = analyze_sentiment("I completed my degree in Computer Science from a college in Pune.")
    assert result.label == "neutral"
    assert result.score == 0.0


def test_sentiment_score_bounded():
    result = analyze_sentiment("love " * 50)
    assert -100.0 <= result.score <= 100.0


# ---------------------------------------------------------------------------
# detect_uncertainty
# ---------------------------------------------------------------------------

def test_uncertainty_markers_detected():
    result = detect_uncertainty("I think it was around three years, probably, but I'm not sure.")
    assert "i think" in result.markers_found
    assert "probably" in result.markers_found
    assert "not sure" in result.markers_found


def test_no_uncertainty_gives_zero_rate():
    result = detect_uncertainty("I have three years of experience with React.")
    assert result.uncertainty_rate_per_100_words == 0.0


def test_uncertainty_distinct_from_hesitation():
    # "probably" is an uncertainty marker but not a filler word --
    # the two detectors should disagree on this text, confirming
    # they measure genuinely different things.
    text = "It was probably around three years."
    hesitation = detect_hesitation(text)
    uncertainty = detect_uncertainty(text)
    assert hesitation.filler_count == 0
    assert len(uncertainty.markers_found) == 1


# ---------------------------------------------------------------------------
# analyze_answer_communication -- per-answer bundle
# ---------------------------------------------------------------------------

def test_analyze_answer_communication_bundles_all_four_signals():
    result = analyze_answer_communication("Um, I think it was around three years, probably.", turn_id="t000")
    assert result.turn_id == "t000"
    assert result.hesitation.filler_count >= 1
    assert result.uncertainty.markers_found
    assert result.length_pace.word_count > 0


def test_to_dict_round_trips_expected_keys():
    result = analyze_answer_communication("I have three years of experience.", turn_id="t000")
    d = result.to_dict()
    assert d["turn_id"] == "t000"
    assert set(d.keys()) == {"turn_id", "hesitation", "length_pace", "sentiment", "uncertainty"}


# ---------------------------------------------------------------------------
# build_communication_profile -- call-level aggregate, reuses Day 26's findings
# ---------------------------------------------------------------------------

def test_empty_call_returns_zero_with_note():
    profile = build_communication_profile([], [])
    assert profile.communication_strength_score == 0.0
    assert "note" in profile.component_breakdown


def test_clean_confident_call_scores_high():
    answers = [
        _answer("I have three years of experience with React and Node.js, and I really enjoy building things.", "experience"),
        _answer("I completed my B.Tech in Computer Science from a college in Pune.", "education"),
    ]
    profile = build_communication_profile(answers, consistency_findings=[])
    assert profile.communication_strength_score >= 70


def test_hesitant_uncertain_call_scores_lower_than_clean_call():
    clean = [_answer("I have three years of experience with React and Node.js.", "experience")]
    hesitant = [_answer("Um, I think, maybe, it was around three years, I'm not really sure, you know.", "experience")]
    clean_profile = build_communication_profile(clean, consistency_findings=[])
    hesitant_profile = build_communication_profile(hesitant, consistency_findings=[])
    assert hesitant_profile.communication_strength_score < clean_profile.communication_strength_score


def test_contradictions_reused_not_recomputed():
    answers = [_answer("I have three years of experience.", "experience")]
    findings = ["Experience-years mismatch across answers ['t000', 't004']: values [3.0, 8.0] disagree by more than 1.0 year(s)."]
    profile = build_communication_profile(answers, consistency_findings=findings)
    assert profile.contradiction_count == 1
    assert profile.contradiction_findings == findings


def test_contradiction_penalty_lowers_score():
    answers = [_answer("I have three years of experience.", "experience")]
    no_conflict = build_communication_profile(answers, consistency_findings=[])
    with_conflict = build_communication_profile(answers, consistency_findings=["some conflict"])
    assert with_conflict.communication_strength_score < no_conflict.communication_strength_score


def test_communication_strength_score_bounded():
    answers = [_answer("Um, uh, I think, maybe, I'm not sure, you know, kind of difficult, frustrating, nervous.", "experience")]
    profile = build_communication_profile(answers, consistency_findings=["a", "b", "c", "d"])
    assert 0.0 <= profile.communication_strength_score <= 100.0


def test_component_breakdown_has_expected_keys():
    answers = [_answer("I have three years of experience.", "experience")]
    profile = build_communication_profile(answers, consistency_findings=[])
    for key in ["avg_hesitation_rate_per_100_words", "hesitation_penalty", "avg_uncertainty_rate_per_100_words",
                "uncertainty_penalty", "contradiction_penalty", "avg_sentiment_score", "sentiment_adjustment"]:
        assert key in profile.component_breakdown


def test_profile_to_dict_round_trips():
    answers = [_answer("I have three years of experience.", "experience", turn_id="t000")]
    profile = build_communication_profile(answers, consistency_findings=[])
    d = profile.to_dict()
    assert "communication_strength_score" in d
    assert len(d["answer_signals"]) == 1
