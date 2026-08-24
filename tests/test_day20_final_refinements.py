"""
Day 20 tests: the two final refinements to ranking_engine.classify_zone()
— category-specific thresholds and the skill-relevance floor — plus
backward-compatibility guarantees for existing callers.
"""

import pytest

from parsers.ranking_engine import (
    classify_zone,
    CATEGORY_THRESHOLDS,
    DEFAULT_THRESHOLDS,
    SKILL_RELEVANCE_FLOOR,
)


# ---------------------------------------------------------------------------
# Backward compatibility: existing bare calls must behave exactly as before
# ---------------------------------------------------------------------------

def test_bare_call_still_uses_default_thresholds():
    assert classify_zone(55.0) == "shortlist"
    assert classify_zone(54.9) == "review"
    assert classify_zone(24.9) == "reject"


def test_explicit_thresholds_still_override_everything():
    custom = {"shortlist": 80.0, "review": 50.0}
    # Even with a role_category given, an explicit thresholds arg wins.
    assert classify_zone(70.0, custom, role_category="tech") == "review"
    assert classify_zone(85.0, custom, role_category="tech") == "shortlist"


def test_no_skill_match_score_means_no_floor_applied():
    # Omitting skill_match_score entirely must not trigger the floor --
    # existing callers that don't pass it get the old behavior.
    assert classify_zone(30.0, role_category="tech") == "review"


# ---------------------------------------------------------------------------
# New behavior: category-specific thresholds
# ---------------------------------------------------------------------------

def test_tech_category_has_lower_shortlist_threshold_than_default():
    assert CATEGORY_THRESHOLDS["tech"]["shortlist"] < DEFAULT_THRESHOLDS["shortlist"]


def test_business_category_threshold_matches_default():
    assert CATEGORY_THRESHOLDS["business"]["shortlist"] == DEFAULT_THRESHOLDS["shortlist"]


def test_tech_role_category_shortlists_at_lower_score_than_default():
    # A score that would only be REVIEW under the global default should
    # SHORTLIST under the tech-specific threshold -- this is the exact
    # fix for Day 17's under-shortlisting finding.
    score = 49.5  # real score: resume_16_senior_backend_lead vs jd_01
    assert classify_zone(score) == "review"  # bare call: old global behavior
    assert classify_zone(score, role_category="tech") == "shortlist"  # Day 20 fix


def test_unknown_role_category_falls_back_to_default():
    assert classify_zone(55.0, role_category="nonexistent-category") == "shortlist"
    assert classify_zone(50.0, role_category="creative") == "review"  # not yet calibrated, uses default


# ---------------------------------------------------------------------------
# New behavior: skill-relevance floor
# ---------------------------------------------------------------------------

def test_skill_match_below_floor_forces_reject_regardless_of_score():
    # A high overall score should NOT save a candidate with near-zero
    # skill relevance -- this is the exact fix for Day 17's "irrelevant
    # candidate landing in REVIEW" finding.
    assert classify_zone(70.0, skill_match_score=0.0) == "reject"
    assert classify_zone(70.0, skill_match_score=5.0) == "reject"


def test_skill_match_at_or_above_floor_does_not_force_reject():
    assert classify_zone(70.0, skill_match_score=SKILL_RELEVANCE_FLOOR) == "shortlist"
    assert classify_zone(30.0, skill_match_score=SKILL_RELEVANCE_FLOOR) == "review"


def test_skill_floor_does_not_catch_sparse_but_relevant_skills():
    # resume_13_fresher_no_experience's real skill_match score (20.0) --
    # sparse but genuinely relevant (matched React.js, a core skill) --
    # must NOT be caught by the floor. This is the documented boundary:
    # the floor catches zero-relevance cases, not just low-count ones.
    assert classify_zone(29.5, skill_match_score=20.0) == "review"


def test_skill_floor_known_gap_does_not_catch_peripheral_only_matches():
    # Documented, known, UNRESOLVED limitation: a candidate matching only
    # peripheral/tooling skills (not the role's core stack) still sits
    # at skill_match=20.0, same as a genuinely-relevant sparse match --
    # this test documents that the floor does NOT distinguish them
    # (see resume_11_python_backend_dev in day20_final_review.md).
    # This is intentionally asserting the CURRENT (imperfect) behavior,
    # not the ideal one -- a future day's work, not silently claimed as done.
    assert classify_zone(34.9, skill_match_score=20.0) == "review"  # NOT rejected, despite being a real mismatch


# ---------------------------------------------------------------------------
# Combined: category threshold AND skill floor together
# ---------------------------------------------------------------------------

def test_skill_floor_takes_priority_over_category_shortlist():
    # Even a score that would clear the tech shortlist threshold must
    # still be rejected if skill relevance is below the floor.
    assert classify_zone(60.0, role_category="tech", skill_match_score=0.0) == "reject"


def test_category_threshold_and_skill_floor_together_reproduce_day20_result():
    # Spot-check against the real, measured Day 20 re-evaluation result
    # for two of the fixed cases.
    assert classify_zone(50.3, role_category="tech", skill_match_score=80.0) == "shortlist"  # resume_01 vs jd_01
    assert classify_zone(27.6, role_category="business", skill_match_score=0.0) == "reject"  # resume_05 vs jd_02
