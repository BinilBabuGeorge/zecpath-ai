import json
from pathlib import Path

import pytest

from parsers import cross_round_aggregation_engine as day51
from parsers import ranking_engine
from parsers.ats_scoring_engine import ATSScoreResult, ComponentResult, score_candidate
from parsers.consistency_audit import (
    PropertyResult,
    _check,
    check_threshold_relationships,
    run_property_audit,
    threshold_registry,
)
from parsers.cross_round_aggregation_engine import RoundResult, compute_cross_round_score, compute_from_round_outputs, round_from_ats
from parsers.hr_interview_question_bank import ExperienceLevel, RoleType
from parsers.scoring_calibration import (
    ATS_SCALES,
    COMMON_HOLD,
    COMMON_SELECTED,
    FLOOR_CAP,
    align_ats_score,
    describe_alignment,
)
from parsers.semantic_matcher import SemanticMatcher

TECH, EXPERIENCED, FRESHER = RoleType.TECHNICAL, ExperienceLevel.EXPERIENCED, ExperienceLevel.FRESHER
TECH_CUTS = ranking_engine.CATEGORY_THRESHOLDS["tech"]
BIZ_CUTS = ranking_engine.CATEGORY_THRESHOLDS["business"]


# ---------------------------------------------------------------------------
# The alignment function
# ---------------------------------------------------------------------------

def test_anchors_land_exactly_on_the_aggregates_bands():
    for category, cuts in (("tech", TECH_CUTS), ("business", BIZ_CUTS)):
        assert align_ats_score(0.0, category) == 0.0
        assert align_ats_score(cuts["review"], category) == COMMON_HOLD
        assert align_ats_score(cuts["shortlist"], category) == COMMON_SELECTED
        assert align_ats_score(100.0, category) == 100.0


def test_common_bands_are_pinned_to_day_51():
    assert COMMON_HOLD == day51.HOLD_THRESHOLD and COMMON_SELECTED == day51.SELECTED_THRESHOLD


def test_alignment_never_reorders_candidates():
    for category in (None, "tech", "business", "creative"):
        previous = -1.0
        for raw in [x / 4 for x in range(0, 401)]:
            aligned = align_ats_score(raw, category)
            assert aligned >= previous
            previous = aligned


def test_alignment_keeps_every_ats_zone_in_the_matching_aggregate_band():
    for category, cuts in (("tech", TECH_CUTS), ("business", BIZ_CUTS)):
        for raw in [x / 2 for x in range(0, 201)]:
            aligned = align_ats_score(raw, category)
            if raw >= cuts["shortlist"]:
                assert aligned >= COMMON_SELECTED
            elif raw >= cuts["review"]:
                assert COMMON_HOLD <= aligned < COMMON_SELECTED + 1e-9
            else:
                assert aligned < COMMON_HOLD


def test_alignment_stays_within_zero_and_one_hundred():
    assert all(0.0 <= align_ats_score(x, "tech") <= 100.0 for x in range(0, 101))


def test_an_unknown_or_missing_category_falls_back_to_the_default_cutoffs():
    default = ranking_engine.DEFAULT_THRESHOLDS
    assert align_ats_score(default["shortlist"], None) == COMMON_SELECTED
    assert align_ats_score(default["shortlist"], "no-such-category") == COMMON_SELECTED


def test_a_typical_clean_tech_match_moves_from_mediocre_to_selectable():
    assert align_ats_score(50.2, "tech") == pytest.approx(71.8, abs=0.05)         # raw 50.2 read as "hold" on the old scale


def test_the_skill_floor_caps_a_candidate_below_the_hold_threshold():
    # The ATS rejects a skill match under its floor regardless of overall score; so must the aligned scale.
    assert align_ats_score(27.7, "business") >= COMMON_HOLD                                    # by score alone: REVIEW-level
    assert align_ats_score(27.7, "business", skill_match_score=0.0) == FLOOR_CAP < COMMON_HOLD
    assert align_ats_score(27.7, "business", skill_match_score=ranking_engine.SKILL_RELEVANCE_FLOOR) == align_ats_score(27.7, "business")


def test_the_floor_never_raises_a_score():
    assert align_ats_score(10.0, "tech", skill_match_score=0.0) == min(align_ats_score(10.0, "tech"), FLOOR_CAP)


def test_alignment_rejects_bad_input():
    for bad in (-1, 100.5, float("nan"), True, "50"):
        with pytest.raises(ValueError):
            align_ats_score(bad, "tech")


def test_describe_alignment_is_one_plain_sentence_and_mentions_the_floor_when_it_applies():
    text = describe_alignment(50.2, "tech")
    assert "aligned to 71.8" in text and "shortlist cutoff 47" in text and "relevance floor" not in text
    assert "relevance floor" in describe_alignment(27.7, "business", 0.0)


