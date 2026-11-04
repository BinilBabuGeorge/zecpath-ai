import json
from datetime import date
from pathlib import Path

import pytest

from parsers.resume_readiness import MAX_WORDS, MIN_WORDS, ReadinessReport, check_resume_readiness

S = Path("data/samples")
JD = (S / "jds/jd_01_mern_developer.txt").read_text(encoding="utf-8")
AS_OF = date(2026, 10, 30)
FILLER = " ".join(["delivered"] * 90)
GOOD = f"Priya Rao\nSummary:\nBackend developer. {FILLER}\n{{skills}}\nReact, Node.js, MongoDB, Docker\n{{exp}}\n- Developer, Acme (Jan 2022 - Jan 2025)\n"


def codes(r):
    return {i.code for i in r.issues}


def rep(text, jd=None):
    return check_resume_readiness(text, jd, AS_OF)


# ---------------------------------------------------------------- the sample resumes
@pytest.mark.parametrize("name", sorted(p.stem for p in (S / "resumes").glob("*.txt")))
def test_every_sample_resume_is_readable(name):
    r = rep((S / "resumes" / f"{name}.txt").read_text(encoding="utf-8"))
    assert r.ready and r.sections_found["Skills"] and "NO_SKILLS_SECTION" not in codes(r)


def test_a_complete_resume_has_all_sections_dates_and_skills():
    r = rep((S / "resumes/resume_01_mern_developer.txt").read_text(encoding="utf-8"))
    assert all(r.sections_found[k] for k in ("Summary", "Skills", "Experience", "Education")) and r.experience_entries == 2 and r.experience_years == 5.3
    assert "React.js" in r.skills_found or "React" in r.skills_found


# ---------------------------------------------------------------- headings (Day 57 root cause)
@pytest.mark.parametrize("skills,exp", [("Skills:", "Experience:"), ("Technical Skills", "Work Experience"), ("KEY SKILLS", "PROFESSIONAL EXPERIENCE"), ("Core Competencies:", "Employment History")])
def test_common_heading_wordings_are_read(skills, exp):
    r = rep(GOOD.format(skills=skills, exp=exp))
    assert r.ready and r.sections_found["Skills"] and r.sections_found["Experience"] and r.experience_entries == 1 and codes(r) == set()


def test_a_missing_skills_heading_is_the_only_blocker():
    r = rep(GOOD.format(skills="Tools I use", exp="Experience:"))
    assert not r.ready and "NO_SKILLS_SECTION" in codes(r)
    assert [i.severity for i in r.issues if i.code == "NO_SKILLS_SECTION"] == ["blocker"]


def test_inline_skills_field_counts_as_a_skills_section():
    r = rep(f"Priya\nSummary:\nDev. {FILLER}\nSkills: React, Node.js, MongoDB\nExperience:\n- Dev, Acme (Jan 2022 - Jan 2025)\n")
    assert r.sections_found["Skills"] and r.ready


def test_unrecognized_headings_are_reported_but_not_blocking():
    r = rep(GOOD.format(skills="Skills:", exp="Experience:") + "PROJECTS\nShop app\nLanguages:\nEnglish\n")
    assert r.unrecognized_headings == ["PROJECTS", "Languages"] and "UNRECOGNIZED_HEADINGS" in codes(r) and r.ready


def test_plain_words_and_the_candidates_name_are_not_mistaken_for_headings():
    r = rep(GOOD.format(skills="Skills:", exp="Experience:") + "Chess\nReading\n")
    assert r.unrecognized_headings == []


# ---------------------------------------------------------------- experience and dates
def test_a_bad_date_is_explained_and_not_double_reported():
    r = rep(GOOD.format(skills="Skills:", exp="Experience:").replace("Jan 2022 - Jan 2025", "Mar 2024 - Jan 2023"))
    assert "DATE_PROBLEM" in codes(r) and "NO_DATED_ROLES" not in codes(r) and r.experience_years == 0.0


def test_an_undated_experience_section_asks_for_the_expected_format():
    r = rep(GOOD.format(skills="Skills:", exp="Experience:").replace("(Jan 2022 - Jan 2025)", ""))
    assert "NO_DATED_ROLES" in codes(r) and "Jan 2022 - Present" in next(i.suggestion for i in r.issues if i.code == "NO_DATED_ROLES")


