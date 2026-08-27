from pathlib import Path

import pytest

from parsers.semantic_matcher import SemanticMatcher
from parsers.ats_scoring_engine import score_candidate
from parsers.ranking_engine import classify_zone
from parsers.eligibility_engine import (
    EligibilityRules,
    EligibilityResult,
    evaluate_eligibility,
    extract_candidate_location,
)

RESUME_DIR = Path("data/samples/resumes")
JD_DIR = Path("data/samples/jds")


@pytest.fixture(scope="module")
def matcher():
    resume_files = sorted(RESUME_DIR.glob("*.txt"))
    jd_files = sorted(JD_DIR.glob("*.txt"))
    corpus = [f.read_text() for f in resume_files + jd_files]
    return SemanticMatcher(corpus)


@pytest.fixture(scope="module")
def jd_text():
    return (JD_DIR / "jd_01_mern_developer.txt").read_text()


def score(resume_id, matcher, jd_text):
    text = (RESUME_DIR / f"{resume_id}.txt").read_text()
    return text, score_candidate(text, jd_text, matcher)


# ---------------------------------------------------------------------------
# Rule configuration format: round-trip serialization
# ---------------------------------------------------------------------------

def test_rules_round_trip_through_dict():
    rules = EligibilityRules(
        job_id="jd_01", min_ats_score=50.0, mandatory_skills=["React.js", "MongoDB"],
        min_experience_years=2.0, max_experience_years=6.0,
        allowed_locations=["Bengaluru"], require_availability=True,
    )
    restored = EligibilityRules.from_dict(rules.to_dict())
    assert restored == rules


def test_rules_from_dict_handles_missing_optional_keys():
    minimal = EligibilityRules.from_dict({"job_id": "jd_02"})
    assert minimal.job_id == "jd_02"
    assert minimal.mandatory_skills == []
    assert minimal.min_ats_score is None


def test_rules_defaults_have_no_constraints():
    rules = EligibilityRules(job_id="jd_01")
    assert rules.mandatory_skills == []
    assert rules.min_experience_years is None
    assert rules.allowed_locations is None
    assert rules.require_availability is False


# ---------------------------------------------------------------------------
# Default behavior: no extra rules -> pure score-based, reuses Day 20 zones
# ---------------------------------------------------------------------------

def test_no_rules_configured_matches_ranking_engine_zone_exactly(matcher, jd_text):
    text, result = score("resume_01_mern_developer", matcher, jd_text)
    rules = EligibilityRules(job_id="jd_01_mern_developer")
    elig = evaluate_eligibility("resume_01_mern_developer", text, result, rules)

    skill_c = next(c for c in result.components if c.name == "skill_match")
    expected_zone = classify_zone(result.overall_score, role_category=result.role_category, skill_match_score=skill_c.score)
    assert elig.score_zone == expected_zone


def test_no_rules_tag_mapping_is_consistent(matcher, jd_text):
    tag_map = {"shortlist": "ELIGIBLE", "review": "REVIEW", "reject": "REJECTED"}
    for cid in ["resume_01_mern_developer", "resume_11_python_backend_dev", "resume_13_fresher_no_experience"]:
        text, result = score(cid, matcher, jd_text)
        rules = EligibilityRules(job_id="jd_01_mern_developer")
        elig = evaluate_eligibility(cid, text, result, rules)
        assert elig.tag == tag_map[elig.score_zone]


# ---------------------------------------------------------------------------
# Hard gate: mandatory skills
# ---------------------------------------------------------------------------

def test_missing_mandatory_skill_rejects_regardless_of_score(matcher, jd_text):
    text, result = score("resume_01_mern_developer", matcher, jd_text)
    # resume_01 scores well (ELIGIBLE with no rules), but require a skill it lacks
    rules = EligibilityRules(job_id="jd_01_mern_developer", mandatory_skills=["Kubernetes"])
    elig = evaluate_eligibility("resume_01_mern_developer", text, result, rules)
    assert elig.tag == "REJECTED"
    assert "Kubernetes" in elig.reasons[0]
    assert elig.gates_applied["mandatory_skills"] is False


def test_present_mandatory_skill_passes_gate(matcher, jd_text):
    text, result = score("resume_01_mern_developer", matcher, jd_text)
    rules = EligibilityRules(job_id="jd_01_mern_developer", mandatory_skills=["React.js"])
    elig = evaluate_eligibility("resume_01_mern_developer", text, result, rules)
    assert elig.gates_applied["mandatory_skills"] is True
    assert elig.tag != "REJECTED"


