from pathlib import Path

import pytest

from parsers.semantic_matcher import SemanticMatcher
from parsers.ats_scoring_engine import (
    score_candidate,
    infer_role_category,
    _redistribute_weights,
    WEIGHT_PROFILES,
)

RESUME_DIR = Path("data/samples/resumes")
JD_DIR = Path("data/samples/jds")


@pytest.fixture(scope="module")
def matcher():
    resume_files = sorted(RESUME_DIR.glob("*.txt"))
    jd_files = sorted(JD_DIR.glob("*.txt"))
    corpus = [f.read_text() for f in resume_files + jd_files]
    return SemanticMatcher(corpus)


# ---------------------------------------------------------------------------
# Role category inference and weight profiles
# ---------------------------------------------------------------------------

def test_infer_role_category_detects_tech():
    jd_skills_text = "React.js, Node.js, MongoDB, Docker"
    assert infer_role_category(jd_skills_text) == "tech"


def test_infer_role_category_detects_business():
    jd_skills_text = "Cold Calling, Salesforce, Negotiation"
    assert infer_role_category(jd_skills_text) == "business"


def test_infer_role_category_falls_back_to_default_for_unrecognized_text():
    assert infer_role_category("completely unrecognized words here") == "default"


def test_all_weight_profiles_sum_to_one():
    for profile_name, weights in WEIGHT_PROFILES.items():
        assert sum(weights.values()) == pytest.approx(1.0), f"{profile_name} weights don't sum to 1.0"


def test_tech_and_business_profiles_have_different_weights():
    assert WEIGHT_PROFILES["tech"] != WEIGHT_PROFILES["business"]


# ---------------------------------------------------------------------------
# Weight redistribution
# ---------------------------------------------------------------------------

def test_redistribute_weights_unchanged_when_all_available():
    base = {"a": 0.4, "b": 0.3, "c": 0.3}
    availability = {"a": True, "b": True, "c": True}
    result = _redistribute_weights(base, availability)
    assert result == base


def test_redistribute_weights_sums_to_one_when_one_missing():
    base = {"a": 0.4, "b": 0.3, "c": 0.3}
    availability = {"a": True, "b": False, "c": True}
    result = _redistribute_weights(base, availability)
    assert result["b"] == 0.0
    assert sum(result.values()) == pytest.approx(1.0)


def test_redistribute_weights_all_missing_returns_zeros():
    base = {"a": 0.4, "b": 0.3, "c": 0.3}
    availability = {"a": False, "b": False, "c": False}
    result = _redistribute_weights(base, availability)
    assert all(v == 0.0 for v in result.values())


# ---------------------------------------------------------------------------
# End-to-end scoring
# ---------------------------------------------------------------------------

def test_score_candidate_matched_pair_scores_higher_than_mismatched(matcher):
    mern_resume = (RESUME_DIR / "resume_01_mern_developer.txt").read_text()
    sales_resume = (RESUME_DIR / "resume_03_sales_executive.txt").read_text()
    mern_jd = (JD_DIR / "jd_01_mern_developer.txt").read_text()

    matched_result = score_candidate(mern_resume, mern_jd, matcher)
    mismatched_result = score_candidate(sales_resume, mern_jd, matcher)

    assert matched_result.overall_score > mismatched_result.overall_score


def test_score_candidate_auto_infers_role_category(matcher):
    resume = (RESUME_DIR / "resume_01_mern_developer.txt").read_text()
    jd = (JD_DIR / "jd_01_mern_developer.txt").read_text()
    result = score_candidate(resume, jd, matcher)
    assert result.role_category == "tech"


def test_score_candidate_respects_explicit_role_category_override(matcher):
    resume = (RESUME_DIR / "resume_01_mern_developer.txt").read_text()
    jd = (JD_DIR / "jd_01_mern_developer.txt").read_text()
    result = score_candidate(resume, jd, matcher, role_category="creative")
    assert result.role_category == "creative"


def test_score_candidate_all_components_present_for_complete_resume(matcher):
    resume = (RESUME_DIR / "resume_01_mern_developer.txt").read_text()
    jd = (JD_DIR / "jd_01_mern_developer.txt").read_text()
    result = score_candidate(resume, jd, matcher)
    assert all(c.available for c in result.components)
    assert result.missing_data_notes == []


