"""
Edge-Case Sweep and Output Sanity Checks (Day 57)

WHAT THIS IS: a systematic way to find bugs instead of waiting for them. It feeds
awkward-but-realistic inputs (empty, huge, unicode, out-of-range, contradictory,
NaN) into the PUBLIC entry point of each engine and classifies what happens.

HOW A CASE IS JUDGED. Each case states what a correct system should do:
  graceful -- return a sensible result (e.g. an empty resume scores low, it must not crash)
  reject   -- refuse with a clear ValueError/TypeError (e.g. a score of NaN)
  either   -- either of the above is fine; only a crash or a nonsense result is wrong
and may carry a `check(result)` that returns a problem string for a result that
"worked" but is wrong (a score outside 0-100, an empty answer scored as good,
a 126-year career accepted, two identical jobs counted twice).

OUTCOMES: ok | rejected_cleanly            -> pass
          crash (unexpected exception type) | bad_output | silently_accepted
          | timeout                         -> fail

EVERY SWEEP RESULT IS EVIDENCE, NOT A PROOF. A sweep of ~60 hand-chosen cases finds
the bugs those cases reach; it does not show the absence of others. The point of
running it BEFORE and AFTER the Day 57 fixes is that the difference is measured.
"""

from __future__ import annotations

import dataclasses
import json
import math
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)

PASS_STATUSES = ("ok", "rejected_cleanly")
TIMEOUT_SECONDS = 20.0
CLEAN_REJECTIONS = (ValueError, TypeError)


@dataclass
class EdgeCase:
    id: str
    area: str
    description: str
    fn: Callable[[], Any]
    expect: str = "graceful"                         # graceful | reject | either
    check: Optional[Callable[[Any], Optional[str]]] = None


@dataclass
class CaseResult:
    id: str
    area: str
    description: str
    status: str
    detail: str = ""
    ms: float = 0.0

    @property
    def passed(self) -> bool:
        return self.status in PASS_STATUSES


# --------------------------------------------------------------- output sanity
def find_bad_numbers(obj: Any, path: str = "result", depth: int = 0, limit: int = 8) -> List[str]:
    """NaN / infinity anywhere, and any *score*/*percentage* float outside 0-100. Walks dataclasses, dicts, lists, enums."""
    out: List[str] = []
    if depth > 6 or len(out) >= limit:
        return out
    if isinstance(obj, bool) or obj is None or isinstance(obj, (str, bytes, Enum)):
        return out
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            out.append(f"{path} is {obj}")
        return out
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        items = [(f.name, getattr(obj, f.name, None)) for f in dataclasses.fields(obj)]
    elif isinstance(obj, dict):
        items = [(str(k), v) for k, v in obj.items()]
    elif isinstance(obj, (list, tuple)):
        items = [(f"[{i}]", v) for i, v in enumerate(obj[:50])]
    else:
        return out
    for name, v in items:
        p = f"{path}.{name}"
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            low = name.lower()
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                out.append(f"{p} is {v}")
            elif ("score" in low or "percentage" in low) and not ("weight" in low or "max" in low or "std" in low or "cutoff" in low or "threshold" in low) and not (0.0 <= v <= 100.0):
                out.append(f"{p}={v} outside 0-100")
        else:
            out.extend(find_bad_numbers(v, p, depth + 1, limit))
        if len(out) >= limit:
            break
    return out[:limit]


# ----------------------------------------------------------------------- runner
def _call_with_timeout(fn: Callable[[], Any], seconds: float):
    box: Dict[str, Any] = {}

    def target() -> None:
        try:
            box["value"] = fn()
        except BaseException as exc:          # noqa: BLE001 - the sweep must classify, not crash
            box["error"] = exc
    t = threading.Thread(target=target, daemon=True)
    t0 = time.perf_counter()
    t.start(); t.join(seconds)
    ms = (time.perf_counter() - t0) * 1000
    if t.is_alive():
        return "timeout", None, ms
    return ("error", box["error"], ms) if "error" in box else ("value", box.get("value"), ms)


