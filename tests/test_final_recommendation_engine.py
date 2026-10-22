import json

import pytest

from parsers import cross_round_aggregation_engine as day51
from parsers.behavioral_signal_engine import (
    BehavioralInsightReport,
    DistractionSpikeResult,
    FocusConsistencyResult,
    TimedSessionTracker,
    VerbalHesitationSummary,
    build_behavioral_insight_report,
)
from parsers.cross_round_aggregation_engine import RoundResult, compute_cross_round_score
from parsers.final_recommendation_engine import (
    DECISION_FIELDS,
    NOTICES,
    CandidateDecision,
    DecisionOutcome,
    DecisionPolicy,
    HoldKind,
    HumanReview,
    assess_risk_factors,
    compute_confidence,
    decide,
    finalize_automatically,
    finalize_with_human,
)
from parsers.hr_interview_question_bank import ExperienceLevel, InterviewSession, RoleType
from parsers.integrity_detection_engine import BrowserEvent, BrowserEventType as T, build_integrity_report

TECH, NON_TECH = RoleType.TECHNICAL, RoleType.NON_TECHNICAL
EXPERIENCED, FRESHER = ExperienceLevel.EXPERIENCED, ExperienceLevel.FRESHER
SELECTED, HOLD, REJECTED = DecisionOutcome.SELECTED, DecisionOutcome.HOLD_REVIEW, DecisionOutcome.REJECTED


def rounds(ats, screening, hr, tech, machine):
    values = {"ats": ats, "screening": screening, "hr_interview": hr, "technical_interview": tech, "machine_test": machine}
    return [RoundResult(name, score) for name, score in values.items()]


def score_for(*values, role=TECH, exp=EXPERIENCED, cid="c1", **kw):
    return compute_cross_round_score(rounds(*values), role, exp, cid, **kw)


def flat(value, **kw):
    return score_for(value, value, value, value, value, **kw)


def behavior(spikes=0, focus=90.0, hesitation=2.0):
    return BehavioralInsightReport(
        FocusConsistencyResult([30.0, 31.0], 30.5, 0.5, 0.02, focus),
        DistractionSpikeResult([f"q{i}" for i in range(spikes)], spikes, 30.0, 100.0 - 30 * spikes),
        VerbalHesitationSummary({}, hesitation),
    )


def trace(decision, rule_id):
    return next(r for r in decision.rule_trace if r.rule_id == rule_id)


# ---------------------------------------------------------------------------
# Policy: the hard line on automation
# ---------------------------------------------------------------------------

def test_thresholds_are_pinned_to_day_51():
    policy = DecisionPolicy()
    assert policy.selected_threshold == day51.SELECTED_THRESHOLD and policy.hold_threshold == day51.HOLD_THRESHOLD


def test_default_policy_is_recommend_only():
    assert DecisionPolicy().auto_apply == {}


def test_a_rejection_can_never_be_configured_as_automatic():
    with pytest.raises(ValueError):
        DecisionPolicy(auto_apply={REJECTED: True})


def test_a_hold_cannot_be_configured_as_automatic_either():
    with pytest.raises(ValueError):
        DecisionPolicy(auto_apply={HOLD: True})


def test_only_selected_may_be_auto_applied_and_it_is_allowed_when_explicit():
    assert DecisionPolicy(auto_apply={SELECTED: True}).auto_apply[SELECTED] is True
    assert DecisionPolicy(auto_apply={REJECTED: False}).auto_apply[REJECTED] is False


def test_hold_threshold_must_be_below_selected_threshold():
    with pytest.raises(ValueError):
        DecisionPolicy(selected_threshold=60, hold_threshold=60)


# ---------------------------------------------------------------------------
# Decision categories (score band)
# ---------------------------------------------------------------------------

def test_clear_strong_candidate_is_selected():
    d = decide(flat(90))
    assert d.outcome is SELECTED and d.score_band is SELECTED and d.hold_kind is None
    assert d.confidence.band == "high"


