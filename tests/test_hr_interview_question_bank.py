from parsers.hr_interview_question_bank import (
    ExperienceLevel, RoleType, InterviewPhase, CATEGORIES, CATEGORY_METADATA,
    generate_hr_interview_questions, InterviewSession, InterviewQuestionState,
)


# ---------------------------------------------------------------------------
# Category taxonomy
# ---------------------------------------------------------------------------

def test_six_categories_defined():
    assert len(CATEGORIES) == 6
    assert set(CATEGORIES) == {
        "self_introduction", "career_journey", "strengths_weaknesses",
        "teamwork_culture_fit", "career_goals", "availability_commitment",
    }


def test_every_category_maps_to_a_phase():
    for category in CATEGORIES:
        assert isinstance(CATEGORY_METADATA[category]["phase"], InterviewPhase)


def test_all_four_phases_have_at_least_one_category():
    phases_used = {meta["phase"] for meta in CATEGORY_METADATA.values()}
    assert phases_used == set(InterviewPhase)


# ---------------------------------------------------------------------------
# Role-based question generator -- the flagship differentiation
# ---------------------------------------------------------------------------

def test_generates_one_question_per_category():
    qs = generate_hr_interview_questions(ExperienceLevel.FRESHER, RoleType.TECHNICAL)
    assert len(qs) == len(CATEGORIES)
    assert [q.category for q in qs] == CATEGORIES


def test_career_journey_differs_across_all_four_combinations():
    texts = set()
    for exp in (ExperienceLevel.FRESHER, ExperienceLevel.EXPERIENCED):
        for role in (RoleType.TECHNICAL, RoleType.NON_TECHNICAL):
            qs = generate_hr_interview_questions(exp, role)
            career_q = next(q for q in qs if q.category == "career_journey")
            texts.add(career_q.text)
    assert len(texts) == 4  # all four combinations produce genuinely distinct text


def test_teamwork_varies_by_experience_only_not_role_type():
    fresher_tech = generate_hr_interview_questions(ExperienceLevel.FRESHER, RoleType.TECHNICAL)
    fresher_nontech = generate_hr_interview_questions(ExperienceLevel.FRESHER, RoleType.NON_TECHNICAL)
    exp_tech = generate_hr_interview_questions(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)

    def teamwork(qs):
        return next(q for q in qs if q.category == "teamwork_culture_fit").text

    assert teamwork(fresher_tech) == teamwork(fresher_nontech)   # same experience level -> same text
    assert teamwork(fresher_tech) != teamwork(exp_tech)          # different experience level -> different text


def test_career_goals_varies_by_role_type_only_not_experience():
    fresher_tech = generate_hr_interview_questions(ExperienceLevel.FRESHER, RoleType.TECHNICAL)
    exp_tech = generate_hr_interview_questions(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)
    fresher_nontech = generate_hr_interview_questions(ExperienceLevel.FRESHER, RoleType.NON_TECHNICAL)

    def goals(qs):
        return next(q for q in qs if q.category == "career_goals").text

    assert goals(fresher_tech) == goals(exp_tech)          # same role type -> same text
    assert goals(fresher_tech) != goals(fresher_nontech)   # different role type -> different text


def test_universal_categories_identical_across_all_combinations():
    all_combos = [
        generate_hr_interview_questions(exp, role)
        for exp in (ExperienceLevel.FRESHER, ExperienceLevel.EXPERIENCED)
        for role in (RoleType.TECHNICAL, RoleType.NON_TECHNICAL)
    ]
    for category in ("self_introduction", "strengths_weaknesses", "availability_commitment"):
        texts = {next(q.text for q in qs if q.category == category) for qs in all_combos}
        assert len(texts) == 1


