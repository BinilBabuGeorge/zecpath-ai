"""
Full System Simulation (Day 56)

WHAT THIS DAY BUILDS: the first run in which a candidate travels through the REAL
engines from an uploaded file to a final decision, with nothing hand-built in
between. Until now (Days 51-55) the round results were constructed by hand or
by stage-specific demos; this module wires the actual stages together:

    upload (PDF/DOCX -> text)  ->  ATS score + zone  ->  screening call
      ->  HR interview score  ->  technical interview score (technical roles only)
      ->  cross-round aggregation  ->  final recommendation  ->  recruiter report

Each stage is TIMED and RECORDED, and every hand-off is a real object passed to
the next engine (the Day 51 adapters take the engines' own result objects).

TWO WAYS OF READING A JOURNEY
  * DIAGNOSTIC: every stage runs for every candidate, so the stages can be
    compared with each other (does a weak resume predict weak interviews?).
  * FUNNEL: what the PRD would actually do -- only a shortlisted candidate gets
    a call, and a candidate who fails a stage stops there. The cutoffs between
    stages (GATE_MIN) are ASSUMED (50, the same "review" floor Day 52 uses):
    the PRD names the gates but gives no numbers.

INCONSISTENCY DETECTION compares what different stages say about the same person
(`find_inconsistencies`): the experience claimed in the screening call vs the
resume, the ATS verdict vs the interviews, large score spreads across rounds,
screening vs HR, the technical tier chosen from different experience sources,
funnel vs final decision, and raw vs zone-aligned ATS scaling.

AI vs HUMAN JUDGEMENT -- WHAT IS AND IS NOT AVAILABLE, STATED PLAINLY:
  * ATS: 12 resume/JD pairs carry a human-assigned zone (Day 20 review file).
    Real human labels -- but the ATS cutoffs were tuned on these same pairs
    (Days 17-20), so agreement here is optimistic.
  * Interview rounds and the final decision: NO independent human labels exist.
    The scripted candidates carry the AUTHOR'S expected outcomes, written before
    the run. That is design intent, not human judgement. To get a real
    comparison, `write_human_worksheet` produces a blank rating sheet for
    recruiters and `human_agreement` scores it once filled in.

THE CLOCK. The experience parser reads "Present" from `date.today()`, so ATS
results drift with the calendar (a resume written as "3 years" parses as 5.3
today). `frozen_today()` pins the clock INSIDE the simulation so runs are
reproducible, without changing any existing module; `ats_zone_drift()` measures
how much the drift matters.

WHAT THIS IS NOT: a load test. The engines are pure-Python scoring logic; real
speech-to-text, text-to-speech, video and network latency are not simulated, so
the timings describe the scoring layer only.
"""

from __future__ import annotations

import csv
import json
import math
import re
import statistics
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from parsers import experience_parser, experience_relevance
from parsers.answer_intent_engine import extract_experience_years
from parsers.ats_scoring_engine import score_candidate
from parsers.cross_round_aggregation_engine import ats_zone_of, compute_from_round_outputs
from parsers.final_recommendation_engine import decide
from parsers.hiring_report_generator import generate_hiring_report
from parsers.hr_interview_question_bank import ExperienceLevel, InterviewSession, RoleType
from parsers.hr_interview_scoring_engine import score_hr_interview
from parsers.ranking_engine import classify_zone
from parsers.resume_extractor import extract_resume
from parsers.screening_pipeline import RobustConversationController, run_screening_call
from parsers.screening_question_bank import CATEGORIES
from parsers.semantic_matcher import SemanticMatcher
from parsers.speech_to_text import RawSTTResult
from parsers.technical_interview_question_bank import TechnicalDomain, TechnicalInterviewSession, experience_years_to_tier
from parsers.technical_skill_scoring_engine import build_technical_evaluation_report
from utils.logger import get_logger

logger = get_logger(__name__)

