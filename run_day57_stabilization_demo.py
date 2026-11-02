"""
Day 57 demo -- Debugging & Stabilization. Regenerates every number quoted in docs/day57_debugging_and_stabilization.md:

  1. SWEEP      the 80-case edge-case sweep: the recorded BEFORE (pristine Day 56 code) vs a live run AFTER the fixes.
  2. FIXES      the headline measurement behind each fix, before (recorded) and after (live).
  3. API        the four service classes at their boundary: example success/error envelopes, a fuzz of bad payloads
                (run() must never raise), JSON-safety, determinism.
  4. JOURNEYS   the 8 Day 56 scripted candidates re-run through the fixed pipeline.

Writes logs/day57_stabilization_run.log and data/results/day57_stabilization_report.json.

HONESTY NOTES: the BEFORE files (data/results/day57_*_before.json) were produced once, from a pristine copy of the Day 56
tree, and are evidence -- do not regenerate them. The sweep is 80 hand-chosen cases; a clean sweep shows those cases pass,
not that no other bug exists.
"""

from __future__ import annotations

import json
import logging
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path

logging.disable(logging.CRITICAL)

from docx import Document

from ats_engine.service import ATSService
from interview_ai.service import InterviewIntelligenceService
from parsers.pipeline_simulation import build_matcher, intent_check, load_scenarios, run_journey
from parsers.stability_checks import build_cases, measure_probes, run_sweep, summarise
from scoring.service import DecisionScoringService
from screening_ai.service import ScreeningService

SAMPLES = Path("data/samples")
LOG_PATH, REPORT_PATH = "logs/day57_stabilization_run.log", "data/results/day57_stabilization_report.json"
Path("logs").mkdir(exist_ok=True)
_lines, report = [], {}


def say(s=""):
    print(s); _lines.append(s)


def head(s):
    say(); say("=" * 78); say(s); say("=" * 78)


matcher = build_matcher(SAMPLES)

# ------------------------------------------------------------------ 1 sweep
head("1. EDGE-CASE SWEEP  80 cases, before vs after")
before = json.loads(Path("data/results/day57_edge_sweep_before.json").read_text(encoding="utf-8"))
cases = build_cases(matcher, (SAMPLES / "jds/jd_01_mern_developer.txt").read_text(encoding="utf-8"), (SAMPLES / "resumes/resume_01_mern_developer.txt").read_text(encoding="utf-8"))
after_results = run_sweep(cases)
after = summarise(after_results)
b = before["summary"]
say(f"BEFORE (pristine Day 56 code): {b['failed']} of {b['cases']} cases failed   {b['by_status']}")
say(f"AFTER  (this run)            : {after['failed']} of {after['cases']} cases failed   {after['by_status']}")
say("by area (failed / cases), before -> after:")
for area in sorted(b["by_area"]):
    say(f"   {area:12} {b['by_area'][area]['failed']:>2} / {b['by_area'][area]['cases']:<3} -> {after['by_area'][area]['failed']:>2} / {after['by_area'][area]['cases']}")
fixed = [c for c in before["cases"] if not (c["status"] in ("ok", "rejected_cleanly"))]
after_by_id = {r.id: r for r in after_results}
say(f"{len(fixed)} cases that failed before; every one now passes: {all(after_by_id[c['id']].passed for c in fixed)}")
for c in fixed:
    say(f"   {c['status']:18} {c['id']:34} {c['detail'][:70]}")
assert after["failed"] == 0 and all(after_by_id[c["id"]].passed for c in fixed)
report["sweep"] = {"before": b, "after": after}

# ------------------------------------------------------------------ 2 fixes
head("2. FIXES  the measurement behind each one (before is recorded, after is live)")
bp = json.loads(Path("data/results/day57_probes_before.json").read_text(encoding="utf-8"))["probes"]
ap = measure_probes(matcher, str(SAMPLES))
labels = {
    "years_for_2019_to_2022": "years counted for a job '2019 - 2022'",
    "years_end_before_start": "years for a job whose end is before its start",
    "years_job_starting_2031": "years for a job starting in the future",
    "years_career_from_1900": "years for a career starting in 1900",
    "hr_score_six_yes_answers": "HR score, six answers of 'yes'",
    "hr_score_six_good_answers": "HR score, six thoughtful answers",
    "screening_score_digit_strings": "screening score, a call of digit strings",
    "silent_call_ended_early": "silent caller: call ended early",
    "silent_call_turns_before_it_stopped": "silent caller: turns before the call stopped",
    "rich_introductions_flagged_off_topic_of_3": "natural introductions judged off-topic (of 3)",
    "ats_score_heading_Skills": "ATS score, resume headed 'Skills:'",
    "ats_score_heading_Technical_Skills": "ATS score, same resume headed 'Technical Skills'",
    "zone_when_job_description_has_no_requirements": "ATS zone when the JD has no requirements section",
    "ats_rejected_candidate_fit_raw_and_aligned": "ATS-rejected candidate: fit raw / aligned",
    "ats_rejected_candidate_outcome_raw_and_aligned": "ATS-rejected candidate: outcome raw / aligned",
}
say(f"{'measurement':54} {'before':>22}  {'after':>22}")
for k, label in labels.items():
    say(f"{label:54} {str(bp[k]):>22}  {str(ap[k]):>22}")
tp_b, tp_a = bp["technical_phrasing"], ap["technical_phrasing"]
say("technical scoring, one answer varied (before -> after):")
for k in tp_b:
    say(f"   {k:20} {tp_b[k]:5.1f} -> {tp_a[k]:5.1f}")
say("open gap (not fixed): a confidently wrong answer still scores within 3 points of a correct paraphrase "
    f"({tp_a['wrong_but_confident']} vs {tp_a['correct_paraphrase']})")
