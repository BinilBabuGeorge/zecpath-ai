"""Day 57 -- the public API boundary: the four service classes. Contract: run() never raises, every response is JSON-safe and
one of two shapes (success / error), invalid input is refused with a code and a field, and nothing is invented."""
import dataclasses
import json
import math
from enum import Enum
from pathlib import Path

import pytest

from ats_engine.service import ATSService
from interview_ai.service import InterviewIntelligenceService
from scoring.service import DecisionScoringService
from screening_ai.service import ScreeningService
from utils.base_service import API_VERSION, MAX_ITEMS, MAX_TEXT_CHARS, BaseAIService, ServiceInputError, to_json_safe

SAMPLES = Path("data/samples")
JD = (SAMPLES / "jds" / "jd_01_mern_developer.txt").read_text(encoding="utf-8")
RESUME = (SAMPLES / "resumes" / "resume_01_mern_developer.txt").read_text(encoding="utf-8")
ALL = [ATSService, ScreeningService, InterviewIntelligenceService, DecisionScoringService]
ENVELOPE = {"service", "model_version", "api_version", "status"}
GOOD = "I work well in teams and communicate clearly; on my last project I led a migration and mentored two juniors."
GOOD_TURNS = [{"text": t} for t in ["I'm Nikhil, a backend developer from Pune.", "B.Tech in Computer Science from PES University.", "I have about three years of backend experience.",
                                    "Python, Django, PostgreSQL and some React.", "I'm currently in Pune and happy to relocate.", "I'm expecting around ten lakhs per annum.",
                                    "My notice period is sixty days."]] * 2


def assert_json_safe(r):
    json.dumps(r, allow_nan=False)


def err(r, code, field=None):
    assert r["status"] == "error" and r["error"]["code"] == code, r
    if field:
        assert r["error"]["field"] == field
    assert ENVELOPE <= set(r)
    assert_json_safe(r)


# ------------------------------------------------------------------ envelope and boundary
BAD_PAYLOADS = [None, "text", 42, [], [1, 2], True, {}, {"x": 1}, {"resume_text": None}, {"resume_text": 5, "job_description": 5},
                {"ats_score": float("nan")}, {"turns": "abc"}, {"answers": 7}, {"interview_type": None}, {"candidate_id": ["a"]}]


@pytest.mark.parametrize("cls", ALL)
@pytest.mark.parametrize("payload", BAD_PAYLOADS)
def test_run_never_raises_and_always_returns_a_json_safe_envelope(cls, payload):
    r = cls().run(payload)
    assert isinstance(r, dict) and r["status"] in ("success", "error") and ENVELOPE <= set(r)
    assert r["api_version"] == API_VERSION
    assert_json_safe(r)
    if r["status"] == "error":
        assert set(r["error"]) == {"code", "message", "field"} and r["error"]["message"]


@pytest.mark.parametrize("cls", ALL)
def test_non_dict_payload_is_invalid_payload(cls):
    err(cls().run("hello"), "invalid_payload")
    err(cls().run(None), "invalid_payload")


def test_process_still_raises_typed_errors_for_direct_callers():
    with pytest.raises(ServiceInputError) as e:
        DecisionScoringService().process({})
    assert e.value.code == "missing_field"


def test_an_unexpected_bug_is_logged_but_never_leaks_internals():
    class Broken(BaseAIService):
        def process(self, payload):
            raise RuntimeError("secret database password is hunter2")
    r = Broken().run({})
    err(r, "internal_error")
    assert "hunter2" not in json.dumps(r) and "RuntimeError" not in json.dumps(r)


def test_to_json_safe():
    class Color(Enum):
        RED = "red"

    @dataclasses.dataclass
    class P:
        x: float
        c: Color
    out = to_json_safe({"a": float("nan"), "b": float("inf"), "c": (1, 2), "d": {3, 1}, "e": P(1.5, Color.RED), "f": Color.RED, "g": None, "h": True})
    assert out == {"a": None, "b": None, "c": [1, 2], "d": [1, 3], "e": {"x": 1.5, "c": "red"}, "f": "red", "g": None, "h": True}
    json.dumps(out, allow_nan=False)
    deep = cur = {}
    for _ in range(40):
        cur["n"] = {}; cur = cur["n"]
    json.dumps(to_json_safe(deep))


