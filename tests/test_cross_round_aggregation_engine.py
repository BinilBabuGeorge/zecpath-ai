import json

import pytest

from parsers.ats_scoring_engine import ATSScoreResult, ComponentResult
from parsers.cross_round_aggregation_engine import (
    BORDERLINE_MARGIN,
    HOLD_THRESHOLD,
    ROLE_WEIGHT_PROFILES,
    ROUND_NAMES,
    SELECTED_THRESHOLD,
    RoundResult,
    RoundStatus,
    compute_cross_round_score,
    compute_from_round_outputs,
    normalize_score,
    rank_candidates,
    resolve_weights,
    round_from_ats,
    round_from_hr,
    round_from_machine_test,
    round_from_screening,
    round_from_technical,
)
from parsers.hr_interview_question_bank import ExperienceLevel, RoleType
from parsers.hr_interview_scoring_engine import ConsistencyAssessment, HRInterviewScoreReport, WeightConfig
from parsers.integrity_detection_engine import IntegrityRiskTag
from parsers.machine_test_evaluation_engine import (
    MachineTestTask,
    MachineTestType,
    TaskAttempt,
    build_machine_test_report,
)
from parsers.screening_scoring_engine import ScreeningScoreResult
from parsers.technical_interview_question_bank import DifficultyTier
from parsers.technical_skill_scoring_engine import TechnicalEvaluationReport
from parsers import unified_scoring_engine as day41

TECH = RoleType.TECHNICAL
NON_TECH = RoleType.NON_TECHNICAL
EXPERIENCED = ExperienceLevel.EXPERIENCED
FRESHER = ExperienceLevel.FRESHER


def rr(name, score, **kw):
    return RoundResult(name, score, **kw)


def full(ats=80, screening=70, hr=60, tech=90, machine=100):
    return [rr("ats", ats), rr("screening", screening), rr("hr_interview", hr),
            rr("technical_interview", tech), rr("machine_test", machine)]


def contribution(score, name):
    return next(c for c in score.contributions if c.round_name == name)


def only(name, value):
    """Custom weights that put everything on one round, so fit == that round's score."""
    return {r: (1.0 if r == name else 0.0) for r in ROUND_NAMES}, [rr(name, value)]


# ---------------------------------------------------------------------------
# Configuration and continuity with Day 41
# ---------------------------------------------------------------------------

def test_every_role_profile_sums_to_one():
    for weights in ROLE_WEIGHT_PROFILES.values():
        assert sum(weights.values()) == pytest.approx(1.0)


def test_thresholds_are_pinned_to_day_41():
    assert SELECTED_THRESHOLD == day41._SELECTED_THRESHOLD
    assert HOLD_THRESHOLD == day41._HOLD_THRESHOLD


def test_non_technical_experienced_reproduces_day_41_exactly():
    new = compute_cross_round_score([rr("ats", 62.0), rr("screening", 75.0), rr("hr_interview", 81.0)], NON_TECH, EXPERIENCED)
    old = day41.compute_unified_score(day41.RoundScores(62.0, 75.0, 81.0), RoleType.NON_TECHNICAL)
    assert new.hiring_fit_percentage == pytest.approx(old.hiring_fit_percentage, abs=0.02)
    assert new.recommendation == old.decision


def test_technical_profile_deliberately_weights_skill_rounds_most():
    w = ROLE_WEIGHT_PROFILES[TECH]
    assert w["technical_interview"] + w["machine_test"] == pytest.approx(0.60)
    assert w["ats"] < w["technical_interview"]


# ---------------------------------------------------------------------------
# Score normalization and input validation
# ---------------------------------------------------------------------------

def test_normalize_score_converts_each_scale():
    assert normalize_score(7.5, "0-10") == 75.0
    assert normalize_score(0.62, "0-1") == 62.0
    assert normalize_score(88.0) == 88.0


def test_normalize_score_rejects_bad_input_instead_of_clamping():
    for bad, scale in [(-1, "0-100"), (101, "0-100"), (11, "0-10"), (1.2, "0-1"), (float("nan"), "0-100"), ("80", "0-100"), (True, "0-100")]:
        with pytest.raises(ValueError):
            normalize_score(bad, scale)
    with pytest.raises(ValueError):
        normalize_score(50, "percent")