# ---------------------------------------------------------------------------
# The Day 51 hook: opt-in, default unchanged
# ---------------------------------------------------------------------------

def make_ats(overall=50.2, skill=80.0, category="tech", available=True):
    return ATSScoreResult(overall, category, [ComponentResult("skill_match", skill, 0.35, 0.35, skill * 0.35, available, {})])


def test_the_default_scale_is_raw_so_earlier_days_results_do_not_change():
    assert round_from_ats(make_ats(72.0)).score == 72.0
    assert round_from_ats(make_ats(72.0), "raw").score == 72.0 and "aligned" not in round_from_ats(make_ats(72.0)).note


def test_zone_aligned_scale_changes_the_score_and_explains_itself():
    r = round_from_ats(make_ats(50.2), "zone_aligned")
    assert r.score == pytest.approx(71.8, abs=0.05) and "aligned to 71.8" in r.note


def test_zone_aligned_honours_the_skill_floor_from_the_result_components():
    r = round_from_ats(make_ats(27.7, skill=0.0, category="business"), "zone_aligned")
    assert r.score == FLOOR_CAP and "relevance floor" in r.note


def test_an_unavailable_ats_result_is_still_missing_on_either_scale():
    for scale in ATS_SCALES:
        assert round_from_ats(make_ats(available=False), scale).score is None
        assert round_from_ats(None, scale).score is None


def test_an_unknown_scale_is_rejected():
    with pytest.raises(ValueError):
        round_from_ats(make_ats(), "percentile")
    with pytest.raises(ValueError):
        compute_from_round_outputs(ats=make_ats(), ats_scale="percentile", role_type=TECH, experience_level=EXPERIENCED)


def other_rounds_at(value):
    return [RoundResult(n, value) for n in ("screening", "hr_interview", "technical_interview", "machine_test")]


def test_aligned_scale_stops_a_shortlisted_ats_candidate_from_dragging_the_aggregate():
    raw = compute_cross_round_score([round_from_ats(make_ats(50.2))] + other_rounds_at(80.0), TECH, EXPERIENCED, "c")
    aligned = compute_cross_round_score([round_from_ats(make_ats(50.2), "zone_aligned")] + other_rounds_at(80.0), TECH, EXPERIENCED, "c")
    assert aligned.hiring_fit_percentage > raw.hiring_fit_percentage
    assert abs(aligned.hiring_fit_percentage - 80.0) < abs(raw.hiring_fit_percentage - 80.0)


def test_aligned_scale_removes_a_spurious_round_disagreement_flag():
    base = [RoundResult(n, 85.0) for n in ("screening", "hr_interview", "technical_interview", "machine_test")]
    raw = compute_cross_round_score([round_from_ats(make_ats(48.0))] + base, TECH, EXPERIENCED, "c")
    aligned = compute_cross_round_score([round_from_ats(make_ats(48.0), "zone_aligned")] + base, TECH, EXPERIENCED, "c")
    assert "ROUND_DISAGREEMENT" in [f.code for f in raw.flags]
    assert "ROUND_DISAGREEMENT" not in [f.code for f in aligned.flags]


def test_compute_from_round_outputs_passes_the_scale_through_end_to_end():
    raw = compute_from_round_outputs(ats=make_ats(50.2), role_type=TECH, experience_level=EXPERIENCED, candidate_id="c")
    aligned = compute_from_round_outputs(ats=make_ats(50.2), ats_scale="zone_aligned", role_type=TECH, experience_level=EXPERIENCED, candidate_id="c")
    assert next(c for c in raw.contributions if c.round_name == "ats").score == pytest.approx(50.2)
    assert next(c for c in aligned.contributions if c.round_name == "ats").score == pytest.approx(71.8, abs=0.05)


# ---------------------------------------------------------------------------
# On the project's real human-labelled ATS pairs
# ---------------------------------------------------------------------------

RESUMES, JDS = Path("data/samples/resumes"), Path("data/samples/jds")
GROUND_TRUTH = Path("data/ground_truth_ats/day20_manual_review_revised.json")


def band(score):
    return "SHORTLIST" if score >= 70 else "REVIEW" if score >= 50 else "REJECT"


@pytest.fixture(scope="module")
def labelled_scores():
    corpus = [f.read_text() for f in sorted(RESUMES.glob("*.txt")) + sorted(JDS.glob("*.txt"))]
    matcher = SemanticMatcher(corpus)
    rows = []
    for p in json.load(open(GROUND_TRUTH, encoding="utf-8"))["pairs"]:
        r = score_candidate((RESUMES / f"{p['resume_id']}.txt").read_text(), (JDS / f"{p['jd_id']}.txt").read_text(), matcher)
        skill = next((c.score for c in r.components if c.name == "skill_match" and c.available), None)
        rows.append({"raw": r.overall_score, "category": r.role_category, "skill": skill, "human": p["expected_zone"]})
    return rows