STAGES = ("upload", "ats", "screening", "hr_interview", "technical_interview", "aggregation", "decision", "report")
GATE_MIN = {"screening": 50.0, "hr_interview": 50.0, "technical_interview": 50.0}   # ASSUMED, see docstring
EXPERIENCE_TOLERANCE_YEARS = 1.5
SPREAD_THRESHOLD = 30.0
DIVERGENCE_STRONG, DIVERGENCE_WEAK = 70.0, 50.0
OUTCOMES = ("selected", "hold_review", "rejected")


# --------------------------------------------------------------------------- clock
@contextmanager
def frozen_today(as_of: date) -> Iterator[None]:
    """Pin what "Present" means for the experience parser. Since Day 57 this uses the parser's own `reference_date`
    (before that it patched `date`); behaviour is the same, the mechanism is now a supported API."""
    with experience_parser.reference_date(as_of):
        yield


# ---------------------------------------------------------------------- data model
@dataclass
class CandidateScenario:
    id: str
    label: str
    probe: str
    resume: str
    jd: str
    role_type: str
    domain: Optional[str]
    screening: List[Dict[str, Any]]
    hr: List[str]
    technical: Optional[Dict[str, List[str]]]
    acceptable: List[str]
    rationale: str
    reask: Dict[str, str] = field(default_factory=dict)


def load_scenarios(path: str | Path) -> List[CandidateScenario]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [CandidateScenario(**s) for s in data["scenarios"]]


@dataclass
class StageRecord:
    stage: str
    status: str                 # ran | skipped | error
    ms: float = 0.0
    summary: Dict[str, Any] = field(default_factory=dict)
    note: str = ""


@dataclass
class Inconsistency:
    code: str
    severity: str               # info | warning | serious
    stages: Tuple[str, ...]
    detail: str


@dataclass
class JourneyResult:
    scenario: CandidateScenario
    stages: Dict[str, StageRecord]
    ats: Any = None
    screening: Any = None
    hr: Any = None
    technical: Any = None
    score_raw: Any = None
    decision_raw: Any = None
    score_aligned: Any = None
    decision_aligned: Any = None
    report: Any = None
    zone: str = ""
    funnel_stage: str = ""
    funnel_note: str = ""
    resume_years_parsed: float = 0.0
    resume_years_stated: Optional[float] = None
    claimed_years: Optional[float] = None
    tier_used: Optional[str] = None
    inconsistencies: List[Inconsistency] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def total_ms(self) -> float:
        return sum(s.ms for s in self.stages.values())

    @property
    def outcome(self) -> str:
        return self.decision_raw.outcome.value if self.decision_raw is not None else "error"

    @property
    def outcome_aligned(self) -> str:
        return self.decision_aligned.outcome.value if self.decision_aligned is not None else "error"


# ------------------------------------------------------------------------ stages
def reactive_screening_turns(sc: CandidateScenario, max_turns: int = 21) -> List[RawSTTResult]:
    """A candidate who answers the question actually being asked. The controller is run turn by turn so that a re-ask
    (e.g. after an answer is judged off-topic) is met with the candidate's re-ask answer instead of the next scripted line.
    The same controller is then replayed by `run_screening_call` on exactly these turns."""
    answers = dict(zip(CATEGORIES, sc.screening))
    ctl = RobustConversationController(categories=list(CATEGORIES))
    asked: Dict[str, int] = {}
    turns: List[RawSTTResult] = []
    while not ctl.is_call_complete and len(turns) < max_turns:
        cat = ctl.current_category
        if cat is None or cat not in answers:
            break
        asked[cat] = asked.get(cat, 0) + 1
        src = answers[cat]
        text = sc.reask.get(cat, src["text"]) if asked[cat] > 1 else src["text"]
        turn = RawSTTResult(text=text, confidence=src.get("confidence", 0.9))
        turns.append(turn)
        ctl.process_turn(turn)
    return turns


def build_matcher(samples_dir: str | Path = "data/samples") -> SemanticMatcher:
    base = Path(samples_dir)
    corpus = [f.read_text(encoding="utf-8") for f in sorted((base / "resumes").glob("*.txt")) + sorted((base / "jds").glob("*.txt"))]
    return SemanticMatcher(corpus)


