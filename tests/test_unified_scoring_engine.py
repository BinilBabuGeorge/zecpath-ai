from parsers.hr_interview_question_bank import RoleType
from parsers.unified_scoring_engine import (
    RoundWeights, RoundScores, ROLE_WEIGHT_PROFILES, compute_unified_score, _redistribute_weights,
)


# ---------------------------------------------------------------------------
# RoundWeights validation
# ---------------------------------------------------------------------------

def test_role_weight_profiles_sum_to_one():
    for role, weights in ROLE_WEIGHT_PROFILES.items():
        weights.validate()  # should not raise


def test_invalid_weights_raise():
    raised = False
    try:
        RoundWeights(ats=0.5, screening=0.5, hr_interview=0.5).validate()
    except ValueError:
        raised = True
    assert raised


def test_negative_weight_raises():
    raised = False
    try:
        RoundWeights(ats=-0.1, screening=0.6, hr_interview=0.5).validate()
    except ValueError:
        raised = True
    assert raised


# ---------------------------------------------------------------------------
# Weight redistribution for missing rounds
# ---------------------------------------------------------------------------

def test_redistribution_all_available_matches_base_weights():
    weights = RoundWeights(ats=0.4, screening=0.15, hr_interview=0.45)
    availability = {"ats": True, "screening": True, "hr_interview": True}
    result = _redistribute_weights(weights, availability)
    assert abs(result["ats"] - 0.4) < 0.001
    assert abs(result["hr_interview"] - 0.45) < 0.001


def test_redistribution_one_missing_sums_to_one():
    weights = RoundWeights(ats=0.4, screening=0.15, hr_interview=0.45)
    availability = {"ats": True, "screening": False, "hr_interview": True}
    result = _redistribute_weights(weights, availability)
    assert "screening" not in result
    assert abs(sum(result.values()) - 1.0) < 0.001


def test_redistribution_preserves_relative_proportion():
    weights = RoundWeights(ats=0.4, screening=0.15, hr_interview=0.45)
    availability = {"ats": True, "screening": False, "hr_interview": True}
    result = _redistribute_weights(weights, availability)
    # ats:hr_interview should stay at the same 0.4:0.45 ratio.
    assert abs(result["ats"] / result["hr_interview"] - (0.4 / 0.45)) < 0.001


def test_redistribution_all_missing_returns_zeros():
    weights = RoundWeights(ats=0.4, screening=0.15, hr_interview=0.45)
    availability = {"ats": False, "screening": False, "hr_interview": False}
    result = _redistribute_weights(weights, availability)
    assert all(v == 0.0 for v in result.values())


# ---------------------------------------------------------------------------
# compute_unified_score -- full candidate
# ---------------------------------------------------------------------------

def test_full_candidate_all_rounds_included():
    scores = RoundScores(ats_score=82.0, screening_score=74.0, hr_interview_score=88.0)
    result = compute_unified_score(scores, role_type=RoleType.TECHNICAL, candidate_id="C001")
    assert result.missing_rounds == []
    assert all(c.included for c in result.contributions)
    assert 0.0 <= result.hiring_fit_percentage <= 100.0


def test_high_scores_produce_selected_decision():
    scores = RoundScores(ats_score=90.0, screening_score=85.0, hr_interview_score=92.0)
    result = compute_unified_score(scores, role_type=RoleType.TECHNICAL)
    assert result.decision == "selected"
    assert result.hiring_fit_percentage >= 70.0


def test_low_scores_produce_rejected_decision():
    scores = RoundScores(ats_score=20.0, screening_score=15.0, hr_interview_score=25.0)
    result = compute_unified_score(scores, role_type=RoleType.TECHNICAL)
    assert result.decision == "rejected"
    assert result.hiring_fit_percentage < 50.0


def test_mid_scores_produce_hold_decision():
    scores = RoundScores(ats_score=55.0, screening_score=55.0, hr_interview_score=55.0)
    result = compute_unified_score(scores, role_type=RoleType.TECHNICAL)
    assert result.decision == "hold"


# ---------------------------------------------------------------------------
# Missing rounds
# ---------------------------------------------------------------------------

def test_missing_round_is_flagged_and_excluded():
    scores = RoundScores(ats_score=82.0, screening_score=None, hr_interview_score=88.0)
    result = compute_unified_score(scores, role_type=RoleType.TECHNICAL)
    assert result.missing_rounds == ["screening"]
    screening_contribution = next(c for c in result.contributions if c.round_name == "screening")
    assert screening_contribution.included is False
    assert screening_contribution.contribution == 0.0


def test_missing_round_weight_fully_redistributed_to_others():
    scores = RoundScores(ats_score=100.0, screening_score=None, hr_interview_score=100.0)
    result = compute_unified_score(scores, role_type=RoleType.TECHNICAL)
    # With both remaining rounds at 100 and weight fully redistributed between them, the total should be 100.
    assert result.hiring_fit_percentage == 100.0


# ---------------------------------------------------------------------------
# Role-based weighting
# ---------------------------------------------------------------------------

def test_different_roles_use_different_default_weights():
    tech_weights = ROLE_WEIGHT_PROFILES[RoleType.TECHNICAL]
    non_tech_weights = ROLE_WEIGHT_PROFILES[RoleType.NON_TECHNICAL]
    assert tech_weights.as_dict() != non_tech_weights.as_dict()


def test_role_type_changes_resulting_score():
    scores = RoundScores(ats_score=90.0, screening_score=50.0, hr_interview_score=60.0)
    tech_result = compute_unified_score(scores, role_type=RoleType.TECHNICAL)
    non_tech_result = compute_unified_score(scores, role_type=RoleType.NON_TECHNICAL)
    assert tech_result.hiring_fit_percentage != non_tech_result.hiring_fit_percentage


def test_custom_weights_override_role_default():
    scores = RoundScores(ats_score=80.0, screening_score=80.0, hr_interview_score=80.0)
    custom = RoundWeights(ats=1.0, screening=0.0, hr_interview=0.0)
    result = compute_unified_score(scores, role_type=RoleType.TECHNICAL, weights=custom)
    assert result.weights_used.ats == 1.0


# ---------------------------------------------------------------------------
# Output format
# ---------------------------------------------------------------------------

def test_to_dict_round_trips_key_fields():
    scores = RoundScores(ats_score=82.0, screening_score=74.0, hr_interview_score=88.0)
    result = compute_unified_score(scores, role_type=RoleType.TECHNICAL, candidate_id="C001")
    d = result.to_dict()
    assert d["candidate_id"] == "C001"
    assert d["hiring_fit_percentage"] == result.hiring_fit_percentage
    assert d["decision"] == result.decision
    assert len(d["contributions"]) == 3


def test_to_summary_text_contains_key_fields():
    scores = RoundScores(ats_score=82.0, screening_score=74.0, hr_interview_score=88.0)
    result = compute_unified_score(scores, role_type=RoleType.TECHNICAL, candidate_id="C001")
    text = result.to_summary_text()
    assert "Hiring-Fit Score" in text
    assert "C001" in text
    assert "ats" in text and "screening" in text and "hr_interview" in text
