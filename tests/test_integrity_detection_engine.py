import json
from dataclasses import replace

import pytest

from parsers.behavioral_signal_engine import TimedResponseRecord, TimedSessionTracker
from parsers.hr_interview_question_bank import InterviewSession, ExperienceLevel, RoleType
from parsers.integrity_detection_engine import (
    ALERT_FLAG_AT,
    AlertLevel,
    AwayCause,
    BrowserEvent,
    BrowserEventType as T,
    IntegrityMonitor,
    IntegrityRiskTag,
    QuestionWindow,
    build_away_intervals,
    build_integrity_report,
    compute_risk_tag,
    compute_signals,
    detect_burst_pattern,
    detect_lookup_pattern,
    evaluate_threshold_flags,
    windows_from_records,
)


def hidden(t):
    return BrowserEvent(T.TAB_HIDDEN, t)


def visible(t):
    return BrowserEvent(T.TAB_VISIBLE, t)


def blur(t):
    return BrowserEvent(T.WINDOW_BLUR, t)


def focus(t):
    return BrowserEvent(T.WINDOW_FOCUS, t)


def _records(latencies):
    return [TimedResponseRecord(f"q{i + 1}", "an answer", lat) for i, lat in enumerate(latencies)]


# ---------------------------------------------------------------------------
# Event pairing
# ---------------------------------------------------------------------------

def test_hidden_then_visible_makes_one_tab_switch_interval():
    ivs = build_away_intervals([hidden(10), visible(25)])
    assert len(ivs) == 1
    assert (ivs[0].start, ivs[0].end, ivs[0].duration) == (10, 25, 15)
    assert ivs[0].cause is AwayCause.TAB_SWITCH


def test_blur_without_hidden_is_window_blur_cause():
    ivs = build_away_intervals([blur(5), focus(12)])
    assert ivs[0].cause is AwayCause.WINDOW_BLUR


def test_browser_firing_both_hidden_and_blur_merges_into_one_interval():
    # A real tab change fires blur + hidden together, then visible + focus together.
    ivs = build_away_intervals([blur(10), hidden(10.01), visible(20), focus(20.01)])
    assert len(ivs) == 1
    assert ivs[0].cause is AwayCause.TAB_SWITCH
    assert ivs[0].end == 20.01


def test_interval_stays_open_until_both_states_clear():
    ivs = build_away_intervals([blur(10), hidden(12), visible(14), focus(30)])
    assert len(ivs) == 1 and ivs[0].end == 30


def test_unsorted_events_are_ordered_by_timestamp():
    ivs = build_away_intervals([visible(25), hidden(10)])
    assert len(ivs) == 1 and ivs[0].duration == 15


def test_orphan_and_duplicate_return_events_are_harmless():
    ivs = build_away_intervals([visible(3), focus(4), hidden(10), visible(20), visible(21)])
    assert len(ivs) == 1


def test_unclosed_interval_is_closed_at_session_end_and_marked():
    ivs = build_away_intervals([hidden(50)], session_end=90)
    assert ivs[0].unclosed is True and ivs[0].duration == 40


def test_events_after_session_end_are_ignored():
    ivs = build_away_intervals([hidden(10), visible(20), hidden(200), visible(210)], session_end=100)
    assert len(ivs) == 1


def test_negative_timestamp_rejected():
    with pytest.raises(ValueError):
        BrowserEvent(T.TAB_HIDDEN, -1)


def test_no_events_gives_no_intervals():
    assert build_away_intervals([]) == []


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

def test_sub_threshold_blips_are_ignored_but_counted_for_transparency():
    ivs = build_away_intervals([blur(10), focus(10.8), hidden(40), visible(50)])
    sig = compute_signals(ivs, 100)
    assert sig.away_event_count == 1
    assert sig.ignored_blips == 1


def test_signals_split_tab_switch_from_window_blur():
    ivs = build_away_intervals([hidden(10), visible(20), blur(40), focus(50)])
    sig = compute_signals(ivs, 100)
    assert (sig.tab_switch_count, sig.window_blur_count) == (1, 1)
    assert sig.total_away_seconds == 20 and sig.away_fraction == 0.2


def test_away_fraction_is_none_when_session_length_unknown():
    sig = compute_signals(build_away_intervals([hidden(1), visible(9)]), None)
    assert sig.away_fraction is None


def test_events_are_assigned_to_the_question_on_screen():
    windows = [QuestionWindow("q1", 0, 30), QuestionWindow("q2", 30, 60)]
    ivs = build_away_intervals([hidden(35), visible(45)], windows=windows)
    assert ivs[0].question_id == "q2"


# ---------------------------------------------------------------------------
# Threshold flags
# ---------------------------------------------------------------------------

def _flags_for(events, duration=600):
    return evaluate_threshold_flags(compute_signals(build_away_intervals(events), duration))


def test_single_short_absence_raises_no_flags():
    assert _flags_for([hidden(100), visible(104)]) == []