def test_a_student_with_no_experience_gets_a_warning_not_a_blocker():
    r = rep((S / "resumes/resume_13_fresher_no_experience.txt").read_text(encoding="utf-8"))
    assert r.ready and "NO_EXPERIENCE_SECTION" in codes(r) and "Students can skip" in next(i.suggestion for i in r.issues if i.code == "NO_EXPERIENCE_SECTION")


def test_present_follows_as_of():
    t = GOOD.format(skills="Skills:", exp="Experience:").replace("Jan 2025", "Present")
    assert check_resume_readiness(t, None, date(2027, 1, 1)).experience_years > check_resume_readiness(t, None, date(2025, 6, 1)).experience_years


# ---------------------------------------------------------------- length and content
def test_empty_and_whitespace_text_is_the_only_issue_and_a_blocker():
    for t in ("", "   \n  "):
        r = rep(t)
        assert not r.ready and codes(r) == {"NO_TEXT"}


def test_length_limits():
    short = rep("Skills:\nReact\nExperience:\n- Dev, Acme (Jan 2022 - Jan 2025)")
    assert "VERY_SHORT" in codes(short) and short.word_count < MIN_WORDS
    long_text = GOOD.format(skills="Skills:", exp="Experience:") + " ".join(["word"] * MAX_WORDS)
    assert "VERY_LONG" in codes(rep(long_text))


def test_job_skill_gap_lists_only_missing_skills_and_warns_not_to_invent():
    r = rep(GOOD.format(skills="Skills:", exp="Experience:"), JD)
    gap = next(i for i in r.issues if i.code == "JOB_SKILLS_NOT_MENTIONED")
    assert r.skills_in_job_not_in_resume and "MongoDB" not in r.skills_in_job_not_in_resume and "Add them only if you genuinely have them" in gap.suggestion
    assert "JOB_SKILLS_NOT_MENTIONED" not in codes(rep(GOOD.format(skills="Skills:", exp="Experience:")))      # no job description -> no job hint


def test_a_skill_mentioned_only_in_the_experience_text_is_not_reported_missing():
    t = GOOD.format(skills="Skills:", exp="Experience:") + "- Built CI/CD pipelines with Jenkins\n"
    assert "CI/CD" not in rep(t, JD).skills_in_job_not_in_resume


# ---------------------------------------------------------------- the design rules
def test_the_report_never_contains_the_resume_text_or_a_score():
    secret = "Priya Rao"
    d = rep(GOOD.format(skills="Skills:", exp="Experience:") + "Contact: priya.rao@example.com +91 98765 43210\n", JD).to_dict()
    blob = json.dumps(d)
    assert secret not in blob and "example.com" not in blob and "98765" not in blob
    assert not any("score" in k or "weight" in k or "zone" in k for k in d)


def test_report_is_json_safe_deterministic_and_has_a_stable_shape():
    t = (S / "resumes/resume_01_mern_developer.txt").read_text(encoding="utf-8")
    a, b = rep(t, JD).to_dict(), rep(t, JD).to_dict()
    assert a == b and json.dumps(a, allow_nan=False)
    assert set(a) == {"ready", "sections_found", "unrecognized_headings", "experience_entries", "experience_years", "skills_found", "skills_in_job_not_in_resume", "word_count", "issues"}


def test_every_issue_has_a_plain_message_and_a_suggestion_and_valid_severity():
    r = rep("Tools\nReact\n")
    assert r.issues and all(i.message and i.suggestion and i.severity in ("blocker", "warning", "tip") for i in r.issues)


def test_input_must_be_text():
    for bad in (None, 5, ["a"], b"bytes"):
        with pytest.raises(TypeError):
            check_resume_readiness(bad)
    with pytest.raises(TypeError):
        check_resume_readiness("text", 7)


def test_it_does_not_change_what_present_means_afterwards():
    from parsers import experience_parser
    check_resume_readiness(GOOD.format(skills="Skills:", exp="Experience:"), None, date(2020, 1, 1))
    assert experience_parser._REFERENCE_DATE is None