def test_round_result_rejects_unknown_round_and_invalid_score():
    with pytest.raises(ValueError):
        RoundResult("culture_fit", 50)
    with pytest.raises(ValueError):
        RoundResult("ats", 140)


def test_round_result_normalizes_non_percent_scales():
    assert RoundResult("hr_interview", 8.0, scale="0-10").normalized == 80.0


def test_duplicate_round_is_rejected():
    with pytest.raises(ValueError):
        compute_cross_round_score([rr("ats", 50), rr("ats", 60)])


# ---------------------------------------------------------------------------
# Weighting
# ---------------------------------------------------------------------------

def test_complete_technical_candidate_exact_weighted_score():
    score = compute_cross_round_score(full(), TECH, EXPERIENCED, "c1")
    assert score.hiring_fit_percentage == 84.0         # .1*80 + .1*70 + .2*60 + .3*90 + .3*100
    assert score.recommendation == "selected"
    assert not score.provisional and score.coverage == pytest.approx(1.0)


def test_fresher_adjustment_halves_ats_weight_and_is_listed():
    _, adjusted, notes, profile = resolve_weights(TECH, FRESHER)
    assert adjusted["ats"] < 0.06 and sum(adjusted.values()) == pytest.approx(1.0)
    assert adjusted["machine_test"] > ROLE_WEIGHT_PROFILES[TECH]["machine_test"]
    assert any("Fresher" in n and "ats" in n for n in notes) and profile == "technical/fresher/v1"


def test_fresher_with_weak_resume_but_strong_skills_is_not_dragged_down_by_ats():
    rounds = full(ats=30, screening=85, hr=85, tech=90, machine=90)
    fresher = compute_cross_round_score(rounds, TECH, FRESHER)
    experienced = compute_cross_round_score(rounds, TECH, EXPERIENCED)
    assert fresher.hiring_fit_percentage > experienced.hiring_fit_percentage


def test_experienced_profile_applies_no_adjustment():
    assert resolve_weights(TECH, EXPERIENCED)[2] == []


def test_non_technical_role_marks_technical_rounds_not_applicable():
    score = compute_cross_round_score([rr("ats", 70), rr("screening", 70), rr("hr_interview", 70)], NON_TECH, EXPERIENCED)
    assert score.not_applicable_rounds == ["technical_interview", "machine_test"]
    assert score.missing_rounds == [] and not score.provisional
    assert contribution(score, "machine_test").status is RoundStatus.NOT_APPLICABLE


def test_score_for_a_round_the_role_does_not_use_is_ignored_and_flagged():
    with_extra = compute_cross_round_score([rr("ats", 70), rr("screening", 70), rr("hr_interview", 70), rr("machine_test", 5)], NON_TECH, EXPERIENCED)
    without = compute_cross_round_score([rr("ats", 70), rr("screening", 70), rr("hr_interview", 70)], NON_TECH, EXPERIENCED)
    assert with_extra.hiring_fit_percentage == without.hiring_fit_percentage
    assert "ROUND_NOT_APPLICABLE_IGNORED" in [f.code for f in with_extra.flags]


def test_custom_weights_are_validated():
    with pytest.raises(ValueError):
        compute_cross_round_score(full(), custom_weights={"ats": 1.0})                         # wrong keys
    with pytest.raises(ValueError):
        compute_cross_round_score(full(), custom_weights={**{r: 0.2 for r in ROUND_NAMES}, "ats": -0.2, "machine_test": 0.6})
    with pytest.raises(ValueError):
        compute_cross_round_score(full(), custom_weights={r: 0.3 for r in ROUND_NAMES})        # sums to 1.5


def test_custom_weights_are_used_as_given_with_no_experience_adjustment():
    weights = {"ats": 0.5, "screening": 0.5, "hr_interview": 0.0, "technical_interview": 0.0, "machine_test": 0.0}
    score = compute_cross_round_score(full(ats=40, screening=80), TECH, FRESHER, custom_weights=weights)
    assert score.hiring_fit_percentage == 60.0 and score.weight_profile_id == "custom"
    assert "hr_interview" in score.not_applicable_rounds


