from pathlib import Path

import pytest

from parsers.semantic_matcher import (
    SemanticMatcher,
    normalize_for_embedding,
    compare_resume_to_jd,
    classify_score,
)
from parsers.section_extractor import extract_resume_sections, extract_jd_sections

RESUME_DIR = Path("data/samples/resumes")
JD_DIR = Path("data/samples/jds")


@pytest.fixture(scope="module")
def matcher():
    resume_files = sorted(RESUME_DIR.glob("*.txt"))
    jd_files = sorted(JD_DIR.glob("*.txt"))
    corpus = [f.read_text() for f in resume_files + jd_files]
    return SemanticMatcher(corpus)


# ---------------------------------------------------------------------------
# Normalization preprocessing
# ---------------------------------------------------------------------------

def test_normalize_for_embedding_unifies_skill_synonyms():
    a = normalize_for_embedding("ReactJS and Node JS")
    b = normalize_for_embedding("React.js and Node.js")
    assert a == b


def test_normalize_for_embedding_leaves_unknown_words_unchanged():
    result = normalize_for_embedding("some completely unrelated words here")
    assert "unrelated" in result


# ---------------------------------------------------------------------------
# Core similarity behavior
# ---------------------------------------------------------------------------

def test_identical_text_has_similarity_of_one(matcher):
    text = "React.js, Node.js, MongoDB, Express.js developer"
    assert matcher.similarity(text, text) == pytest.approx(1.0, abs=0.01)


def test_completely_unrelated_text_has_low_similarity(matcher):
    score = matcher.similarity("React.js Node.js MongoDB developer", "cold calling sales negotiation CRM")
    assert score < 0.05


def test_synonym_rewording_increases_similarity_vs_no_normalization():
    resume_files = sorted(RESUME_DIR.glob("*.txt"))
    jd_files = sorted(JD_DIR.glob("*.txt"))
    corpus = [f.read_text() for f in resume_files + jd_files]

    matcher_with = SemanticMatcher(corpus, normalize=True)
    matcher_without = SemanticMatcher(corpus, normalize=False)

    text_a = "ReactJS, Node JS, Mongo DB"
    text_b = "React.js, Node.js, MongoDB"

    with_score = matcher_with.similarity(text_a, text_b)
    without_score = matcher_without.similarity(text_a, text_b)
    assert with_score > without_score


# ---------------------------------------------------------------------------
# Section extraction
# ---------------------------------------------------------------------------

def test_extract_resume_sections_finds_skills_and_experience():
    text = (RESUME_DIR / "resume_01_mern_developer.txt").read_text()
    sections = extract_resume_sections(text)
    assert "React.js" in sections["skills"]
    assert "Brightwave" in sections["experience"]


def test_extract_jd_sections_finds_required_skills_and_responsibilities():
    text = (JD_DIR / "jd_01_mern_developer.txt").read_text()
    sections = extract_jd_sections(text)
    assert "React" in sections["skills"]
    assert "REST APIs" in sections["experience"]


# ---------------------------------------------------------------------------
# Classification thresholds
# ---------------------------------------------------------------------------

def test_classify_score_strong_match():
    assert classify_score(0.9, {"strong": 0.5, "moderate": 0.25}) == "Strong Match"


def test_classify_score_moderate_match():
    assert classify_score(0.3, {"strong": 0.5, "moderate": 0.25}) == "Moderate Match"


def test_classify_score_weak_match():
    assert classify_score(0.1, {"strong": 0.5, "moderate": 0.25}) == "Weak Match"


# ---------------------------------------------------------------------------
# End-to-end resume-to-JD comparison, using real known cases
# ---------------------------------------------------------------------------

def test_matching_resume_scores_higher_than_mismatched_resume(matcher):
    mern_resume = extract_resume_sections((RESUME_DIR / "resume_01_mern_developer.txt").read_text())
    sales_resume = extract_resume_sections((RESUME_DIR / "resume_03_sales_executive.txt").read_text())
    mern_jd = extract_jd_sections((JD_DIR / "jd_01_mern_developer.txt").read_text())

    thresholds = {"strong": 1.0, "moderate": 1.0}
    mern_result = compare_resume_to_jd(mern_resume, mern_jd, matcher, thresholds)
    sales_result = compare_resume_to_jd(sales_resume, mern_jd, matcher, thresholds)

    assert mern_result.overall_score > sales_result.overall_score


def test_matcher_recognizes_same_role_despite_different_wording(matcher):
    """resume_01 (MERN dev) should score meaningfully against BOTH jd_01
    (same wording) and jd_03 (differently-worded 'Frontend Engineer (MERN)'
    from Day 6) -- proving synonym normalization bridges the wording gap."""
    mern_resume = extract_resume_sections((RESUME_DIR / "resume_01_mern_developer.txt").read_text())
    jd_01 = extract_jd_sections((JD_DIR / "jd_01_mern_developer.txt").read_text())
    jd_03 = extract_jd_sections((JD_DIR / "jd_03_frontend_engineer_mern.txt").read_text())

    thresholds = {"strong": 1.0, "moderate": 1.0}
    result_01 = compare_resume_to_jd(mern_resume, jd_01, matcher, thresholds)
    result_03 = compare_resume_to_jd(mern_resume, jd_03, matcher, thresholds)

    assert result_01.overall_score > 0.1
    assert result_03.overall_score > 0.1


def test_backend_python_dev_does_not_falsely_match_mern_jd(matcher):
    """Regression test for a real validation case: a Python/Django backend
    developer (genuinely different stack) should NOT score above the
    tuned strong-match threshold against a MERN JD."""
    python_resume = extract_resume_sections((RESUME_DIR / "resume_11_python_backend_dev.txt").read_text())
    mern_jd = extract_jd_sections((JD_DIR / "jd_01_mern_developer.txt").read_text())

    thresholds = {"strong": 0.1356, "moderate": 0.0678}
    result = compare_resume_to_jd(python_resume, mern_jd, matcher, thresholds)
    assert result.classification != "Strong Match"


# ---------------------------------------------------------------------------
# Robustness on every sample resume x JD pair
# ---------------------------------------------------------------------------

ALL_RESUMES = sorted(RESUME_DIR.glob("*.txt"))
ALL_JDS = sorted(JD_DIR.glob("*.txt"))


@pytest.mark.parametrize("resume_path", ALL_RESUMES, ids=[p.name for p in ALL_RESUMES])
def test_every_resume_produces_valid_scores_against_every_jd(matcher, resume_path):
    resume_sections = extract_resume_sections(resume_path.read_text())
    thresholds = {"strong": 0.5, "moderate": 0.25}
    for jd_path in ALL_JDS:
        jd_sections = extract_jd_sections(jd_path.read_text())
        result = compare_resume_to_jd(resume_sections, jd_sections, matcher, thresholds)
        assert 0.0 <= result.overall_score <= 1.0
        assert result.classification in {"Strong Match", "Moderate Match", "Weak Match"}
