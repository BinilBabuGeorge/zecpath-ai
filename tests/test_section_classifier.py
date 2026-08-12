from pathlib import Path

import pytest

from parsers.section_classifier import (
    classify_resume,
    _match_heading,
    _looks_like_skills_line,
    TARGET_SECTIONS,
)

RESUME_DIR = Path("data/labeled_resumes")
ALL_RESUMES = sorted(RESUME_DIR.glob("*.txt"))


# ---------------------------------------------------------------------------
# Heading synonym matching
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("heading,expected", [
    ("Skills:", "Skills"),
    ("What I Know:", "Skills"),
    ("Experience:", "Work Experience"),
    ("My Journey:", "Work Experience"),
    ("Professional Experience:", "Work Experience"),
    ("Education:", "Education"),
    ("Academic Background:", "Education"),
    ("Certifications:", "Certifications"),
    ("Licenses & Badges:", "Certifications"),
    ("Projects:", "Projects"),
])
def test_match_heading_recognizes_known_synonyms(heading, expected):
    assert _match_heading(heading) == expected


def test_match_heading_returns_none_for_non_heading_line():
    assert _match_heading("Built a product recommendation model") is None


# ---------------------------------------------------------------------------
# Content-shape heuristics
# ---------------------------------------------------------------------------

def test_looks_like_skills_line_detects_comma_list():
    assert _looks_like_skills_line("Python, Django, PostgreSQL, Redis, Docker") is True


def test_looks_like_skills_line_rejects_sentence_with_period():
    assert _looks_like_skills_line("Comfortable working across the stack, using React and Node.") is False


def test_looks_like_skills_line_rejects_short_list_with_long_items():
    long_line = "A very long descriptive sentence fragment, another long descriptive fragment here"
    assert _looks_like_skills_line(long_line) is False


# ---------------------------------------------------------------------------
# End-to-end classification on every sample resume
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("resume_path", ALL_RESUMES, ids=[p.name for p in ALL_RESUMES])
def test_classify_resume_returns_only_known_labels(resume_path):
    text = resume_path.read_text(encoding="utf-8")
    result = classify_resume(text)
    valid_labels = set(TARGET_SECTIONS) | {"Other"}
    for item in result:
        assert item.section in valid_labels


@pytest.mark.parametrize("resume_path", ALL_RESUMES, ids=[p.name for p in ALL_RESUMES])
def test_classify_resume_produces_nonempty_output(resume_path):
    text = resume_path.read_text(encoding="utf-8")
    result = classify_resume(text)
    assert len(result) > 0


def test_classify_resume_handles_completely_missing_headings():
    text = (RESUME_DIR / "resume_11_no_headings.txt").read_text(encoding="utf-8")
    result = classify_resume(text)
    sections_found = {item.section for item in result}
    assert {"Skills", "Work Experience", "Education", "Certifications"}.issubset(sections_found)


def test_classify_resume_handles_nonstandard_heading_synonyms():
    text = (RESUME_DIR / "resume_12_nonstandard_headings.txt").read_text(encoding="utf-8")
    result = classify_resume(text)
    sections_found = {item.section for item in result}
    assert {"Skills", "Work Experience", "Education", "Certifications"}.issubset(sections_found)


def test_classify_resume_detects_projects_section():
    text = (RESUME_DIR / "resume_13_with_projects.txt").read_text(encoding="utf-8")
    result = classify_resume(text)
    project_lines = [item for item in result if item.section == "Projects"]
    assert len(project_lines) == 2


def test_classify_resume_known_limitation_cert_without_keyword():
    """Documents a known weakness: a certification line with no
    'certified/certificate' keyword and no governing heading falls
    through to 'Other' instead of 'Certifications'. See accuracy report."""
    text = (RESUME_DIR / "resume_14_hard_cert_no_keyword.txt").read_text(encoding="utf-8")
    result = classify_resume(text)
    last_line = result[-1]
    assert "AWS Solutions Architect" in last_line.line
    assert last_line.section == "Other"  # documents the current (incorrect) behavior


def test_classify_resume_known_limitation_skills_as_prose():
    """Documents a known weakness: skills written as a prose sentence
    (not a comma list) with no governing heading are missed. See
    accuracy report."""
    text = (RESUME_DIR / "resume_15_hard_skills_prose.txt").read_text(encoding="utf-8")
    result = classify_resume(text)
    skills_line = [item for item in result if "Comfortable working" in item.line][0]
    assert skills_line.section == "Other"  # documents the current (incorrect) behavior
