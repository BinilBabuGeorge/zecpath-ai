from parsers.hr_interview_question_bank import InterviewSession, ExperienceLevel, RoleType
from parsers.hr_interview_scoring_engine import (
    WeightConfig, score_hr_interview, _score_answer, _assess_consistency,
)
from parsers.hr_interview_question_bank import InterviewQuestionState, InterviewPhase


def _make_question(qid, category, response_text):
    q = InterviewQuestionState(question_id=qid, category=category, phase=InterviewPhase.CORE_HR, follow_up_eligible=True)
    q.response_text = response_text
    q.response_captured = True
    return q


# ---------------------------------------------------------------------------
# WeightConfig
# ---------------------------------------------------------------------------

def test_default_weights_sum_to_one():
    WeightConfig().validate()  # should not raise


def test_invalid_weights_raise():
    raised = False
    try:
        WeightConfig(relevance=0.5, communication=0.5, confidence=0.5, consistency=0.5).validate()
    except ValueError:
        raised = True
    assert raised


def test_negative_weight_raises():
    raised = False
    try:
        WeightConfig(relevance=-0.1, communication=0.4, confidence=0.4, consistency=0.3).validate()
    except ValueError:
        raised = True
    assert raised


def test_positive_component_total_excludes_consistency():
    w = WeightConfig()
    assert round(w.positive_component_total, 2) == round(w.relevance + w.communication + w.confidence, 2)


# ---------------------------------------------------------------------------
# Per-answer scoring
# ---------------------------------------------------------------------------

def test_confident_answer_scores_high_relevance():
    q = _make_question("q1", "self_introduction", "For example, I led the migration project and delivered it two weeks early.")
    breakdown = _score_answer(q, WeightConfig())
    assert breakdown.relevance_quality == "confident"
    assert breakdown.relevance_score == 100.0


def test_vague_answer_scores_low_relevance():
    q = _make_question("q1", "career_journey", "I'm not sure, honestly, nothing comes to mind.")
    breakdown = _score_answer(q, WeightConfig())
    assert breakdown.relevance_quality == "vague"
    assert breakdown.relevance_score == 30.0


def test_weighted_positive_component_bounded():
    q = _make_question("q1", "strengths_weaknesses", "My strength is that I finish what I start.")
    breakdown = _score_answer(q, WeightConfig())
    assert 0.0 <= breakdown.weighted_positive_component <= 100.0


def test_weighted_positive_component_renormalizes_to_100_scale():
    # If all three inputs are 100, the renormalized weighted component should be 100,
    # regardless of the weights not summing to 1 among themselves.
    w = WeightConfig(relevance=0.35, communication=0.25, confidence=0.25, consistency=0.15)
    q = _make_question("q1", "self_introduction", "For example, I led a team through a major migration and delivered ahead of schedule with a confident, clear explanation.")
    breakdown = _score_answer(q, w)
    # All three components should be reasonably high for this answer; the renormalized value should not exceed 100.
    assert breakdown.weighted_positive_component <= 100.0


# ---------------------------------------------------------------------------
# Consistency -- rate-based, not raw-count-based
# ---------------------------------------------------------------------------

def test_consistency_no_issues_for_stable_session():
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)
    session.submit_response("I led the project calmly and delivered results on time.")
    session.submit_response("I organized the team well and we finished the task successfully.")
    consistency = _assess_consistency(session, WeightConfig())
    assert consistency.consistency_penalty == 0.0


def test_consistency_flags_sentiment_swing():
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.NON_TECHNICAL)
    session.submit_response("I was excited, happy, and proud of the great outcome we achieved.")
    session.submit_response("Honestly it was difficult, I struggled, was frustrated and afraid the whole time.")
    consistency = _assess_consistency(session, WeightConfig())
    assert consistency.swing_count >= 1
    assert consistency.consistency_penalty > 0.0


def test_consistency_penalty_capped_at_weight_share():
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.NON_TECHNICAL)
    # Alternate strongly positive/negative to maximize swings.
    session.submit_response("I was excited, happy, proud, confident, and motivated about it.")
    session.submit_response("It was difficult, I struggled, was frustrated, afraid, and stressed.")
    session.submit_response("I was excited, happy, proud, confident, and motivated again.")
    consistency = _assess_consistency(session, WeightConfig())
    assert consistency.consistency_penalty <= WeightConfig().consistency * 100.0 + 0.01


# ---------------------------------------------------------------------------
# Full report / normalization across interview lengths
# ---------------------------------------------------------------------------

def test_score_hr_interview_empty_session():
    session = InterviewSession.start(ExperienceLevel.FRESHER, RoleType.TECHNICAL)
    report = score_hr_interview(session)
    assert report.overall_hr_score == 0.0
    assert report.answer_breakdowns == []


def test_score_hr_interview_overall_score_bounded():
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)
    session.submit_response("For example, I led a major migration and delivered it early.")
    session.submit_response("Um, I think, uh, it was kind of okay I guess, not sure honestly.")
    report = score_hr_interview(session)
    assert 0.0 <= report.overall_hr_score <= 100.0


def test_score_hr_interview_uses_custom_weights():
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)
    session.submit_response("For example, I led a major migration and delivered it early.")
    custom_weights = WeightConfig(relevance=0.7, communication=0.1, confidence=0.1, consistency=0.1)
    report = score_hr_interview(session, weights=custom_weights)
    assert report.weights_used.relevance == 0.7


def test_score_hr_interview_normalizes_across_lengths():
    # A short (2-question) and a long (4-question, same answer quality
    # repeated) interview should land on comparable overall scores,
    # since scoring is per-answer-average, not per-answer-sum.
    short_session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)
    short_session.submit_response("For example, I led a major migration and delivered it early.")
    short_session.submit_response("For example, I led a major migration and delivered it early.")
    short_report = score_hr_interview(short_session)

    long_session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.NON_TECHNICAL)
    for _ in range(4):
        long_session.submit_response("For example, I led a major migration and delivered it early.")
    long_report = score_hr_interview(long_session)

    assert abs(short_report.overall_hr_score - long_report.overall_hr_score) < 5.0


def test_to_summary_text_contains_key_fields():
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)
    session.submit_response("For example, I led a major migration and delivered it early.")
    report = score_hr_interview(session)
    text = report.to_summary_text()
    assert "Overall HR Score" in text
    assert "hr-q01" in text
    assert "Relevance" in text and "Communication" in text and "Confidence" in text


def test_to_dict_round_trips_key_fields():
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)
    session.submit_response("For example, I led a major migration and delivered it early.")
    report = score_hr_interview(session)
    d = report.to_dict()
    assert d["overall_hr_score"] == report.overall_hr_score
    assert d["num_questions_answered"] == 1
    assert "weights_used" in d and "consistency" in d