def upload_resume(path: str | Path) -> Tuple[str, List[str]]:
    """The real upload path: only PDF and DOCX are supported by the extractor (PRD also lists DOC)."""
    ex = extract_resume(str(path))
    text = getattr(ex, "cleaned_text", None) or getattr(ex, "raw_text", "") or ""
    return text, list(getattr(ex, "warnings", []) or [])


def ats_zone(result: Any) -> str:
    """The ATS zone, from the one shared definition (Day 57 moved it to the aggregation engine)."""
    return ats_zone_of(result)


def _stated_years(text: str) -> Optional[float]:
    m = re.search(r"(\d+(?:\.\d+)?)\+?\s*years", text, re.I)
    return float(m.group(1)) if m else None


def _timed(rec: Dict[str, StageRecord], name: str, fn, *a, **k):
    t0 = time.perf_counter()
    try:
        out = fn(*a, **k)
        rec[name] = StageRecord(name, "ran", (time.perf_counter() - t0) * 1000)
        return out
    except Exception as exc:       # a stage failure is a finding, not a crash
        rec[name] = StageRecord(name, "error", (time.perf_counter() - t0) * 1000, note=f"{type(exc).__name__}: {exc}")
        logger.warning("stage %s failed: %s", name, exc)
        return None


def run_journey(sc: CandidateScenario, matcher: SemanticMatcher, resume_file: str | Path, jd_text: str,
                as_of: date, generated_at: str = "2026-10-30") -> JourneyResult:
    rec: Dict[str, StageRecord] = {}
    j = JourneyResult(sc, rec)
    technical_role = sc.role_type == "technical"
    with frozen_today(as_of):
        up = _timed(rec, "upload", upload_resume, resume_file)
        if up is None:
            j.errors.append("upload failed"); return j
        text, warnings = up
        rec["upload"].summary = {"chars": len(text), "warnings": len(warnings), "format": Path(resume_file).suffix.lower()}

        j.ats = _timed(rec, "ats", score_candidate, text, jd_text, matcher)
        if j.ats is not None:
            j.zone = ats_zone(j.ats)
            rec["ats"].summary = {"score": round(j.ats.overall_score, 1), "zone": j.zone, "role_category": j.ats.role_category}
        entries = experience_parser.parse_experience(text)
        j.resume_years_parsed = round(experience_parser.compute_total_experience(entries).total_years, 1)
        j.resume_years_stated = _stated_years(text)

        turns = reactive_screening_turns(sc)
        call = _timed(rec, "screening", run_screening_call, turns, candidate_id=sc.id, job_role=sc.label)
        if call is not None:
            j.screening = call.scoring_result
            rec["screening"].summary = {"score": round(call.scoring_result.total_score, 1), "answered": len(call.categories_answered), "missing": list(call.categories_missing), "turns": len(turns), "reasks": len(turns) - len(CATEGORIES)}
            j.claimed_years = extract_experience_years(sc.screening[2]["text"])

        level = ExperienceLevel.FRESHER if j.resume_years_parsed < 1 else ExperienceLevel.EXPERIENCED
        role = RoleType.TECHNICAL if technical_role else RoleType.NON_TECHNICAL

        def _hr():
            s = InterviewSession.start(level, role)
            for answer in sc.hr:
                if s.is_complete:
                    break
                s.submit_response(answer)
            return score_hr_interview(s)
        j.hr = _timed(rec, "hr_interview", _hr)
        if j.hr is not None:
            rec["hr_interview"].summary = {"score": round(j.hr.overall_hr_score, 1), "answered": j.hr.num_questions_answered}

        if technical_role and sc.technical:
            def _tech():
                s = TechnicalInterviewSession.start(TechnicalDomain(sc.domain), j.resume_years_parsed)
                j.tier_used = s.tier.value
                for answer in sc.technical[s.tier.value]:
                    if s.is_complete:
                        break
                    s.submit_response(answer)
                return build_technical_evaluation_report(s)
            j.technical = _timed(rec, "technical_interview", _tech)
            if j.technical is not None:
                rec["technical_interview"].summary = {"score": round(j.technical.overall_score, 1), "tier": j.tier_used}
        else:
            rec["technical_interview"] = StageRecord("technical_interview", "skipped", note="non-technical role: no technical round")

        def _agg(scale: str):
            return compute_from_round_outputs(ats=j.ats, screening=j.screening, hr=j.hr, technical=j.technical, ats_scale=scale,
                                              role_type=role, experience_level=level, candidate_id=sc.id)
        j.score_raw = _timed(rec, "aggregation", _agg, "raw")
        j.score_aligned = _agg("zone_aligned") if j.score_raw is not None else None
        if j.score_raw is not None:
            j.decision_raw = _timed(rec, "decision", decide, j.score_raw)
            j.decision_aligned = decide(j.score_aligned) if j.score_aligned is not None else None
            if j.decision_raw is not None:
                rec["decision"].summary = {"outcome": j.decision_raw.outcome.value, "hiring_fit": round(j.score_raw.hiring_fit_percentage, 1),
                                           "provisional": j.score_raw.provisional, "automation_eligible": j.decision_raw.automation_eligible}
                j.report = _timed(rec, "report", generate_hiring_report, j.decision_raw, j.score_raw, ats=j.ats, screening=j.screening,
                                  hr=j.hr, technical=j.technical, generated_at=generated_at, role_title=sc.label, candidate_label=sc.id)
    j.funnel_stage, j.funnel_note = funnel_outcome(j)
    j.inconsistencies = find_inconsistencies(j)
    return j