def test_mid_scorer_is_held_for_review_as_a_mid_score():
    d = decide(flat(60))
    assert d.outcome is HOLD and d.hold_kind is HoldKind.MID_SCORE and d.score_band is HOLD


def test_clear_weak_candidate_is_recommended_for_rejection():
    d = decide(flat(30))
    assert d.outcome is REJECTED and d.hold_kind is None


def test_incomplete_candidate_is_held_pending_evidence_with_the_rounds_named():
    incomplete = compute_cross_round_score([r for r in rounds(90, 90, 90, 90, 90) if r.round_name != "machine_test"], TECH, EXPERIENCED, "p")
    d = decide(incomplete)
    assert d.outcome is HOLD and d.hold_kind is HoldKind.PENDING_EVIDENCE
    assert trace(d, "R1_EVIDENCE_COMPLETE").fired
    assert any("machine_test" in c for c in d.what_would_change)


def test_a_candidate_with_no_scored_round_is_held_with_zero_confidence():
    d = decide(compute_cross_round_score([], TECH, EXPERIENCED, "empty"))
    assert d.outcome is HOLD and d.hold_kind is HoldKind.PENDING_EVIDENCE and d.confidence.score == 0.0
    assert d.hiring_fit_percentage is None


def test_provisional_high_score_is_never_selected():
    incomplete = compute_cross_round_score([RoundResult("ats", 99), RoundResult("screening", 99)], TECH, EXPERIENCED, "p")
    assert decide(incomplete).outcome is HOLD


# ---------------------------------------------------------------------------
# The rules (hybrid logic)
# ---------------------------------------------------------------------------

def test_r2_a_failed_critical_round_blocks_selection_even_when_the_average_is_high():
    candidate = score_for(95, 95, 95, 35, 95)           # fit 77: the score alone would select
    d = decide(candidate)
    assert d.score_band is SELECTED and d.outcome is HOLD and d.hold_kind is HoldKind.SELECTION_BLOCKED
    assert trace(d, "R2_CRITICAL_ROUND_FLOORS").fired and "technical_interview 35" in trace(d, "R2_CRITICAL_ROUND_FLOORS").detail


def test_r2_does_not_fire_when_every_critical_round_clears_its_floor():
    assert not trace(decide(flat(90)), "R2_CRITICAL_ROUND_FLOORS").fired


def test_r3_medium_or_high_integrity_blocks_selection_and_lowers_confidence():
    clean = decide(flat(90))
    for tag in ("medium", "high"):
        d = decide(flat(90, integrity_risk_tag=tag))
        assert d.outcome is HOLD and d.hold_kind is HoldKind.SELECTION_BLOCKED and trace(d, "R3_INTEGRITY_GATE").fired
        assert d.confidence.score < clean.confidence.score
        assert d.hiring_fit_percentage == clean.hiring_fit_percentage       # the number is untouched


def test_r3_low_integrity_is_informational_only():
    d = decide(flat(90, integrity_risk_tag="low"))
    assert d.outcome is SELECTED and not trace(d, "R3_INTEGRITY_GATE").fired


def test_integrity_report_object_from_day_49_adds_its_flags_to_the_risk_factor():
    events = [BrowserEvent(T.TAB_HIDDEN, 100), BrowserEvent(T.TAB_VISIBLE, 104), BrowserEvent(T.TAB_HIDDEN, 120),
              BrowserEvent(T.TAB_VISIBLE, 124), BrowserEvent(T.TAB_HIDDEN, 140), BrowserEvent(T.TAB_VISIBLE, 144)]
    report = build_integrity_report(events, session_end=1800)
    d = decide(flat(90), integrity_report=report)
    factor = next(f for f in d.risk_factors if f.category == "integrity")
    assert factor.level == report.risk_tag.value and "BURST_SWITCHING" in factor.detail
    assert d.outcome is HOLD


def test_most_severe_integrity_tag_across_score_and_report_wins():
    report = build_integrity_report([], session_end=1800)               # CLEAR
    d = decide(flat(90, integrity_risk_tag="high"), integrity_report=report)
    assert next(f for f in d.risk_factors if f.category == "integrity").level == "high"