assert ap["hr_score_six_yes_answers"] < 50 < ap["hr_score_six_good_answers"] and ap["silent_call_ended_early"] and tp_a["keyword_salad"] < tp_a["correct_paraphrase"]
report["fixes"] = {"before": bp, "after": ap}

# ------------------------------------------------------------------ 3 API
head("3. API BOUNDARY  four services, one stable contract")
examples = [
    ("ATS (real engine)", ATSService(), {"resume_text": "Skills:\nReact.js, Node.js, MongoDB, Express.js\nExperience:\n- Dev, Acme (Jan 2022 - Jan 2025)\n",
                                          "job_description": "Required Skills:\n- React.js and Node.js\n- MongoDB and Express.js\n"}),
    ("Decision (complete evidence)", DecisionScoringService(), {"candidate_id": "C1", "role_type": "technical", "ats_score": 70, "screening_score": 85, "hr_interview_score": 88,
                                                                  "technical_score": 92, "machine_test_score": 90, "ats_zone": "shortlist"}),
    ("Decision (one round only)", DecisionScoringService(), {"candidate_id": "C2", "ats_score": 90}),
    ("Decision (ATS reject zone)", DecisionScoringService(), {"role_type": "non_technical", "ats_score": 70, "screening_score": 90, "hr_interview_score": 90, "ats_zone": "reject"}),
    ("Screening (no turns)", ScreeningService(), {"candidate_id": "C3"}),
    ("Interview (no answers)", InterviewIntelligenceService(), {"interview_type": "hr"}),
]
for name, svc, payload in examples:
    r = svc.run(payload)
    keys = {k: r[k] for k in ("scoring_mode", "ats_score", "zone", "decision", "hold_kind", "hiring_fit_score", "provisional", "call_status", "screening_score", "interview_status") if k in r}
    say(f"  {name:30} {r['status']:8} {keys}")
errors = [("Decision: NaN score", DecisionScoringService(), {"ats_score": float("nan")}), ("Decision: score 150", DecisionScoringService(), {"ats_score": 150}),
          ("Decision: no scores", DecisionScoringService(), {}), ("ATS: no job description", ATSService(), {"resume_text": "x"}),
          ("Interview: unknown type", InterviewIntelligenceService(), {"interview_type": "karaoke"}), ("Screening: bad turn", ScreeningService(), {"turns": [1]})]
say("error envelopes:")
for name, svc, payload in errors:
    e = svc.run(payload)["error"]
    say(f"  {name:30} code={e['code']:15} field={e['field']}")
bad = [None, "text", 42, [], True, {}, {"x": 1}, {"resume_text": None}, {"ats_score": float("nan")}, {"turns": "abc"}, {"answers": 7}, {"interview_type": None}, {"candidate_id": ["a"]},
       {"ats_score": 50, "screening_score": "x"}, {"resume_text": "x" * 300_000, "job_description": "y"}]
n = ok = 0
for cls in (ATSService, ScreeningService, InterviewIntelligenceService, DecisionScoringService):
    for payload in bad:
        n += 1
        r = cls().run(payload)
        json.dumps(r, allow_nan=False)
        ok += r["status"] in ("success", "error")
say(f"fuzz: {n} bad payloads x services -> {ok} well-formed envelopes, 0 exceptions, all JSON-safe (NaN forbidden)")
assert ok == n
same = all(svc.run(p) == svc.run(p) for _, svc, p in examples)
say(f"determinism: every example returns an identical response on a second call: {same}")
assert same
report["api"] = {"fuzz_payloads": n, "well_formed": ok, "deterministic": same}

# ------------------------------------------------------------------ 4 journeys
head("4. DAY 56 JOURNEYS  re-run through the fixed pipeline")
rows = []
for sc in load_scenarios("data/simulation/day56_scenarios.json"):
    f = Path(tempfile.mkdtemp()) / f"{sc.id}.docx"
    d = Document()
    for ln in (SAMPLES / "resumes" / f"{sc.resume}.txt").read_text(encoding="utf-8").splitlines():
        d.add_paragraph(ln)
    d.save(str(f))
    j = run_journey(sc, matcher, f, (SAMPLES / "jds" / f"{sc.jd}.txt").read_text(encoding="utf-8"), date(2026, 10, 30))
    rows.append(j)
    say(f"  {sc.id}  ATS {j.zone:9} scr {j.stages['screening'].summary['score']:5.1f} turns {j.stages['screening'].summary['turns']:2}  fit {j.score_raw.hiring_fit_percentage:5.1f}/{j.score_aligned.hiring_fit_percentage:5.1f}  "
        f"{j.outcome:11}/{j.outcome_aligned:11} {'ok' if intent_check(j) else 'miss'}")
s8 = next(j for j in rows if j.scenario.id == "S8")
say(f"S8 (ATS-rejected): {s8.outcome} / {s8.outcome_aligned}  (Day 56: hold_review / selected)  hold_kind={s8.decision_aligned.hold_kind.value}")
assert s8.outcome_aligned == "hold_review"
report["journeys"] = [{"id": j.scenario.id, "outcome": j.outcome, "outcome_aligned": j.outcome_aligned, "turns": j.stages["screening"].summary["turns"]} for j in rows]
say(f"outcomes: {dict(Counter(j.outcome for j in rows))}; within the author's acceptable set: {sum(intent_check(j) for j in rows)}/8")

Path(LOG_PATH).write_text("\n".join(_lines) + "\n", encoding="utf-8")
Path(REPORT_PATH).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
say(f"\nwrote {LOG_PATH} and {REPORT_PATH}")