def test_on_the_labelled_pairs_the_raw_ats_score_disagrees_with_humans_at_the_aggregates_bands(labelled_scores):
    agree = sum(band(r["raw"]) == r["human"] for r in labelled_scores)
    shortlisted = [r["raw"] for r in labelled_scores if r["human"] == "SHORTLIST"]
    assert (agree, len(labelled_scores)) == (6, 12)
    assert not any(s >= COMMON_SELECTED for s in shortlisted) and len(shortlisted) == 4        # none of the 4 human-shortlisted pairs reaches 70


def test_on_the_labelled_pairs_the_aligned_score_agrees_with_the_atss_own_zone_decisions(labelled_scores):
    agree = sum(band(align_ats_score(r["raw"], r["category"], r["skill"])) == r["human"] for r in labelled_scores)
    ats_own = sum(
        ranking_engine.classify_zone(r["raw"], role_category=r["category"], skill_match_score=r["skill"]).upper() == r["human"] for r in labelled_scores)
    assert agree == ats_own == 10                       # the alignment reproduces the ATS's own zones: it changes the scale, not the decisions


def test_every_human_shortlisted_pair_is_selectable_after_alignment(labelled_scores):
    for r in labelled_scores:
        if r["human"] == "SHORTLIST":
            assert align_ats_score(r["raw"], r["category"], r["skill"]) >= COMMON_SELECTED


# ---------------------------------------------------------------------------
# The consistency audit
# ---------------------------------------------------------------------------

def test_every_property_holds_and_checks_a_meaningful_number_of_cases():
    results = run_property_audit()
    assert len(results) == 8
    for r in results:
        assert r.passed, f"{r.name}: {r.counterexample}"
        assert r.cases_checked >= 20
    assert sum(r.cases_checked for r in results) > 10_000


def test_the_audit_names_the_properties_it_checks():
    assert {r.name for r in run_property_audit()} == {
        "monotone_in_each_round", "equal_scores_give_that_score", "round_order_does_not_matter", "scale_conversion_is_exact",
        "fit_between_lowest_and_highest_round", "day51_and_day52_bands_agree", "selected_never_carries_a_review_reason",
        "ats_alignment_is_monotone_bounded_zone_preserving"}


def test_a_failing_property_returns_a_concrete_counterexample():
    def cases():
        yield None
        yield None
        yield {"input": 7, "why": "demo"}
        yield None
    r = _check("demo", "a deliberately failing property", cases)
    assert not r.passed and r.cases_checked == 3 and r.counterexample == {"input": 7, "why": "demo"}


def test_a_passing_property_has_no_counterexample():
    r = _check("demo", "passes", lambda: iter([None, None]))
    assert r.passed and r.counterexample is None and r.to_dict()["cases_checked"] == 2
    assert isinstance(r, PropertyResult)


def test_the_threshold_registry_lists_every_decision_cutoff_with_its_location():
    reg = {t.name: t for t in threshold_registry()}
    for name in ("selected_threshold", "hold_threshold", "strength_min", "weakness_max", "ats_shortlist_tech", "ats_skill_floor", "min_reject_confidence"):
        assert name in reg and reg[name].location and reg[name].meaning
    assert reg["selected_threshold"].value == 70.0 and reg["ats_shortlist_tech"].value == 47.0


def test_consistent_relationships_hold():
    holds = {r.statement for r in check_threshold_relationships() if r.holds}
    assert "hold threshold is below the selection threshold" in holds
    assert "a reported 'strength' scores at least as high as a selection" in holds
    assert "every critical-round floor sits below the hold threshold" in holds
    assert "Day 52 policy defaults equal Day 51's thresholds" in holds


def test_the_two_known_findings_are_reported_as_findings_with_a_recommendation():
    """Pins the audit's two real findings. If the reject-confidence floor is raised (as recommended) the second one
    flips to 'holds' and this test should be updated deliberately."""
    broken = {r.statement: r for r in check_threshold_relationships() if not r.holds}
    assert len(broken) == 2
    ats = next(v for k, v in broken.items() if "SAME scale" in k)
    conf = next(v for k, v in broken.items() if "at least as much confidence" in k)
    assert "zone_aligned" in ats.finding and "FINDING" in ats.finding
    assert "min_reject_confidence=60" in conf.finding and "FINDING" in conf.finding


def test_relationship_results_serialise():
    json.dumps([r.to_dict() for r in check_threshold_relationships()])
    json.dumps([t.to_dict() for t in threshold_registry()])
