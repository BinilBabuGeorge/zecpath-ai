from parsers.hr_interview_question_bank import InterviewQuestionState, InterviewPhase, InterviewSession, ExperienceLevel, RoleType
from parsers.hr_followup_engine import (
    assess_behavioral_answer, has_concrete_example, is_vague_behavioral_answer,
    decide_follow_up, process_response_with_follow_up,
    BehavioralAnswerQuality, FollowUpType,
)


def _question(category="career_journey", follow_up_eligible=True):
    return InterviewQuestionState(question_id="q1", category=category, phase=InterviewPhase.CORE_HR, follow_up_eligible=follow_up_eligible)


# ---------------------------------------------------------------------------
# Behavioral answer quality assessment
# ---------------------------------------------------------------------------

def test_missing_when_silent():
    assert assess_behavioral_answer("", is_silent=True) == BehavioralAnswerQuality.MISSING


def test_missing_when_empty_text():
    assert assess_behavioral_answer("   ") == BehavioralAnswerQuality.MISSING


def test_vague_hedge_detected():
    assert assess_behavioral_answer("Honestly, nothing comes to mind right now.") == BehavioralAnswerQuality.VAGUE


def test_thin_short_generic_answer():
    assert assess_behavioral_answer("I am hardworking and a fast learner.") == BehavioralAnswerQuality.THIN


def test_thin_long_but_generic_answer():
    text = "I am hardworking, dedicated, a fast learner, a great communicator, and I always give my best effort in everything I do at work every single day."
    assert assess_behavioral_answer(text) == BehavioralAnswerQuality.THIN


def test_confident_with_concrete_example():
    text = "For example, in my last job I once led a project where we shipped a feature two weeks early after reorganizing the schedule."
    assert assess_behavioral_answer(text) == BehavioralAnswerQuality.CONFIDENT


def test_has_concrete_example_detects_marker():
    assert has_concrete_example("For instance, I handled a tough client call last quarter.")


def test_has_concrete_example_false_without_marker():
    assert not has_concrete_example("I am generally a good communicator.")


def test_is_vague_behavioral_answer_true_for_hedge():
    assert is_vague_behavioral_answer("I don't know, hard to say.")


def test_is_vague_behavioral_answer_false_for_real_answer():
    assert not is_vague_behavioral_answer("I led the backend team on our last release.")


# ---------------------------------------------------------------------------
# decide_follow_up -- the decision tree
# ---------------------------------------------------------------------------

def test_vague_answer_triggers_clarification():
    q = _question()
    decision = decide_follow_up(q, "I really can't think of anything, nothing comes to mind.")
    assert decision.should_follow_up
    assert decision.follow_up_type == FollowUpType.CLARIFICATION


def test_thin_answer_triggers_deepening():
    q = _question()
    decision = decide_follow_up(q, "I worked on a few things and did okay.")
    assert decision.should_follow_up
    assert decision.follow_up_type == FollowUpType.DEEPENING


def test_confident_answer_triggers_example_based():
    q = _question()
    text = "For example, I once redesigned our deployment pipeline in my last job, cutting release time in half."
    decision = decide_follow_up(q, text)
    assert decision.should_follow_up
    assert decision.follow_up_type == FollowUpType.EXAMPLE_BASED


def test_silence_does_not_trigger_follow_up():
    q = _question()
    decision = decide_follow_up(q, "", is_silent=True)
    assert not decision.should_follow_up
    assert decision.answer_quality == BehavioralAnswerQuality.MISSING


def test_ineligible_question_never_gets_a_follow_up():
    q = _question(category="career_goals", follow_up_eligible=False)
    decision = decide_follow_up(q, "nothing comes to mind")
    assert not decision.should_follow_up
    assert "not eligible" in decision.reason


def test_already_asked_follow_up_is_capped():
    q = _question()
    q.follow_up_asked = True
    decision = decide_follow_up(q, "I really can't think of anything.")
    assert not decision.should_follow_up
    assert "capped" in decision.reason


def test_repeated_answer_does_not_trigger_second_follow_up():
    q = _question()
    original = "I am hardworking and a fast learner."
    decision = decide_follow_up(q, "I am hardworking and a fast learner, really.", previous_responses_on_this_question=[original])
    assert not decision.should_follow_up
    assert "repeats an earlier" in decision.reason


def test_follow_up_text_is_category_specific():
    q1 = _question(category="teamwork_culture_fit")
    q2 = _question(category="availability_commitment")
    d1 = decide_follow_up(q1, "nothing comes to mind")
    d2 = decide_follow_up(q2, "nothing comes to mind")
    assert d1.follow_up_text != d2.follow_up_text


# ---------------------------------------------------------------------------
# process_response_with_follow_up -- live session integration
# ---------------------------------------------------------------------------

def test_process_response_records_follow_up_on_state():
    session = InterviewSession.start(ExperienceLevel.FRESHER, RoleType.TECHNICAL)
    q = session.current_question
    decision = process_response_with_follow_up(session, "I am hardworking and a fast learner.")
    assert decision.should_follow_up
    assert q.follow_up_asked
    assert q.follow_up_type == "deepening"
    assert q.follow_up_text == decision.follow_up_text


def test_process_response_does_not_advance_the_session():
    session = InterviewSession.start(ExperienceLevel.FRESHER, RoleType.TECHNICAL)
    process_response_with_follow_up(session, "I am hardworking and a fast learner.")
    assert session.current_question.question_id == "hr-q01"  # still on the same question


def test_process_response_second_call_is_capped_not_duplicated():
    session = InterviewSession.start(ExperienceLevel.FRESHER, RoleType.TECHNICAL)
    process_response_with_follow_up(session, "I am hardworking and a fast learner.")
    decision2 = process_response_with_follow_up(session, "For example, I once built a whole app in college.")
    assert not decision2.should_follow_up


def test_process_response_after_interview_complete_is_safe():
    session = InterviewSession.start(ExperienceLevel.FRESHER, RoleType.TECHNICAL)
    for _ in range(6):
        session.submit_response("a full answer")
    decision = process_response_with_follow_up(session, "anything")
    assert not decision.should_follow_up
    assert "already complete" in decision.reason


def test_ineligible_category_in_live_session_never_follows_up():
    session = InterviewSession.start(ExperienceLevel.FRESHER, RoleType.TECHNICAL)
    for _ in range(4):  # advance to career_goals (index 4), which is follow_up_eligible=False
        session.submit_response("a full answer")
    assert session.current_question.category == "career_goals"
    decision = process_response_with_follow_up(session, "nothing comes to mind")
    assert not decision.should_follow_up
