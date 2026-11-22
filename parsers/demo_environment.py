"""
Demo environment (Day 63): runs the demo dataset through the REAL engines, all five rounds, to a recruiter report

WHAT THIS ADDS TO DAY 56. The Day 56 simulation ran 8 scripted candidates through the ATS, screening, HR and technical rounds; technical
candidates ended "provisional, waiting for the machine test" because no machine-test round existed in the data. The Day 63 dataset has one
for every technical candidate (and browser events for the integrity check), so a candidate here travels the WHOLE pipeline:

    resume file (DOCX/PDF) -> ATS score + zone -> screening call -> HR interview -> technical interview
        -> machine test (+ integrity tag from browser events) -> Hiring Fit Score -> recommendation -> recruiter report

Everything in the "simulated" outputs is produced by the engines in this repository. The dataset supplies INPUTS only: resumes, job
descriptions and what each fictional candidate said or typed. This module wires them together and writes the results.

READING THE RESULTS HONESTLY
  * `expected_outcomes` are the author's design intent, written BEFORE the run. `met` means the system's outcome is inside that set. A
    miss is a finding, not an error, and is reported as such; the expectations are never edited after seeing results.
  * The semantic matcher is fitted per resume/job pair (exactly what ATSService does), so a candidate's ATS score does not depend on who
    else is in the dataset.
  * The clock is frozen at the dataset's as-of date, so results do not change with the day the script is run.
  * Timings describe the scoring layer only (no speech, video or network).

Input contract:  data/demo_dataset/ as written by parsers/demo_dataset_builder.py.
Output contract: a list of CandidateRun objects; write_outputs() puts the JSON, CSV and Markdown results under data/demo_dataset/simulated/.
"""

from __future__ import annotations

import csv
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from parsers.cross_round_aggregation_engine import compute_from_round_outputs
from parsers.final_recommendation_engine import decide
from parsers.hiring_report_generator import generate_hiring_report
from parsers.hr_interview_question_bank import ExperienceLevel, RoleType
from parsers.integrity_detection_engine import BrowserEvent, BrowserEventType, build_integrity_report
from parsers.machine_test_evaluation_engine import (CaseResult, CaseSpec, CodeSnapshot, ExecutionRun, MachineTestTask, MachineTestType, TaskAttempt,
                                                    build_machine_test_report)
from parsers.pipeline_simulation import CandidateScenario, JourneyResult, frozen_today, run_journey, try_upload, upload_resume
from parsers.semantic_matcher import SemanticMatcher
from parsers.technical_interview_question_bank import DifficultyTier

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = ROOT / "data" / "demo_dataset"
SIM_DIR = DATASET_DIR / "simulated"
INTEGRITY_SESSION_SECONDS = 1800.0       # the machine-test window the browser events are measured against


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_dataset(base: Path = DATASET_DIR) -> Dict[str, Any]:
    """Read every file of the dataset into one dict."""
    cands = _read(base / "candidates.json")
    return {
        "base": base, "as_of": cands["as_of"], "candidates": cands["candidates"], "jobs": {j["id"]: j for j in _read(base / "jobs" / "jobs.json")},
        "screening": _read(base / "responses" / "screening_responses.json"), "hr": _read(base / "responses" / "hr_responses.json"),
        "technical": _read(base / "responses" / "technical_responses.json"), "tasks": _read(base / "machine_test" / "tasks.json"),
        "submissions": _read(base / "machine_test" / "submissions.json"), "events": _read(base / "integrity" / "browser_events.json"),
    }


def job_text(ds: Dict[str, Any], job_id: str) -> str:
    return (ds["base"] / ds["jobs"][job_id]["file"]).read_text(encoding="utf-8")


def build_scenario(ds: Dict[str, Any], cand: Dict[str, Any]) -> CandidateScenario:
    """The Day 56 scenario object for one candidate, filled from the dataset files."""
    cid = cand["id"]
    tech = ds["technical"].get(cid)
    return CandidateScenario(
        id=cid, label=cand["job_title"], probe=cand["scenario"], resume=Path(cand["resume_file"]).stem, jd=cand["job_id"],
        role_type=cand["role_type"], domain=cand["domain"],
        screening=[{"text": a["text"], "confidence": a["confidence"]} for a in ds["screening"][cid]["answers"]],
        hr=[a["text"] for a in ds["hr"][cid]["answers"]],
        technical={tech["tier"]: tech["answers"]} if tech else None,
        acceptable=cand["expected_outcomes"], rationale=cand["expected_rationale"], reask=ds["screening"][cid]["reask"])