def test_questions_carry_correct_phase():
    qs = generate_hr_interview_questions(ExperienceLevel.FRESHER, RoleType.TECHNICAL)
    by_category = {q.category: q.phase for q in qs}
    assert by_category["self_introduction"] == InterviewPhase.INTRODUCTION
    assert by_category["career_journey"] == InterviewPhase.CORE_HR
    assert by_category["career_goals"] == InterviewPhase.ROLE_BASED_EVALUATION
    assert by_category["availability_commitment"] == InterviewPhase.CLOSING


def test_follow_up_eligibility_matches_category_defaults():
    qs = generate_hr_interview_questions(ExperienceLevel.FRESHER, RoleType.TECHNICAL)
    by_category = {q.category: q.follow_up_eligible for q in qs}
    assert by_category["self_introduction"] is True
    assert by_category["career_goals"] is False
    assert by_category["availability_commitment"] is False


def test_untranslated_language_falls_back_to_english_with_marker():
    qs = generate_hr_interview_questions(ExperienceLevel.FRESHER, RoleType.TECHNICAL, lang="hi")
    assert all("[NO HI TRANSLATION YET" in q.text for q in qs)


# ---------------------------------------------------------------------------
# InterviewQuestionState
# ---------------------------------------------------------------------------

def test_capture_response_sets_text_and_flag():
    state = InterviewQuestionState(question_id="q1", category="self_introduction", phase=InterviewPhase.INTRODUCTION, follow_up_eligible=True)
    assert not state.response_captured
    state.capture_response("Hello, I'm a developer.")
    assert state.response_captured
    assert state.response_text == "Hello, I'm a developer."


def test_record_follow_up_succeeds_when_eligible():
    state = InterviewQuestionState(question_id="q1", category="career_journey", phase=InterviewPhase.CORE_HR, follow_up_eligible=True)
    state.record_follow_up("Can you elaborate on that?")
    assert state.follow_up_asked
    assert state.follow_up_text == "Can you elaborate on that?"


def test_record_follow_up_raises_when_not_eligible():
    state = InterviewQuestionState(question_id="q1", category="career_goals", phase=InterviewPhase.ROLE_BASED_EVALUATION, follow_up_eligible=False)
    try:
        state.record_follow_up("This should fail.")
        assert False, "expected ValueError"
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# InterviewSession
# ---------------------------------------------------------------------------

def test_session_starts_with_correct_question_count():
    session = InterviewSession.start(ExperienceLevel.FRESHER, RoleType.TECHNICAL)
    assert len(session.questions) == len(CATEGORIES)
    assert not session.is_complete


def test_session_advances_through_all_questions():
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.NON_TECHNICAL)
    count = 0
    while not session.is_complete:
        session.submit_response("a sample answer")
        count += 1
    assert count == len(CATEGORIES)
    assert session.is_complete
    assert session.current_question is None
    assert session.current_phase is None


def test_session_captures_responses_on_the_right_question():
    session = InterviewSession.start(ExperienceLevel.FRESHER, RoleType.TECHNICAL)
    first_question_id = session.current_question.question_id
    session.submit_response("my answer")
    answered = session.questions[0]
    assert answered.question_id == first_question_id
    assert answered.response_text == "my answer"
    assert answered.response_captured


def test_submit_response_after_completion_raises():
    session = InterviewSession.start(ExperienceLevel.FRESHER, RoleType.TECHNICAL)
    for _ in range(len(CATEGORIES)):
        session.submit_response("answer")
    try:
        session.submit_response("one too many")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_questions_by_phase_returns_correct_subset():
    session = InterviewSession.start(ExperienceLevel.FRESHER, RoleType.TECHNICAL)
    core_hr = session.questions_by_phase(InterviewPhase.CORE_HR)
    assert {q.category for q in core_hr} == {"career_journey", "strengths_weaknesses", "teamwork_culture_fit"}


def test_current_phase_tracks_current_question():
    session = InterviewSession.start(ExperienceLevel.FRESHER, RoleType.TECHNICAL)
    assert session.current_phase == InterviewPhase.INTRODUCTION
    session.submit_response("answer")
    assert session.current_phase == InterviewPhase.CORE_HR