def test_frequent_focus_loss_tiers():
    def n_events(n):
        ev = []
        for k in range(n):
            ev += [hidden(100 * k + 10), visible(100 * k + 13)]
        return ev
    assert [f.points for f in _flags_for(n_events(2), 2000) if f.code == "FREQUENT_FOCUS_LOSS"] == [1]
    assert [f.points for f in _flags_for(n_events(4), 2000) if f.code == "FREQUENT_FOCUS_LOSS"] == [2]
    assert [f.points for f in _flags_for(n_events(6), 2000) if f.code == "FREQUENT_FOCUS_LOSS"] == [3]


def test_long_single_absence_flag_tiers():
    medium = _flags_for([hidden(10), visible(22)])
    long_ = _flags_for([hidden(10), visible(50)])
    assert [f.points for f in medium if f.code == "LONG_SINGLE_ABSENCE"] == [1]
    assert [f.points for f in long_ if f.code == "LONG_SINGLE_ABSENCE"] == [2]


def test_significant_away_time_flag_uses_session_fraction():
    flags = _flags_for([hidden(10), visible(50)], duration=200)   # 20% away
    assert any(f.code == "SIGNIFICANT_AWAY_TIME" and f.points == 2 for f in flags)


# ---------------------------------------------------------------------------
# Pattern recognition
# ---------------------------------------------------------------------------

def test_burst_detected_when_three_away_events_fall_in_a_minute():
    ivs = build_away_intervals([hidden(10), visible(14), hidden(30), visible(34), hidden(50), visible(54)])
    assert detect_burst_pattern(ivs).code == "BURST_SWITCHING"


def test_no_burst_when_events_are_spread_out():
    ivs = build_away_intervals([hidden(10), visible(14), hidden(200), visible(204), hidden(400), visible(404)])
    assert detect_burst_pattern(ivs) is None


WINDOWS = [QuestionWindow("q1", 0, 60), QuestionWindow("q2", 60, 120), QuestionWindow("q3", 120, 180)]


def test_lookup_pattern_needs_two_questions_with_leave_early_return_late_shape():
    # q1: leaves at 2s, back at 55s (5s before submit). q2: leaves at 63s, back at 115s.
    ivs = build_away_intervals([hidden(2), visible(55), hidden(63), visible(115)], windows=WINDOWS)
    flag = detect_lookup_pattern(ivs, WINDOWS)
    assert flag.code == "QUESTION_LOOKUP_PATTERN"
    assert flag.evidence["question_ids"] == ["q1", "q2"]


def test_lookup_pattern_not_raised_for_a_single_occurrence():
    ivs = build_away_intervals([hidden(2), visible(55)], windows=WINDOWS)
    assert detect_lookup_pattern(ivs, WINDOWS) is None


def test_mid_question_absence_is_not_a_lookup_pattern():
    # Leaves 30s into each question and returns well before submitting.
    ivs = build_away_intervals([hidden(30), visible(36), hidden(90), visible(96)], windows=WINDOWS)
    assert detect_lookup_pattern(ivs, WINDOWS) is None


# ---------------------------------------------------------------------------
# Day 48 integration -- behavioral signals corroborate, never accuse
# ---------------------------------------------------------------------------

def test_latency_spike_alone_never_raises_integrity_risk():
    records = _records([30, 32, 31, 200, 29, 30])       # huge spike on q4, NO browser events
    report = build_integrity_report([], records=records)
    assert report.risk_tag is IntegrityRiskTag.CLEAR
    assert report.flags == []


def test_spike_plus_focus_loss_on_same_question_adds_corroboration():
    records = _records([30, 32, 31, 200, 29, 30])
    windows = windows_from_records(records)
    start_q4 = windows[3].start
    events = [hidden(start_q4 + 20), visible(start_q4 + 60)]
    report = build_integrity_report(events, records=records)
    codes = [f.code for f in report.flags]
    assert "LATENCY_CORROBORATION" in codes


def test_windows_from_records_are_cumulative():
    w = windows_from_records(_records([10, 20, 5]))
    assert [(x.start, x.end) for x in w] == [(0, 10), (10, 30), (30, 35)]


def test_windows_rebuild_from_a_real_day48_tracker():
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)
    tracker = TimedSessionTracker(session)
    tracker.submit_timed_response("first")
    tracker.submit_timed_response("second")
    w = windows_from_records(tracker.records)
    assert [x.question_id for x in w] == [r.question_id for r in tracker.records]
    assert w[1].start == pytest.approx(w[0].end)


# ---------------------------------------------------------------------------
# Risk tagging
# ---------------------------------------------------------------------------

def test_risk_tag_boundaries():
    from parsers.integrity_detection_engine import IntegrityFlag

    def flag(p):
        return IntegrityFlag("X", "threshold", p, "", {})
    assert compute_risk_tag([])[0] is IntegrityRiskTag.CLEAR
    assert compute_risk_tag([flag(1)])[0] is IntegrityRiskTag.LOW
    assert compute_risk_tag([flag(2)])[0] is IntegrityRiskTag.LOW
    assert compute_risk_tag([flag(3)])[0] is IntegrityRiskTag.MEDIUM
    assert compute_risk_tag([flag(5)])[0] is IntegrityRiskTag.MEDIUM
    assert compute_risk_tag([flag(6)])[0] is IntegrityRiskTag.HIGH


