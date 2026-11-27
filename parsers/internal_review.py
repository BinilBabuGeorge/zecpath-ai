"""
Internal review probes (Day 64): measured evidence about the system's accuracy, UX, performance and engineering health

Day 64 asks for an internal review of the whole system: walk ATS -> Screening -> HR -> Technical -> Decision, find accuracy gaps, UX issues and
performance issues, and prioritise improvements. A review made of opinions cannot be re-checked, so this module turns each question into a
PROBE that runs on the real engines and the Day 63 demo dataset and returns numbers. The review report quotes these numbers; a test fails if
the report and the probes disagree.

THE PROBES
  walkthrough()          the five-stage trace of chosen candidates, with every stage's input, output, time and observations
  accuracy_probes()      expectation agreement, rank agreement between rounds, score spread, ATS-zone vs final outcome, file-format
                         invariance (DOCX vs PDF), robustness to harmless edits (skill spellings, headings, formatting, dates),
                         name-swap fairness, and NEGATIVE CONTROLS (does nonsense ever score well?)
  ux_probes()            an audit of the error messages every service returns for malformed requests, an audit of the 30 recruiter reports
                         (truncated sentences, raw codes, length), and the API pitfalls that surprise a caller
  performance_probes()   per-stage timing over the 30 candidates, resume reading by file type, single-process ATS throughput, cold start
  engineering_probes()   wall-clock reads in the engines, tests per module, CI, style-standard breaches, dependency pinning

WHAT IS AND IS NOT DETERMINISTIC. Everything except `performance_probes()` gives the same answer on every machine for the same code and data.
Timings describe this machine and are reported as measurements, never as guarantees.

WHAT A PROBE CANNOT DO. It finds problems the data can show. It cannot judge whether a weight is right (no labelled outcomes exist), whether a
report is pleasant to read, or what a mentor would say: the reviewer-feedback section is a kit to be filled in, not something invented here.

Input contract:  the demo dataset (data/demo_dataset/) and its simulated run (parsers/demo_environment.py).
Output contract: plain JSON-serialisable dicts.
"""

from __future__ import annotations

import ast
import json
import logging
import re
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from parsers import demo_environment as env
from parsers.demo_dataset_answers import SCREENING_ORDER

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
ENGINE_DIRS = ("ats_engine", "screening_ai", "interview_ai", "scoring", "utils", "parsers")
STAGES = ("upload", "ats", "screening", "hr_interview", "technical_interview", "aggregation", "decision", "report")


def _r(x: Any, n: int = 1) -> Any:
    return round(float(x), n) if isinstance(x, (int, float, np.floating)) else x


def _spread(values: Sequence[float]) -> Dict[str, float]:
    v = [float(x) for x in values]
    return {"n": len(v), "min": _r(min(v)), "max": _r(max(v)), "mean": _r(statistics.fmean(v)), "std": _r(statistics.pstdev(v))}


def _rank(values: Sequence[float]) -> np.ndarray:
    """Average ranks (ties share the mean rank)."""
    arr = np.asarray(values, dtype=float)
    order = arr.argsort(kind="mergesort")
    ranks = np.empty(len(arr))
    i = 0
    while i < len(arr):
        j = i
        while j + 1 < len(arr) and arr[order[j + 1]] == arr[order[i]]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1
        i = j + 1
    return ranks


def spearman(a: Sequence[float], b: Sequence[float]) -> float:
    """Spearman rank correlation without scipy."""
    ra, rb = _rank(a), _rank(b)
    if ra.std() == 0 or rb.std() == 0:
        return 0.0
    return float(np.corrcoef(ra, rb)[0, 1])


