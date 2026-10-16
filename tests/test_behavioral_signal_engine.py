import time

from parsers.hr_interview_question_bank import InterviewSession, ExperienceLevel, RoleType
from parsers.technical_interview_question_bank import TechnicalInterviewSession, TechnicalDomain
from parsers.behavioral_signal_engine import (
    TimedSessionTracker, assess_focus_consistency, assess_distraction_spikes,
    assess_verbal_hesitation, build_behavioral_insight_report, TimedResponseRecord,
)


def _hr_session():
    return InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)


def _tech_session():
    return TechnicalInterviewSession.start(TechnicalDomain.JAVA, 4)


# ---------------------------------------------------------------------------
# Timed tracking works across BOTH session types (duck typing)
# ---------------------------------------------------------------------------

def test_tracker_works_with_hr_interview_session():
    tracker = TimedSessionTracker(_hr_session())
    record = tracker.submit_timed_response("an answer")
    assert record.question_id == "hr-q01"
    assert record.latency_seconds >= 0.0


def test_tracker_works_with_technical_interview_session():
    tracker = TimedSessionTracker(_tech_session())
    record = tracker.submit_timed_response("an answer")
    assert record.question_id == "tech-intro-01"


def test_tracker_records_accumulate_across_session():
    tracker = TimedSessionTracker(_hr_session())
    for _ in range(3):
        tracker.submit_timed_response("an answer")
    assert len(tracker.records) == 3
    assert [r.question_id for r in tracker.records] == ["hr-q01", "hr-q02", "hr-q03"]


def test_tracker_raises_when_session_already_complete():
    session = _hr_session()
    tracker = TimedSessionTracker(session)
    for _ in range(len(session.questions)):
        tracker.submit_timed_response("an answer")
    raised = False
    try:
        tracker.submit_timed_response("one more")
    except ValueError:
        raised = True
    assert raised


def test_direct_submit_response_still_works_unaffected():
    # Neither session class was modified -- confirms the existing,
    # untimed API every prior day's test suite depends on is untouched.
    session = _hr_session()
    session.submit_response("an answer, no timing wrapper involved")
    assert session.questions[0].response_text == "an answer, no timing wrapper involved"


# ---------------------------------------------------------------------------
# Focus consistency (latency variance)
# ---------------------------------------------------------------------------

def test_consistent_latencies_score_high_focus():
    records = [TimedResponseRecord("q1", "a", 1.0), TimedResponseRecord("q2", "a", 1.0), TimedResponseRecord("q3", "a", 1.0)]
    result = assess_focus_consistency(records)
    assert result.focus_level_score == 100.0


def test_highly_variable_latencies_score_low_focus():
    records = [TimedResponseRecord("q1", "a", 0.5), TimedResponseRecord("q2", "a", 5.0), TimedResponseRecord("q3", "a", 0.3)]
    result = assess_focus_consistency(records)
    assert result.focus_level_score < 100.0


def test_single_record_defaults_to_full_focus_score():
    result = assess_focus_consistency([TimedResponseRecord("q1", "a", 2.0)])
    assert result.focus_level_score == 100.0


# ---------------------------------------------------------------------------
# Distraction spikes
# ---------------------------------------------------------------------------

def test_no_spikes_scores_100():
    records = [TimedResponseRecord(f"q{i}", "a", 1.0) for i in range(5)]
    result = assess_distraction_spikes(records)
    assert result.spike_count == 0
    assert result.distraction_frequency_score == 100.0


def test_a_real_spike_is_detected():
    records = [TimedResponseRecord("q1", "a", 1.0), TimedResponseRecord("q2", "a", 1.1), TimedResponseRecord("q3", "a", 10.0), TimedResponseRecord("q4", "a", 0.9)]
    result = assess_distraction_spikes(records)
    assert "q3" in result.spike_question_ids
    assert result.distraction_frequency_score < 100.0


def test_too_few_records_skips_spike_detection():
    records = [TimedResponseRecord("q1", "a", 1.0), TimedResponseRecord("q2", "a", 10.0)]
    result = assess_distraction_spikes(records)
    assert result.spike_count == 0   # below the minimum, not a real "no spikes found" claim


# ---------------------------------------------------------------------------
# Verbal hesitation -- reused from Day 27
# ---------------------------------------------------------------------------

def test_verbal_hesitation_detects_fillers():
    records = [TimedResponseRecord("q1", "Um, I think, uh, it was fine.", 1.0)]
    result = assess_verbal_hesitation(records)
    assert result.average_hesitation_rate_per_100_words > 0.0


def test_verbal_hesitation_zero_for_clean_answer():
    records = [TimedResponseRecord("q1", "I led the migration project and delivered it early.", 1.0)]
    result = assess_verbal_hesitation(records)
    assert result.average_hesitation_rate_per_100_words == 0.0


# ---------------------------------------------------------------------------
# Full report -- explicitly names what's not implemented
# ---------------------------------------------------------------------------

def test_report_explicitly_lists_unimplemented_camera_signals():
    tracker = TimedSessionTracker(_hr_session())
    tracker.submit_timed_response("an answer")
    report = build_behavioral_insight_report(tracker)
    assert "eye_movement_gaze_stability" in report.not_implemented
    assert "head_movement" in report.not_implemented
    assert "facial_engagement" in report.not_implemented
    assert "nervous_gestures_physical" in report.not_implemented


def test_report_to_dict_and_summary_text_both_work():
    tracker = TimedSessionTracker(_hr_session())
    for _ in range(3):
        tracker.submit_timed_response("an answer")
    report = build_behavioral_insight_report(tracker)
    d = report.to_dict()
    assert "focus_level" in d and "distraction_frequency" in d and "verbal_hesitation" in d and "not_implemented" in d
    text = report.to_summary_text()
    assert "Not implemented" in text
    assert "nervous gestures" not in text.lower() or "not a gesture signal" in text.lower()


def test_full_realistic_session_end_to_end():
    session = _tech_session()
    tracker = TimedSessionTracker(session)
    for _ in range(len(session.questions)):
        tracker.submit_timed_response("a reasonably detailed answer")
    assert session.is_complete
    report = build_behavioral_insight_report(tracker)
    assert 0.0 <= report.focus.focus_level_score <= 100.0
    assert 0.0 <= report.distraction.distraction_frequency_score <= 100.0