def run_case(case: EdgeCase) -> CaseResult:
    kind, payload, ms = _call_with_timeout(case.fn, TIMEOUT_SECONDS)
    mk = lambda status, detail="": CaseResult(case.id, case.area, case.description, status, detail, round(ms, 1))
    if kind == "timeout":
        return mk("timeout", f"no result after {TIMEOUT_SECONDS:.0f}s")
    if kind == "error":
        exc = payload
        if isinstance(exc, CLEAN_REJECTIONS) and case.expect in ("reject", "either"):
            return mk("rejected_cleanly", f"{type(exc).__name__}: {str(exc)[:90]}")
        return mk("crash", f"{type(exc).__name__}: {str(exc)[:110]}")
    if case.expect == "reject":
        return mk("silently_accepted", "invalid input was accepted without complaint")
    bad = find_bad_numbers(payload)
    if bad:
        return mk("bad_output", "; ".join(bad[:3]))
    if case.check:
        problem = case.check(payload)
        if problem:
            return mk("bad_output", problem)
    return mk("ok")


def run_sweep(cases: List[EdgeCase]) -> List[CaseResult]:
    return [run_case(c) for c in cases]


def summarise(results: List[CaseResult]) -> Dict[str, Any]:
    by_status: Dict[str, int] = {}
    for r in results:
        by_status[r.status] = by_status.get(r.status, 0) + 1
    areas: Dict[str, Dict[str, int]] = {}
    for r in results:
        a = areas.setdefault(r.area, {"cases": 0, "failed": 0})
        a["cases"] += 1
        a["failed"] += 0 if r.passed else 1
    return {"cases": len(results), "passed": sum(r.passed for r in results), "failed": sum(not r.passed for r in results),
            "by_status": by_status, "by_area": areas}