# --------------------------------------------------------------------------------------------------------------------------- walkthrough
def walkthrough(runs: List[env.CandidateRun], ids: Sequence[str]) -> List[Dict[str, Any]]:
    """The stage-by-stage trace of chosen candidates, from the real run: input, output, time and what a reviewer should look at."""
    by_id = {r.candidate["id"]: r for r in runs}
    out = []
    for cid in ids:
        r = by_id[cid]
        j = r.journey
        stages = []
        ats = j.ats
        stages.append({"stage": "ATS", "input": f"{r.candidate['resume_format'].upper()} resume, job '{r.candidate['job_title']}'",
                       "output": f"{ats.overall_score:.1f} -> {j.zone}", "detail": {c.name: _r(c.score) for c in ats.components}, "note": f"years parsed {j.resume_years_parsed}"})
        if j.screening is not None:
            st = j.stages["screening"].summary or {}
            stages.append({"stage": "Screening", "input": f"{st.get('turns')} turns, {st.get('answered')} categories answered",
                           "output": f"{j.screening.total_score:.1f}", "detail": {"missing": st.get("missing"), "claimed_years": j.claimed_years}, "note": "; ".join(j.screening.consistency_findings)[:140]})
        if j.hr is not None:
            stages.append({"stage": "HR interview", "input": f"{j.hr.num_questions_answered} answers", "output": f"{j.hr.overall_hr_score:.1f}",
                           "detail": {}, "note": ""})
        if j.technical is not None:
            stages.append({"stage": "Technical interview", "input": f"tier {j.tier_used}, 5 answers", "output": f"{j.technical.overall_score:.1f}",
                           "detail": {}, "note": ""})
        if r.machine_report is not None:
            mt = r.machine_report.to_dict()
            stages.append({"stage": "Machine test", "input": "2 coding attempts", "output": f"{mt['overall_score']:.1f} ({mt['score_band']})", "detail": {t["task_id"]: _r(t["task_score"]) for t in mt["tasks"]}, "note": f"integrity {mt['integrity_risk_tag']}"})
        d = r.decision
        stages.append({"stage": "Decision", "input": f"{len(r.score.rounds) if hasattr(r.score, 'rounds') else 'all'} round scores",
                       "output": f"{d.outcome.value}, Hiring Fit {r.score.hiring_fit_percentage:.1f}, confidence {d.confidence.score:.1f}",
                       "detail": {"flags": [f.code for f in r.score.flags]}, "note": (d.reasons[0] if d.reasons else "")[:200]})
        out.append({"id": cid, "scenario": r.candidate["scenario"], "expected": r.candidate["expected_outcomes"], "outcome": r.outcome, "stages": stages})
    return out


# --------------------------------------------------------------------------------------------------------------------------- accuracy
def _ats_score(resume_text: str, jd: str) -> Optional[float]:
    from ats_engine.service import ATSService

    resp = ATSService().run({"resume_text": resume_text, "job_description": jd})
    return resp["ats_score"] if resp.get("status") == "success" else None


def _ats_components(resume_text: str, jd: str) -> Dict[str, float]:
    from ats_engine.service import ATSService

    resp = ATSService().run({"resume_text": resume_text, "job_description": jd})
    return {c["name"]: c["score"] for c in resp["components"]}


def _format_invariance(ds: Dict[str, Any], limit: int = 30) -> Dict[str, Any]:
    """The same resume text as DOCX and as PDF should score identically after real extraction. A PDF wraps long lines, as every real PDF does."""
    from parsers import demo_dataset_builder as builder
    from parsers.pipeline_simulation import upload_resume

    rows = {}
    with tempfile.TemporaryDirectory() as tmp:
        for cand in ds["candidates"][:limit]:
            text = (ds["base"] / "resumes_text" / (Path(cand["resume_file"]).stem + ".txt")).read_text(encoding="utf-8")
            jd = env.job_text(ds, cand["job_id"])
            comps = {}
            for fmt, writer in (("docx", builder.write_docx), ("pdf", builder.write_pdf)):
                path = Path(tmp) / f"{cand['id']}.{fmt}"
                writer(text, path)
                extracted, _ = upload_resume(path)
                comps[fmt] = (_ats_score(extracted, jd), _ats_components(extracted, jd))
            changed = {k: round(comps["pdf"][1][k] - comps["docx"][1][k], 1) for k in comps["docx"][1] if abs(comps["pdf"][1][k] - comps["docx"][1][k]) > 0.05}
            rows[cand["id"]] = {"docx": comps["docx"][0], "pdf": comps["pdf"][0], "delta": round(comps["pdf"][0] - comps["docx"][0], 1), "components_changed": changed}
    differing = {k: v for k, v in rows.items() if abs(v["delta"]) > 0.5}
    worst = min(rows.items(), key=lambda kv: kv[1]["delta"])
    return {"candidates": len(rows), "differing_by_more_than_half_a_point": sorted(differing), "worst": {"id": worst[0], **worst[1]},
            "components_responsible": sorted({c for v in differing.values() for c in v["components_changed"] if c != "semantic"}),
            "mean_delta_when_differing": _r(statistics.fmean([v["delta"] for v in differing.values()])) if differing else 0.0}


def _swap(text: str, old: str, new: str) -> str:
    return text.replace(old, new)


