from parsers.technical_interview_question_bank import (
    TechnicalDomain, DifficultyTier, TechnicalInterviewPhase, TechnicalQuestionType,
    experience_years_to_tier, QUESTION_BANK, get_tiered_questions, TechnicalInterviewSession,
)


# ---------------------------------------------------------------------------
# Experience -> difficulty tier mapping
# ---------------------------------------------------------------------------

def test_zero_to_two_years_maps_to_basics():
    assert experience_years_to_tier(0) == DifficultyTier.BASICS
    assert experience_years_to_tier(1) == DifficultyTier.BASICS
    assert experience_years_to_tier(2) == DifficultyTier.BASICS


def test_three_to_five_years_maps_to_intermediate():
    assert experience_years_to_tier(3) == DifficultyTier.INTERMEDIATE
    assert experience_years_to_tier(4) == DifficultyTier.INTERMEDIATE
    assert experience_years_to_tier(5) == DifficultyTier.INTERMEDIATE


def test_above_five_years_maps_to_advanced():
    assert experience_years_to_tier(5.1) == DifficultyTier.ADVANCED
    assert experience_years_to_tier(6) == DifficultyTier.ADVANCED
    assert experience_years_to_tier(15) == DifficultyTier.ADVANCED


def test_fractional_years_rounds_sensibly():
    assert experience_years_to_tier(2.5) == DifficultyTier.INTERMEDIATE


def test_negative_years_raises():
    raised = False
    try:
        experience_years_to_tier(-1)
    except ValueError:
        raised = True
    assert raised


# ---------------------------------------------------------------------------
# Question bank structure
# ---------------------------------------------------------------------------

def test_every_domain_tier_combination_has_two_conceptual_and_one_scenario():
    for domain in TechnicalDomain:
        for tier in DifficultyTier:
            questions = get_tiered_questions(domain, tier)
            conceptual = [q for q in questions if q.question_type == TechnicalQuestionType.CONCEPTUAL]
            scenario = [q for q in questions if q.question_type == TechnicalQuestionType.SCENARIO_BASED]
            assert len(conceptual) == 2, f"{domain} {tier} has {len(conceptual)} conceptual questions, expected 2"
            assert len(scenario) == 1, f"{domain} {tier} has {len(scenario)} scenario questions, expected 1"


def test_question_bank_has_unique_ids():
    ids = [q.question_id for q in QUESTION_BANK]
    assert len(ids) == len(set(ids))


def test_every_tiered_question_has_skill_tags():
    for q in QUESTION_BANK:
        assert q.skill_tags, f"{q.question_id} has no skill tags"


# ---------------------------------------------------------------------------
# Session construction and tier selection
# ---------------------------------------------------------------------------

def test_session_selects_correct_tier_for_junior_candidate():
    session = TechnicalInterviewSession.start(TechnicalDomain.MERN, 1)
    assert session.tier == DifficultyTier.BASICS


def test_session_selects_correct_tier_for_senior_candidate():
    session = TechnicalInterviewSession.start(TechnicalDomain.DEVOPS, 8)
    assert session.tier == DifficultyTier.ADVANCED


def test_session_has_five_questions_total():
    session = TechnicalInterviewSession.start(TechnicalDomain.JAVA, 4)
    assert len(session.questions) == 5   # intro + experience + 2 conceptual + 1 scenario


def test_session_questions_match_selected_domain_and_tier():
    session = TechnicalInterviewSession.start(TechnicalDomain.MERN, 3)
    tiered_questions = [qs for qs in session.questions if qs.question.question_type in
                         (TechnicalQuestionType.CONCEPTUAL, TechnicalQuestionType.SCENARIO_BASED)]
    for qs in tiered_questions:
        assert qs.question.domain == TechnicalDomain.MERN
        assert qs.question.tier == DifficultyTier.INTERMEDIATE


# ---------------------------------------------------------------------------
# Flow: strictly linear, forward-only, matches the designed phase order
# ---------------------------------------------------------------------------

def test_flow_follows_exact_designed_phase_order():
    session = TechnicalInterviewSession.start(TechnicalDomain.JAVA, 7)
    while not session.is_complete:
        session.submit_response("a sample answer")
    followed = session.phase_sequence_followed()
    assert followed == [
        TechnicalInterviewPhase.INTRODUCTION, TechnicalInterviewPhase.EXPERIENCE_BASED,
        TechnicalInterviewPhase.CONCEPTUAL, TechnicalInterviewPhase.SCENARIO_BASED,
    ]


def test_session_advances_on_submit():
    session = TechnicalInterviewSession.start(TechnicalDomain.DEVOPS, 1)
    first_id = session.current_question.question.question_id
    session.submit_response("an answer")
    assert session.current_question.question.question_id != first_id


def test_session_completes_after_all_questions():
    session = TechnicalInterviewSession.start(TechnicalDomain.MERN, 10)
    for _ in range(len(session.questions)):
        session.submit_response("an answer")
    assert session.is_complete
    assert session.current_question is None


def test_submit_response_after_complete_raises():
    session = TechnicalInterviewSession.start(TechnicalDomain.JAVA, 1)
    for _ in range(len(session.questions)):
        session.submit_response("an answer")
    raised = False
    try:
        session.submit_response("one more")
    except ValueError:
        raised = True
    assert raised


def test_current_phase_reflects_current_question():
    session = TechnicalInterviewSession.start(TechnicalDomain.DEVOPS, 3)
    assert session.current_phase == TechnicalInterviewPhase.INTRODUCTION
    session.submit_response("intro answer")
    assert session.current_phase == TechnicalInterviewPhase.EXPERIENCE_BASED