def build_attempts(ds: Dict[str, Any], cid: str) -> List[TaskAttempt]:
    """Rebuild a candidate's machine-test attempts (engine objects) from the dataset JSON."""
    attempts = []
    for task in ds["tasks"]:
        sub = ds["submissions"].get(cid, {}).get(task["task_id"])
        if sub is None:
            continue
        spec = MachineTestTask(task_id=task["task_id"], task_type=MachineTestType(task["task_type"]), title=task["title"],
                               difficulty=DifficultyTier(task["difficulty"]), time_limit_seconds=task["time_limit_seconds"],
                               language=task["language"], cases=[CaseSpec(c["case_id"], c["visible"]) for c in task["cases"]],
                               reference_runtime_ms=task["reference_runtime_ms"])
        runs = [ExecutionRun(timestamp=r["timestamp"], results=[CaseResult(x["case_id"], x["passed"], x["runtime_ms"], x["timed_out"]) for x in r["results"]],
                             compile_error=r["compile_error"], stdout_tail=r["stdout_tail"], stderr_tail=r["stderr_tail"]) for r in sub["runs"]]
        snaps = [CodeSnapshot(s["timestamp"], s["code"], s["trigger"]) for s in sub["snapshots"]]
        attempts.append(TaskAttempt(spec, snaps, runs, submitted_at=sub["submitted_at"]))
    return attempts


@dataclass
class CandidateRun:
    """Everything the environment learned about one candidate."""
    candidate: Dict[str, Any]
    journey: JourneyResult
    machine_report: Any = None
    integrity_report: Any = None
    score: Any = None
    decision: Any = None
    score_aligned: Any = None
    decision_aligned: Any = None
    report: Any = None
    errors: List[str] = field(default_factory=list)
    ms: float = 0.0

    @property
    def outcome(self) -> str:
        return self.decision.outcome.value if self.decision is not None else "error"

    @property
    def met(self) -> bool:
        return self.outcome in self.candidate["expected_outcomes"]


def run_candidate(ds: Dict[str, Any], cand: Dict[str, Any], as_of: date) -> CandidateRun:
    """One candidate through every round."""
    t0 = time.perf_counter()
    cid = cand["id"]
    sc = build_scenario(ds, cand)
    resume_path = ds["base"] / cand["resume_file"]
    jd = job_text(ds, cand["job_id"])
    text, _warnings = upload_resume(resume_path)
    matcher = SemanticMatcher([text, jd])                         # fitted on this pair only, as ATSService does
    journey = run_journey(sc, matcher, resume_path, jd, as_of, generated_at=ds["as_of"])
    run = CandidateRun(cand, journey, errors=list(journey.errors) + [f"{k}: {v.note}" for k, v in journey.stages.items() if v.status == "error"])
    technical_role = cand["role_type"] == "technical"
    role = RoleType.TECHNICAL if technical_role else RoleType.NON_TECHNICAL
    level = ExperienceLevel.FRESHER if journey.resume_years_parsed < 1 else ExperienceLevel.EXPERIENCED

    integrity_tag = None
    if technical_role:
        events = [BrowserEvent(BrowserEventType(e["event_type"]), e["timestamp"]) for e in ds["events"].get(cid, [])]
        run.integrity_report = build_integrity_report(events, session_end=INTEGRITY_SESSION_SECONDS)
        integrity_tag = run.integrity_report.risk_tag.value
        attempts = build_attempts(ds, cid)
        run.machine_report = build_machine_test_report(attempts, integrity_risk_tag=integrity_tag) if attempts else None

    def _aggregate(scale: str):
        return compute_from_round_outputs(ats=journey.ats, screening=journey.screening, hr=journey.hr, technical=journey.technical,
                                          machine_test=run.machine_report, ats_scale=scale, role_type=role, experience_level=level,
                                          candidate_id=cid, integrity_risk_tag=integrity_tag)
    try:
        with frozen_today(as_of):
            run.score = _aggregate("raw")
            run.decision = decide(run.score, integrity_report=run.integrity_report)
            run.score_aligned = _aggregate("zone_aligned")
            run.decision_aligned = decide(run.score_aligned, integrity_report=run.integrity_report)
            run.report = generate_hiring_report(run.decision, run.score, ats=journey.ats, screening=journey.screening, hr=journey.hr,
                                                technical=journey.technical, machine_test=run.machine_report, integrity=run.integrity_report,
                                                generated_at=ds["as_of"], role_title=cand["job_title"], candidate_label=cid)
    except Exception as exc:                                   # a failure is a finding, never a crash
        run.errors.append(f"final: {type(exc).__name__}: {exc}")
        logger.warning("final stage failed for %s: %s", cid, exc)
    run.ms = (time.perf_counter() - t0) * 1000
    return run