def test_score_candidate_overall_score_in_valid_range(matcher):
    resume = (RESUME_DIR / "resume_01_mern_developer.txt").read_text()
    jd = (JD_DIR / "jd_01_mern_developer.txt").read_text()
    result = score_candidate(resume, jd, matcher)
    assert 0.0 <= result.overall_score <= 100.0


# ---------------------------------------------------------------------------
# Missing data handling -- the key Day 13 requirement
# ---------------------------------------------------------------------------

def test_score_candidate_flags_missing_experience(matcher):
    resume = (RESUME_DIR / "resume_13_fresher_no_experience.txt").read_text()
    jd = (JD_DIR / "jd_01_mern_developer.txt").read_text()
    result = score_candidate(resume, jd, matcher)

    exp_component = [c for c in result.components if c.name == "experience"][0]
    assert exp_component.available is False
    assert exp_component.effective_weight == 0.0
    assert len(result.missing_data_notes) == 1


def test_score_candidate_redistributes_weight_when_experience_missing(matcher):
    resume = (RESUME_DIR / "resume_13_fresher_no_experience.txt").read_text()
    jd = (JD_DIR / "jd_01_mern_developer.txt").read_text()
    result = score_candidate(resume, jd, matcher)

    available_weights = [c.effective_weight for c in result.components if c.available]
    assert sum(available_weights) == pytest.approx(1.0, abs=0.01)


def test_score_candidate_flags_missing_education(matcher):
    resume = (RESUME_DIR / "resume_14_no_education.txt").read_text()
    jd = (JD_DIR / "jd_01_mern_developer.txt").read_text()
    result = score_candidate(resume, jd, matcher)

    edu_component = [c for c in result.components if c.name == "education"][0]
    assert edu_component.available is False
    assert edu_component.effective_weight == 0.0


def test_score_candidate_still_produces_valid_score_with_missing_data(matcher):
    resume = (RESUME_DIR / "resume_13_fresher_no_experience.txt").read_text()
    jd = (JD_DIR / "jd_01_mern_developer.txt").read_text()
    result = score_candidate(resume, jd, matcher)
    assert 0.0 <= result.overall_score <= 100.0


def test_score_candidate_missing_data_note_explains_reason(matcher):
    resume = (RESUME_DIR / "resume_13_fresher_no_experience.txt").read_text()
    jd = (JD_DIR / "jd_01_mern_developer.txt").read_text()
    result = score_candidate(resume, jd, matcher)
    assert "experience" in result.missing_data_notes[0]
    assert "no work experience" in result.missing_data_notes[0].lower() or "redistributed" in result.missing_data_notes[0].lower()


# ---------------------------------------------------------------------------
# Explainability -- every component's contribution must be traceable
# ---------------------------------------------------------------------------

def test_score_candidate_component_contributions_sum_to_overall_score(matcher):
    resume = (RESUME_DIR / "resume_01_mern_developer.txt").read_text()
    jd = (JD_DIR / "jd_01_mern_developer.txt").read_text()
    result = score_candidate(resume, jd, matcher)

    total_contribution = round(sum(c.contribution for c in result.components), 1)
    assert total_contribution == pytest.approx(result.overall_score, abs=0.2)


def test_score_candidate_skill_match_details_list_matched_and_missing_skills(matcher):
    resume = (RESUME_DIR / "resume_01_mern_developer.txt").read_text()
    jd = (JD_DIR / "jd_01_mern_developer.txt").read_text()
    result = score_candidate(resume, jd, matcher)

    skill_component = [c for c in result.components if c.name == "skill_match"][0]
    assert "matched_skills" in skill_component.details
    assert "missing_skills" in skill_component.details


def test_score_candidate_explanation_is_nonempty_string(matcher):
    resume = (RESUME_DIR / "resume_01_mern_developer.txt").read_text()
    jd = (JD_DIR / "jd_01_mern_developer.txt").read_text()
    result = score_candidate(resume, jd, matcher)
    assert isinstance(result.explanation, str)
    assert len(result.explanation) > 0
