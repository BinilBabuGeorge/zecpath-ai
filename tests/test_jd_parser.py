from pathlib import Path

import pytest

from parsers.jd_parser import (
    normalize_role,
    normalize_skill,
    parse_jd,
    _parse_experience,
    _parse_salary,
    _parse_employment_type,
)

RAW_DIR = Path("data/jds_raw")
ALL_JDS = sorted(RAW_DIR.glob("*.txt"))


# ---------------------------------------------------------------------------
# Skill synonym normalization
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("ReactJS", "React.js"),
    ("React.js", "React.js"),
    ("react js", "React.js"),
    ("Node JS", "Node.js"),
    ("NodeJS", "Node.js"),
    ("Mongo DB", "MongoDB"),
    ("MongoDB", "MongoDB"),
    ("Typescript", "TypeScript"),
])
def test_normalize_skill_maps_synonyms_to_canonical_name(raw, expected):
    assert normalize_skill(raw)["name"] == expected


def test_normalize_skill_leaves_unknown_skill_unchanged():
    result = normalize_skill("Quantum Computing")
    assert result["name"] == "Quantum Computing"
    assert result["category"] == "domain"


# ---------------------------------------------------------------------------
# Role synonym normalization
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("MERN Stack Developer", "MERN Stack Developer"),
    ("Frontend Engineer (MERN)", "MERN Stack Developer"),
    ("Sales Executive", "Sales Executive"),
    ("Business Development Executive", "Sales Executive"),
])
def test_normalize_role_maps_variations_to_canonical_family(raw, expected):
    assert normalize_role(raw) == expected


def test_normalize_role_leaves_unmapped_title_unchanged():
    assert normalize_role("Chief Astronaut Officer") == "Chief Astronaut Officer"


# ---------------------------------------------------------------------------
# Field parsing helpers
# ---------------------------------------------------------------------------

def test_parse_experience_range():
    assert _parse_experience("2-4 years") == {"minYears": 2.0, "maxYears": 4.0}


def test_parse_experience_handles_yrs_abbreviation():
    assert _parse_experience("1-3 yrs") == {"minYears": 1.0, "maxYears": 3.0}


def test_parse_experience_returns_none_for_missing_value():
    assert _parse_experience(None) == {"minYears": None, "maxYears": None}


def test_parse_salary_with_rupee_symbol():
    result = _parse_salary("\u20b98,00,000 - \u20b914,00,000 per annum")
    assert result == {"min": 800000, "max": 1400000, "currency": "INR"}


def test_parse_salary_with_rs_prefix():
    result = _parse_salary("Rs. 400000 to Rs. 700000 per year")
    assert result["min"] == 400000
    assert result["max"] == 700000
    assert result["currency"] == "INR"


def test_parse_salary_returns_none_when_absent():
    assert _parse_salary(None) is None


def test_parse_employment_type_normalizes_spacing():
    assert _parse_employment_type("Full time") == "full-time"
    assert _parse_employment_type("full-time") == "full-time"


def test_parse_employment_type_defaults_when_missing():
    assert _parse_employment_type(None) == "full-time"


# ---------------------------------------------------------------------------
# End-to-end parse_jd() across every sample JD
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("file_path", ALL_JDS, ids=[p.name for p in ALL_JDS])
def test_parse_jd_produces_required_top_level_fields(file_path):
    raw = file_path.read_text(encoding="utf-8")
    profile = parse_jd(raw, job_id="JOB-TEST")
    for field in ["jobId", "jobTitle", "department", "location", "employmentType",
                  "requiredSkills", "responsibilities"]:
        assert field in profile


@pytest.mark.parametrize("file_path", ALL_JDS, ids=[p.name for p in ALL_JDS])
def test_parse_jd_extracts_at_least_one_required_skill(file_path):
    raw = file_path.read_text(encoding="utf-8")
    profile = parse_jd(raw, job_id="JOB-TEST")
    assert len(profile["requiredSkills"]) >= 1


@pytest.mark.parametrize("file_path", ALL_JDS, ids=[p.name for p in ALL_JDS])
def test_parse_jd_extracts_at_least_one_responsibility(file_path):
    raw = file_path.read_text(encoding="utf-8")
    profile = parse_jd(raw, job_id="JOB-TEST")
    assert len(profile["responsibilities"]) >= 1


def test_parse_jd_two_differently_worded_mern_jds_normalize_to_same_role():
    jd1 = parse_jd((RAW_DIR / "jd_01_mern_developer.txt").read_text(), "JOB-A")
    jd3 = parse_jd((RAW_DIR / "jd_03_frontend_engineer_mern.txt").read_text(), "JOB-B")
    assert jd1["jobTitle"] == jd3["jobTitle"] == "MERN Stack Developer"
    assert jd1["jobTitleOriginal"] != jd3["jobTitleOriginal"]


def test_parse_jd_two_differently_worded_sales_jds_normalize_to_same_role():
    jd2 = parse_jd((RAW_DIR / "jd_02_sales_executive.txt").read_text(), "JOB-C")
    jd4 = parse_jd((RAW_DIR / "jd_04_business_development_executive.txt").read_text(), "JOB-D")
    assert jd2["jobTitle"] == jd4["jobTitle"] == "Sales Executive"


def test_parse_jd_synonym_heavy_jd_normalizes_all_core_mern_skills():
    raw = (RAW_DIR / "jd_03_frontend_engineer_mern.txt").read_text()
    profile = parse_jd(raw, job_id="JOB-TEST")
    skill_names = {s["name"] for s in profile["requiredSkills"]}
    assert {"React.js", "Node.js", "MongoDB", "Express.js"}.issubset(skill_names)