def run_environment(ds: Optional[Dict[str, Any]] = None, as_of: Optional[date] = None) -> List[CandidateRun]:
    """Run every candidate of the dataset. The clock is frozen at the dataset's as-of date."""
    ds = ds or load_dataset()
    as_of = as_of or date.fromisoformat(ds["as_of"])
    return [run_candidate(ds, c, as_of) for c in ds["candidates"]]


# --------------------------------------------------------------------------------------------------------------------------- checks
def verify_dataset(ds: Optional[Dict[str, Any]] = None) -> List[str]:
    """Problems with the dataset itself (not with the system). An empty list means the dataset is internally consistent."""
    ds = ds or load_dataset()
    problems: List[str] = []
    ids = [c["id"] for c in ds["candidates"]]
    if len(ids) != len(set(ids)):
        problems.append("duplicate candidate ids")
    for c in ds["candidates"]:
        cid = c["id"]
        if c["job_id"] not in ds["jobs"]:
            problems.append(f"{cid}: unknown job {c['job_id']}")
        for key in ("resume_file", "expected_outcomes", "expected_rationale", "scenario"):
            if not c.get(key):
                problems.append(f"{cid}: missing {key}")
        if not (ds["base"] / c["resume_file"]).exists():
            problems.append(f"{cid}: resume file missing")
        if cid not in ds["screening"] or cid not in ds["hr"]:
            problems.append(f"{cid}: missing screening or HR responses")
        if c["role_type"] == "technical" and (cid not in ds["technical"] or cid not in ds["submissions"]):
            problems.append(f"{cid}: technical candidate without technical answers or machine-test attempts")
        if c["role_type"] != "technical" and (cid in ds["technical"] or cid in ds["submissions"]):
            problems.append(f"{cid}: non-technical candidate with a technical round")
    return problems


def edge_file_results(base: Path = DATASET_DIR) -> List[Dict[str, Any]]:
    """What the real upload path does with each deliberately bad file."""
    return [try_upload(p) for p in sorted((base / "edge_files").iterdir())]


# --------------------------------------------------------------------------------------------------------------------------- outputs
def _r(x: Any, n: int = 1) -> Any:
    return round(x, n) if isinstance(x, (int, float)) else x


def _row(run: CandidateRun) -> Dict[str, Any]:
    j, c = run.journey, run.candidate
    mt = run.machine_report
    return {
        "id": c["id"], "name": c["name"], "job": c["job_title"], "scenario": c["scenario"], "resume_quality": c["resume_quality"],
        "ats_score": _r(j.ats.overall_score) if j.ats is not None else None, "ats_zone": j.zone,
        "screening_score": _r(j.screening.total_score) if j.screening is not None else None,
        "hr_score": _r(j.hr.overall_hr_score) if j.hr is not None else None,
        "technical_score": _r(j.technical.overall_score) if j.technical is not None else None,
        "technical_tier": j.tier_used,
        "machine_test_score": _r(mt.overall_score) if mt is not None else None,
        "integrity_tag": run.integrity_report.risk_tag.value if run.integrity_report is not None else None,
        "hiring_fit": _r(run.score.hiring_fit_percentage) if run.score is not None else None,
        "provisional": run.score.provisional if run.score is not None else None,
        "outcome": run.outcome, "outcome_zone_aligned": run.decision_aligned.outcome.value if run.decision_aligned is not None else None,
        "confidence": _r(run.decision.confidence.score) if run.decision is not None else None,
        "human_confirmation_required": run.decision.requires_human_confirmation if run.decision is not None else None,
        "expected": "/".join(c["expected_outcomes"]), "met": run.met, "funnel_stage": j.funnel_stage,
        "flags": ",".join(f.code for f in run.score.flags) if run.score is not None else "",
        "inconsistencies": len(j.inconsistencies), "errors": len(run.errors),
    }


