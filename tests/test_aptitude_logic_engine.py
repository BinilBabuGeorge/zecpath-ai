from parsers.aptitude_logic_engine import (
    APTITUDE_QUESTION_BANK, AptitudeQuestionType, AptitudeSession,
    assess_logical_reasoning, evaluate_aptitude_answer, build_aptitude_profile,
)


def _question(qid):
    return next(q for q in APTITUDE_QUESTION_BANK if q.question_id == qid)


# ---------------------------------------------------------------------------
# Question bank
# ---------------------------------------------------------------------------

def test_question_bank_has_both_types():
    types = {q.question_type for q in APTITUDE_QUESTION_BANK}
    assert AptitudeQuestionType.LOGICAL_REASONING in types
    assert AptitudeQuestionType.SITUATIONAL_JUDGMENT in types


def test_every_question_has_ideal_answer_elements():
    for q in APTITUDE_QUESTION_BANK:
        assert len(q.ideal_answer_elements) >= 3


def test_question_bank_has_unique_ids():
    ids = [q.question_id for q in APTITUDE_QUESTION_BANK]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# Logical reasoning scoring
# ---------------------------------------------------------------------------

def test_strong_answer_matches_most_elements():
    q = _question("apt-lr01")
    text = "Since all labels are wrong, I would pick one fruit from the box labeled Mixed. That tells me its true contents, so I can then deduce the other two boxes and relabel everything correctly."
    result = assess_logical_reasoning(text, q)
    assert result.coverage_ratio >= 0.5
    assert result.logical_reasoning_score > 50.0


def test_weak_answer_matches_few_elements():
    q = _question("apt-lr01")
    text = "I don't know, maybe just guess."
    result = assess_logical_reasoning(text, q)
    assert result.coverage_ratio < 0.5
    assert result.logical_reasoning_score < 50.0


def test_connector_usage_increases_score():
    q = _question("apt-lr03")
    with_connectors = "No, we cannot conclude that, because some blips are trons but the zorgs might be a different subset, therefore they may not overlap."
    without_connectors = "No we cannot conclude that. Some blips are trons. Zorgs might be a different subset."
    with_result = assess_logical_reasoning(with_connectors, q)
    without_result = assess_logical_reasoning(without_connectors, q)
    assert with_result.connector_hits
    assert with_result.logical_reasoning_score >= without_result.logical_reasoning_score


def test_missing_elements_reported():
    q = _question("apt-sj01")
    text = "I would talk to them privately about it."
    result = assess_logical_reasoning(text, q)
    assert "talks to the teammate directly/privately" in result.matched_elements
    assert "considers escalation only if it continues" in result.missing_elements


def test_reasoning_score_bounded():
    q = _question("apt-lr02")
    text = "because therefore since thus hence if then as a result which means so that given that in order to consequently"
    result = assess_logical_reasoning(text, q)
    assert 0.0 <= result.logical_reasoning_score <= 100.0


# ---------------------------------------------------------------------------
# Per-answer evaluation -- reasoning + clarity (Day 35 reuse)
# ---------------------------------------------------------------------------

def test_evaluate_aptitude_answer_combines_reasoning_and_clarity():
    q = _question("apt-sj02")
    text = "For example, I would explain my concern with clear reasoning about the risk. If they still insist, I would respect their decision but document it in writing."
    evaluation = evaluate_aptitude_answer(text, q)
    assert 0.0 <= evaluation.overall_aptitude_score <= 100.0
    assert evaluation.clarity.has_concrete_grounding is True  # "for example" triggers Day 35's concrete marker


def test_vague_answer_penalized_via_reused_clarity_check():
    q = _question("apt-sj03")
    text = "Honestly, nothing comes to mind, I'm not sure."
    evaluation = evaluate_aptitude_answer(text, q)
    assert evaluation.clarity.is_vague is True
    assert evaluation.overall_aptitude_score < 50.0


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

def test_session_starts_with_full_question_bank():
    session = AptitudeSession.start()
    assert len(session.questions) == len(APTITUDE_QUESTION_BANK)
    assert not session.is_complete


def test_session_advances_on_submit():
    session = AptitudeSession.start()
    first_id = session.current_question.question.question_id
    session.submit_response("some answer")
    assert session.questions[0].response_text == "some answer"
    assert session.current_question.question.question_id != first_id


def test_session_completes_after_all_questions():
    session = AptitudeSession.start()
    for _ in range(len(APTITUDE_QUESTION_BANK)):
        session.submit_response("an answer")
    assert session.is_complete
    assert session.current_question is None


def test_submit_response_after_complete_raises():
    session = AptitudeSession.start()
    for _ in range(len(APTITUDE_QUESTION_BANK)):
        session.submit_response("an answer")
    raised = False
    try:
        session.submit_response("one more")
    except ValueError:
        raised = True
    assert raised


# ---------------------------------------------------------------------------
# Session-level aggregate
# ---------------------------------------------------------------------------

def test_build_aptitude_profile_empty_session():
    session = AptitudeSession.start()
    profile = build_aptitude_profile(session)
    assert profile.overall_aptitude_score == 0.0
    assert profile.answer_evaluations == []


def test_build_aptitude_profile_separates_by_type():
    session = AptitudeSession.start()
    for _ in range(len(APTITUDE_QUESTION_BANK)):
        session.submit_response("For example, because therefore this addresses the situation clearly.")
    profile = build_aptitude_profile(session)
    assert profile.logical_reasoning_avg > 0.0
    assert profile.situational_judgment_avg > 0.0
    assert len(profile.answer_evaluations) == len(APTITUDE_QUESTION_BANK)


def test_build_aptitude_profile_skips_unanswered():
    session = AptitudeSession.start()
    session.submit_response("For example, I would talk to them privately.")
    profile = build_aptitude_profile(session)
    assert len(profile.answer_evaluations) == 1