def test_r4_borderline_score_is_held_for_review():
    d = decide(flat(71))
    assert d.score_band is SELECTED and d.outcome is HOLD and trace(d, "R4_REVIEW_FLAGS").fired


def test_r4_strong_round_disagreement_is_held_for_review():
    d = decide(score_for(92, 90, 88, 40, 85))
    assert d.outcome is HOLD and trace(d, "R4_REVIEW_FLAGS").fired


def test_r4_a_round_that_itself_asked_for_review_is_held():
    candidate = compute_cross_round_score(
        [RoundResult("ats", 90), RoundResult("screening", 90), RoundResult("hr_interview", 90), RoundResult("technical_interview", 90),
         RoundResult("machine_test", 90, review_reasons=["design write-up scored by keywords"])], TECH, EXPERIENCED, "c")
    d = decide(candidate)
    assert d.outcome is HOLD and trace(d, "R4_REVIEW_FLAGS").fired


def test_r5_low_confidence_blocks_selection():
    d = decide(flat(75), policy=DecisionPolicy(min_select_confidence=99.0))      # fit 75: 5 points from the threshold, not borderline
    assert d.outcome is HOLD and d.hold_kind is HoldKind.SELECTION_BLOCKED and trace(d, "R5_SELECT_CONFIDENCE_FLOOR").fired
    assert not trace(d, "R4_REVIEW_FLAGS").fired                                 # R5 alone caused the hold


def test_r6_low_confidence_turns_a_rejection_into_a_review():
    d = decide(flat(42), policy=DecisionPolicy(min_reject_confidence=99.5))
    assert d.score_band is REJECTED and d.outcome is HOLD and d.hold_kind is HoldKind.INSUFFICIENT_EVIDENCE_TO_REJECT
    assert trace(d, "R6_REJECT_CONFIDENCE_FLOOR").fired


def test_r6_shaky_rejection_evidence_in_a_realistic_case():
    shaky = score_for(80, 20, 45, 30, 60)                               # fit 46, scattered rounds
    plain = decide(shaky)
    assert plain.outcome is REJECTED
    with_integrity = decide(shaky, integrity_report=build_integrity_report(
        [BrowserEvent(T.TAB_HIDDEN, 100), BrowserEvent(T.TAB_VISIBLE, 104), BrowserEvent(T.TAB_HIDDEN, 120),
         BrowserEvent(T.TAB_VISIBLE, 124), BrowserEvent(T.TAB_HIDDEN, 140), BrowserEvent(T.TAB_VISIBLE, 144)], session_end=1800))
    assert with_integrity.outcome is HOLD and with_integrity.hold_kind is HoldKind.INSUFFICIENT_EVIDENCE_TO_REJECT


def test_r7_a_rejection_always_needs_a_human_and_is_marked_in_the_trace():
    d = decide(flat(30))
    assert trace(d, "R7_REJECTION_NEEDS_HUMAN").fired and d.requires_human_confirmation and not d.automation_eligible


def test_rule_trace_lists_every_rule_whether_or_not_it_fired():
    ids = [r.rule_id for r in decide(flat(90)).rule_trace]
    assert ids == ["R1_EVIDENCE_COMPLETE", "R2_CRITICAL_ROUND_FLOORS", "R3_INTEGRITY_GATE", "R4_REVIEW_FLAGS",
                   "R5_SELECT_CONFIDENCE_FLOOR", "R6_REJECT_CONFIDENCE_FLOOR", "R7_REJECTION_NEEDS_HUMAN"]


# ---------------------------------------------------------------------------
# Risk factors can only move toward review, never toward rejection
# ---------------------------------------------------------------------------

def test_no_combination_of_risk_factors_turns_a_non_rejected_candidate_into_a_rejected_one():
    for value in (30, 45, 55, 65, 72, 80, 95):
        clean = decide(flat(value))
        for tag in (None, "clear", "low", "medium", "high"):
            for spikes in (0, 1, 3):
                for focus in (90.0, 30.0):
                    risky = decide(flat(value, integrity_risk_tag=tag), behavior_report=behavior(spikes, focus))
                    if clean.outcome is not REJECTED:
                        assert risky.outcome is not REJECTED
                    if clean.outcome is not SELECTED:
                        assert risky.outcome is not SELECTED


