from parsers.answer_intent_engine import understand_answer
from parsers.screening_scoring_engine import (
    score_answer, score_screening_call, ScoreComponent, QuestionScore, ScreeningScoreResult,
)


def _answer(text, category, turn_id="t000", is_silent=False):
    return understand_answer(text, expected_category=category, turn_id=turn_id, is_silent=is_silent)


# ---------------------------------------------------------------------------
# score_answer -- single-answer scoring
# ---------------------------------------------------------------------------

def test_missing_answer_scores_zero_on_clarity_relevance_completeness():
    a = _answer("", "salary", is_silent=True)
    qs = score_answer(a)
    assert qs.components["clarity"].score == 0.0
    assert qs.components["relevance"].score == 0.0
    assert qs.components["completeness"].score == 0.0


def test_vague_answer_scores_low_but_not_all_zero():
    a = _answer("I'm not sure, maybe.", "salary")
    qs = score_answer(a)
    assert qs.components["clarity"].score < 50
    assert qs.components["completeness"].score < 50


def test_off_topic_answer_scores_zero_relevance_and_completeness():
    a = _answer("My current CTC is twelve lakhs.", "location")
    qs = score_answer(a)
    assert qs.components["relevance"].score == 0.0
    assert qs.components["completeness"].score == 0.0
    # Clarity should still be reasonably high -- they spoke clearly, just off-topic.
    assert qs.components["clarity"].score >= 40


def test_ok_structured_answer_with_extraction_scores_full_completeness():
    a = _answer("I have three years of experience.", "experience")
    qs = score_answer(a)
    assert qs.components["completeness"].score == 100.0


def test_ok_structured_answer_without_extraction_scores_partial_completeness():
    a = _answer("I'm expecting a good package, it's negotiable.", "salary")
    qs = score_answer(a)
    assert qs.components["completeness"].score == 40.0
    assert "could not extract" in qs.components["completeness"].note


def test_ok_open_ended_answer_scores_full_completeness():
    a = _answer("I completed my B.Tech in Computer Science from a college in Pune.", "education")
    qs = score_answer(a)
    assert qs.components["completeness"].score == 100.0


def test_relevance_reflects_partial_topic_match():
    # t000-style answer: mostly skills content, but does contain "i'm a"
    # (introduction phrasing) -- relevance should be a partial score,
    # not a flat 0 or 100.
    a = _answer("Hi, I'm a full stack developer with about three years of experience, mostly working on React and Node.js.", "introduction")
    qs = score_answer(a)
    assert 0 < qs.components["relevance"].score < 100


def test_structured_category_weighs_completeness_more_than_open_ended():
    structured = _answer("I have three years of experience.", "experience")
    open_ended = _answer("I completed my B.Tech in Computer Science from a college in Pune.", "education")
    qs_structured = score_answer(structured)
    qs_open = score_answer(open_ended)
    # Same underlying quality (OK, full marks on every component) --
    # weighted_total should be equal here since both max out, but the
    # profiles used must differ (checked directly).
    from parsers.screening_scoring_engine import _weight_profile_for
    assert _weight_profile_for("experience")["completeness"] > _weight_profile_for("education")["completeness"]
    assert _weight_profile_for("education")["clarity"] > _weight_profile_for("experience")["clarity"]


def test_consistency_defaults_to_neutral_before_cross_check():
    a = _answer("I have three years of experience.", "experience")
    qs = score_answer(a)
    assert qs.components["consistency"].score == 100.0
    assert "Not yet cross-checked" in qs.components["consistency"].note


def test_weighted_total_is_between_zero_and_hundred():
    a = _answer("I have three years of experience.", "experience")
    qs = score_answer(a)
    assert 0.0 <= qs.weighted_total <= 100.0


def test_to_dict_round_trips_expected_keys():
    a = _answer("I have three years of experience.", "experience", turn_id="call_x-t000")
    qs = score_answer(a)
    d = qs.to_dict()
    assert d["turn_id"] == "call_x-t000"
    assert set(d["components"].keys()) == {"clarity", "relevance", "completeness", "consistency"}
    assert "weighted_total" in d


# ---------------------------------------------------------------------------
# score_screening_call -- aggregate + consistency cross-check
# ---------------------------------------------------------------------------

def test_empty_call_returns_zero_with_note():
    result = score_screening_call([])
    assert result.total_score == 0.0
    assert result.consistency_findings == ["No answers to score."]


def test_consistent_experience_across_answers_scores_full_consistency():
    answers = [
        _answer("Hi, I'm a developer with three years of experience.", "introduction", turn_id="t000"),
        _answer("I've been working professionally for around three years now.", "experience", turn_id="t001"),
    ]
    result = score_screening_call(answers)
    for qs in result.question_scores:
        assert qs.components["consistency"].score == 100.0
    assert not result.consistency_findings


def test_conflicting_experience_across_answers_flagged_and_penalized():
    answers = [
        _answer("Hi, I'm a developer with three years of experience.", "introduction", turn_id="t000"),
        _answer("I have eight years of experience in this field.", "experience", turn_id="t001"),
    ]
    result = score_screening_call(answers)
    assert len(result.consistency_findings) == 1
    assert "mismatch" in result.consistency_findings[0].lower()
    for qs in result.question_scores:
        assert qs.components["consistency"].score == 40.0


def test_salary_different_units_not_penalized_but_noted():
    answers = [
        _answer("My current CTC is around eight lakhs.", "salary", turn_id="t000"),
        _answer("My expected salary is around 45k a month.", "salary", turn_id="t001"),
    ]
    result = score_screening_call(answers)
    assert any("different units" in f for f in result.consistency_findings)
    # Not penalized -- consistency should remain untouched (neutral default) for both.
    for qs in result.question_scores:
        assert qs.components["consistency"].score == 100.0


def test_salary_same_unit_wide_spread_flagged():
    answers = [
        _answer("My current CTC is around three lakhs.", "salary", turn_id="t000"),
        _answer("I'm expecting around ten lakhs per annum.", "salary", turn_id="t001"),
    ]
    result = score_screening_call(answers)
    assert any("vary widely" in f for f in result.consistency_findings)


def test_availability_conflict_immediate_vs_notice_period():
    answers = [
        _answer("I can join immediately, I'm not serving any notice.", "availability", turn_id="t000"),
        _answer("My notice period is two weeks.", "availability", turn_id="t001"),
    ]
    result = score_screening_call(answers)
    assert any("Availability conflict" in f for f in result.consistency_findings)
    for qs in result.question_scores:
        assert qs.components["consistency"].score == 40.0


def test_total_score_is_average_of_question_weighted_totals():
    answers = [
        _answer("I have three years of experience.", "experience", turn_id="t000"),
        _answer("", "salary", turn_id="t001", is_silent=True),
    ]
    result = score_screening_call(answers)
    manual_avg = round(sum(qs.weighted_total for qs in result.question_scores) / 2, 1)
    assert result.total_score == manual_avg


def test_screening_score_result_to_dict_round_trips():
    answers = [_answer("I have three years of experience.", "experience", turn_id="t000")]
    result = score_screening_call(answers)
    d = result.to_dict()
    assert "total_score" in d
    assert "consistency_findings" in d
    assert len(d["question_scores"]) == 1
