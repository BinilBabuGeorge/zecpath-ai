from pathlib import Path

import pytest

from parsers.education_parser import (
    parse_education,
    parse_certifications,
    normalize_degree,
    categorize_certification,
)
from parsers.education_relevance import score_education_relevance

SAMPLE_DIR = Path("data/samples")


# ---------------------------------------------------------------------------
# Degree normalization
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected_canonical,expected_level", [
    ("B.Tech", "B.Tech", "Bachelor's"),
    ("BTech", "B.Tech", "Bachelor's"),
    ("Bachelor of Technology", "B.Tech", "Bachelor's"),
    ("MBA", "MBA", "Master's"),
    ("M.B.A.", "MBA", "Master's"),
    ("Master of Business Administration", "MBA", "Master's"),
    ("B.E.", "B.E.", "Bachelor's"),
    ("BE", "B.E.", "Bachelor's"),
    ("PhD", "Ph.D", "Doctorate"),
    ("Diploma", "Diploma", "Diploma"),
])
def test_normalize_degree_handles_variations(raw, expected_canonical, expected_level):
    canonical, level = normalize_degree(raw)
    assert canonical == expected_canonical
    assert level == expected_level


def test_normalize_degree_falls_back_for_unknown_degree():
    canonical, level = normalize_degree("Bachelor of Underwater Basket Weaving")
    assert level is None
    assert canonical == "Bachelor of Underwater Basket Weaving"


# ---------------------------------------------------------------------------
# Education parsing
# ---------------------------------------------------------------------------

def test_parse_education_extracts_degree_field_institution_year():
    text = "- B.Tech in Computer Science, VIT Vellore, 2021"
    entries = parse_education(text)
    assert len(entries) == 1
    e = entries[0]
    assert e.degree == "B.Tech"
    assert e.field_of_study == "Computer Science"
    assert e.institution == "VIT Vellore"
    assert e.year == 2021


def test_parse_education_handles_missing_field_of_study():
    text = "- B.Com, Osmania University, 2019"
    entries = parse_education(text)
    assert len(entries) == 1
    assert entries[0].field_of_study is None
    assert entries[0].degree == "B.Com"


def test_parse_education_handles_multiple_degrees():
    text = (
        "- B.Sc in Statistics, Christ University, 2018\n"
        "- M.Tech in Data Science, IIIT Bangalore, 2022\n"
    )
    entries = parse_education(text)
    assert len(entries) == 2
    assert entries[0].degree == "B.Sc"
    assert entries[1].degree == "M.Tech"


def test_parse_education_returns_empty_for_no_matches():
    assert parse_education("No education info here.") == []


# ---------------------------------------------------------------------------
# Certification parsing
# ---------------------------------------------------------------------------

def test_parse_certifications_extracts_name_and_year():
    text = "- MongoDB Certified Developer Associate (2023)"
    certs = parse_certifications(text)
    assert len(certs) == 1
    assert certs[0].name == "MongoDB Certified Developer Associate"
    assert certs[0].year == 2023
    assert certs[0].issuer is None


def test_parse_certifications_extracts_issuer_when_present():
    text = "- AWS Solutions Architect - Associate, Amazon Web Services (2023)"
    certs = parse_certifications(text)
    assert len(certs) == 1
    assert certs[0].issuer == "Amazon Web Services"
    assert "AWS Solutions Architect" in certs[0].name


def test_parse_certifications_assigns_category():
    text = "- Tally Certified Professional (2020)"
    certs = parse_certifications(text)
    assert certs[0].category == "Finance/Accounting"


def test_categorize_certification_defaults_to_other_for_unknown():
    assert categorize_certification("Advanced Underwater Basket Weaving Certificate") == "Other"


def test_categorize_certification_known_limitation_multi_domain_cert():
    """Documents a known limitation: a cert spanning two domains (AWS +
    Machine Learning) is categorized by whichever keyword is found first
    in dictionary order (Cloud/DevOps), not necessarily the most relevant
    category (Data/Analytics). See education relevance report."""
    category = categorize_certification("AWS Certified Machine Learning - Specialty")
    assert category == "Cloud/DevOps"  # documents current (imperfect) behavior


# ---------------------------------------------------------------------------
# Relevance scoring
# ---------------------------------------------------------------------------

def test_score_education_relevance_full_score_for_exact_match():
    text = "- B.Tech in Computer Science, VIT Vellore, 2021\n- MongoDB Certified Developer Associate (2023)"
    education = parse_education(text)
    certs = parse_certifications(text)
    result = score_education_relevance(education, certs, "Bachelor's", ["Computer Science"], ["Software Development"])
    assert result.overall_score == 100.0


def test_score_education_relevance_penalizes_degree_shortfall():
    text = "- Diploma in Computer Engineering, Government Polytechnic, 2023"
    education = parse_education(text)
    result = score_education_relevance(education, [], "Bachelor's", [], [])
    assert result.degree_level_score < 100.0


def test_score_education_relevance_higher_degree_meets_lower_requirement():
    text = "- M.Tech in Data Science, IIIT Bangalore, 2022"
    education = parse_education(text)
    result = score_education_relevance(education, [], "Bachelor's", [], [])
    assert result.degree_level_score == 100.0


def test_score_education_relevance_picks_highest_ranked_degree_as_best_match():
    text = "- B.Sc in Statistics, Christ University, 2018\n- M.Tech in Data Science, IIIT Bangalore, 2022"
    education = parse_education(text)
    result = score_education_relevance(education, [], "Bachelor's", [], [])
    assert result.best_matching_degree == "M.Tech"


def test_score_education_relevance_certification_bonus_capped_at_20():
    text = (
        "- AWS Certified Developer Associate (2022)\n"
        "- Azure Fundamentals (2022)\n"
        "- Kubernetes Application Developer Certification (2023)\n"
    )
    certs = parse_certifications(text)
    result = score_education_relevance([], certs, None, [], ["Cloud/DevOps"])
    assert result.certification_bonus <= 20.0


def test_score_education_relevance_zero_bonus_when_no_certs_match():
    text = "- Tally Certified Professional (2020)"
    certs = parse_certifications(text)
    result = score_education_relevance([], certs, None, [], ["Cloud/DevOps"])
    assert result.certification_bonus == 0.0


def test_score_education_relevance_handles_no_education_gracefully():
    result = score_education_relevance([], [], "Bachelor's", ["Computer Science"], [])
    assert 0.0 <= result.overall_score <= 100.0


# ---------------------------------------------------------------------------
# End-to-end on every sample resume
# ---------------------------------------------------------------------------

ALL_SAMPLES = sorted(SAMPLE_DIR.glob("*.txt"))


@pytest.mark.parametrize("resume_path", ALL_SAMPLES, ids=[p.name for p in ALL_SAMPLES])
def test_parse_education_produces_entries_for_every_sample(resume_path):
    text = resume_path.read_text(encoding="utf-8")
    entries = parse_education(text)
    assert len(entries) > 0


@pytest.mark.parametrize("resume_path", ALL_SAMPLES, ids=[p.name for p in ALL_SAMPLES])
def test_relevance_score_in_valid_range_for_every_sample(resume_path):
    text = resume_path.read_text(encoding="utf-8")
    education = parse_education(text)
    certs = parse_certifications(text)
    result = score_education_relevance(education, certs, "Bachelor's", [], [])
    assert 0.0 <= result.overall_score <= 100.0