def test_risk_factors_never_change_the_hiring_fit():
    a = decide(flat(80))
    b = decide(flat(80, integrity_risk_tag="high"), behavior_report=behavior(3, 30.0))
    assert a.hiring_fit_percentage == b.hiring_fit_percentage


def test_behavior_spikes_and_uneven_pacing_lower_confidence_only():
    clean = decide(flat(90))
    some = decide(flat(90), behavior_report=behavior(spikes=2))
    both = decide(flat(90), behavior_report=behavior(spikes=2, focus=30.0))
    assert next(f for f in some.risk_factors if f.category == "behavior").level == "low"
    assert next(f for f in both.risk_factors if f.category == "behavior").level == "medium"
    assert both.confidence.score < some.confidence.score < clean.confidence.score
    assert some.outcome is SELECTED


def test_verbal_hesitation_is_shown_but_never_used():
    low = decide(flat(90), behavior_report=behavior(hesitation=1.0))
    high = decide(flat(90), behavior_report=behavior(hesitation=40.0))
    assert low.confidence.score == high.confidence.score and low.outcome == high.outcome
    assert "NOT used" in next(f for f in high.risk_factors if f.category == "behavior").detail


def test_calm_behavior_is_informational():
    factor = next(f for f in decide(flat(90), behavior_report=behavior()).risk_factors if f.category == "behavior")
    assert factor.level == "none" and factor.effect == "informational"


def test_a_real_day_48_tracker_report_feeds_the_decision():
    tracker = TimedSessionTracker(InterviewSession.start(EXPERIENCED, TECH))
    for text in ("first answer", "second answer", "third answer"):
        tracker.submit_timed_response(text)
    d = decide(flat(90), behavior_report=build_behavioral_insight_report(tracker))
    assert any(f.category == "behavior" for f in d.risk_factors) and d.outcome is SELECTED


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------

def test_confidence_components_are_in_range_and_the_score_is_0_to_100():
    for value in (20, 49, 50, 69, 70, 71, 90):
        c = decide(flat(value)).confidence
        for part in (c.margin, c.coverage, c.agreement, c.stability):
            assert 0.0 <= part <= 1.0
        assert 0.0 <= c.score <= 100.0


def test_confidence_is_lowest_at_a_threshold_and_grows_with_distance():
    at_edge = decide(flat(70)).confidence.score
    near = decide(flat(75)).confidence.score
    far = decide(flat(90)).confidence.score
    assert at_edge < near < far


def test_missing_evidence_lowers_confidence():
    full = decide(flat(90)).confidence
    partial = decide(compute_cross_round_score([r for r in rounds(90, 90, 90, 90, 90) if r.round_name != "machine_test"], TECH, EXPERIENCED)).confidence
    assert partial.coverage < full.coverage and partial.score < full.score


def test_a_provisional_score_can_never_have_high_confidence():
    pending = compute_cross_round_score([r for r in rounds(95, 95, 95, 95, 95) if r.round_name != "machine_test"], TECH, EXPERIENCED)
    conf = decide(pending).confidence
    assert conf.score <= 60.0 and conf.band != "high"
    assert decide(flat(95)).confidence.band == "high"


def test_disagreeing_rounds_lower_confidence():
    agreeing = decide(score_for(80, 80, 80, 80, 80)).confidence
    scattered = decide(score_for(100, 100, 100, 40, 100)).confidence
    assert scattered.agreement < agreeing.agreement


def test_a_fragile_score_is_less_stable_than_a_robust_one():
    robust = decide(flat(90)).confidence.stability
    fragile = decide(score_for(100, 100, 100, 100, 20)).confidence.stability       # dropping one round changes the band
    assert fragile < robust