def summarise(runs: List[CandidateRun]) -> Dict[str, Any]:
    """Counts the documents quote."""
    rows = [_row(r) for r in runs]
    outcomes: Dict[str, int] = {}
    for r in rows:
        outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1
    by_job: Dict[str, Dict[str, int]] = {}
    for r in rows:
        d = by_job.setdefault(r["job"], {"candidates": 0, "met": 0})
        d["candidates"] += 1
        d["met"] += int(r["met"])
    zones: Dict[str, int] = {}
    for r in rows:
        zones[r["ats_zone"]] = zones.get(r["ats_zone"], 0) + 1
    return {"candidates": len(rows), "outcomes": outcomes, "ats_zones": zones, "expected_outcome_met": sum(int(r["met"]) for r in rows),
            "expected_outcome_missed": [r["id"] for r in rows if not r["met"]], "by_job": by_job,
            "provisional": sum(int(bool(r["provisional"])) for r in rows), "with_errors": [r["id"] for r in rows if r["errors"]],
            "automated_rejections": sum(1 for r in runs if r.decision is not None and r.decision.outcome.value == "rejected" and not r.decision.requires_human_confirmation),
            "miss_explanations": {r.candidate["id"]: {"outcome": r.outcome, "expected": r.candidate["expected_outcomes"], "flags": [f.code for f in r.score.flags],
                                                      "reason": r.decision.reasons[0] if r.decision.reasons else ""} for r in runs if not r.met},
            "integrity_tags": {t: sum(1 for r in rows if r["integrity_tag"] == t) for t in ("clear", "low", "medium", "high")},
            "total_ms": _r(sum(r.ms for r in runs), 0)}