# ------------------------------------------------------------------------ funnel
def funnel_outcome(j: JourneyResult) -> Tuple[str, str]:
    """Where the PRD funnel would stop this candidate, under the ASSUMED GATE_MIN cutoffs."""
    if j.ats is None:
        return "error", "no ATS result"
    if j.zone == "reject":
        return "stopped_at_ats", "ATS zone REJECT: no call is triggered"
    if j.zone != "shortlist":
        return "held_at_ats", f"ATS zone {j.zone.upper()}: needs a human before any call"
    for stage, obj, key in (("screening", j.screening, "total_score"), ("hr_interview", j.hr, "overall_hr_score"),
                            ("technical_interview", j.technical, "overall_score")):
        if stage == "technical_interview" and j.scenario.role_type != "technical":
            continue
        if obj is None:
            return f"stopped_at_{stage}", "stage produced no result"
        if getattr(obj, key) < GATE_MIN[stage]:
            return f"stopped_at_{stage}", f"{stage} score {getattr(obj, key):.1f} below the assumed gate {GATE_MIN[stage]:.0f}"
    return "reached_final_decision", "passed every gate"


# --------------------------------------------------------------- inconsistencies
def find_inconsistencies(j: JourneyResult) -> List[Inconsistency]:
    out: List[Inconsistency] = []

    def add(code: str, sev: str, stages: Tuple[str, ...], detail: str) -> None:
        out.append(Inconsistency(code, sev, stages, detail))

    parsed, stated, claimed = j.resume_years_parsed, j.resume_years_stated, j.claimed_years
    if claimed is not None:
        refs = [v for v in (parsed, stated) if v is not None]
        nearest = min(refs, key=lambda v: abs(v - claimed)) if refs else None
        if nearest is not None and abs(claimed - nearest) > EXPERIENCE_TOLERANCE_YEARS:
            add("EXP_CLAIM_VS_RESUME", "serious", ("upload", "screening"),
                f"screening claim {claimed:g}y vs resume {stated if stated is not None else 'n/a'}y stated / {parsed:g}y from dates")
    if stated is not None and abs(stated - parsed) > EXPERIENCE_TOLERANCE_YEARS:
        add("RESUME_STATED_VS_DATES", "warning", ("upload", "ats"),
            f"resume says {stated:g}y but its dates add up to {parsed:g}y (a 'Present' end date is counted up to today)")
    if j.tier_used and claimed is not None:
        claimed_tier = experience_years_to_tier(claimed).value
        if claimed_tier != j.tier_used:
            add("TECH_TIER_SOURCE", "warning", ("screening", "technical_interview"),
                f"technical tier '{j.tier_used}' came from resume dates ({parsed:g}y); the claimed {claimed:g}y would give '{claimed_tier}'")
    scores = {c.round_name: c.score for c in (j.score_aligned.contributions if j.score_aligned is not None else []) if isinstance(c.score, (int, float))}
    if len(scores) >= 3 and max(scores.values()) - min(scores.values()) >= SPREAD_THRESHOLD:
        lo, hi = min(scores, key=scores.get), max(scores, key=scores.get)
        add("ROUND_SPREAD", "warning", (lo, hi), f"{hi} {scores[hi]:.0f} vs {lo} {scores[lo]:.0f} (spread {max(scores.values()) - min(scores.values()):.0f}, on the zone-aligned scale)")
    later = [v for v in (getattr(j.screening, "total_score", None), getattr(j.hr, "overall_hr_score", None), getattr(j.technical, "overall_score", None)) if v is not None]
    if later:
        avg = sum(later) / len(later)
        if j.zone in ("reject", "review") and avg >= DIVERGENCE_STRONG:
            add("ATS_BELOW_INTERVIEWS", "warning", ("ats", "screening"), f"ATS zone {j.zone.upper()} but the interview average is {avg:.0f}: possible ATS false negative")
        if j.zone == "shortlist" and avg < DIVERGENCE_WEAK:
            add("ATS_ABOVE_INTERVIEWS", "warning", ("ats", "hr_interview"), f"ATS SHORTLIST but the interview average is {avg:.0f}: the resume did not predict the interviews")
    if j.screening is not None and j.hr is not None and abs(j.screening.total_score - j.hr.overall_hr_score) >= 25:
        add("SCREENING_VS_HR", "info", ("screening", "hr_interview"), f"screening {j.screening.total_score:.0f} vs HR {j.hr.overall_hr_score:.0f}")
    if j.decision_raw is not None:
        if j.funnel_stage.startswith("stopped") and j.outcome == "selected":
            add("FUNNEL_VS_DECISION", "serious", ("decision",), f"funnel says {j.funnel_stage} but the decision engine says SELECTED")
        if j.funnel_stage == "reached_final_decision" and j.outcome == "rejected":
            add("FUNNEL_VS_DECISION", "warning", ("decision",), "passed every gate but the decision engine says REJECTED")
        if j.funnel_stage in ("stopped_at_ats", "held_at_ats"):
            via = [n for n, o in (("raw", j.outcome), ("zone-aligned", j.outcome_aligned)) if o == "selected"]
            if via:
                add("ATS_GATE_BYPASSED", "serious", ("ats", "decision"),
                    f"ATS zone {j.zone.upper()} (the funnel would not advance this candidate) yet the {' and '.join(via)} ATS scale gives SELECTED: interview strength outweighs a no-match resume")
        if j.outcome != j.outcome_aligned:
            add("ATS_SCALE_CHANGES_OUTCOME", "warning", ("ats", "decision"), f"raw ATS scale -> {j.outcome}; zone-aligned scale -> {j.outcome_aligned}")
        if j.score_raw is not None and j.score_raw.provisional:
            add("PROVISIONAL_EVIDENCE", "info", ("aggregation",), f"missing rounds: {', '.join(j.score_raw.missing_rounds) or 'none'}; automation_eligible={j.decision_raw.automation_eligible}")
    for r in j.stages.values():
        if r.status == "error":
            add("STAGE_ERROR", "serious", (r.stage,), r.note)
    return out