def test_mandatory_skill_match_is_case_insensitive(matcher, jd_text):
    text, result = score("resume_01_mern_developer", matcher, jd_text)
    rules = EligibilityRules(job_id="jd_01_mern_developer", mandatory_skills=["react.js"])
    elig = evaluate_eligibility("resume_01_mern_developer", text, result, rules)
    assert elig.gates_applied["mandatory_skills"] is True


def test_no_mandatory_skills_configured_gate_not_in_result(matcher, jd_text):
    text, result = score("resume_01_mern_developer", matcher, jd_text)
    rules = EligibilityRules(job_id="jd_01_mern_developer")
    elig = evaluate_eligibility("resume_01_mern_developer", text, result, rules)
    assert "mandatory_skills" not in elig.gates_applied


# ---------------------------------------------------------------------------
# Hard gate: experience range
# ---------------------------------------------------------------------------

def test_below_minimum_experience_rejects(matcher, jd_text):
    text, result = score("resume_13_fresher_no_experience", matcher, jd_text)
    rules = EligibilityRules(job_id="jd_01_mern_developer", min_experience_years=2.0)
    elig = evaluate_eligibility("resume_13_fresher_no_experience", text, result, rules)
    assert elig.tag == "REJECTED"
    assert "below minimum" in elig.reasons[0]


def test_above_maximum_experience_rejects_when_cap_explicitly_set(matcher, jd_text):
    text, result = score("resume_16_senior_backend_lead", matcher, jd_text)
    rules = EligibilityRules(job_id="jd_01_mern_developer", max_experience_years=3.0)
    elig = evaluate_eligibility("resume_16_senior_backend_lead", text, result, rules)
    assert elig.tag == "REJECTED"
    assert "above maximum" in elig.reasons[0]


def test_overqualification_never_rejects_when_no_max_configured(matcher, jd_text):
    # Day 20's core lesson: don't penalize seniority. Without an explicit
    # max_experience_years, a senior candidate must never be rejected on
    # experience grounds alone.
    text, result = score("resume_16_senior_backend_lead", matcher, jd_text)
    rules = EligibilityRules(job_id="jd_01_mern_developer", min_experience_years=1.0)
    elig = evaluate_eligibility("resume_16_senior_backend_lead", text, result, rules)
    assert elig.gates_applied["experience_range"] is True


def test_within_range_experience_passes(matcher, jd_text):
    text, result = score("resume_01_mern_developer", matcher, jd_text)
    rules = EligibilityRules(job_id="jd_01_mern_developer", min_experience_years=1.0, max_experience_years=10.0)
    elig = evaluate_eligibility("resume_01_mern_developer", text, result, rules)
    assert elig.gates_applied["experience_range"] is True


# ---------------------------------------------------------------------------
# Soft gate: location (downgrades, never hard-rejects)
# ---------------------------------------------------------------------------

def test_location_mismatch_downgrades_eligible_to_review_not_rejected(matcher, jd_text):
    text, result = score("resume_01_mern_developer", matcher, jd_text)
    rules = EligibilityRules(job_id="jd_01_mern_developer", allowed_locations=["Mumbai"])
    elig = evaluate_eligibility("resume_01_mern_developer", text, result, rules)
    assert elig.tag == "REVIEW"
    assert elig.tag != "REJECTED"


def test_location_match_passes_cleanly(matcher, jd_text):
    text, result = score("resume_01_mern_developer", matcher, jd_text)
    # resume_01's actual location is Bengaluru
    rules = EligibilityRules(job_id="jd_01_mern_developer", allowed_locations=["Bengaluru"])
    elig = evaluate_eligibility("resume_01_mern_developer", text, result, rules)
    assert elig.gates_applied["location"] is True


def test_extract_candidate_location_finds_real_field():
    text = (RESUME_DIR / "resume_01_mern_developer.txt").read_text()
    assert extract_candidate_location(text) == "Bengaluru, India"


def test_extract_candidate_location_returns_none_when_absent():
    assert extract_candidate_location("Name: Someone\nNo location field here") is None


# ---------------------------------------------------------------------------
# Documented non-gate: availability
# ---------------------------------------------------------------------------

def test_require_availability_always_adds_a_note_never_changes_tag(matcher, jd_text):
    text, result = score("resume_01_mern_developer", matcher, jd_text)
    rules_off = EligibilityRules(job_id="jd_01_mern_developer", require_availability=False)
    rules_on = EligibilityRules(job_id="jd_01_mern_developer", require_availability=True)
    elig_off = evaluate_eligibility("resume_01_mern_developer", text, result, rules_off)
    elig_on = evaluate_eligibility("resume_01_mern_developer", text, result, rules_on)
    assert elig_off.tag == elig_on.tag  # never used as an active gate
    assert any("NOT evaluated" in r for r in elig_on.reasons)