def write_outputs(runs: List[CandidateRun], out_dir: Path = SIM_DIR) -> Dict[str, Any]:
    """Write the simulated results (ATS, screening, interviews, machine test, pipeline, reports, summary)."""
    (out_dir / "reports").mkdir(parents=True, exist_ok=True)
    ats, screening, interviews, machine = [], [], [], []
    for r in runs:
        j, c = r.journey, r.candidate
        if j.ats is not None:
            ats.append({"id": c["id"], "job": c["job_title"], "overall_score": _r(j.ats.overall_score), "zone": j.zone, "role_category": j.ats.role_category,
                        "components": [{"name": x.name, "score": _r(x.score), "available": x.available, "effective_weight": _r(x.effective_weight, 3),
                                        "contribution": _r(x.contribution)} for x in j.ats.components],
                        "notes": list(j.ats.missing_data_notes), "years_parsed": j.resume_years_parsed})
        if j.screening is not None:
            st = j.stages["screening"].summary or {}
            screening.append({"id": c["id"], "total_score": _r(j.screening.total_score), "answered": st.get("answered"), "missing": st.get("missing"),
                              "turns": st.get("turns"), "consistency_findings": list(j.screening.consistency_findings),
                              "claimed_years": j.claimed_years, "resume_years_parsed": j.resume_years_parsed,
                              "questions": [{"category": q.category if hasattr(q, "category") else None, "score": _r(getattr(q, "weighted_total", None))} for q in j.screening.question_scores]})
        item: Dict[str, Any] = {"id": c["id"], "hr_score": _r(j.hr.overall_hr_score) if j.hr is not None else None,
                                "hr_answers_scored": j.hr.num_questions_answered if j.hr is not None else None,
                                "technical_score": _r(j.technical.overall_score) if j.technical is not None else None, "technical_tier": j.tier_used}
        interviews.append(item)
        if r.machine_report is not None:
            mt = r.machine_report.to_dict()
            machine.append({"id": c["id"], "overall_score": mt["overall_score"], "band": mt["score_band"], "integrity_risk_tag": mt["integrity_risk_tag"],
                            "human_review_required": mt["human_review_required"], "human_review_reasons": mt["human_review_reasons"],
                            "tasks": [{"task_id": t["task_id"], "score": t["task_score"], "flags": [f["code"] for f in t["flags"]]} for t in mt["tasks"]]})
        if r.report is not None:
            (out_dir / "reports" / f"{c['id']}.md").write_text(r.report.to_markdown(), encoding="utf-8")
    rows = [_row(r) for r in runs]
    for name, data in (("ats_results.json", ats), ("screening_outputs.json", screening), ("interview_results.json", interviews),
                       ("machine_test_results.json", machine), ("pipeline_results.json", rows)):
        (out_dir / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with (out_dir / "pipeline_results.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    summary = summarise(runs)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


# --------------------------------------------------------------------------------------------------------------------------- findings
def _component(run: CandidateRun, name: str) -> Optional[float]:
    for comp in run.journey.ats.components if run.journey.ats is not None else []:
        if comp.name == name:
            return comp.score
    return None


def probe_findings(runs: List[CandidateRun], ds: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Things the demo data shows about the SYSTEM. Every statement is computed from the run; nothing here is typed in advance."""
    from parsers import answer_intent_engine
    from parsers.demo_dataset_builder import render_resume_text
    from parsers.demo_dataset_content import PERSONAS
    from ats_engine.service import ATSService

    by_id = {r.candidate["id"]: r for r in runs}
    out: List[Dict[str, Any]] = []

    flipped = [r.candidate["id"] for r in runs if r.decision_aligned is not None and r.outcome != r.decision_aligned.outcome.value]
    to_selected = [i for i in flipped if by_id[i].decision_aligned.outcome.value == "selected"]
    ats_scores = [r.journey.ats.overall_score for r in runs if r.journey.ats is not None and r.journey.ats.overall_score > 10]
    ats_lo, ats_hi = min(ats_scores), max(ats_scores)
    out.append({"id": "F1", "title": "The raw ATS scale blocks strong candidates from 'selected'",
                "statement": f"{len(flipped)} of {len(runs)} outcomes change when the ATS round is put on the common scale (ats_scale='zone_aligned'); "
                             f"{len(to_selected)} candidates move from hold_review to selected. By default the ATS scores here run from {ats_lo:.1f} to {ats_hi:.1f} while most "
                             "interview scores are 80 or more, so the round-disagreement rule trips.",
                "evidence": {"changed": flipped, "become_selected": to_selected}})

    scr = [r.journey.screening.total_score for r in runs if r.journey.screening is not None and r.candidate["answer_levels"]["screening"] != "dropped"]
    out.append({"id": "F2", "title": "The screening score barely discriminates",
                "statement": f"Across the {len(scr)} candidates whose call completed, screening scores range only from {min(scr):.1f} to {max(scr):.1f}; "
                             "a candidate who answered vaguely and was re-asked scores close to one who answered well.",
                "evidence": {"min": round(min(scr), 1), "max": round(max(scr), 1)}})

    nh = [(i, by_id[i]) for i in ("DC-13", "DC-25")]
    out.append({"id": "F3", "title": "A resume without section headings is read as having no experience",
                "statement": "; ".join(f"{i} ({r.candidate['years_on_resume']} years on the resume) parses to {r.journey.resume_years_parsed} years and an ATS score of "
                                         f"{r.journey.ats.overall_score:.1f} ({r.journey.zone})" for i, r in nh)
                             + f". DC-13 is then asked the '{by_id['DC-13'].journey.tier_used}' technical questions.",
                "evidence": {i: {"parsed_years": r.journey.resume_years_parsed, "ats": round(r.journey.ats.overall_score, 1), "zone": r.journey.zone} for i, r in nh}})

    persona = next(p for p in PERSONAS if p["id"] == "DC-28")
    plain = dict(persona, style="standard")
    jd = job_text(ds, "JOB-06")
    with_header = ATSService().run({"resume_text": render_resume_text(persona), "job_description": jd})
    without = ATSService().run({"resume_text": render_resume_text(plain), "job_description": jd})
    diff = abs(with_header["ats_score"] - without["ats_score"])
    out.append({"id": "F4", "title": "Personal details in a resume do not move the ATS score (fairness probe)",
                "statement": f"DC-28's resume with gender, birth date, religion and father's name scores {with_header['ats_score']} against {without['ats_score']} for the "
                             f"same resume without that header (difference {diff:.2f}).",
                "evidence": {"with_header": with_header["ats_score"], "without_header": without["ats_score"], "difference": round(diff, 2)}})

    k = by_id["DC-04"]
    out.append({"id": "F5", "title": "Later rounds catch what a keyword-stuffed resume hides",
                "statement": f"DC-04's stuffed resume reaches the '{k.journey.zone}' zone (ATS {k.journey.ats.overall_score:.1f}); the technical interview "
                             f"({k.journey.technical.overall_score:.1f}) and machine test ({k.machine_report.overall_score:.1f}) bring the final outcome to {k.outcome}.",
                "evidence": {"zone": k.journey.zone, "technical": round(k.journey.technical.overall_score, 1), "machine_test": round(k.machine_report.overall_score, 1), "outcome": k.outcome}})

    g = by_id["DC-21"]
    out.append({"id": "F6", "title": "Nothing in the scoring looks at how long a candidate stays",
                "statement": f"DC-21 has five employers in four years and is {g.outcome} (Hiring Fit {g.score.hiring_fit_percentage:.1f}), like a candidate with a stable history.",
                "evidence": {"outcome": g.outcome, "fit": round(g.score.hiring_fit_percentage, 1), "employers": 5}})

    v14, v15 = by_id["DC-14"], by_id["DC-15"]
    out.append({"id": "F7", "title": "Skills outside the ATS vocabulary earn no credit",
                "statement": f"DC-15 (Ansible, Helm, Prometheus, Grafana) gets a skill-match of {_component(v15, 'skill_match'):.1f} and ATS {v15.journey.ats.overall_score:.1f} "
                             f"({v15.journey.zone}) while DC-14 (Terraform, Jenkins, AWS) gets {_component(v14, 'skill_match'):.1f} and {v14.journey.ats.overall_score:.1f}; "
                             f"their technical interviews score {v15.journey.technical.overall_score:.1f} and {v14.journey.technical.overall_score:.1f}.",
                "evidence": {"DC-15_skill_match": round(_component(v15, "skill_match"), 1), "DC-14_skill_match": round(_component(v14, "skill_match"), 1)}})

    i9 = by_id["DC-09"]
    out.append({"id": "F8", "title": "An integrity tag stops an automatic selection",
                "statement": f"DC-09's Hiring Fit is {i9.score.hiring_fit_percentage:.1f} (selection threshold 70) but {len(ds['events']['DC-09'])} browser events give the tag "
                             f"'{i9.integrity_report.risk_tag.value}', so the outcome is {i9.outcome}.",
                "evidence": {"tag": i9.integrity_report.risk_tag.value, "fit": round(i9.score.hiring_fit_percentage, 1), "outcome": i9.outcome}})

    d30 = by_id["DC-30"]
    out.append({"id": "F9", "title": "A dropped call is held for evidence, not rejected",
                "statement": f"DC-30's call ended after 3 of 7 questions (screening {d30.journey.screening.total_score:.1f}); the outcome is {d30.outcome}.",
                "evidence": {"screening": round(d30.journey.screening.total_score, 1), "outcome": d30.outcome}})

    months = answer_intent_engine.extract_experience_years("I have six months of internship experience")
    out.append({"id": "F10", "title": "'Six months' is read as six years in a screening answer",
                "statement": f"extract_experience_years('I have six months of internship experience') returns {months}. The dataset's fresher candidates therefore say '0.5 years' instead.",
                "evidence": {"returned": months}})
    return out