def test_confidence_is_explicitly_not_a_probability():
    note = decide(flat(90)).confidence.note
    assert "not a probability" in note and "not calibrated" in note


def test_compute_confidence_can_be_called_directly():
    candidate = flat(90)
    conf = compute_confidence(candidate, assess_risk_factors(candidate), DecisionPolicy())
    assert conf.score > 90 and conf.band == "high"


# ---------------------------------------------------------------------------
# Automation, finalization and the audit trail
# ---------------------------------------------------------------------------

AUTO = DecisionPolicy(auto_apply={SELECTED: True})


def test_nothing_is_eligible_for_automation_under_the_default_policy():
    assert not decide(flat(95)).automation_eligible and decide(flat(95)).requires_human_confirmation


def test_a_clean_selected_decision_is_eligible_only_when_the_policy_enables_it():
    d = decide(flat(95), policy=AUTO)
    assert d.automation_eligible and not d.requires_human_confirmation
    finalized = finalize_automatically(d)
    assert finalized.decided_by == "policy:auto_advance" and finalized.final_outcome is SELECTED and not finalized.overridden


def test_a_blocked_or_flagged_selection_is_never_automation_eligible():
    assert not decide(flat(95, integrity_risk_tag="high"), policy=AUTO).automation_eligible
    assert not decide(flat(71), policy=AUTO).automation_eligible


def test_the_policys_confidence_bar_is_respected():
    strict = DecisionPolicy(auto_apply={SELECTED: True}, auto_min_confidence=99.9)
    assert decide(flat(80)).outcome is SELECTED and not decide(flat(80), policy=strict).automation_eligible


def test_holds_and_rejections_are_never_automation_eligible_even_with_the_policy_on():
    assert not decide(flat(60), policy=AUTO).automation_eligible
    assert not decide(flat(30), policy=AUTO).automation_eligible


def test_finalize_automatically_refuses_anything_not_eligible():
    for d in (decide(flat(95)), decide(flat(60), policy=AUTO), decide(flat(30), policy=AUTO)):
        with pytest.raises(ValueError):
            finalize_automatically(d)


def test_a_human_confirms_a_rejection_and_it_is_recorded():
    d = decide(flat(30))
    final = finalize_with_human(d, HumanReview("recruiter-7", REJECTED))
    assert final.final_outcome is REJECTED and final.decided_by == "human:recruiter-7" and not final.overridden
    assert final.candidate_notice == NOTICES[REJECTED]


def test_overriding_the_engine_requires_a_written_note():
    d = decide(flat(30))
    with pytest.raises(ValueError):
        finalize_with_human(d, HumanReview("recruiter-7", SELECTED))
    final = finalize_with_human(d, HumanReview("recruiter-7", HOLD, note="Strong referral; re-interview first."))
    assert final.overridden and final.engine_outcome is REJECTED and final.final_outcome is HOLD


def test_a_named_reviewer_is_mandatory():
    with pytest.raises(ValueError):
        finalize_with_human(decide(flat(30)), HumanReview("  ", REJECTED))


def test_audit_record_captures_engine_outcome_final_outcome_and_who_decided():
    record = finalize_with_human(decide(flat(30)), HumanReview("r1", REJECTED)).audit_record()
    assert set(record) == {"candidate_id", "engine_outcome", "final_outcome", "decided_by", "overridden", "note"}


# ---------------------------------------------------------------------------
# Candidate-facing notice
# ---------------------------------------------------------------------------

def test_an_unconfirmed_rejection_reads_as_under_review_for_the_candidate():
    d = decide(flat(30))
    assert d.outcome is REJECTED and d.candidate_notice() == NOTICES[HOLD]
    assert "decided not to move forward" not in d.candidate_notice()


def test_notices_never_contain_scores_risk_factors_or_integrity_language():
    for text in NOTICES.values():
        lowered = text.lower()
        for banned in ("integrity", "score", "risk", "confidence", "%", "behavio", "cheat"):
            assert banned not in lowered
        assert not any(ch.isdigit() for ch in text)