PERTURBATIONS: List[Tuple[str, str, Callable[[str], str]]] = [
    ("skill spelling: ReactJS / NodeJS / ExpressJS", "skills", lambda t: t.replace("React.js", "ReactJS").replace("Node.js", "NodeJS").replace("Express.js", "ExpressJS")),
    ("skill spelling: Postgres / SpringBoot / RESTful", "skills", lambda t: t.replace("PostgreSQL", "Postgres").replace("Spring Boot", "SpringBoot").replace("REST APIs", "RESTful web services")),
    ("skill spelling: SFDC / cold-calling", "skills", lambda t: t.replace("Salesforce", "SFDC").replace("Cold Calling", "cold-calling")),
    ("heading: Skills -> Technical Skills", "headings", lambda t: t.replace("Skills:", "Technical Skills:")),
    ("heading: Skills -> Core Competencies", "headings", lambda t: t.replace("Skills:", "Core Competencies:")),
    ("heading on its own line: Skills", "headings", lambda t: t.replace("Skills: ", "Skills\n")),
    ("heading on its own line: Technical Skills", "headings", lambda t: t.replace("Skills: ", "Technical Skills\n")),
    ("heading on its own line: Core Competencies", "headings", lambda t: t.replace("Skills: ", "Core Competencies\n")),
    ("heading: Experience -> Work History", "headings", lambda t: t.replace("Experience:", "Work History:")),
    ("heading: Experience -> Professional Experience", "headings", lambda t: t.replace("Experience:", "Professional Experience:")),
    ("heading: Education -> Academic Background", "headings", lambda t: t.replace("Education:", "Academic Background:")),
    ("heading: Summary -> Profile", "headings", lambda t: t.replace("Summary:", "Profile:")),
    ("formatting: all lower case", "formatting", lambda t: t.lower()),
    ("formatting: headings upper case", "formatting", lambda t: re.sub(r"^(Summary|Skills|Experience|Education|Certifications):", lambda m: m.group(1).upper() + ":", t, flags=re.M)),
    ("formatting: blank line after every line", "formatting", lambda t: "\n\n".join(t.splitlines())),
    ("formatting: bullets '-' -> '*'", "formatting", lambda t: re.sub(r"^- ", "* ", t, flags=re.M)),
    ("dates: 'Nov 2022' -> '11/2022'", "dates", lambda t: re.sub(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) (\d{4})", lambda m: "%02d/%s" % (["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"].index(m.group(1)) + 1, m.group(2)), t)),
    ("dates: 'Present' -> 'Till date'", "dates", lambda t: t.replace("Present", "Till date")),
    ("dates: 'Present' -> 'Current'", "dates", lambda t: t.replace("Present", "Current")),
    ("order: Education before Experience", "order", lambda t: _education_first(t)),
]


def _education_first(text: str) -> str:
    m = re.search(r"\nExperience:\n(.*?)\n(Education:\n.*?)(\n\n|\Z)", text, flags=re.S)
    if not m:
        return text
    return text[:m.start()] + "\n" + m.group(2) + "\n\nExperience:\n" + m.group(1) + text[m.end():]


def _robustness(ds: Dict[str, Any], ids: Sequence[str]) -> Dict[str, Any]:
    from parsers import experience_parser
    from parsers.pipeline_simulation import frozen_today

    rows: List[Dict[str, Any]] = []
    for cid in ids:
        cand = next(c for c in ds["candidates"] if c["id"] == cid)
        base_text = (ds["base"] / "resumes_text" / (Path(cand["resume_file"]).stem + ".txt")).read_text(encoding="utf-8")
        jd = env.job_text(ds, cand["job_id"])
        with frozen_today(date.fromisoformat(ds["as_of"])):
            base = _ats_score(base_text, jd)
            base_years = experience_parser.compute_total_experience(experience_parser.parse_experience(base_text)).total_years
            for name, category, fn in PERTURBATIONS:
                new_text = fn(base_text)
                if new_text == base_text:
                    continue                                   # the edit does not apply to this resume
                score = _ats_score(new_text, jd)
                years = experience_parser.compute_total_experience(experience_parser.parse_experience(new_text)).total_years
                rows.append({"id": cid, "perturbation": name, "category": category, "base": _r(base), "after": _r(score), "delta": _r(score - base),
                             "years_before": _r(base_years), "years_after": _r(years)})
    worst: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        w = worst.get(row["perturbation"])
        if w is None or abs(row["delta"]) > abs(w["delta"]):
            worst[row["perturbation"]] = row
    losing = sorted((w for w in worst.values() if w["delta"] <= -3.0), key=lambda w: w["delta"])
    by_category = {}
    for row in rows:
        by_category.setdefault(row["category"], []).append(row["delta"])
    return {"resumes": list(ids), "cases": len(rows), "max_loss": _r(min(r["delta"] for r in rows)), "max_gain": _r(max(r["delta"] for r in rows)),
            "losing_3_or_more": [{"perturbation": w["perturbation"], "id": w["id"], "delta": w["delta"], "years": f"{w['years_before']} -> {w['years_after']}"} for w in losing],
            "mean_delta_by_category": {k: _r(statistics.fmean(v)) for k, v in by_category.items()}}


def _name_swap(ds: Dict[str, Any], pairs: int = 8) -> Dict[str, Any]:
    """Swap the candidate's name (and e-mail) for another candidate's: the ATS score must not move."""
    from parsers.demo_dataset_builder import _email

    cands = ds["candidates"]
    diffs = []
    for i in range(pairs):
        a, b = cands[i], cands[(i + 7) % len(cands)]
        text = (ds["base"] / "resumes_text" / (Path(a["resume_file"]).stem + ".txt")).read_text(encoding="utf-8")
        jd = env.job_text(ds, a["job_id"])
        swapped = text.replace(a["name"], b["name"])
        from parsers.demo_dataset_content import PERSONAS
        pa = next(p for p in PERSONAS if p["id"] == a["id"])
        pb = next(p for p in PERSONAS if p["id"] == b["id"])
        swapped = swapped.replace(_email(pa), _email(pb))
        diffs.append(abs(_ats_score(text, jd) - _ats_score(swapped, jd)))
    return {"swaps": pairs, "max_difference": _r(max(diffs), 2)}


def _negative_controls(ds: Dict[str, Any]) -> Dict[str, Any]:
    """Does nonsense ever score well? Every score here should be low; a high one is an accuracy gap."""
    from ats_engine.service import ATSService
    from interview_ai.service import InterviewIntelligenceService
    from screening_ai.service import ScreeningService

    out: Dict[str, Any] = {}
    mern_jd = env.job_text(ds, "JOB-01")
    designer = (ds["base"] / "resumes_text" / "DC-22_kavya_reddy.txt").read_text(encoding="utf-8")
    out["ats_unrelated_resume"] = _r(ATSService().run({"resume_text": designer, "job_description": mern_jd})["ats_score"])
    out["ats_one_line_resume"] = _r(ATSService().run({"resume_text": "I am a hard working person.", "job_description": mern_jd}).get("ats_score", -1))
    screening = ScreeningService()
    def scr(texts):
        resp = screening.run({"candidate_id": "NC", "job_role": "MERN Stack Developer", "turns": [{"text": t, "confidence": 0.9} for t in texts]})
        return _r(resp.get("screening_score", -1))
    out["screening_gibberish"] = scr(["asdf qwer zxcv"] * 7)
    out["screening_dont_know"] = scr(["I do not know."] * 7)
    out["screening_off_topic"] = scr(["The weather is nice today and I like football."] * 7)
    interview = InterviewIntelligenceService()
    def hr(texts):
        resp = interview.run({"interview_type": "hr", "role_type": "technical", "experience_level": "experienced", "answers": texts})
        return _r(resp.get("hr_score", -1))
    out["hr_gibberish"] = hr(["asdf qwer zxcv"] * 6)
    out["hr_one_word"] = hr(["Yes."] * 6)
    out["hr_off_topic"] = hr(["I like pizza and cricket and watching films with my family on weekends."] * 6)
    def tech(texts):
        resp = interview.run({"interview_type": "technical", "domain": "mern", "experience_years": 4, "answers": texts})
        return _r(resp.get("technical_score", resp.get("overall_score", -1)))
    out["technical_gibberish"] = tech(["asdf qwer zxcv"] * 5)
    out["technical_dont_know"] = tech(["I do not know this."] * 5)
    out["technical_off_topic"] = tech(["I enjoy hiking and I support my local football team every weekend."] * 5)
    from parsers.demo_environment import build_attempts
    stub = build_attempts(ds, "DC-04")                          # a broken-code attempt from the dataset
    from parsers.machine_test_evaluation_engine import build_machine_test_report
    out["machine_test_broken_code"] = _r(build_machine_test_report(stub, integrity_risk_tag="clear").overall_score)
    out["high_scoring_nonsense"] = sorted(k for k, v in out.items() if isinstance(v, (int, float)) and v >= 50)
    return out


def accuracy_probes(ds: Dict[str, Any], runs: List[env.CandidateRun]) -> Dict[str, Any]:
    rows = [env._row(r) for r in runs]
    summary = env.summarise(runs)
    fit = [r["hiring_fit"] for r in rows]
    ats = [r["ats_score"] for r in rows]
    tech_rows = [r for r in rows if r["technical_score"] is not None]
    crosstab: Dict[str, Dict[str, int]] = {}
    for r in rows:
        crosstab.setdefault(r["ats_zone"], {}).setdefault(r["outcome"], 0)
        crosstab[r["ats_zone"]][r["outcome"]] += 1
    disagreement = sum(1 for r in runs if any(f.code == "ROUND_DISAGREEMENT" for f in r.score.flags))
    disagreement_aligned = sum(1 for r in runs if r.score_aligned is not None and any(f.code == "ROUND_DISAGREEMENT" for f in r.score_aligned.flags))
    aligned_flips = sum(1 for r in runs if r.decision_aligned is not None and r.outcome != r.decision_aligned.outcome.value)
    strong_by_domain: Dict[str, List[float]] = {}
    for run in runs:
        if run.candidate["answer_levels"]["technical"] == "strong" and run.journey.technical is not None:
            strong_by_domain.setdefault(run.candidate["domain"], []).append(run.journey.technical.overall_score)
    spreads = {"ats": _spread([r["ats_score"] for r in rows if r["ats_score"] > 10]),
               "screening": _spread([r["screening_score"] for r in rows if r["screening_score"] > 60]),
               "hr": _spread([r["hr_score"] for r in rows]),
               "technical": _spread([r["technical_score"] for r in tech_rows]),
               "machine_test": _spread([r["machine_test_score"] for r in tech_rows]),
               "hiring_fit": _spread(fit)}
    return {
        "expected_outcome_met": summary["expected_outcome_met"], "candidates": summary["candidates"], "missed": summary["expected_outcome_missed"],
        "rank_agreement_with_hiring_fit": {"ats": _r(spearman(ats, fit), 2), "screening": _r(spearman([r["screening_score"] for r in rows], fit), 2),
                                           "hr": _r(spearman([r["hr_score"] for r in rows], fit), 2),
                                           "technical": _r(spearman([r["technical_score"] for r in tech_rows], [r["hiring_fit"] for r in tech_rows]), 2),
                                           "machine_test": _r(spearman([r["machine_test_score"] for r in tech_rows], [r["hiring_fit"] for r in tech_rows]), 2)},
        "technical_strong_answers_by_domain": {k: {"candidates": len(v), "mean": _r(statistics.fmean(v))} for k, v in sorted(strong_by_domain.items())},
        "score_spread": spreads, "ats_zone_by_outcome": crosstab, "round_disagreement_flagged": disagreement, "round_disagreement_flagged_with_aligned_ats": disagreement_aligned, "outcomes_changed_by_aligned_ats": aligned_flips,
        "format_invariance": _format_invariance(ds), "robustness": _robustness(ds, ("DC-01", "DC-10", "DC-17", "DC-22", "DC-26")),
        "name_swap": _name_swap(ds), "negative_controls": _negative_controls(ds),
    }


# --------------------------------------------------------------------------------------------------------------------------- UX
def _error_payloads() -> Dict[str, List[Tuple[str, Any]]]:
    edge = ROOT / "data" / "demo_dataset" / "edge_files"
    return {
        "ATSService": [("empty payload", {}), ("resume_text not text", {"resume_text": 5, "job_description": "x"}), ("empty resume", {"resume_text": "", "job_description": "x"}),
                       ("no job description", {"resume_text": "x"}), ("payload is a list", [])],
        "ScreeningService": [("empty payload", {}), ("turns not a list", {"turns": "abc"}), ("no turns", {"turns": []}),
                             ("turn without text", {"turns": [{"confidence": 0.5}]}), ("confidence above 1", {"turns": [{"text": "hi", "confidence": 2}]})],
        "InterviewIntelligenceService": [("empty payload", {}), ("unknown interview type", {"interview_type": "oral"}), ("answers not a list", {"interview_type": "hr", "answers": "x"}),
                                         ("technical without domain", {"interview_type": "technical", "answers": ["a"]}), ("unknown role type", {"interview_type": "hr", "role_type": "alien", "answers": ["x"]})],
        "DecisionScoringService": [("empty payload", {}), ("score above 100", {"ats_score": 150}), ("score not a number", {"ats_score": "high"}),
                                   ("negative score", {"hr_interview_score": -5}), ("unknown role type", {"role_type": "x"})],
        "ResumeParsingService": [("empty payload", {}), ("file does not exist", {"file_path": "nope.pdf"}), ("corrupt PDF", {"file_path": str(edge / "corrupt_resume.pdf")}),
                                 ("legacy .doc", {"file_path": str(edge / "legacy_resume.doc")}), ("empty file", {"file_path": str(edge / "empty_resume.docx")})],
    }


def _service(name: str):
    from ats_engine.resume_parsing_service import ResumeParsingService
    from ats_engine.service import ATSService
    from interview_ai.service import InterviewIntelligenceService
    from scoring.service import DecisionScoringService
    from screening_ai.service import ScreeningService

    return {"ATSService": ATSService, "ScreeningService": ScreeningService, "InterviewIntelligenceService": InterviewIntelligenceService,
            "DecisionScoringService": DecisionScoringService, "ResumeParsingService": ResumeParsingService}[name]()


SCORE_KEYS = ("screening_score", "hr_score", "technical_score", "ats_score", "hiring_fit_percentage")


def _error_audit() -> Dict[str, Any]:
    """Send malformed requests to every service and grade what comes back: a code, a named field and a message that says what to do."""
    rows = []
    for name, cases in _error_payloads().items():
        service = _service(name)
        for label, payload in cases:
            resp = service.run(payload)
            err = resp.get("error") or {}
            message = err.get("message", "")
            rows.append({"service": name, "case": label, "status": resp.get("status"), "code": err.get("code"), "field": err.get("field"), "message": message,
                         "has_field": bool(err.get("field")), "actionable": bool(re.search(r"\b(must|expected|one of|should|supported|at least|at most|required)\b", message, re.I)),
                         "score_returned": next((resp[k] for k in SCORE_KEYS if isinstance(resp.get(k), (int, float))), None),
                         "silent_success": resp.get("status") == "success" and any(isinstance(resp.get(k), (int, float)) for k in SCORE_KEYS),
                         "handled_by_design": resp.get("status") == "success" and not any(isinstance(resp.get(k), (int, float)) for k in SCORE_KEYS)})
    silent = [r for r in rows if r["silent_success"]]
    by_design = [r for r in rows if r["handled_by_design"]]
    no_field = [r for r in rows if r["status"] == "error" and not r["has_field"]]
    vague = [r for r in rows if r["status"] == "error" and not r["actionable"]]
    return {"cases": len(rows), "rejected_with_error": sum(1 for r in rows if r["status"] == "error"),
            "answered_with_null_score_and_a_warning": [f"{r['service']}: {r['case']}" for r in by_design],
            "accepted_and_scored": [f"{r['service']}: {r['case']}" for r in silent],
            "scores_returned_for_bad_input": {f"{r['service']}: {r['case']}": r["score_returned"] for r in silent},
            "error_without_field": [f"{r['service']}: {r['case']}" for r in no_field], "error_not_actionable": [f"{r['service']}: {r['case']} -> {r['message'][:70]}" for r in vague],
            "rows": rows}


def _report_audit(base: Path) -> Dict[str, Any]:
    reports = sorted((base / "simulated" / "reports").glob("DC-*.md"))
    words, unbalanced, escaped, codes, truncated_ids = [], 0, 0, 0, []
    for f in reports:
        text = f.read_text(encoding="utf-8")
        words.append(len(text.split()))
        head = text.split("## Strengths")[0]
        bad = [ln for ln in head.splitlines() if ln.count("(") != ln.count(")") or (len(ln) > 190 and not ln.rstrip().endswith((".", ")", "|")))]
        if bad:
            unbalanced += 1
            truncated_ids.append(f.stem)
        escaped += len(re.findall(r"\\_", text))
        codes += len(re.findall(r"\b[A-Z]{3,}_[A-Z_]{3,}\b", head))
    return {"reports": len(reports), "words": _spread(words), "reports_over_1000_words": sum(1 for w in words if w > 1000),
            "reports_with_cut_off_summary_lines": unbalanced, "cut_off_examples": truncated_ids[:6], "escaped_underscores": escaped, "raw_code_tokens_in_summary": codes}


def _pitfalls(ds: Dict[str, Any]) -> Dict[str, Any]:
    """Behaviours that surprise a caller, demonstrated on the real services."""
    from interview_ai.service import InterviewIntelligenceService
    from screening_ai.service import ScreeningService
    from parsers import answer_intent_engine

    good_tech = ds["technical"]["DC-01"]["answers"]
    svc = InterviewIntelligenceService()
    payload = {"interview_type": "technical", "domain": "mern", "experience_years": 4}
    in_order = svc.run(dict(payload, answers=good_tech))["technical_score"]
    shifted = svc.run(dict(payload, answers=good_tech[2:] + good_tech[:2]))["technical_score"]     # the same five answers, the tier questions first
    turns = [{"text": a["text"], "confidence": a["confidence"]} for a in ds["screening"]["DC-01"]["answers"]]
    ordered = ScreeningService().run({"candidate_id": "P1", "job_role": "x", "turns": turns})
    swapped = ScreeningService().run({"candidate_id": "P2", "job_role": "x", "turns": turns[::-1]})
    return {"technical_answers_in_order": _r(in_order), "technical_same_answers_reordered": _r(shifted),
            "screening_in_order_missing": ordered.get("categories_missing"), "screening_reversed_missing": swapped.get("categories_missing"),
            "screening_reversed_score": _r(swapped.get("screening_score")),
            "six_months_read_as_years": answer_intent_engine.extract_experience_years("I have six months of internship experience")}


def ux_probes(ds: Dict[str, Any]) -> Dict[str, Any]:
    return {"error_messages": {k: v for k, v in _error_audit().items() if k != "rows"}, "error_rows": _error_audit()["rows"],
            "reports": _report_audit(ds["base"]), "pitfalls": _pitfalls(ds)}


# --------------------------------------------------------------------------------------------------------------------------- performance
def performance_probes(ds: Dict[str, Any], runs: Optional[List[env.CandidateRun]] = None) -> Dict[str, Any]:
    """Measured on THIS machine (a shared laptop or container): trust the ratios and the ranking, not the milliseconds."""
    from ats_engine.service import ATSService
    from parsers.pipeline_simulation import upload_resume

    runs = runs or env.run_environment(ds)
    stage_ms: Dict[str, List[float]] = {s: [] for s in STAGES}
    totals, remainder = [], []
    for r in runs:
        known = 0.0
        for s in STAGES:
            rec = r.journey.stages.get(s)
            if rec is not None and rec.status == "ran":
                stage_ms[s].append(rec.ms)
                known += rec.ms
        totals.append(r.ms)
        remainder.append(max(r.ms - known, 0.0))
    def stats(v):
        v = sorted(v)
        return {"n": len(v), "mean": _r(statistics.fmean(v), 1), "p50": _r(v[len(v) // 2], 1), "p95": _r(v[min(len(v) - 1, int(len(v) * 0.95))], 1), "max": _r(v[-1], 1)} if v else None
    per_stage = {s: stats(v) for s, v in stage_ms.items() if v}
    per_stage["machine test, final aggregation and report"] = stats(remainder)
    per_stage["whole candidate"] = stats(totals)
    extract = {"docx": [], "pdf": []}
    for c in ds["candidates"]:
        t0 = time.perf_counter()
        upload_resume(ds["base"] / c["resume_file"])
        extract[c["resume_format"]].append((time.perf_counter() - t0) * 1000)
    pairs = [((ds["base"] / "resumes_text" / (Path(c["resume_file"]).stem + ".txt")).read_text(encoding="utf-8"), env.job_text(ds, c["job_id"])) for c in ds["candidates"]]
    svc = ATSService()
    t0 = time.perf_counter()
    for text, jd in pairs * 3:
        svc.run({"resume_text": text, "job_description": jd})
    elapsed = time.perf_counter() - t0
    cold = subprocess.run([sys.executable, "-c", "import time,logging; logging.disable(logging.CRITICAL); t=time.perf_counter();"
                           "from ats_engine.service import ATSService; ATSService().run({'resume_text':'React Node.js MongoDB','job_description':'Needs React and Node.js'});"
                           "print(round((time.perf_counter()-t)*1000))"], capture_output=True, text=True, cwd=str(ROOT), timeout=120)
    slowest = max((s for s in per_stage if s not in ("whole candidate",)), key=lambda s: per_stage[s]["mean"])
    return {"stage_ms": per_stage, "slowest_stage_by_mean": slowest,
            "resume_extraction_ms": {k: stats(v) for k, v in extract.items()},
            "ats_single_process": {"pairs": len(pairs) * 3, "seconds": _r(elapsed, 2), "per_second": _r(len(pairs) * 3 / elapsed, 1)},
            "cold_start_first_ats_ms": int(cold.stdout.strip()) if cold.returncode == 0 and cold.stdout.strip().isdigit() else None,
            "note": "Measured on one shared machine; compare stages with each other, not with another computer."}


# --------------------------------------------------------------------------------------------------------------------------- engineering
CLOCK_CALLS = {"today", "now", "utcnow", "time", "monotonic"}


def _clock_reads() -> List[str]:
    sites = []
    for d in ENGINE_DIRS:
        for f in sorted((ROOT / d).glob("*.py")):
            if f.name in ("pipeline_simulation.py", "demo_environment.py", "internal_review.py", "perf.py", "observability.py"):
                continue                                          # timing and clock-freezing helpers read the clock on purpose
            tree = ast.parse(f.read_text(encoding="utf-8", errors="ignore"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in CLOCK_CALLS and isinstance(node.func.value, ast.Name) \
                        and node.func.value.id in ("date", "datetime", "time"):
                    sites.append(f"{d}/{f.name}:{node.lineno} {node.func.value.id}.{node.func.attr}()")
    return sites


def engineering_probes() -> Dict[str, Any]:
    modules = [p for d in ENGINE_DIRS for p in sorted((ROOT / d).glob("*.py")) if p.name != "__init__.py"]
    tests = {p.name for p in (ROOT / "tests").glob("test_*.py")}
    def has_test(p: Path) -> bool:
        return f"test_{p.stem}.py" in tests or f"test_{p.stem.replace('_engine', '')}.py" in tests or any(t.startswith(f"test_{p.stem}") for t in tests)
    untested = [f"{p.parent.name}/{p.name}" for p in modules if not has_test(p)]
    long_lines: Dict[str, int] = {}
    prints = []
    for p in modules:
        text = p.read_text(encoding="utf-8", errors="ignore")
        n = sum(1 for ln in text.splitlines() if len(ln) > 100)
        if n:
            long_lines[f"{p.parent.name}/{p.name}"] = n
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
                prints.append(f"{p.parent.name}/{p.name}:{node.lineno}")
    reqs = [ln.strip() for ln in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    docstring = sum(1 for p in modules if ast.get_docstring(ast.parse(p.read_text(encoding="utf-8", errors="ignore"))))
    sizes = sorted(((len(p.read_text(encoding="utf-8", errors="ignore").splitlines()), f"{p.parent.name}/{p.name}") for p in modules), reverse=True)[:5]
    standards = (ROOT / "docs" / "CODE_STANDARDS.md").read_text(encoding="utf-8", errors="ignore")
    return {"modules": len(modules), "modules_without_a_matching_test_file": untested, "wall_clock_reads": _clock_reads(),
            "ci_workflow_present": (ROOT / ".github" / "workflows").exists(), "gitattributes_present": (ROOT / ".gitattributes").exists(),
            "requirements_pinned": sum(1 for r in reqs if "==" in r), "requirements_total": len(reqs),
            "lines_over_100_chars": {"total": sum(long_lines.values()), "files": len(long_lines), "worst": sorted(long_lines.items(), key=lambda kv: -kv[1])[:5]},
            "standard_mentions_line_length_100": "100" in standards, "print_calls_in_engines": prints, "modules_with_docstring": docstring,
            "largest_modules": [{"lines": n, "module": m} for n, m in sizes]}


# --------------------------------------------------------------------------------------------------------------------------- everything
def collect_evidence(ds: Optional[Dict[str, Any]] = None, runs: Optional[List[env.CandidateRun]] = None, measure_performance: bool = True) -> Dict[str, Any]:
    """Run every probe and return the evidence dict the report is written from."""
    ds = ds or env.load_dataset()
    runs = runs or env.run_environment(ds)
    evidence = {"as_of": ds["as_of"], "walkthrough": walkthrough(runs, ("DC-01", "DC-04", "DC-09", "DC-13", "DC-30")), "accuracy": accuracy_probes(ds, runs),
                "ux": ux_probes(ds), "engineering": engineering_probes(), "findings_from_day63": env.probe_findings(runs, ds)}
    if measure_performance:
        evidence["performance_measured"] = performance_probes(ds, runs)
    return evidence