# --------------------------------------------------------------------- AI vs human
def load_ats_human_labels(path: str | Path = "data/ground_truth_ats/day20_manual_review_revised.json") -> List[Dict[str, str]]:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return [{"resume": p["resume_id"], "jd": p["jd_id"], "human_zone": p["expected_zone"]} for p in d["pairs"]]


def ats_vs_human(matcher: SemanticMatcher, as_of: date, samples_dir: str | Path = "data/samples",
                 labels: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, Any]]:
    base, rows = Path(samples_dir), []
    with frozen_today(as_of):
        for lab in labels or load_ats_human_labels():
            res = score_candidate((base / "resumes" / f"{lab['resume']}.txt").read_text(encoding="utf-8"),
                                  (base / "jds" / f"{lab['jd']}.txt").read_text(encoding="utf-8"), matcher)
            z = ats_zone(res)
            rows.append({**lab, "score": round(res.overall_score, 1), "ai_zone": z, "agree": z == lab["human_zone"].lower()})
    return rows


def ats_zone_drift(matcher: SemanticMatcher, date_a: date, date_b: date, **kw: Any) -> Dict[str, Any]:
    """How many ATS zones change when only the calendar date changes."""
    a, b = ats_vs_human(matcher, date_a, **kw), ats_vs_human(matcher, date_b, **kw)
    flips = [(x["resume"], x["ai_zone"], y["ai_zone"]) for x, y in zip(a, b) if x["ai_zone"] != y["ai_zone"]]
    return {"pairs": len(a), "zone_changes": len(flips), "changes": flips,
            "max_score_shift": round(max(abs(x["score"] - y["score"]) for x, y in zip(a, b)), 1)}


