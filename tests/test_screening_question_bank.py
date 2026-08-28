from pathlib import Path

import pytest

from parsers.semantic_matcher import SemanticMatcher
from parsers.ats_scoring_engine import score_candidate
from parsers.screening_question_bank import (
    generate_screening_questions,
    get_template_text,
    QUESTION_TEMPLATES,
    CATEGORY_METADATA,
    CATEGORIES,
    SUPPORTED_LANGUAGES,
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


# ---------------------------------------------------------------------------
# Category mapping deliverable
# ---------------------------------------------------------------------------

def test_seven_required_categories_present():
    expected = {"introduction", "education", "experience", "skills", "location", "salary", "notice_period"}
    assert set(CATEGORIES) == expected


def test_every_category_has_complete_metadata():
    required_keys = {"default_mandatory", "default_scoring_importance", "applicable_roles"}
    for cat, meta in CATEGORY_METADATA.items():
        assert required_keys <= set(meta.keys()), cat


def test_scoring_importance_values_are_valid():
    valid = {"high", "medium", "low"}
    for meta in CATEGORY_METADATA.values():
        assert meta["default_scoring_importance"] in valid


# ---------------------------------------------------------------------------
# Reusable templates deliverable
# ---------------------------------------------------------------------------

def test_every_template_belongs_to_a_known_category():
    for tmpl in QUESTION_TEMPLATES.values():
        assert tmpl.category in CATEGORIES


def test_every_template_has_english_text():
    for tid, tmpl in QUESTION_TEMPLATES.items():
        assert tmpl.localized_text.get("en"), tid


def test_every_expected_answer_type_is_a_known_value():
    valid = {"free_text", "number", "duration", "yes_no", "list"}
    for tmpl in QUESTION_TEMPLATES.values():
        assert tmpl.expected_answer_type in valid


def test_get_template_text_falls_back_to_english_for_unpopulated_language():
    text = get_template_text("intro_general", QUESTION_TEMPLATES, lang="hi")
    assert "NO HI TRANSLATION" in text
    assert QUESTION_TEMPLATES["intro_general"].localized_text["en"] in text


def test_get_template_text_returns_english_directly_for_en():
    text = get_template_text("intro_general", QUESTION_TEMPLATES, lang="en")
    assert text == QUESTION_TEMPLATES["intro_general"].localized_text["en"]


def test_supported_languages_matches_prd_language_set():
    assert set(SUPPORTED_LANGUAGES) == {"en", "hi", "ml", "ta"}


# ---------------------------------------------------------------------------
# AI conversation-ready question objects: JD-only generation
# ---------------------------------------------------------------------------

def test_jd_only_generation_covers_all_universal_categories(jd_text):
    qs = generate_screening_questions(jd_text, "jd_01_mern_developer")
    categories_present = {q.category for q in qs}
    for universal_cat in ["introduction", "education", "experience", "location", "salary", "notice_period"]:
        assert universal_cat in categories_present


def test_jd_only_generation_includes_skill_questions_from_jd(jd_text):
    qs = generate_screening_questions(jd_text, "jd_01_mern_developer")
    skill_qs = [q for q in qs if q.category == "skills"]
    assert len(skill_qs) > 0
    # Must be clean skill names, not raw JD requirement sentences
    # (regression test for the "Strong proficiency in React.js and
    # Node.js" bug found and fixed while building this module)
    for q in skill_qs:
        assert "Strong proficiency" not in q.text
        assert len(q.text) < 150  # a real skill name, not a full requirement sentence


def test_jd_only_generation_no_unfilled_placeholders(jd_text):
    qs = generate_screening_questions(jd_text, "jd_01_mern_developer")
    for q in qs:
        assert "{" not in q.text and "}" not in q.text


def test_jd_only_generation_every_question_has_unique_id(jd_text):
    qs = generate_screening_questions(jd_text, "jd_01_mern_developer")
    ids = [q.id for q in qs]
    assert len(ids) == len(set(ids))


def test_education_question_uses_jd_specific_degree_when_available(jd_text):
    qs = generate_screening_questions(jd_text, "jd_01_mern_developer")
    edu_q = next(q for q in qs if q.category == "education")
    assert "Computer Science" in edu_q.text
    assert edu_q.source == "jd_derived"


def test_salary_question_uses_jd_range_when_available(jd_text):
    qs = generate_screening_questions(jd_text, "jd_01_mern_developer")
    salary_q = next(q for q in qs if q.category == "salary")
    assert "800000" in salary_q.text and "1400000" in salary_q.text


def test_notice_period_always_generated(jd_text):
    # Directly ties to Day 21's documented gap: this category IS where
    # availability actually gets asked, since it can't be gated from
    # resume data alone.
    qs = generate_screening_questions(jd_text, "jd_01_mern_developer")
    notice_qs = [q for q in qs if q.category == "notice_period"]
    assert len(notice_qs) == 1
    assert notice_qs[0].mandatory is True


def test_max_skill_questions_is_respected(jd_text):
    qs = generate_screening_questions(jd_text, "jd_01_mern_developer", max_skill_questions=1)
    skill_qs = [q for q in qs if q.category == "skills" and q.source == "jd_derived"]
    assert len(skill_qs) == 1


# ---------------------------------------------------------------------------
# AI conversation-ready question objects: personalized (resume + ATS) generation
# ---------------------------------------------------------------------------

def test_personalized_generation_adds_education_followup_when_missing(matcher, jd_text):
    text = (RESUME_DIR / "resume_14_no_education.txt").read_text()
    result = score_candidate(text, jd_text, matcher)
    qs = generate_screening_questions(jd_text, "jd_01_mern_developer", resume_text=text, ats_result=result)
    followups = [q for q in qs if q.source == "ats_followup" and q.category == "education"]
    assert len(followups) == 1
    assert "weren't able to find" in followups[0].text


def test_personalized_generation_no_education_followup_when_present(matcher, jd_text):
    text = (RESUME_DIR / "resume_01_mern_developer.txt").read_text()
    result = score_candidate(text, jd_text, matcher)
    qs = generate_screening_questions(jd_text, "jd_01_mern_developer", resume_text=text, ats_result=result)
    followups = [q for q in qs if q.source == "ats_followup" and q.category == "education"]
    assert len(followups) == 0


def test_personalized_generation_verifies_missing_mandatory_skills(matcher, jd_text):
    text = (RESUME_DIR / "resume_11_python_backend_dev.txt").read_text()
    result = score_candidate(text, jd_text, matcher)
    qs = generate_screening_questions(jd_text, "jd_01_mern_developer", resume_text=text, ats_result=result)
    verify_qs = [q for q in qs if q.source == "ats_followup" and "requires" in q.text]
    assert len(verify_qs) > 0
    for q in verify_qs:
        assert q.mandatory is True
        assert q.scoring_importance == "high"


def test_personalized_generation_asks_depth_question_for_matched_skill(matcher, jd_text):
    text = (RESUME_DIR / "resume_01_mern_developer.txt").read_text()
    result = score_candidate(text, jd_text, matcher)
    qs = generate_screening_questions(jd_text, "jd_01_mern_developer", resume_text=text, ats_result=result)
    depth_qs = [q for q in qs if q.source == "ats_followup" and "walk me through a specific project" in q.text]
    assert len(depth_qs) > 0
    assert depth_qs[0].mandatory is False  # a depth question is optional, not a hard gate


def test_experience_question_personalizes_with_real_candidate_years(matcher, jd_text):
    text = (RESUME_DIR / "resume_01_mern_developer.txt").read_text()
    result = score_candidate(text, jd_text, matcher)
    qs = generate_screening_questions(jd_text, "jd_01_mern_developer", resume_text=text, ats_result=result)
    exp_q = next(q for q in qs if q.category == "experience" and q.source == "jd_derived")
    assert "2.0" in exp_q.text and "4.0" in exp_q.text  # the JD's band
    assert "{" not in exp_q.text


def test_no_ats_followups_when_ats_result_not_provided(jd_text):
    qs = generate_screening_questions(jd_text, "jd_01_mern_developer")
    assert all(q.source != "ats_followup" for q in qs)


def test_all_questions_have_correct_language_tag(jd_text):
    qs = generate_screening_questions(jd_text, "jd_01_mern_developer", lang="en")
    assert all(q.language == "en" for q in qs)