# ------------------------------------------------------------------------------- ATS
def test_ats_engine_mode_returns_the_real_score_zone_and_components():
    r = ATSService().run({"resume_text": RESUME, "job_description": JD})
    assert r["status"] == "success" and r["scoring_mode"] == "ats_engine"
    assert 0 <= r["ats_score"] <= 100 and r["zone"] in ("shortlist", "review", "reject")
    assert {c["name"] for c in r["components"]} >= {"skill_match", "semantic"} and r["warnings"] == []


def test_ats_score_is_deterministic_and_matches_the_engine_for_the_same_pair():
    from parsers.ats_scoring_engine import score_candidate
    from parsers.semantic_matcher import SemanticMatcher
    from parsers.experience_parser import reference_date
    from datetime import date
    a = ATSService().run({"resume_text": RESUME, "job_description": JD})
    b = ATSService().run({"resume_text": RESUME, "job_description": JD})
    assert a == b
    with reference_date(date.today()):
        expected = score_candidate(RESUME, JD, SemanticMatcher([RESUME, JD])).overall_score
    assert a["ats_score"] == round(expected, 2)


def test_same_resume_scores_the_same_under_heading_synonyms():          # before: "Technical Skills" scored 14.9 vs 50.7
    base = "Summary:\nMERN developer.\n{s}\nReact.js, Node.js, MongoDB, Express.js, REST API, Git\n{e}\n- Developer, Acme (Jan 2022 - Jan 2025)\n"
    scores = {ATSService().run({"resume_text": base.format(s=s, e=e), "job_description": JD})["ats_score"]
              for s, e in [("Skills:", "Experience:"), ("Technical Skills", "Work Experience"), ("KEY SKILLS", "PROFESSIONAL EXPERIENCE")]}
    assert len(scores) == 1


def test_a_job_description_without_requirements_is_capped_at_review_with_a_warning():
    r = ATSService().run({"resume_text": "Skills:\nReact", "job_description": "We need a developer with React."})
    assert r["zone"] == "review" and any("No skills could be compared" in w for w in r["warnings"])


def test_an_empty_resume_scores_low_with_a_warning_not_an_error():
    r = ATSService().run({"resume_text": "", "job_description": JD})
    assert r["status"] == "success" and r["ats_score"] < 30 and r["zone"] != "shortlist" and any("empty" in w for w in r["warnings"])


def test_ats_requires_something_to_score_against():
    err(ATSService().run({"resume_text": "React"}), "missing_field", "job_description")


def test_ats_input_validation():
    err(ATSService().run({"resume_text": 123, "job_description": JD}), "invalid_input", "resume_text")
    err(ATSService().run({"resume_text": "x", "job_description": ""}), "invalid_input", "job_description")
    err(ATSService().run({"resume_text": "x" * (MAX_TEXT_CHARS + 1), "job_description": JD}), "too_large", "resume_text")
    err(ATSService().run({"resume_text": "x", "job_requirements": "react"}), "invalid_input", "job_requirements")
    err(ATSService().run({"resume_text": "x", "job_requirements": [1, 2]}), "invalid_input", "job_requirements")
    err(ATSService().run({"resume_text": "x", "job_requirements": ["a"] * (MAX_ITEMS + 1)}), "too_large", "job_requirements")


def test_legacy_keyword_mode_still_works_and_says_it_is_deprecated():
    r = ATSService().run({"resume_text": "React Node.js", "job_requirements": ["react", "node.js", "python", "sql"]})
    assert r["scoring_mode"] == "keyword_coverage" and r["ats_score"] == 50.0 and r["matched_keywords"] == ["react", "node.js"]
    assert any("Deprecated" in w for w in r["warnings"])


def test_an_injected_matcher_is_used_for_batch_consistency():
    class Spy:
        calls = 0
        def __init__(self, real): self.real = real
        def __getattr__(self, n):
            Spy.calls += 1
            return getattr(self.real, n)
    from parsers.semantic_matcher import SemanticMatcher
    ATSService(matcher=Spy(SemanticMatcher([RESUME, JD]))).run({"resume_text": RESUME, "job_description": JD})
    assert Spy.calls > 0


# ------------------------------------------------------------------------- decision / scoring
FULL_TECH = {"role_type": "technical", "ats_score": 70, "screening_score": 85, "hr_interview_score": 88, "technical_score": 92, "machine_test_score": 90, "ats_zone": "shortlist"}