# ---------------------------------------------------------------------------
# Missing rounds, provisional scores
# ---------------------------------------------------------------------------

def test_missing_round_makes_the_score_provisional_and_recommendation_incomplete():
    rounds = [r for r in full() if r.round_name != "machine_test"]
    score = compute_cross_round_score(rounds, TECH, EXPERIENCED)
    assert score.provisional and score.recommendation == "incomplete"
    assert score.missing_rounds == ["machine_test"]
    assert score.coverage == pytest.approx(0.70)
    assert sum(c.effective_weight for c in score.contributions) == pytest.approx(1.0)


def test_missing_weight_is_redistributed_proportionally_not_zeroed():
    rounds = [r for r in full(ats=80, screening=80, hr=80, tech=80) if r.round_name != "machine_test"]
    assert compute_cross_round_score(rounds, TECH, EXPERIENCED).hiring_fit_percentage == 80.0


def test_a_real_zero_is_scored_but_a_missing_round_is_not():
    zero = compute_cross_round_score([rr("ats", 0.0), rr("screening", 80), rr("hr_interview", 80), rr("technical_interview", 80), rr("machine_test", 80)], TECH, EXPERIENCED)
    missing = compute_cross_round_score([rr("ats", None), rr("screening", 80), rr("hr_interview", 80), rr("technical_interview", 80), rr("machine_test", 80)], TECH, EXPERIENCED)
    assert contribution(zero, "ats").status is RoundStatus.SCORED and zero.hiring_fit_percentage < 80
    assert contribution(missing, "ats").status is RoundStatus.MISSING and missing.hiring_fit_percentage == 80.0


def test_no_rounds_scored_gives_no_fit_not_zero():
    score = compute_cross_round_score([], TECH, EXPERIENCED, "c0")
    assert score.hiring_fit_percentage is None and score.recommendation == "incomplete"
    assert "No round has been scored" in score.explain()


def test_incomplete_candidate_is_not_pushed_to_review_just_for_being_incomplete():
    rounds = [rr("ats", 85), rr("screening", 85)]
    assert compute_cross_round_score(rounds, TECH, EXPERIENCED).human_review_required is False


# ---------------------------------------------------------------------------
# Recommendation thresholds and review rules
# ---------------------------------------------------------------------------

def test_recommendation_thresholds():
    def rec(value):
        weights, rounds = only("ats", value)
        return compute_cross_round_score(rounds, custom_weights=weights).recommendation
    assert rec(70.0) == "selected" and rec(69.9) == "hold"
    assert rec(50.0) == "hold" and rec(49.9) == "rejected"


def test_rejected_always_requires_human_review():
    weights, rounds = only("ats", 20.0)
    score = compute_cross_round_score(rounds, custom_weights=weights)
    assert score.recommendation == "rejected" and score.human_review_required
    assert any("always reviewed by a person" in r for r in score.human_review_reasons)


def test_clear_high_scorer_needs_no_review_and_nothing_is_automatic():
    score = compute_cross_round_score(full(90, 90, 90, 90, 90), TECH, EXPERIENCED)
    assert score.recommendation == "selected" and not score.human_review_required
    assert score.automated_decision == "none"


def test_borderline_scores_are_flagged_for_review():
    weights, near_select = only("ats", 72.0)
    near = compute_cross_round_score(near_select, custom_weights=weights)
    _, far = only("ats", 85.0)
    clear = compute_cross_round_score(far, custom_weights=weights)
    assert "BORDERLINE" in [f.code for f in near.flags] and near.human_review_required
    assert "BORDERLINE" not in [f.code for f in clear.flags]
    assert BORDERLINE_MARGIN == 3.0


def test_strong_round_disagreement_is_flagged_even_when_the_average_looks_fine():
    score = compute_cross_round_score(full(ats=95, screening=95, hr=90, tech=45, machine=95), TECH, EXPERIENCED)
    assert "ROUND_DISAGREEMENT" in [f.code for f in score.flags]
    assert score.human_review_required


