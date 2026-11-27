"""Day 65 tests: final polish. Scoring consistency, readable recruiter output, clear errors, silent calls, CI and line endings."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ats_engine.service import ATSService
from parsers.answer_intent_engine import extract_experience_years
from screening_ai.service import ScreeningService

ROOT = Path(__file__).resolve().parent.parent
REPORTS = sorted((ROOT / "data" / "demo_dataset" / "simulated" / "reports").glob("DC-*.md"))


# ------------------------------------------------------------------------------------------------------ scoring consistency (ACC-10)
@pytest.mark.parametrize("text,years", [
    ("I have six months of internship experience", 0.5), ("I have 6 months experience", 0.5), ("18 months", 1.5),
    ("one year six months", 1.5), ("two and a half years", 2.5), ("3 years", 3.0), ("5+ years", 5.0), ("fifteen qualified demos a month", 15.0)])
def test_experience_is_read_in_years_using_the_unit(text, years):
    assert extract_experience_years(text) == years


def test_text_without_a_number_stays_unknown():
    assert extract_experience_years("I am a fresher") is None


def test_the_same_input_always_gives_the_same_score():
    jd = "Requirements: React, Node.js, MongoDB. 3 years experience."
    cv = "Skills: React, Node.js, MongoDB\nExperience: 4 years as a full stack developer"
    first = [ATSService().run({"resume_text": cv, "job_description": jd}) for _ in range(3)]
    assert first[0] == first[1] == first[2]
    turns = [{"text": "I am Asha, a developer from Kochi.", "confidence": 0.9}]
    a, b = ScreeningService().run({"candidate_id": "C", "turns": turns}), ScreeningService().run({"candidate_id": "C", "turns": turns})
    assert a == b


# ------------------------------------------------------------------------------------------------------ recruiter-facing output (UX-02)
def _summary_lines(text: str):
    head = text.split("## Strengths")[0]
    return [ln for ln in head.splitlines() if ln.startswith("- Strongest areas") or ln.startswith("- Main concerns")]


def test_every_report_summary_line_is_a_finished_sentence():
    assert len(REPORTS) == 30
    for f in REPORTS:
        lines = _summary_lines(f.read_text(encoding="utf-8"))
        assert len(lines) == 2, f.name
        for ln in lines:
            assert ln.rstrip().endswith("."), (f.name, ln[-60:])
            assert ln.count("(") == ln.count(")"), (f.name, ln)
            assert len(ln) < 190, (f.name, len(ln))


def test_summary_concerns_use_plain_words_not_codes_or_long_sentences():
    for f in REPORTS:
        for ln in _summary_lines(f.read_text(encoding="utf-8")):
            assert "An average hides this" not in ln and "special-casing" not in ln


# ------------------------------------------------------------------------------------------------------ error handling (UX-03, UX-04)
def test_ats_errors_name_the_field_and_say_what_to_send():
    for payload in ({}, {"resume_text": "x"}, {"resume_text": "", "job_description": "the and of"}):
        r = ATSService().run(payload)
        assert r["status"] == "error" and r["error"]["field"] == "job_description"
        assert any(w in r["error"]["message"] for w in ("required", "must"))


def test_a_body_that_is_not_an_object_names_the_body():
    r = ATSService().run([])
    assert r["error"]["code"] == "invalid_payload" and r["error"]["field"] == "request_body"


def test_a_turn_with_no_text_is_silence_and_gets_no_score():
    r = ScreeningService().run({"candidate_id": "C", "turns": [{"confidence": 0.5}]})
    assert r["status"] == "success" and r["screening_score"] is None and r["call_status"] == "not_started"
    assert r["warnings"] and "retry" in r["warnings"][0]


def test_a_real_answer_is_still_scored():
    r = ScreeningService().run({"candidate_id": "C", "turns": [{"text": "I am Asha, a developer based in Kochi.", "confidence": 0.9}]})
    assert r["screening_score"] is not None and r["call_status"] != "not_started"


# ------------------------------------------------------------------------------------------------------ engineering (ENG-01, ENG-04)
def test_a_ci_workflow_runs_pytest_on_both_python_versions():
    wf = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    assert "pytest" in wf and "3.11" in wf and "3.12" in wf and "push" in wf


def test_gitattributes_normalises_line_endings():
    assert "* text=auto" in (ROOT / ".gitattributes").read_text(encoding="utf-8")


def test_the_before_and_after_table_is_committed_and_all_targets_it_names_are_met():
    data = json.loads((ROOT / "data" / "review" / "day65_before_after.json").read_text(encoding="utf-8"))
    assert data["rows"] and all(r["met"] for r in data["rows"]), [r["id"] for r in data["rows"] if not r["met"]]