# ----------------------------------------------------------------------- cases
def build_cases(matcher: Any, jd_text: str, resume_text: str) -> List[EdgeCase]:
    """The sweep. Imports are local so the sweep still loads if a module is being changed."""
    from parsers.ats_scoring_engine import score_candidate
    from parsers.cross_round_aggregation_engine import RoundResult, compute_cross_round_score
    from parsers.experience_parser import compute_total_experience, parse_experience
    from parsers.final_recommendation_engine import decide
    from parsers.hr_interview_question_bank import ExperienceLevel, InterviewSession, RoleType
    from parsers.hr_interview_scoring_engine import score_hr_interview
    from parsers.resume_extractor import extract_resume
    from parsers.screening_pipeline import run_screening_call
    from parsers.speech_to_text import RawSTTResult
    from parsers.technical_interview_question_bank import TechnicalDomain, TechnicalInterviewSession
    from parsers.technical_skill_scoring_engine import build_technical_evaluation_report
    import os, tempfile

    cases: List[EdgeCase] = []
    add = lambda *a, **k: cases.append(EdgeCase(*a, **k))

    # ---------------- ATS
    def ats(resume: Any, jd: Any = jd_text) -> Any:
        return lambda: score_candidate(resume, jd, matcher)

    def low_for_empty(r: Any) -> Optional[str]:
        return f"an empty resume scored {r.overall_score:.1f}" if r.overall_score > 30 else None
    add("ats_empty_resume", "ats", "empty resume text", ats(""), "graceful", low_for_empty)
    add("ats_whitespace_resume", "ats", "whitespace-only resume", ats("  \n\t  \n"), "graceful", low_for_empty)
    add("ats_none_resume", "ats", "resume is None", ats(None), "reject")
    add("ats_none_jd", "ats", "job description is None", ats(resume_text, None), "reject")
    add("ats_empty_jd", "ats", "empty job description", ats(resume_text, ""), "either")
    add("ats_one_char", "ats", "one-character resume", ats("x"), "graceful", low_for_empty)
    add("ats_huge_resume", "ats", "300k-character resume", ats(resume_text * 150), "graceful")
    add("ats_unicode", "ats", "Malayalam/Hindi/emoji resume", ats("മലയാളം ഡെവലപ്പർ हिन्दी अनुभव 😀 React Node.js"), "graceful")
    add("ats_symbols_only", "ats", "symbols only", ats("@@@ ### $$$ %%% ^^^ &&&"), "graceful", low_for_empty)
    add("ats_numbers_only", "ats", "numbers only", ats("2019 2020 2021 2022 12345 67890"), "graceful", low_for_empty)
    add("ats_html_injection", "ats", "HTML/script in resume", ats("<script>alert(1)</script> React developer <b>MongoDB</b>"), "graceful")
    add("ats_non_string", "ats", "resume is a number", ats(12345), "reject")

    # ---------------- experience parsing
    def exp(text: str) -> Callable[[], Any]:
        return lambda: compute_total_experience(parse_experience(text))
    add("exp_end_before_start", "experience", "end date earlier than start", exp("Experience:\n- Engineer, Acme (Mar 2024 - Jan 2023)\n"), "graceful",
        lambda r: f"negative or impossible total {r.total_years}" if r.total_years < 0 or r.total_years > 1.5 else None)
    add("exp_future_start", "experience", "job starting in 2031", exp("Experience:\n- Engineer, Acme (Jan 2031 - Present)\n"), "graceful",
        lambda r: f"future job counted as {r.total_years} years" if r.total_years != 0 else None)
    add("exp_duplicate_roles", "experience", "two identical 2-year roles", exp("Experience:\n- Engineer, Acme (Jan 2020 - Jan 2022)\n- Engineer, Acme (Jan 2020 - Jan 2022)\n"), "graceful",
        lambda r: f"two identical roles counted as {r.total_years} years (double counted)" if r.total_years > 2.6 else None)
    add("exp_year_only", "experience", "year-only dates", exp("Experience:\n- Engineer, Acme (2019 - 2022)\n"), "graceful",
        lambda r: f"2019-2022 gave {r.total_years} years" if not 2.5 <= r.total_years <= 3.5 else None)
    add("exp_garbage_dates", "experience", "non-date text in the date slot", exp("Experience:\n- Engineer, Acme (Foo 2020 - Bar)\n"), "graceful")
    add("exp_implausible", "experience", "career starting in 1900", exp("Experience:\n- Engineer, Acme (Jan 1900 - Present)\n"), "graceful",
        lambda r: f"accepted a {r.total_years}-year career" if r.total_years > 60 else None)
    add("exp_many_entries", "experience", "500 job entries", exp("Experience:\n" + "".join(f"- Role{i}, Co{i} (Jan 2010 - Jan 2011)\n" for i in range(500))), "graceful",
        lambda r: f"500 one-year jobs in one year counted as {r.total_years}y" if r.total_years > 20 else None)
    add("exp_empty", "experience", "empty text", exp(""), "graceful")

    # ---------------- upload
    def upload(name: str, data: bytes) -> Callable[[], Any]:
        def go() -> Any:
            d = tempfile.mkdtemp(); p = os.path.join(d, name)
            open(p, "wb").write(data)
            return extract_resume(p)
        return go
    add("up_txt", "upload", ".txt file", upload("a.txt", b"hello"), "reject")
    add("up_doc", "upload", "legacy .doc file", upload("a.doc", b"\xd0\xcf\x11\xe0"), "reject")
    add("up_corrupt_pdf", "upload", "corrupt PDF", upload("a.pdf", b"not a pdf"), "reject")
    add("up_zero_docx", "upload", "zero-byte DOCX", upload("a.docx", b""), "reject")
    add("up_missing", "upload", "file that does not exist", lambda: extract_resume("/nonexistent/none.docx"), "reject")

    # ---------------- screening conversation
    def call(turns: List[Any], **kw: Any) -> Callable[[], Any]:
        return lambda: run_screening_call(turns, candidate_id="edge", job_role="edge", **kw)
    T = lambda t, c=0.9, s=False: RawSTTResult(text=t, confidence=c, is_silent=s)

    def weak(r: Any) -> Optional[str]:
        s = r.scoring_result.total_score
        return f"scored {s:.1f} for nothing useful" if s >= 50 else None

    def ended(r: Any) -> Optional[str]:
        return "call neither completed nor ended early" if not (r.controller.is_call_complete or r.controller.call_ended_early) else weak(r)
    add("scr_no_turns", "screening", "no turns at all", call([]), "graceful", weak)
    add("scr_all_silent", "screening", "10 silent turns", call([T("", 0.0, True) for _ in range(10)]), "graceful", ended)
    add("scr_empty_text", "screening", "10 empty-text turns", call([T("") for _ in range(10)]), "graceful", ended)
    add("scr_gibberish_loop", "screening", "30 turns of 'banana'", call([T("banana") for _ in range(30)]), "graceful", ended)
    add("scr_repeat_same", "screening", "same sentence 20 times", call([T("I am a developer.") for _ in range(20)]), "graceful")
    add("scr_numbers_only", "screening", "numbers only", call([T("12345 67890") for _ in range(8)]), "graceful", weak)
    add("scr_huge_text", "screening", "20k-character answers", call([T("I work with React and Node. " * 800) for _ in range(7)]), "graceful")
    add("scr_unicode", "screening", "Malayalam answers", call([T("ഞാൻ ഒരു ഡെവലപ്പർ ആണ്") for _ in range(8)]), "graceful")
    add("scr_extra_turns", "screening", "50 turns (more than questions)", call([T("I am a developer in Bengaluru with three years experience.") for _ in range(50)]), "graceful")
    add("scr_conf_nan", "screening", "ASR confidence NaN", call([T("I am a developer.", float("nan")) for _ in range(7)]), "either")
    add("scr_conf_negative", "screening", "ASR confidence -1", call([T("I am a developer.", -1.0) for _ in range(7)]), "either")
    add("scr_conf_over_one", "screening", "ASR confidence 7.5", call([T("I am a developer.", 7.5) for _ in range(7)]), "either")
    add("scr_unknown_category", "screening", "category list with an unknown category", call([T("hi")], categories=["hobby"]), "reject")
    add("scr_empty_categories", "screening", "empty category list", call([T("hi")], categories=[]), "either")

    # ---------------- HR interview
    def hr(answers: List[str]) -> Callable[[], Any]:
        def go() -> Any:
            s = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)
            for a in answers:
                if s.is_complete:
                    break
                s.submit_response(a)
            return score_hr_interview(s)
        return go
    weak_hr = lambda r: f"HR score {r.overall_hr_score:.1f} for empty/useless answers" if r.overall_hr_score >= 50 else None
    add("hr_zero_answers", "hr", "no answers submitted", hr([]), "either", weak_hr)
    add("hr_empty_answers", "hr", "6 empty answers", hr([""] * 6), "either", weak_hr)
    add("hr_whitespace", "hr", "6 whitespace answers", hr(["   "] * 6), "either", weak_hr)
    add("hr_one_word", "hr", "6 one-word answers", hr(["yes"] * 6), "graceful", weak_hr)
    add("hr_huge", "hr", "6 answers of 10k characters", hr(["I enjoy teamwork and clear communication. " * 250] * 6), "graceful")
    add("hr_unicode", "hr", "Hindi answers", hr(["मैं एक डेवलपर हूँ और टीम में काम करना पसंद करता हूँ"] * 6), "graceful")
    add("hr_none_answer", "hr", "None as an answer", hr([None] * 6), "reject")
    add("hr_too_many", "hr", "12 answers (more than questions)", hr(["I like teamwork and I communicate clearly with everyone."] * 12), "graceful")

    # ---------------- technical interview
    def tech(answers: List[str], years: Any = 3, domain: Any = TechnicalDomain.MERN) -> Callable[[], Any]:
        def go() -> Any:
            s = TechnicalInterviewSession.start(domain, years)
            for a in answers:
                if s.is_complete:
                    break
                s.submit_response(a)
            return build_technical_evaluation_report(s)
        return go
    weak_t = lambda r: f"technical score {r.overall_score:.1f} for empty/useless answers" if r.overall_score >= 50 else None
    add("tech_zero_answers", "technical", "no answers submitted", tech([]), "either", weak_t)
    add("tech_empty_answers", "technical", "5 empty answers", tech([""] * 5), "either", weak_t)
    add("tech_keyword_list", "technical", "5 answers that are only a keyword list", tech(["event loop libuv thread pool task queue timers phase poll phase microtask callbacks"] * 5), "graceful",
        lambda r: f"a keyword list scored {r.overall_score:.1f}" if r.overall_score >= 40 else None)
    add("tech_negative_years", "technical", "experience of -1 years", tech(["I built APIs."] * 5, -1), "either")
    add("tech_nan_years", "technical", "experience NaN", tech(["I built APIs."] * 5, float("nan")), "reject")
    add("tech_huge_years", "technical", "experience 80 years", tech(["I built APIs."] * 5, 80), "either")
    add("tech_bad_domain", "technical", "domain 'cobol'", lambda: TechnicalInterviewSession.start("cobol", 3), "reject")
    add("tech_unicode", "technical", "Hindi answers", tech(["मैं रिएक्ट और नोड पर काम करता हूँ"] * 5), "graceful")
    add("tech_huge", "technical", "5 answers of 20k characters", tech(["React uses components and state hooks. " * 500] * 5), "graceful")

    # ---------------- aggregation and decision
    from parsers.hr_interview_question_bank import ExperienceLevel as EL, RoleType as RT
    def agg(make_rounds: Callable[[], List[Any]]) -> Callable[[], Any]:
        # rounds are built INSIDE the timed call: RoundResult validates on construction, and that rejection is itself a result
        return lambda: compute_cross_round_score(make_rounds(), RT.TECHNICAL, EL.EXPERIENCED, "edge")
    R = RoundResult
    inbounds = lambda r: f"hiring fit {r.hiring_fit_percentage}" if not 0 <= r.hiring_fit_percentage <= 100 else None
    add("agg_no_rounds", "aggregation", "no rounds at all", agg(lambda: []), "either")
    add("agg_over_100", "aggregation", "a round score of 150", agg(lambda: [R("ats", 150), R("screening", 80)]), "either", inbounds)
    add("agg_negative", "aggregation", "a round score of -20", agg(lambda: [R("ats", -20), R("screening", 80)]), "either", inbounds)
    add("agg_nan", "aggregation", "a round score of NaN", agg(lambda: [R("ats", float("nan")), R("screening", 80)]), "reject")
    add("agg_none_score", "aggregation", "a round score of None", agg(lambda: [R("ats", None), R("screening", 80)]), "either")
    add("agg_duplicate_round", "aggregation", "the same round twice", agg(lambda: [R("ats", 90), R("ats", 10), R("screening", 80)]), "either")
    add("agg_unknown_round", "aggregation", "an unknown round name", agg(lambda: [R("karate", 90), R("ats", 70)]), "either")
    def never_selects_zeros(r: Any) -> Optional[str]:
        d = decide(r)
        return "all-zero candidate was SELECTED" if d.outcome.value == "selected" else None
    add("agg_all_zero", "aggregation", "every round 0", agg(lambda: [R(n, 0) for n in ("ats", "screening", "hr_interview", "technical_interview", "machine_test")]), "graceful", never_selects_zeros)

    # ---------------- service boundary (the public API)
    # The sweep calls `run()` where it exists (the Day 57 stable boundary) and `process()` where it does not, so the same cases
    # measure the API as it was before Day 57 and as it is now.
    from ats_engine.service import ATSService
    from interview_ai.service import InterviewIntelligenceService
    from scoring.service import DecisionScoringService
    from screening_ai.service import ScreeningService

    def svc(cls: Any, payload: Any) -> Callable[[], Any]:
        def go() -> Any:
            inst = cls()
            return (getattr(inst, "run", None) or inst.process)(payload)
        return go

    def envelope(r: Any) -> Optional[str]:
        if not isinstance(r, dict) or "status" not in r:
            return "response is not a status envelope"
        try:
            json.dumps(r, allow_nan=False)
        except (TypeError, ValueError) as exc:
            return f"response is not JSON-safe: {str(exc)[:60]}"
        return None

    def must_error(r: Any) -> Optional[str]:
        return envelope(r) or (None if r["status"] == "error" else "invalid input was accepted as a success")

    def must_succeed(extra: Callable[[Dict[str, Any]], Optional[str]]) -> Callable[[Any], Optional[str]]:
        return lambda r: envelope(r) or (f"an error was returned for valid input: {r.get('error')}" if r["status"] == "error" else extra(r))

    add("svc_ats_payload_none", "service", "ATS service: payload is None", svc(ATSService, None), "graceful", must_error)
    add("svc_ats_payload_string", "service", "ATS service: payload is a string", svc(ATSService, "hello"), "graceful", must_error)
    add("svc_ats_resume_is_number", "service", "ATS service: resume_text is a number", svc(ATSService, {"resume_text": 123, "job_description": jd_text}), "graceful", must_error)
    add("svc_ats_nothing_to_score_against", "service", "ATS service: no job description and no requirements", svc(ATSService, {"resume_text": "React developer"}), "graceful", must_error)
    add("svc_ats_oversized_resume", "service", "ATS service: 300k-character resume", svc(ATSService, {"resume_text": "x" * 300_000, "job_description": jd_text}), "graceful", must_error)
    add("svc_decision_empty", "service", "Decision service: empty payload", svc(DecisionScoringService, {}), "graceful", must_error)
    add("svc_decision_nan", "service", "Decision service: NaN score", svc(DecisionScoringService, {"ats_score": float("nan"), "screening_score": 70}), "graceful", must_error)
    add("svc_decision_over_100", "service", "Decision service: score 150", svc(DecisionScoringService, {"ats_score": 150}), "graceful", must_error)
    add("svc_decision_string_score", "service", "Decision service: score is text", svc(DecisionScoringService, {"ats_score": "high"}), "graceful", must_error)
    add("svc_decision_missing_is_not_zero", "service", "Decision service: one strong round, others not yet run",
        svc(DecisionScoringService, {"ats_score": 90}), "graceful",
        must_succeed(lambda r: "one round of 90 was turned into a rejection (missing rounds were counted as zero)" if r.get("decision") == "rejected" else None))
    add("svc_decision_partial_never_rejects", "service", "Decision service: two weak rounds of a technical role",
        svc(DecisionScoringService, {"ats_score": 10, "screening_score": 10, "role_type": "technical"}), "graceful",
        must_succeed(lambda r: "a candidate was rejected on incomplete evidence" if r.get("decision") == "rejected" else None))
    add("svc_screening_no_turns", "service", "Screening service: no call turns", svc(ScreeningService, {"candidate_id": "C1"}), "graceful",
        must_succeed(lambda r: "reports an answered call that never happened" if r.get("call_status") == "answered" else None))
    add("svc_screening_bad_turns", "service", "Screening service: turns are not objects", svc(ScreeningService, {"candidate_id": "C1", "turns": [1, 2, 3]}), "graceful", must_error)
    add("svc_interview_no_answers", "service", "Interview service: no answers",  svc(InterviewIntelligenceService, {"interview_type": "hr"}), "graceful",
        must_succeed(lambda r: "returns a placeholder transcript / zero scores as if they were results" if ("transcript" in r or r.get("communication_score") == 0.0) else None))
    add("svc_interview_unknown_type", "service", "Interview service: interview_type 'karaoke'", svc(InterviewIntelligenceService, {"interview_type": "karaoke"}), "graceful", must_error)
    add("svc_interview_technical_nan_years", "service", "Interview service: technical interview with NaN years",
        svc(InterviewIntelligenceService, {"interview_type": "technical", "domain": "mern", "experience_years": float("nan"), "answers": ["x"]}), "graceful", must_error)
    return cases


