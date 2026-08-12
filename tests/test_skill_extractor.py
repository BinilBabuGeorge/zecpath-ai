from pathlib import Path

import pytest

from parsers.skill_extractor import extract_skills
from parsers.skill_dictionary import SKILL_DICTIONARY, SKILL_STACKS

SAMPLE_DIR = Path("data/samples")


def _names(skills):
    return {s.name for s in skills}


# ---------------------------------------------------------------------------
# Exact / synonym matching
# ---------------------------------------------------------------------------

def test_extract_skills_finds_exact_comma_list():
    skills = extract_skills("React.js, Node.js, MongoDB, Docker")
    assert {"React.js", "Node.js", "MongoDB", "Docker"}.issubset(_names(skills))


def test_extract_skills_recognizes_common_synonyms():
    skills = extract_skills("ReactJS, NodeJS, Mongo DB")
    assert _names(skills) == {"React.js", "Node.js", "MongoDB"}


def test_extract_skills_exact_match_has_full_confidence():
    skills = extract_skills("Docker")
    assert skills[0].confidence == 1.0
    assert skills[0].method == "exact"


def test_extract_skills_does_not_double_match_substring_skill():
    """'SQL' should not also be extracted separately from inside 'Postgre SQL'."""
    skills = extract_skills("Postgre SQL")
    names = _names(skills)
    assert "PostgreSQL" in names
    assert "SQL" not in names


# ---------------------------------------------------------------------------
# Skill stack expansion
# ---------------------------------------------------------------------------

def test_extract_skills_expands_mern_stack():
    skills = extract_skills("Frontend Engineer (MERN) with 3 years experience")
    assert {"MongoDB", "Express.js", "React.js", "Node.js"}.issubset(_names(skills))


def test_extract_skills_stack_expansion_has_lower_confidence_than_exact():
    stack_skills = extract_skills("MERN developer")
    exact_skills = extract_skills("React.js developer")
    stack_confidence = [s.confidence for s in stack_skills if s.name == "React.js"][0]
    exact_confidence = [s.confidence for s in exact_skills if s.name == "React.js"][0]
    assert stack_confidence < exact_confidence


@pytest.mark.parametrize("stack_name", list(SKILL_STACKS.keys()))
def test_all_defined_stacks_expand_correctly(stack_name):
    skills = extract_skills(f"Experience with the {stack_name} stack")
    expected = set(SKILL_STACKS[stack_name])
    assert expected.issubset(_names(skills))


# ---------------------------------------------------------------------------
# Fuzzy spelling-variant matching
# ---------------------------------------------------------------------------

def test_extract_skills_catches_misspelling_via_fuzzy_match():
    skills = extract_skills("Kuberentes, Dcoker")
    names = _names(skills)
    # At least the closer misspelling should be caught
    assert "Kubernetes" in names


def test_fuzzy_matches_have_lower_confidence_than_exact():
    skills = extract_skills("Kuberentes")
    assert skills[0].method == "fuzzy"
    assert skills[0].confidence < 1.0


# ---------------------------------------------------------------------------
# Extraction from prose / scattered mentions (Day 8's known limitation)
# ---------------------------------------------------------------------------

def test_extract_skills_finds_skills_inside_prose_sentence():
    """This is the exact case that broke Day 8's section classifier --
    skills written as a sentence, not a comma list."""
    text = "Comfortable working across the stack, mainly using React and Node on the frontend and backend, with some exposure to Docker for containerization."
    skills = extract_skills(text)
    assert {"React.js", "Node.js", "Docker"}.issubset(_names(skills))


def test_extract_skills_finds_skills_mentioned_only_in_experience_bullets():
    text = "Built REST APIs with Node.js and Express, deployed via Docker on AWS."
    skills = extract_skills(text)
    assert {"Node.js", "Express.js", "Docker", "AWS", "REST APIs"}.issubset(_names(skills))


# ---------------------------------------------------------------------------
# Deduplication and confidence boosting
# ---------------------------------------------------------------------------

def test_extract_skills_deduplicates_repeated_mentions():
    text = "Python, Python, Python developer with Python experience"
    skills = extract_skills(text)
    python_matches = [s for s in skills if s.name == "Python"]
    assert len(python_matches) == 1


def test_extract_skills_tracks_all_mentions_of_a_skill():
    text = "Python developer. Wrote Python services. Uses Python daily."
    skills = extract_skills(text)
    python_skill = [s for s in skills if s.name == "Python"][0]
    assert len(python_skill.mentions) == 3


# ---------------------------------------------------------------------------
# Category / group assignment
# ---------------------------------------------------------------------------

def test_extract_skills_assigns_correct_group_for_business_skill():
    skills = extract_skills("Cold Calling, Salesforce, Negotiation")
    business_skills = [s for s in skills if s.group == "business"]
    assert len(business_skills) == 3


def test_extract_skills_assigns_correct_group_for_creative_skill():
    skills = extract_skills("Figma, Adobe XD, Prototyping")
    creative_skills = [s for s in skills if s.group == "creative"]
    assert len(creative_skills) == 3


def test_every_dictionary_entry_has_required_fields():
    for name, info in SKILL_DICTIONARY.items():
        assert "synonyms" in info
        assert "group" in info
        assert "category" in info
        assert info["group"] in {"tech", "business", "creative"}


# ---------------------------------------------------------------------------
# End-to-end on every sample resume
# ---------------------------------------------------------------------------

ALL_SAMPLES = sorted(SAMPLE_DIR.glob("*.txt"))


@pytest.mark.parametrize("resume_path", ALL_SAMPLES, ids=[p.name for p in ALL_SAMPLES])
def test_extract_skills_produces_results_for_every_sample(resume_path):
    text = resume_path.read_text(encoding="utf-8")
    skills = extract_skills(text)
    assert len(skills) > 0


@pytest.mark.parametrize("resume_path", ALL_SAMPLES, ids=[p.name for p in ALL_SAMPLES])
def test_extract_skills_all_confidences_in_valid_range(resume_path):
    text = resume_path.read_text(encoding="utf-8")
    skills = extract_skills(text)
    for s in skills:
        assert 0.0 <= s.confidence <= 1.0