def test_every_outcome_has_a_candidate_notice():
    assert set(NOTICES) == {SELECTED, HOLD, REJECTED}


# ---------------------------------------------------------------------------
# Explainability and output format
# ---------------------------------------------------------------------------

def test_decision_output_has_every_documented_field_and_is_json_serializable():
    data = json.loads(json.dumps(decide(flat(90)).to_dict()))
    for key in DECISION_FIELDS:
        assert key in data
    assert data["schema_version"] == "1.0" and data["automated_action"] == "none"


def test_to_dict_values_are_plain_strings_not_enums():
    data = decide(flat(60)).to_dict()
    assert data["outcome"] == "hold_review" and data["hold_kind"] == "mid_score" and data["score_band"] == "hold_review"


def test_explain_states_outcome_score_band_rules_and_confirmation():
    text = decide(score_for(95, 95, 95, 35, 95)).explain()
    assert "HOLD / REVIEW" in text and "The score alone says SELECTED" in text and "R2_CRITICAL_ROUND_FLOORS" in text
    assert "Human confirmation required" in text


def test_explanations_have_no_doubled_punctuation():
    text = decide(score_for(95, 95, 95, 35, 95)).explain()
    assert ".." not in text


def test_a_rule_that_did_not_fire_shows_no_misleading_detail():
    d = decide(flat(30))                                   # every skill round is below its floor, but the score is not in the selection band
    assert not trace(d, "R2_CRITICAL_ROUND_FLOORS").fired and trace(d, "R2_CRITICAL_ROUND_FLOORS").detail == ""
    rejected_with_integrity = decide(flat(30, integrity_risk_tag="high"))
    assert not trace(rejected_with_integrity, "R3_INTEGRITY_GATE").fired and trace(rejected_with_integrity, "R3_INTEGRITY_GATE").detail == ""
    assert any(f.category == "integrity" and f.level == "high" for f in rejected_with_integrity.risk_factors)     # still visible as a risk factor


def test_pending_decision_does_not_claim_a_score_band():
    incomplete = compute_cross_round_score([RoundResult("ats", 90)], TECH, EXPERIENCED, "p")
    assert "The score alone says" not in decide(incomplete).explain()


def test_summary_text_shows_the_rule_trace_and_risk_factors():
    text = decide(flat(90, integrity_risk_tag="high")).to_summary_text()
    assert "[FIRED] R3_INTEGRITY_GATE" in text and "integrity: high" in text and "not an automated decision" in text


def test_what_would_change_gives_concrete_conditions():
    mid = decide(flat(60))
    assert any("+10.0 points" in c for c in mid.what_would_change)
    rejected = decide(flat(30))
    assert any("+20.0 points" in c for c in rejected.what_would_change)
    blocked = decide(flat(90, integrity_risk_tag="high"))
    assert any("integrity" in c.lower() for c in blocked.what_would_change)


def test_not_implemented_and_caveats_are_always_present():
    d = decide(flat(90))
    assert {"confidence_calibration", "decision_bias_audit", "notification_delivery", "audit_persistence_and_appeals",
            "legal_review"} == set(d.not_implemented)
    assert any("never toward rejection" in c for c in d.caveats)


def test_decisions_are_deterministic_and_do_not_share_mutable_defaults():
    a, b = decide(flat(80)), decide(flat(80))
    a.caveats.append("x")
    a.not_implemented["x"] = "y"
    assert "x" not in b.caveats and "x" not in b.not_implemented
    assert decide(flat(80)).to_dict() == decide(flat(80)).to_dict()


def test_fresher_and_non_technical_candidates_flow_through_the_same_engine():
    fresher = decide(score_for(35, 80, 78, 88, 90, exp=FRESHER))
    assert fresher.outcome is SELECTED
    non_tech = decide(compute_cross_round_score([RoundResult("ats", 85), RoundResult("screening", 85), RoundResult("hr_interview", 90)],
                                                NON_TECH, EXPERIENCED, "n"))
    assert non_tech.outcome is SELECTED and non_tech.role_type == "non_technical"