def test_fresher_thin_resume_is_not_flagged_as_round_disagreement():
    score = compute_cross_round_score(full(ats=30, screening=85, hr=85, tech=90, machine=90), TECH, FRESHER)
    assert "ROUND_DISAGREEMENT" not in [f.code for f in score.flags]
    assert not score.human_review_required


def test_the_same_scores_for_an_experienced_candidate_are_flagged():
    score = compute_cross_round_score(full(ats=30, screening=85, hr=85, tech=90, machine=90), TECH, EXPERIENCED)
    assert "ROUND_DISAGREEMENT" in [f.code for f in score.flags]


def test_fresher_with_a_weak_skill_round_is_still_flagged():
    score = compute_cross_round_score(full(ats=80, screening=85, hr=85, tech=40, machine=90), TECH, FRESHER)
    assert "ROUND_DISAGREEMENT" in [f.code for f in score.flags]


def test_similar_round_scores_raise_no_disagreement_flag():
    score = compute_cross_round_score(full(80, 78, 82, 75, 85), TECH, EXPERIENCED)
    assert "ROUND_DISAGREEMENT" not in [f.code for f in score.flags]


def test_integrity_tag_adds_review_but_never_changes_the_score():
    base = compute_cross_round_score(full(90, 90, 90, 90, 90), TECH, EXPERIENCED)
    flagged = compute_cross_round_score(full(90, 90, 90, 90, 90), TECH, EXPERIENCED, integrity_risk_tag=IntegrityRiskTag.HIGH)
    assert flagged.hiring_fit_percentage == base.hiring_fit_percentage
    assert flagged.human_review_required and flagged.integrity_risk_tag == "high"
    assert "INTEGRITY_REVIEW" in [f.code for f in flagged.flags]


def test_low_or_absent_integrity_tag_adds_no_review():
    for tag in (None, "clear", "low", IntegrityRiskTag.LOW):
        score = compute_cross_round_score(full(90, 90, 90, 90, 90), TECH, EXPERIENCED, integrity_risk_tag=tag)
        assert not score.human_review_required


def test_most_severe_integrity_tag_across_sources_wins():
    rounds = full(90, 90, 90, 90, 90)
    rounds[4] = rr("machine_test", 90, integrity_risk_tag="low")
    score = compute_cross_round_score(rounds, TECH, EXPERIENCED, integrity_risk_tag="medium")
    assert score.integrity_risk_tag == "medium"


def test_review_reasons_from_a_round_are_carried_with_the_round_name():
    rounds = full(90, 90, 90, 90, 90)
    rounds[4] = rr("machine_test", 90, review_reasons=["design write-up scored by keywords"])
    score = compute_cross_round_score(rounds, TECH, EXPERIENCED)
    assert score.human_review_required
    assert any(r.startswith("machine_test:") for r in score.human_review_reasons)


# ---------------------------------------------------------------------------
# Transparency
# ---------------------------------------------------------------------------

def test_contributions_add_up_to_the_hiring_fit():
    score = compute_cross_round_score(full(77, 64, 58, 91, 83), TECH, EXPERIENCED)
    assert sum(c.contribution for c in score.contributions) == pytest.approx(score.hiring_fit_percentage, abs=0.05)
    assert sum(c.effective_weight for c in score.contributions) == pytest.approx(1.0)


def test_every_contribution_shows_base_adjusted_and_effective_weight():
    score = compute_cross_round_score(full(), TECH, FRESHER)
    ats = contribution(score, "ats")
    assert ats.base_weight == 0.10 and ats.adjusted_weight < ats.base_weight


def test_sensitivity_shows_the_score_without_each_round():
    score = compute_cross_round_score(full(80, 80, 80, 80, 100), TECH, EXPERIENCED)
    # without machine_test (weight .3) the rest average to exactly 80
    assert score.sensitivity["machine_test"] == 80.0
    assert score.sensitivity["ats"] > score.hiring_fit_percentage - 1


def test_sensitivity_is_empty_with_a_single_scored_round():
    assert compute_cross_round_score([rr("ats", 70)], TECH, EXPERIENCED).sensitivity == {}