def test_two_brief_unrelated_switches_stay_low():
    records = _records([60, 60, 60, 60, 60])
    events = [hidden(70), visible(76), hidden(190), visible(194)]
    report = build_integrity_report(events, records=records)
    assert report.risk_tag is IntegrityRiskTag.LOW
    assert report.human_review_required is False


def test_lookup_behavior_with_spikes_reaches_high():
    records = _records([60, 60, 120, 60, 120])
    w = windows_from_records(records)
    events = [
        hidden(w[2].start + 2), visible(w[2].end - 4),
        hidden(w[4].start + 3), visible(w[4].end - 3),
    ]
    report = build_integrity_report(events, records=records)
    assert report.risk_tag in (IntegrityRiskTag.MEDIUM, IntegrityRiskTag.HIGH)
    assert any(f.code == "QUESTION_LOOKUP_PATTERN" for f in report.flags)
    assert report.human_review_required is True


# ---------------------------------------------------------------------------
# Real-time alerts
# ---------------------------------------------------------------------------

def _feed(monitor, pairs):
    alerts = []
    for start in pairs:
        monitor.record_event(hidden(start))
        alerts.append(monitor.record_event(visible(start + 5)))
    return alerts


def test_escalation_ladder_notice_warning_then_internal_flag():
    m = IntegrityMonitor()
    a1, a2, a3, a4, a5 = _feed(m, [10, 50, 90, 130, 170])
    assert a1.level is AlertLevel.NOTICE
    assert a2.level is AlertLevel.WARNING and a3.level is AlertLevel.WARNING
    assert a4.level is AlertLevel.FLAG and a4.away_event_count == ALERT_FLAG_AT
    assert a5 is None          # flag is raised once, not repeatedly


def test_flag_alert_is_internal_only_and_notice_warning_are_candidate_visible():
    m = IntegrityMonitor()
    alerts = _feed(m, [10, 50, 90, 130])
    assert alerts[0].candidate_message and alerts[1].candidate_message
    assert alerts[3].candidate_message is None


def test_hidden_event_alone_does_not_alert_until_the_candidate_returns():
    m = IntegrityMonitor()
    assert m.record_event(hidden(10)) is None


def test_sub_threshold_blip_raises_no_alert():
    m = IntegrityMonitor()
    m.record_event(blur(10))
    assert m.record_event(focus(10.5)) is None


def test_poll_raises_one_warning_for_a_long_ongoing_absence():
    m = IntegrityMonitor()
    m.record_event(hidden(100))
    assert m.poll(110) is None
    alert = m.poll(135)
    assert alert.level is AlertLevel.WARNING and alert.trigger == "long_absence"
    assert m.poll(160) is None      # not repeated for the same absence


def test_finalize_includes_alerts_in_report():
    m = IntegrityMonitor()
    _feed(m, [10, 50])
    report = m.finalize(session_end=300)
    assert [a.level for a in report.alerts] == [AlertLevel.NOTICE, AlertLevel.WARNING]


# ---------------------------------------------------------------------------
# Honesty / safety guarantees of the report
# ---------------------------------------------------------------------------

def test_report_always_lists_unobservable_signals_explicitly():
    report = build_integrity_report([])
    assert set(report.not_implemented) == {
        "external_voice_detection", "repeated_looking_away", "secondary_device_or_mobile_usage",
    }
    assert "external_voice_detection" in report.to_summary_text()


def test_report_never_takes_automated_action_or_changes_scores():
    report = build_integrity_report([hidden(1), visible(100)] * 1, session_end=120)
    assert report.automated_action == "none"
    assert report.scoring_impact == "none"


def test_clear_tag_is_not_worded_as_a_guarantee():
    d = build_integrity_report([]).to_dict()
    assert "not proof" in d["risk_meaning"]
    assert any("not an integrity guarantee" in c for c in d["caveats"])


def test_report_is_json_serializable_and_complete():
    records = _records([60, 60, 60])
    report = build_integrity_report([hidden(70), visible(90)], records=records)
    data = json.loads(json.dumps(report.to_dict()))
    for key in ("risk_tag", "signals", "flags", "alerts", "not_implemented", "caveats",
                "automated_action", "scoring_impact", "human_review_required"):
        assert key in data


def test_two_independent_reports_do_not_share_mutable_defaults():
    a = build_integrity_report([])
    b = build_integrity_report([])
    a.caveats.append("x")
    a.not_implemented["x"] = "y"
    assert "x" not in b.not_implemented and "x" not in b.caveats


def test_record_replace_helper_does_not_mutate_original_records():
    records = _records([10, 10, 10])
    replace(records[0], latency_seconds=99)
    assert records[0].latency_seconds == 10