def parsed_years_asof(resume_text: str, as_of: date) -> float:
    with frozen_today(as_of):
        return round(experience_parser.compute_total_experience(experience_parser.parse_experience(resume_text)).total_years, 1)


def tier_drift(resumes: Dict[str, str], date_a: date, date_b: date) -> List[Dict[str, Any]]:
    """Technical question tier (chosen from resume-parsed years) for the same resume on two different dates."""
    rows = []
    for rid, text in resumes.items():
        ya, yb = parsed_years_asof(text, date_a), parsed_years_asof(text, date_b)
        ta, tb = experience_years_to_tier(ya).value, experience_years_to_tier(yb).value
        rows.append({"resume": rid, "years_a": ya, "years_b": yb, "tier_a": ta, "tier_b": tb, "changed": ta != tb})
    return rows


WORKSHEET_COLUMNS = ["candidate_id", "label", "ai_ats_score", "ai_ats_zone", "ai_screening", "ai_hr", "ai_technical", "ai_hiring_fit", "ai_outcome",
                     "human_final_outcome", "human_rater", "human_notes"]


def write_human_worksheet(journeys: List[JourneyResult], path: str | Path) -> int:
    """A blank rating sheet for recruiters: AI numbers shown, human columns empty."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(WORKSHEET_COLUMNS)
        for j in journeys:
            w.writerow([j.scenario.id, j.scenario.label, getattr(j.ats, "overall_score", ""), j.zone, getattr(j.screening, "total_score", ""),
                        getattr(j.hr, "overall_hr_score", ""), getattr(j.technical, "overall_score", ""),
                        round(j.score_raw.hiring_fit_percentage, 1) if j.score_raw is not None else "", j.outcome, "", "", ""])
    return len(journeys)


def load_human_ratings(path: str | Path) -> Dict[str, List[str]]:
    p = Path(path)
    if not p.exists():
        return {}
    out: Dict[str, List[str]] = {}
    with open(p, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            v = (row.get("human_final_outcome") or "").strip().lower()
            if v in OUTCOMES:
                out.setdefault(row["candidate_id"], []).append(v)
    return out


def human_agreement(ai: Dict[str, str], human: Dict[str, List[str]]) -> Dict[str, Any]:
    """Exact agreement and the two costly disagreements (AI selects what a human rejects, and the reverse)."""
    rated = [(cid, r) for cid, rs in human.items() if cid in ai for r in rs]
    if not rated:
        return {"ratings": 0, "agreement": None, "note": "no human ratings yet"}
    agree = sum(ai[c] == r for c, r in rated)
    return {"ratings": len(rated), "candidates": len({c for c, _ in rated}), "agreement": round(agree / len(rated), 3),
            "ai_selected_human_rejected": sum(ai[c] == "selected" and r == "rejected" for c, r in rated),
            "ai_rejected_human_selected": sum(ai[c] == "rejected" and r == "selected" for c, r in rated)}


def intent_check(j: JourneyResult) -> bool:
    """Author's a-priori acceptable set (design intent -- NOT human judgement)."""
    return j.outcome in j.scenario.acceptable