def test_decision_with_complete_strong_evidence_selects_and_is_a_recommendation():
    r = DecisionScoringService().run({**FULL_TECH, "candidate_id": "C1"})
    assert r["decision"] == "selected" and r["hold_kind"] is None and r["human_confirmation_required"] is False and r["status"] == "success"
    assert 0 <= r["hiring_fit_score"] <= 100 and r["reasons"]


def test_a_missing_round_is_absent_not_zero():                   # before: {"ats_score": 90} -> rejected
    r = DecisionScoringService().run({"ats_score": 90})
    assert r["decision"] != "rejected" and r["provisional"] is True and "screening" in r["missing_rounds"]


def test_incomplete_evidence_is_never_a_rejection():             # before: two weak rounds -> "rejected"
    r = DecisionScoringService().run({"role_type": "technical", "ats_score": 10, "screening_score": 10})
    assert r["decision"] == "hold_review" and r["hold_kind"] == "pending_evidence"


def test_a_technical_role_without_a_machine_test_is_pending_not_selected():
    r = DecisionScoringService().run({**FULL_TECH, "machine_test_score": None})
    assert r["decision"] == "hold_review" and "machine_test" in r["missing_rounds"]


def test_complete_weak_evidence_recommends_rejection_for_a_person_to_confirm():
    r = DecisionScoringService().run({"role_type": "technical", "ats_score": 5, "screening_score": 5, "hr_interview_score": 5, "technical_score": 5, "machine_test_score": 5})
    assert r["decision"] == "rejected" and r["human_confirmation_required"] is True and r["automated_action"] in (None, "none")


def test_an_ats_reject_zone_blocks_selection_even_with_strong_interviews():     # Day 56 finding F1, at the API
    strong = {"role_type": "non_technical", "ats_score": 70, "screening_score": 90, "hr_interview_score": 90}
    assert DecisionScoringService().run({**strong, "ats_zone": "shortlist"})["decision"] == "selected"
    r = DecisionScoringService().run({**strong, "ats_zone": "reject"})
    assert r["decision"] == "hold_review" and r["hold_kind"] == "selection_blocked" and r["human_review_required"]
    assert any("ATS zone is REJECT" in x for x in r["human_review_reasons"])


def test_legacy_aliases_and_ignored_keys_are_reported():
    r = DecisionScoringService().run({"role_type": "non_technical", "ats_score": 60, "screening_score": 70, "communication_score": 85, "behavior_score": 99})
    assert r["status"] == "success" and len(r["warnings"]) == 2
    assert any("communication_score" in w for w in r["warnings"]) and any("behavior_score" in w for w in r["warnings"])
    err(DecisionScoringService().run({"ats_score": 60, "hr_interview_score": 80, "communication_score": 70}), "invalid_input", "communication_score")


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), 101, -1, "high", True, [50]])
def test_invalid_scores_are_refused_with_the_field_name(bad):    # before: NaN passed through to the output
    err(DecisionScoringService().run({"ats_score": 50, "screening_score": bad}), "invalid_score", "screening_score")


def test_decision_input_validation():
    err(DecisionScoringService().run({}), "missing_field")
    err(DecisionScoringService().run({"ats_score": None}), "missing_field")
    err(DecisionScoringService().run({"ats_score": 50, "role_type": "astronaut"}), "unsupported_value", "role_type")
    err(DecisionScoringService().run({"ats_score": 50, "ats_zone": "maybe"}), "unsupported_value", "ats_zone")
    err(DecisionScoringService().run({"ats_score": 50, "candidate_id": 7}), "invalid_input", "candidate_id")


def test_decision_is_deterministic_and_json_safe():
    a, b = DecisionScoringService().run(FULL_TECH), DecisionScoringService().run(FULL_TECH)
    assert a == b
    assert_json_safe(a)


# ------------------------------------------------------------------------------ screening
def test_no_turns_means_not_started_not_a_fake_answered_call():  # before: call_status "answered", score 0
    r = ScreeningService().run({"candidate_id": "C1"})
    assert r["call_status"] == "not_started" and r["screening_score"] is None and r["turns_used"] == 0 and r["warnings"]