def test_explain_states_formula_inputs_provisional_status_and_recommendation():
    provisional = compute_cross_round_score([r for r in full() if r.round_name != "machine_test"], TECH, FRESHER, "c9")
    text = provisional.explain()
    assert "PROVISIONAL" in text and "machine_test" in text and "INCOMPLETE" in text
    assert "weighted average" in text and "Fresher profile" in text


def test_explain_does_not_name_a_round_the_result_leans_on_when_none_matters():
    even = compute_cross_round_score(full(80, 80, 80, 80, 80), TECH, EXPERIENCED).explain()
    skewed = compute_cross_round_score(full(80, 80, 80, 80, 100), TECH, EXPERIENCED).explain()
    assert "does not lean on any one round" in even and "leans on most" not in even
    assert "Without machine_test" in skewed


def test_summary_text_marks_provisional_scores():
    provisional = compute_cross_round_score([rr("ats", 80)], TECH, EXPERIENCED)
    assert "PROVISIONAL" in provisional.to_summary_text() and "MISSING" in provisional.to_summary_text()


def test_score_object_is_json_serializable_and_complete():
    data = json.loads(json.dumps(compute_cross_round_score(full(), TECH, FRESHER, "c1").to_dict()))
    for key in ("hiring_fit_percentage", "recommendation", "weight_profile_id", "formula", "adjustments", "contributions",
                "sensitivity", "flags", "automated_decision", "human_review_required", "not_implemented", "caveats", "coverage"):
        assert key in data


def test_not_implemented_and_caveats_are_always_present():
    score = compute_cross_round_score(full(), TECH, EXPERIENCED)
    assert {"cohort_percentile_normalization", "calibration_against_hiring_outcomes", "aggregate_fairness_analysis",
            "live_service_wiring"} == set(score.not_implemented)
    assert any("not calibrated" in c for c in score.caveats)


def test_scores_do_not_share_mutable_defaults_and_are_deterministic():
    a = compute_cross_round_score(full(), TECH, EXPERIENCED)
    b = compute_cross_round_score(full(), TECH, EXPERIENCED)
    a.caveats.append("x")
    assert "x" not in b.caveats
    assert a.to_dict()["hiring_fit_percentage"] == b.to_dict()["hiring_fit_percentage"]


# ---------------------------------------------------------------------------
# Adapters -- evidence, not numbers (built on the real earlier classes)
# ---------------------------------------------------------------------------

def component(available):
    return ComponentResult("skills", 70.0, 0.4, 0.4, 28.0, available)


def hr_report(answered, score=70.0):
    return HRInterviewScoreReport(score, WeightConfig(), [], 0.0, 0.0, 0.0, ConsistencyAssessment(0, 0, 0.0, 0.0, []), answered)


def test_ats_adapter_requires_an_available_component():
    assert round_from_ats(ATSScoreResult(0.0, "tech", [component(False)])).score is None
    scored = round_from_ats(ATSScoreResult(72.0, "tech", [component(True)]))
    assert scored.score == 72.0 and scored.round_name == "ats"


def test_screening_adapter_treats_zero_with_no_answers_as_missing():
    assert round_from_screening(ScreeningScoreResult(0.0, [])).score is None
    assert round_from_screening(ScreeningScoreResult(66.0, [object(), object()])).score == 66.0


def test_hr_adapter_treats_zero_with_no_answers_as_missing():
    assert round_from_hr(hr_report(0, 0.0)).score is None
    assert round_from_hr(hr_report(4, 74.0)).score == 74.0


def test_technical_adapter_treats_empty_evaluation_as_missing():
    assert round_from_technical(TechnicalEvaluationReport([], 0.0, {})).score is None
    assert round_from_technical(TechnicalEvaluationReport([object()], 68.5, {})).score == 68.5


def test_every_adapter_handles_none():
    for adapter in (round_from_ats, round_from_screening, round_from_hr, round_from_technical, round_from_machine_test):
        assert adapter(None).score is None