# -------------------------------------------------------------------- performance
def percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values); k = (len(s) - 1) * p / 100.0
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] if lo == hi else s[lo] + (s[hi] - s[lo]) * (k - lo)


def stage_timing(journeys: List[JourneyResult]) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for st in STAGES:
        ms = [j.stages[st].ms for j in journeys if st in j.stages and j.stages[st].status == "ran"]
        if ms:
            out[st] = {"n": len(ms), "median_ms": round(statistics.median(ms), 2), "p95_ms": round(percentile(ms, 95), 2), "max_ms": round(max(ms), 2)}
    return out


# --------------------------------------------------------------- targeted probes
def try_upload(path: str | Path) -> Dict[str, Any]:
    """What the real upload path does with a given file: text out, or a named error. Never raises."""
    try:
        text, warnings = upload_resume(path)
        return {"file": Path(path).name, "result": "text" if text.strip() else "empty_text", "chars": len(text), "warnings": len(warnings)}
    except Exception as exc:
        return {"file": Path(path).name, "result": "error", "error": f"{type(exc).__name__}: {str(exc)[:80]}"}


def screening_isolation_probe(scenarios: List[CandidateScenario]) -> List[Dict[str, Any]]:
    """Each scripted answer is put to the engine ALONE against its own question, so the engine's reading of the answer
    is separated from conversation-flow effects."""
    rows = []
    for sc in scenarios:
        for cat, ans in zip(CATEGORIES, sc.screening):
            call = run_screening_call([RawSTTResult(text=ans["text"], confidence=ans.get("confidence", 0.9))], categories=[cat], candidate_id=sc.id, job_role="probe")
            q = call.scoring_result.question_scores[0]
            rows.append({"candidate": sc.id, "category": cat, "quality": q.quality.value, "score": round(q.weighted_total, 1)})
    return rows


_PHRASING_BASE = [
    "I'm a full-stack developer with about three years on the MERN stack and I led a migration to TypeScript.",
    "I built an internal admin platform with an Express and MongoDB backend, a REST API, and a React dashboard with JWT authentication.",
    "__VARIED__",
    "Indexes let MongoDB avoid a full collection scan, giving faster lookups. They use a B-tree structure, with slower writes and extra storage as the trade-off.",
    "I'd check logs and monitoring to see where requests stall, then look at the connection pool and database latency and tune timeout settings.",
]
PHRASING_VARIANTS = {
    "rubric_phrases": "Node.js is single-threaded and non-blocking. The event loop runs in phases, like the timers phase and the poll phase, and takes callbacks from the task queue. Heavy I/O is delegated by libuv to a background thread pool, and promise microtasks run between phases.",
    "correct_paraphrase": "Node runs your JavaScript on one thread, but it never sits waiting on slow work like files or network calls. It hands those off, carries on with other requests, and runs your callback when the result is ready, so one thread can serve many users at once.",
    "keyword_salad": "event loop libuv thread pool task queue timers phase poll phase microtask non-blocking single-threaded callbacks",
    "wrong_but_confident": "Node.js creates a new thread for every request, which is why it is so fast, and the event loop is just the loop that restarts the server when it crashes.",
}


def technical_phrasing_probe(years: float = 3.0) -> Dict[str, float]:
    """The same concept answered four ways in one intermediate-tier interview; only the event-loop answer varies."""
    out: Dict[str, float] = {}
    for name, text in PHRASING_VARIANTS.items():
        s = TechnicalInterviewSession.start(TechnicalDomain.MERN, years)
        for ans in _PHRASING_BASE:
            if s.is_complete:
                break
            s.submit_response(text if ans == "__VARIED__" else ans)
        out[name] = round(build_technical_evaluation_report(s).overall_score, 1)
    return out