def test_a_conversation_is_scored_by_the_real_pipeline():
    r = ScreeningService().run({"candidate_id": "C1", "turns": GOOD_TURNS})
    assert r["status"] == "success" and r["call_status"] in ("completed", "incomplete") and 0 < r["screening_score"] <= 100
    assert set(r["categories_answered"]) | set(r["categories_missing"]) == {"introduction", "education", "experience", "skills", "location", "salary", "notice_period"}


def test_a_silent_caller_is_ended_not_walked_through_every_question():
    r = ScreeningService().run({"candidate_id": "C1", "turns": [{"text": "", "is_silent": True, "confidence": 0.0}] * 10})
    assert r["call_status"] == "ended_early" and r["screening_score"] < 50


@pytest.mark.parametrize("turns,field", [([1, 2], "turns[0]"), ([{"text": 5}], "turns[0]"), ([{"text": "hi", "confidence": float("nan")}], "turns[0].confidence"),
                                         ([{"text": "hi", "confidence": 2.0}], "turns[0].confidence"), ([{"text": "hi", "confidence": True}], "turns[0].confidence")])
def test_screening_turn_validation(turns, field):
    err(ScreeningService().run({"turns": turns}), "invalid_input", field)


def test_screening_other_validation():
    err(ScreeningService().run({"turns": "hello"}), "invalid_input", "turns")
    err(ScreeningService().run({"candidate_id": 5}), "invalid_input", "candidate_id")
    err(ScreeningService().run({"turns": [{"text": "hi"}] * (MAX_ITEMS + 1)}), "too_large", "turns")


# ------------------------------------------------------------------------------ interview
def test_interview_with_no_answers_is_not_started_with_null_scores():     # before: placeholder transcript and zeros
    for t in ("hr", "technical"):
        r = InterviewIntelligenceService().run({"interview_type": t, "experience_years": 3, "answers": []})
        assert r["interview_status"] == "not_started" and r["communication_score"] is None and "transcript" not in r


def test_hr_answers_are_scored_by_the_real_engine():
    r = InterviewIntelligenceService().run({"interview_type": "hr", "answers": [GOOD] * 6})
    assert r["interview_status"] == "scored" and r["hr_score"] > 70 and r["answers_scored"] == 6 and r["non_substantive_answers"] == 0


def test_content_free_hr_answers_score_low_and_are_counted():
    r = InterviewIntelligenceService().run({"interview_type": "hr", "answers": ["yes"] * 6})
    assert r["hr_score"] < 50 and r["non_substantive_answers"] == 5


def test_extra_answers_are_ignored_with_a_warning():
    r = InterviewIntelligenceService().run({"interview_type": "hr", "answers": [GOOD] * 9})
    assert r["answers_scored"] == 6 and r["answers_ignored"] == 3 and r["warnings"]


def test_technical_interview_reports_the_tier_and_scores():
    r = InterviewIntelligenceService().run({"interview_type": "technical", "domain": "mern", "experience_years": 3, "answers": ["I build REST APIs with Express and MongoDB."] * 5})
    assert r["interview_status"] == "scored" and r["tier"] == "intermediate" and 0 <= r["technical_score"] <= 100


@pytest.mark.parametrize("payload,code,field", [
    ({"interview_type": "karaoke"}, "unsupported_value", "interview_type"),
    ({"interview_type": "final"}, "unsupported_value", "interview_type"),
    ({"interview_type": "machine_test"}, "unsupported_value", "interview_type"),
    ({"interview_type": "technical", "answers": ["x"]}, "missing_field", "experience_years"),
    ({"interview_type": "technical", "experience_years": float("nan"), "answers": ["x"]}, "invalid_input", None),
    ({"interview_type": "technical", "experience_years": -2, "answers": ["x"]}, "invalid_input", None),
    ({"interview_type": "technical", "experience_years": 3, "domain": "cobol", "answers": ["x"]}, "unsupported_value", "domain"),
    ({"interview_type": "hr", "answers": [None]}, "invalid_input", "answers[0]"),
    ({"interview_type": "hr", "answers": "text"}, "invalid_input", "answers"),
    ({"interview_type": "hr", "answers": ["x" * 20_001]}, "too_large", "answers[0]"),
    ({"interview_type": "hr", "role_type": "wizard", "answers": ["x"]}, "unsupported_value", "role_type"),
])
def test_interview_validation(payload, code, field):
    err(InterviewIntelligenceService().run(payload), code, field)