# ---------------------------------------------------------------------------
# Custom min_ats_score override
# ---------------------------------------------------------------------------

def test_custom_min_ats_score_overrides_default_zone(matcher, jd_text):
    text, result = score("resume_11_python_backend_dev", matcher, jd_text)
    # resume_11 scores 34.9 -- REVIEW under Day 20 defaults. A very low
    # custom cutoff should push it to ELIGIBLE instead.
    rules = EligibilityRules(job_id="jd_01_mern_developer", min_ats_score=30.0)
    elig = evaluate_eligibility("resume_11_python_backend_dev", text, result, rules)
    assert elig.tag == "ELIGIBLE"
    assert any("Custom min_ats_score" in r for r in elig.reasons)


def test_custom_min_ats_score_can_reject_a_default_shortlist(matcher, jd_text):
    text, result = score("resume_01_mern_developer", matcher, jd_text)
    rules = EligibilityRules(job_id="jd_01_mern_developer", min_ats_score=99.0)
    elig = evaluate_eligibility("resume_01_mern_developer", text, result, rules)
    assert elig.tag == "REJECTED"


# ---------------------------------------------------------------------------
# Combined: hard gates take priority over score
# ---------------------------------------------------------------------------

def test_hard_gate_failure_overrides_even_a_perfect_score(matcher, jd_text):
    text, result = score("resume_01_mern_developer", matcher, jd_text)
    rules = EligibilityRules(
        job_id="jd_01_mern_developer", min_ats_score=0.0,  # would trivially pass
        mandatory_skills=["Kubernetes"],  # resume_01 lacks this
    )
    elig = evaluate_eligibility("resume_01_mern_developer", text, result, rules)
    assert elig.tag == "REJECTED"


def test_reasons_is_never_empty(matcher, jd_text):
    for cid in ["resume_01_mern_developer", "resume_11_python_backend_dev"]:
        text, result = score(cid, matcher, jd_text)
        elig = evaluate_eligibility(cid, text, result, EligibilityRules(job_id="jd_01_mern_developer"))
        assert len(elig.reasons) > 0


# ---------------------------------------------------------------------------
# Rule config validation -- catches the exact real bug found while writing
# this module's own example config
# ---------------------------------------------------------------------------

def test_validate_rules_catches_non_canonical_skill_name():
    from parsers.eligibility_engine import validate_rules_against_dictionary
    rules = EligibilityRules(job_id="jd_02", mandatory_skills=["Salesforce CRM"])
    warnings = validate_rules_against_dictionary(rules)
    assert len(warnings) == 1
    assert "Salesforce CRM" in warnings[0]


def test_validate_rules_suggests_the_correct_canonical_name():
    from parsers.eligibility_engine import validate_rules_against_dictionary
    rules = EligibilityRules(job_id="jd_02", mandatory_skills=["Salesforce CRM"])
    warnings = validate_rules_against_dictionary(rules)
    assert "Salesforce" in warnings[0]


def test_validate_rules_passes_clean_for_correct_canonical_names():
    from parsers.eligibility_engine import validate_rules_against_dictionary
    rules = EligibilityRules(job_id="jd_01", mandatory_skills=["React.js", "MongoDB"])
    assert validate_rules_against_dictionary(rules) == []


def test_validate_rules_is_case_insensitive():
    from parsers.eligibility_engine import validate_rules_against_dictionary
    rules = EligibilityRules(job_id="jd_01", mandatory_skills=["react.js"])
    assert validate_rules_against_dictionary(rules) == []


def test_validate_rules_empty_mandatory_skills_produces_no_warnings():
    from parsers.eligibility_engine import validate_rules_against_dictionary
    rules = EligibilityRules(job_id="jd_01")
    assert validate_rules_against_dictionary(rules) == []


def test_all_bundled_example_configs_pass_validation():
    import json
    from pathlib import Path as P
    from parsers.eligibility_engine import validate_rules_against_dictionary
    config_dir = P("data/eligibility_rules")
    for f in config_dir.glob("*.json"):
        rules = EligibilityRules.from_dict(json.loads(f.read_text()))
        warnings = validate_rules_against_dictionary(rules)
        assert warnings == [], f"{f.name} has invalid mandatory_skills: {warnings}"
