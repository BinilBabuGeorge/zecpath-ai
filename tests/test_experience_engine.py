from pathlib import Path

import pytest

from parsers.experience_parser import parse_experience, compute_total_experience
from parsers.experience_relevance import (
    normalize_title,
    title_similarity,
    score_experience_relevance,
)

SAMPLE_DIR = Path("data/samples")


# ---------------------------------------------------------------------------
# Basic parsing
# ---------------------------------------------------------------------------

def test_parse_experience_extracts_title_company_dates():
    text = "- Software Engineer, Brightwave Technologies (Jun 2022 - Present)\nBuilt APIs."
    entries = parse_experience(text)
    assert len(entries) == 1
    e = entries[0]
    assert e.title == "Software Engineer"
    assert e.company == "Brightwave Technologies"
    assert e.start_year == 2022 and e.start_month == 6
    assert e.is_current is True


def test_parse_experience_parses_fixed_end_date():
    text = "- Junior Developer, CodeNest Pvt Ltd (Jul 2021 - May 2022)\nDeveloped things."
    entries = parse_experience(text)
    e = entries[0]
    assert e.end_year == 2022 and e.end_month == 5
    assert e.is_current is False


def test_parse_experience_attaches_description_to_correct_entry():
    text = (
        "- Role A, Company A (Jan 2020 - Dec 2020)\nDid task A.\n"
        "- Role B, Company B (Jan 2021 - Present)\nDid task B."
    )
    entries = parse_experience(text)
    assert entries[0].description == "Did task A."
    assert entries[1].description == "Did task B."


def test_parse_experience_stops_attaching_at_section_boundary():
    """Regression test for a real bug: Education content was leaking into
    the last Experience entry's description when run on full resume text."""
    text = (
        "- Associate PM, Vantage (Jun 2019 - Jul 2020)\nSupported pricing.\n\n"
        "Education:\n- MBA, IIM Bangalore, 2019"
    )
    entries = parse_experience(text)
    assert len(entries) == 1
    assert "MBA" not in entries[0].description
    assert "Supported pricing." == entries[0].description


def test_parse_experience_returns_empty_list_for_no_entries():
    assert parse_experience("Just some text with no dated roles.") == []


# ---------------------------------------------------------------------------
# Total experience calculation
# ---------------------------------------------------------------------------

def test_compute_total_experience_sums_non_overlapping_roles():
    text = (
        "- Role A, Company A (Jan 2020 - Dec 2020)\n"
        "- Role B, Company B (Jan 2021 - Dec 2021)\n"
    )
    entries = parse_experience(text)
    summary = compute_total_experience(entries)
    assert summary.total_months == 24


def test_compute_total_experience_does_not_double_count_overlap():
    """Two fully overlapping 12-month roles should count as 12 months
    total, not 24 -- this is the core de-duplication requirement."""
    text = (
        "- Role A, Company A (Jan 2021 - Dec 2021)\n"
        "- Role B, Company B (Jan 2021 - Dec 2021)\n"
    )
    entries = parse_experience(text)
    summary = compute_total_experience(entries)
    assert summary.total_months == 12


def test_compute_total_experience_detects_gap():
    text = (
        "- Role A, Company A (Jan 2020 - Mar 2020)\n"
        "- Role B, Company B (Aug 2020 - Dec 2020)\n"
    )
    entries = parse_experience(text)
    summary = compute_total_experience(entries)
    assert len(summary.gaps) == 1


def test_compute_total_experience_detects_no_gap_for_consecutive_roles():
    text = (
        "- Role A, Company A (Jan 2020 - Mar 2020)\n"
        "- Role B, Company B (Apr 2020 - Dec 2020)\n"
    )
    entries = parse_experience(text)
    summary = compute_total_experience(entries)
    assert len(summary.gaps) == 0


def test_compute_total_experience_detects_overlap():
    text = (
        "- Role A, Company A (Jan 2020 - Aug 2020)\n"
        "- Role B, Company B (Jun 2020 - Dec 2020)\n"
    )
    entries = parse_experience(text)
    summary = compute_total_experience(entries)
    assert len(summary.overlaps) == 1


def test_compute_total_experience_handles_empty_list():
    summary = compute_total_experience([])
    assert summary.total_months == 0
    assert summary.gaps == []


# ---------------------------------------------------------------------------
# Title normalization & similarity
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("Senior Product Manager", "Product Manager"),
    ("Associate Product Manager", "Product Manager"),
    ("Product Manager", "Product Manager"),
    ("Frontend Engineer (MERN)", "MERN Stack Developer"),
])
def test_normalize_title_maps_variations(raw, expected):
    assert normalize_title(raw) == expected


def test_title_similarity_is_perfect_for_synonymous_titles():
    assert title_similarity("Senior Product Manager", "Product Manager") == 1.0


def test_title_similarity_is_low_for_unrelated_titles():
    assert title_similarity("Accountant", "MERN Stack Developer") < 0.4


# ---------------------------------------------------------------------------
# Relevance scoring
# ---------------------------------------------------------------------------

def test_score_experience_relevance_ranks_matching_role_higher():
    text = (
        "- Product Manager, Vantage (Jan 2022 - Present)\nOwned the roadmap.\n"
        "- Accountant, OldCo (Jan 2018 - Dec 2019)\nManaged ledgers.\n"
    )
    entries = parse_experience(text)
    result = score_experience_relevance(entries, "Product Manager", [])
    scores = {r.title: r.role_score for r in result.role_breakdown}
    assert scores["Product Manager"] > scores["Accountant"]


def test_score_experience_relevance_current_role_has_full_recency_weight():
    text = "- Product Manager, Vantage (Jan 2022 - Present)\nOwned the roadmap.\n"
    entries = parse_experience(text)
    result = score_experience_relevance(entries, "Product Manager", [])
    assert result.role_breakdown[0].recency_weight == 1.0


def test_score_experience_relevance_returns_zero_for_no_experience():
    result = score_experience_relevance([], "Product Manager", [])
    assert result.overall_score == 0.0


def test_score_experience_relevance_skill_overlap_increases_score():
    text_with_skills = "- Developer, Co (Jan 2022 - Present)\nBuilt APIs with React.js and Node.js.\n"
    text_without_skills = "- Developer, Co (Jan 2022 - Present)\nDid general development work.\n"

    entries_with = parse_experience(text_with_skills)
    entries_without = parse_experience(text_without_skills)

    result_with = score_experience_relevance(entries_with, "Developer", ["React.js", "Node.js"])
    result_without = score_experience_relevance(entries_without, "Developer", ["React.js", "Node.js"])

    assert result_with.overall_score > result_without.overall_score


# ---------------------------------------------------------------------------
# End-to-end on every sample resume
# ---------------------------------------------------------------------------

ALL_SAMPLES = sorted(SAMPLE_DIR.glob("*.txt"))


@pytest.mark.parametrize("resume_path", ALL_SAMPLES, ids=[p.name for p in ALL_SAMPLES])
def test_parse_experience_produces_entries_for_every_sample(resume_path):
    text = resume_path.read_text(encoding="utf-8")
    entries = parse_experience(text)
    assert len(entries) > 0


@pytest.mark.parametrize("resume_path", ALL_SAMPLES, ids=[p.name for p in ALL_SAMPLES])
def test_compute_total_experience_is_nonnegative_for_every_sample(resume_path):
    text = resume_path.read_text(encoding="utf-8")
    entries = parse_experience(text)
    summary = compute_total_experience(entries)
    assert summary.total_months >= 0