# ------------------------------------------------------------- before / after probes
def measure_probes(matcher: Any, samples_dir: str = "data/samples") -> Dict[str, Any]:
    """The headline numbers behind each Day 57 fix, measured with APIs that exist both before and after the fixes, so the same
    function can be run against the old tree and the new one. Used by the demo and recorded in the report."""
    import tempfile
    from datetime import date
    from pathlib import Path
    from docx import Document
    from parsers.ats_scoring_engine import score_candidate
    from parsers.experience_parser import compute_total_experience, parse_experience
    from parsers.hr_interview_question_bank import ExperienceLevel, InterviewSession, RoleType
    from parsers.hr_interview_scoring_engine import score_hr_interview
    from parsers.pipeline_simulation import ats_zone, frozen_today, load_scenarios, run_journey, technical_phrasing_probe
    from parsers.screening_pipeline import run_screening_call
    from parsers.speech_to_text import RawSTTResult

    base = Path(samples_dir)
    out: Dict[str, Any] = {}
    T = lambda t, c=0.9, s=False: RawSTTResult(text=t, confidence=c, is_silent=s)

    def years(text: str, as_of: Optional[date] = None) -> float:
        with frozen_today(as_of or date(2026, 10, 30)):
            return compute_total_experience(parse_experience("Experience:\n" + text)).total_years
    out["years_for_2019_to_2022"] = years("- Engineer, Acme (2019 - 2022)\n")
    out["years_end_before_start"] = years("- Engineer, Acme (Mar 2024 - Jan 2023)\n")
    out["years_job_starting_2031"] = years("- Engineer, Acme (Jan 2031 - Present)\n")
    out["years_career_from_1900"] = years("- Engineer, Acme (Jan 1900 - Present)\n")

    def hr(answers: List[str]) -> float:
        s = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)
        for a in answers:
            s.submit_response(a)
        return round(score_hr_interview(s).overall_hr_score, 1)
    out["hr_score_six_yes_answers"] = hr(["yes"] * 6)
    out["hr_score_six_good_answers"] = hr(["I work well in teams and communicate clearly; on my last project I led a migration and mentored two juniors."] * 6)

    out["screening_score_digit_strings"] = round(run_screening_call([T("12345 67890") for _ in range(8)], candidate_id="p", job_role="p").scoring_result.total_score, 1)
    silent = run_screening_call([T("", 0.0, True) for _ in range(30)], candidate_id="p", job_role="p")
    out["silent_call_ended_early"] = bool(silent.controller.call_ended_early)
    out["silent_call_turns_before_it_stopped"] = len(silent.controller.outcome_log)
    intros = ["Hi, I'm Ananya Rao, a MERN stack developer based in Bengaluru.", "My name is Arjun and I work at Infosys as a tech lead.", "I am Priya, a sales executive with a BBA from Delhi University."]
    out["rich_introductions_flagged_off_topic_of_3"] = sum(
        run_screening_call([T(t)], categories=["introduction"], candidate_id="p", job_role="p").scoring_result.question_scores[0].quality.value == "off_topic" for t in intros)

    out["technical_phrasing"] = technical_phrasing_probe()

    jd = (base / "jds/jd_01_mern_developer.txt").read_text(encoding="utf-8")
    body = "React.js, Node.js, MongoDB, Express.js, REST API, Git, TypeScript, Docker"
    with frozen_today(date(2026, 10, 30)):
        mk = lambda s, e: f"Summary:\nMERN developer.\n{s}\n{body}\n{e}\n- Developer, Acme (Jan 2022 - Jan 2025)\n"
        out["ats_score_heading_Skills"] = round(score_candidate(mk("Skills:", "Experience:"), jd, matcher).overall_score, 1)
        out["ats_score_heading_Technical_Skills"] = round(score_candidate(mk("Technical Skills", "Work Experience"), jd, matcher).overall_score, 1)
        free = score_candidate("Skills:\nReact\nExperience:\n- A, B (Jan 2022 - Jan 2025)", "We need a developer with React and Node experience.", matcher)
        out["zone_when_job_description_has_no_requirements"] = ats_zone(free)

    sc = {s.id: s for s in load_scenarios("data/simulation/day56_scenarios.json")}["S8"]
    path = Path(tempfile.mkdtemp()) / "s8.docx"
    d = Document()
    for ln in (base / "resumes" / f"{sc.resume}.txt").read_text(encoding="utf-8").splitlines():
        d.add_paragraph(ln)
    d.save(str(path))
    j = run_journey(sc, matcher, path, (base / "jds" / f"{sc.jd}.txt").read_text(encoding="utf-8"), date(2026, 10, 30))
    out["ats_rejected_candidate_fit_raw_and_aligned"] = [round(j.score_raw.hiring_fit_percentage, 1), round(j.score_aligned.hiring_fit_percentage, 1)]
    out["ats_rejected_candidate_outcome_raw_and_aligned"] = [j.outcome, j.outcome_aligned]
    return out