def design_report(tag=None):
    task = MachineTestTask("d1", MachineTestType.SYSTEM_DESIGN, "Design", DifficultyTier.ADVANCED, 1800,
                           design_components={"cache": ["cache"], "database": ["database"]})
    text = "We use a database and a cache because reads dominate, which is a trade-off. " * 5
    return build_machine_test_report([TaskAttempt(task, design_text=text, submitted_at=600)], integrity_risk_tag=tag)


def test_machine_test_adapter_carries_review_reasons_and_tag_but_drops_the_integrity_line():
    report = design_report(IntegrityRiskTag.MEDIUM)
    result = round_from_machine_test(report)
    assert result.score == report.overall_score and result.integrity_risk_tag == "medium"
    assert result.review_reasons and not any("integrity tag" in r.lower() for r in result.review_reasons)


def test_machine_test_integrity_tag_yields_exactly_one_consolidated_review_line():
    score = compute_from_round_outputs(
        ats=ATSScoreResult(85.0, "tech", [component(True)]), screening=ScreeningScoreResult(85.0, [object()]),
        hr=hr_report(3, 85.0), technical=TechnicalEvaluationReport([object()], 85.0, {}), machine_test=design_report(IntegrityRiskTag.HIGH),
        role_type=TECH, experience_level=EXPERIENCED, candidate_id="c7",
    )
    integrity_lines = [r for r in score.human_review_reasons if "integrity tag" in r.lower()]
    assert len(integrity_lines) == 1 and score.integrity_risk_tag == "high"


def test_end_to_end_with_missing_rounds_from_real_result_objects():
    score = compute_from_round_outputs(
        ats=ATSScoreResult(75.0, "tech", [component(True)]), hr=hr_report(0, 0.0), technical=TechnicalEvaluationReport([], 0.0, {}),
        role_type=TECH, experience_level=EXPERIENCED,
    )
    assert score.missing_rounds == ["screening", "hr_interview", "technical_interview", "machine_test"]
    assert score.recommendation == "incomplete"


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

def fit_for(candidate_id, value, experience=EXPERIENCED, drop=()):
    rounds = [r for r in full(value, value, value, value, value) if r.round_name not in drop]
    return compute_cross_round_score(rounds, TECH, experience, candidate_id)


def test_ranking_orders_complete_candidates_by_fit_and_shares_tied_ranks():
    ranking = rank_candidates([fit_for("b", 80), fit_for("a", 90), fit_for("c", 80), fit_for("d", 60)])
    assert [(r.candidate_id, r.rank) for r in ranking.ranked] == [("a", 1), ("b", 2), ("c", 2), ("d", 4)]


def test_incomplete_candidates_are_listed_as_not_comparable_with_a_reason():
    ranking = rank_candidates([fit_for("a", 90), fit_for("p", 99, drop=("machine_test",))])
    assert [r.candidate_id for r in ranking.ranked] == ["a"]
    assert ranking.not_comparable[0]["candidate_id"] == "p" and "machine_test" in ranking.not_comparable[0]["reason"]


def test_ranking_rejects_mixed_role_types():
    non_tech = compute_cross_round_score([rr("ats", 70), rr("screening", 70), rr("hr_interview", 70)], NON_TECH, EXPERIENCED, "n")
    with pytest.raises(ValueError):
        rank_candidates([fit_for("a", 90), non_tech])


def test_fresher_and_experienced_candidates_for_the_same_role_are_ranked_together():
    ranking = rank_candidates([fit_for("exp", 80), fit_for("fresh", 85, FRESHER)])
    assert [r.candidate_id for r in ranking.ranked] == ["fresh", "exp"]
    assert {r.experience_level for r in ranking.ranked} == {"fresher", "experienced"}


def test_ranking_rows_carry_the_integrity_tag_so_a_flagged_candidate_is_visible():
    flagged = compute_cross_round_score(full(90, 90, 90, 90, 90), TECH, EXPERIENCED, "f", integrity_risk_tag="high")
    ranking = rank_candidates([flagged, fit_for("a", 80)])
    top = ranking.ranked[0]
    assert top.candidate_id == "f" and top.integrity_risk_tag == "high" and top.human_review_required


def test_ranking_serializes_to_json():
    json.dumps(rank_candidates([fit_for("a", 90)]).to_dict())
