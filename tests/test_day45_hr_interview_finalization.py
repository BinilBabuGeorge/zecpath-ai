from parsers.hr_interview_question_bank import InterviewSession, ExperienceLevel, RoleType
from parsers.hr_interview_finalization import submit_scrubbed_response


# ---------------------------------------------------------------------------
# Scrubbing happens BEFORE storage
# ---------------------------------------------------------------------------

def test_demographic_disclosure_is_redacted_before_storage():
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)
    result = submit_scrubbed_response(session, "I'm a single mother, I led the migration project.")
    assert "[REDACTED]" in result.question.response_text
    assert "mother" not in result.question.response_text.lower()


def test_categories_detected_are_reported():
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)
    result = submit_scrubbed_response(session, "As a 45-year-old, I bring real experience.")
    assert "Age" in result.categories_detected


def test_clean_text_has_no_categories_and_is_unchanged():
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)
    text = "I led the migration project and delivered it two weeks early."
    result = submit_scrubbed_response(session, text)
    assert result.categories_detected == []
    assert result.question.response_text == text


def test_non_demographic_content_around_disclosure_is_preserved():
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)
    result = submit_scrubbed_response(session, "Being Muslim, I'd need Friday prayer time, but otherwise flexible.")
    assert "Friday prayer time" in result.question.response_text
    assert "otherwise flexible" in result.question.response_text


# ---------------------------------------------------------------------------
# Follow-up decision runs on the SCRUBBED text, not the raw text
# ---------------------------------------------------------------------------

def test_follow_up_decision_included_by_default():
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)
    result = submit_scrubbed_response(session, "Um, I think, uh, I did some stuff at my last job.")
    assert result.follow_up is not None
    assert result.follow_up.should_follow_up is True


def test_follow_up_decision_can_be_skipped():
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)
    result = submit_scrubbed_response(session, "I led the migration project.", decide_follow_ups=False)
    assert result.follow_up is None


def test_concrete_content_survives_scrubbing_for_follow_up_classification():
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)
    result = submit_scrubbed_response(session, "I'm a single mother, and for example I led the migration project and delivered it two weeks early.")
    # The demographic clause is redacted but the concrete-example clause survives,
    # so the follow-up classifier should still see a confident answer.
    assert result.follow_up.answer_quality.value == "confident"


def test_follow_up_not_decided_for_non_eligible_question():
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)
    # Advance to whichever question is NOT follow_up_eligible, if any exists in this bank;
    # otherwise this test still documents the intended behavior for such a question.
    ineligible = next((q for q in session.questions if not q.follow_up_eligible), None)
    if ineligible is None:
        return  # every question in this bank is follow-up eligible -- nothing to test here
    while session.current_question.question_id != ineligible.question_id:
        session.submit_response("skipping ahead")
    result = submit_scrubbed_response(session, "some answer")
    assert result.follow_up is None


# ---------------------------------------------------------------------------
# Session completion and existing behavior are unaffected
# ---------------------------------------------------------------------------

def test_session_advances_normally():
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)
    first_id = session.current_question.question_id
    submit_scrubbed_response(session, "an answer")
    assert session.current_question is None or session.current_question.question_id != first_id


def test_raises_on_already_complete_session():
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)
    while not session.is_complete:
        submit_scrubbed_response(session, "an answer")
    raised = False
    try:
        submit_scrubbed_response(session, "one more")
    except ValueError:
        raised = True
    assert raised


def test_direct_submit_response_still_works_unaffected():
    # InterviewSession itself was NOT modified -- confirms the existing,
    # unwrapped API every prior day's test suite depends on is untouched.
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)
    session.submit_response("I'm a single mother, unredacted on purpose here.")
    assert "single mother" in session.questions[0].response_text
