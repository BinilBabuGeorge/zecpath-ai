"""
Review plan (Day 64): the improvement list, its prioritisation, the scorecard, the acceptance targets and the action plan

Every improvement is written as a function of the EVIDENCE the probes in `parsers/internal_review.py` collected, so each item quotes numbers
measured on this system, not recollections. The prioritisation is a published formula, not a feeling:

    priority score = impact x confidence / effort          impact 1-5, confidence 1-3, effort in working days
    P0  the system can give a candidate a wrong or unfair result (flag `harm`) and impact is 4 or 5
    P1  score at or above 3.0       P2  at or above 1.5       P3  below 1.5

Impact, confidence and effort are the author's estimates, labelled as such; the formula only makes the reasoning visible and repeatable.
A large item scores low because it is large, so three items are also marked GATE: they must be done before any real candidate data is used, whatever their score.

THE ACCEPTANCE TARGETS. Each target is a measurement the probes already make, with the value that would count as fixed. After a fix, re-running
`python run_day64_internal_review.py` shows whether the target is met: the review is repeatable, and the probes double as regression checks.

REVIEWER FEEDBACK. Day 64 asks for feedback from mentors and reviewers. That cannot be generated; `data/review/feedback_log.json` holds whatever
has been recorded (empty until a session is held), `merge_feedback()` turns each entry into a triage item, and the report states how many
entries it was built from. The session kit is docs/day64_review_session_kit.md.

Input contract:  the evidence dict from internal_review.collect_evidence().
Output contract: lists of plain dicts (JSON-serialisable).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
FEEDBACK_LOG = ROOT / "data" / "review" / "feedback_log.json"
AREAS = ("accuracy", "ux", "performance", "engineering", "governance")


def priority_score(item: Dict[str, Any]) -> float:
    """impact x confidence / effort, rounded to one decimal."""
    return round(item["impact"] * item["confidence"] / item["effort_days"], 1)


def priority_band(item: Dict[str, Any]) -> str:
    if item.get("harm") and item["impact"] >= 4:
        return "P0"
    score = priority_score(item)
    return "P1" if score >= 3.0 else ("P2" if score >= 1.5 else "P3")


def _item(id_: str, area: str, title: str, problem: str, fix: str, impact: int, confidence: int, effort: float, *, harm: bool = False,
          links: Optional[List[str]] = None, acceptance: str = "", decision: str = "", depends: Optional[List[str]] = None, risk: str = "low",
          basis: str = "measured") -> Dict[str, Any]:
    return {"basis": basis, "id": id_, "area": area, "title": title, "problem": problem, "fix": fix, "impact": impact, "confidence": confidence, "effort_days": effort,
            "harm": harm, "links": links or [], "acceptance": acceptance, "decision_needed": decision, "depends_on": depends or [], "risk": risk}


def improvements(ev: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The improvement list, with every number read from the evidence."""
    a, u, g = ev["accuracy"], ev["ux"], ev["engineering"]
    pf, ne, rb, nc = a["format_invariance"], a["negative_controls"], a["robustness"], a["negative_controls"]
    errs, rep, pit = u["error_messages"], u["reports"], u["pitfalls"]
    perf = ev.get("performance_measured") or {}
    stage = perf.get("stage_ms", {})
    f63 = {f["id"]: f for f in ev["findings_from_day63"]}
    losing = rb["losing_3_or_more"]
    heading_losses = [x for x in losing if x["perturbation"].startswith("heading:")]
    bullet_loss = next((x for x in losing if "bullets" in x["perturbation"]), None)
    alias_losses = [x for x in losing if x["perturbation"].startswith("skill spelling")]
    items: List[Dict[str, Any]] = [
        _item("ACC-01", "accuracy", "Wrapped lines of the Skills section are dropped",
              f"The same resume as DOCX and as PDF differs by more than half a point for {len(pf['differing_by_more_than_half_a_point'])} of {pf['candidates']} candidates "
              f"({', '.join(pf['differing_by_more_than_half_a_point'])}); the worst is {pf['worst']['id']} ({pf['worst']['delta']} points, "
              f"{', '.join(f'{k} {v}' for k, v in pf['worst']['components_changed'].items() if k != 'semantic')}). A PDF wraps long lines, and only the first line of the "
              "'Skills:' line is read. Every real PDF wraps. The Day 63 PDF candidates carry this penalty.",
              "Treat the lines that follow a section heading, up to the next heading, as part of that section; join wrapped lines before skill extraction.",
              5, 3, 2.0, harm=True, links=["C1"], acceptance="format_invariance: no candidate differs by more than 0.5 point between DOCX and PDF",
              depends=[]),
        _item("ACC-02", "accuracy", "Nonsense answers earn a middling screening score",
              f"Seven answers of 'asdf qwer zxcv' score {ne['screening_gibberish']}; 'I do not know' scores {ne['screening_dont_know']}; seven off-topic sentences score "
              f"{ne['screening_off_topic']}. The engine counts a turn as an answer to the question asked even when it contains nothing relevant.",
              "Gate each answer on content: require the expected kind of value or at least one topic term; otherwise mark the turn 'needs review' and leave it out of the score.",
              5, 3, 3.0, harm=True, acceptance="negative_controls: every screening control scores below 40, or the call is marked incomplete"),
        _item("ACC-03", "accuracy", "Off-topic HR answers score 75",
              f"Six sentences about pizza and cricket score {ne['hr_off_topic']} on the HR round (relevance is held near 60, confidence 100 because nothing hesitates); "
              f"gibberish scores {ne['hr_gibberish']} and 'Yes.' scores {ne['hr_one_word']}.",
              "Remove the relevance floor; add an off-topic check against the question; do not award confidence to an answer with no content.",
              4, 3, 3.0, harm=True, acceptance="negative_controls: every HR control scores below 40"),
        _item("ACC-04", "accuracy", "A resume without section headings is read as having no experience",
              f63["F3"]["statement"],
              "When the text is long but no section is found, infer sections from dates and job-title patterns; if that fails, send the resume to review instead of scoring it.",
              5, 3, 3.0, harm=True, links=["C1"], acceptance="robustness: a headingless resume keeps its years and scores within 10 points of the same resume with headings"),
        _item("ACC-05", "accuracy", "The raw ATS scale makes the round-disagreement rule fire for most candidates",
              f63["F1"]["statement"] + f" The rule is flagged for {a['round_disagreement_flagged']} of {a['candidates']} candidates on the raw scale and "
              f"{a['round_disagreement_flagged_with_aligned_ats']} on the common scale.",
              "Make the common scale the default (ats_scale='zone_aligned'), then re-check the disagreement threshold on the demo set; record a new golden file for the change.",
              4, 3, 2.0, harm=True, decision="Owner: change a default that alters results", acceptance="round_disagreement_flagged is below half of the candidates",
              risk="medium: changes outcomes, needs a new golden file"),
        _item("ACC-06", "accuracy", "Skills the ATS does not know earn nothing",
              f63["F7"]["statement"] + (" Spelling variants lose points: " + "; ".join(f"{x['perturbation'].split(': ')[1]} ({x['delta']})" for x in alias_losses) + "." if alias_losses else ""),
              "Add the common aliases at once (a day's work), then widen the 72-skill vocabulary by domain with a review of each addition.",
              4, 3, 3.0, acceptance="robustness: no skill-spelling variant loses 3 or more points; DC-15's skill match rises"),
        _item("ACC-07", "accuracy", "Heading and bullet variants change the score",
              "Harmless edits that lose 3 or more points: " + ("; ".join(f"{x['perturbation']} on {x['id']} ({x['delta']})" for x in (heading_losses + ([bullet_loss] if bullet_loss else []))) or "none found") + ".",
              "Accept common heading synonyms (Technical Skills, Core Competencies) inline and on their own line; accept '*' and '•' bullets.",
              3, 3, 2.0, acceptance="robustness: no heading or bullet variant loses 3 or more points"),
        _item("ACC-08", "accuracy", "Technical interview scoring may under-reward DevOps answers",
              "Candidates whose answers were all written at the 'strong' level score on the technical round: " +
              ", ".join(f"{k} {v['mean']} (n={v['candidates']})" for k, v in a["technical_strong_answers_by_domain"].items()) +
              "; the key-concept lists differ by domain, so equal-quality answers do not score alike.",
              "Review the key-concept lists of each domain and tier with a subject expert; add a test that equal-quality answers across domains score within 10 points.",
              4, 2, 3.0, links=["F2"], acceptance="strong answers in every domain score within 10 points of each other"),
        _item("ACC-09", "accuracy", "The screening score barely separates candidates",
              f63["F2"]["statement"] + f" Its rank agreement with the final Hiring Fit is {a['rank_agreement_with_hiring_fit']['screening']}, against "
              f"{a['rank_agreement_with_hiring_fit']['technical']} for the technical round.",
              "Give a re-asked answer less credit than a first answer; score completeness and specificity, not only presence.",
              3, 3, 3.0, depends=["ACC-02"], acceptance="score spread among completed calls is at least 25 points"),
        _item("ACC-10", "accuracy", "'Six months' is read as six years",
              f"extract_experience_years('I have six months of internship experience') returns {pit['six_months_read_as_years']}.",
              "Read the unit that follows the number: months divide by 12.", 3, 3, 0.5, harm=True, acceptance="the function returns 0.5"),
        _item("ACC-11", "accuracy", "The technical tier counts years of any kind",
              "DC-05 has two development years after four in QA and is asked the 'advanced' questions, because the tier comes from total years.",
              "Derive the tier from years in relevant roles (the experience-relevance module already scores relevance).", 3, 2, 2.0, acceptance="DC-05 receives the intermediate tier"),
        _item("ACC-12", "accuracy", "Nothing reads how long a candidate stays",
              f63["F6"]["statement"], "Add an informational flag (never a score) for several short tenures, shown to the recruiter; decide the policy first.",
              2, 2, 1.5, decision="Owner: is job-hopping a recruiter judgement or a system flag?", acceptance="a flag appears for DC-21 and is not used in the score"),
        _item("ACC-13", "accuracy", "Weights and thresholds are reasoned, not calibrated",
              "No labelled hiring outcomes exist, so no weight, cutoff or confidence figure can be checked against reality; 12 labelled ATS pairs are the only human ratings.",
              "Start recording recruiter decisions and outcomes; run the evaluation harness on them before changing any weight.", 5, 3, 20.0, links=["F2", "F3"],
              acceptance="at least 200 labelled candidates and a calibration report", risk="needs data from the backend"),
        _item("ACC-14", "accuracy", "Machine tests exist only for Python",
              "JavaScript and Java candidates are given Python tasks; static code analysis reads Python only.", "Add task variants and a runner per language in a real sandbox.",
              3, 3, 10.0, links=["S2"], acceptance="a JavaScript task is scored for a MERN candidate", depends=["ENG-07"]),
        _item("UX-01", "ux", "Answers are matched to questions by position",
              f"The same five technical answers score {pit['technical_answers_in_order']} in the order asked and {pit['technical_same_answers_reordered']} when sent in a different order; "
              f"screening turns sent in reverse leave {len(pit['screening_reversed_missing'])} categories missing and score {pit['screening_reversed_score']}.",
              "Accept a question id with each answer and match by id; keep position as a fallback with a warning.", 4, 3, 2.0, acceptance="reordering answers that carry ids does not change the score"),
        _item("UX-02", "ux", "Recruiter reports are long, and some lines are cut off",
              f"All {rep['reports']} reports run from {rep['words']['min']} to {rep['words']['max']} words (mean {rep['words']['mean']}); {rep['reports_with_cut_off_summary_lines']} have a cut-off or "
              f"unbalanced line in the summary; {rep['escaped_underscores']} escaped underscores show raw rule codes such as machine\\_test.",
              "Put a one-page summary first; cut text at sentence ends; show plain-language rule names; render underscores properly.", 3, 3, 2.0,
              acceptance="reports_with_cut_off_summary_lines is 0 and the summary fits one page"),
        _item("UX-03", "ux", "Some error messages do not say what to do",
              f"Of {errs['cases']} malformed requests, {errs['rejected_with_error']} get an error; {len(errs['error_not_actionable'])} messages do not say what is allowed or what to send, and "
              f"{len(errs['error_without_field'])} name no field ({'; '.join(errs['error_without_field'])}).",
              "Give every message the field, what was received and what is accepted.", 2, 3, 1.0, acceptance="error_not_actionable and error_without_field are empty"),
        _item("UX-04", "ux", "A screening turn with no text is scored",
              ("; ".join(f"{k} returns a score of {v}" for k, v in errs["scores_returned_for_bad_input"].items()) + " instead of an error.") if errs["scores_returned_for_bad_input"]
              else f"Day 64 measured 1 of {errs['cases']} malformed requests accepted and scored (a turn with no text scored 13.6). Fixed on Day 65: it is now read as silence and the call returns no score.", "Reject a turn with no text with a named field.", 2, 3, 0.5,
              acceptance="accepted_and_scored is empty"),
        _item("PERF-01", "performance", "PDF reading is the slowest part of the cheap stages",
              f"Resume reading takes {perf.get('resume_extraction_ms', {}).get('pdf', {}).get('mean')} ms for a PDF and {perf.get('resume_extraction_ms', {}).get('docx', {}).get('mean')} ms for a DOCX "
              f"(measured here); scoring one ATS pair takes about {round(1000 / perf['ats_single_process']['per_second'], 1) if perf else '?'} ms.",
              "Cache extracted text by file hash (the parse cache from Day 60 already exists) and read pages in one pass.", 2, 2, 1.0, acceptance="a repeated PDF read takes under 5 ms"),
        _item("PERF-02", "performance", "The first request pays an import cost",
              f"The first ATS call in a fresh process takes {perf.get('cold_start_first_ats_ms')} ms; the first candidate's machine-test and report stage takes {perf.get('stage_ms', {}).get('machine test, final aggregation and report', {}).get('max')} ms "
              "against a median of about 20 ms.",
              "Add the machine-test, aggregation and report modules to utils.warmup.warm_up().", 2, 3, 0.5, acceptance="first-candidate stage within 3 times the median"),
        _item("ENG-01", "engineering", "There is no automated test run on every push",
              f"{'No .github/workflows folder exists' if not g['ci_workflow_present'] else 'A workflow exists'}. Two problems this week would have been caught by one: "
              "an f-string that only fails before Python 3.12, and three golden tests that failed because the calendar moved.",
              "Add a GitHub Actions workflow that runs pytest on Python 3.11 and 3.12 for every push.", 4, 3, 0.5, acceptance="a push runs the suite on both versions"),
        _item("ENG-02", "engineering", "Engine code reads today's date",
              f"{len(g['wall_clock_reads'])} reads of the wall clock in engine modules ({', '.join(g['wall_clock_reads'][:3])}, ...). The ATS experience score therefore changes with the day, "
              "which broke three Day 60 tests on 2026-11-22 and a fourth on 2026-11-26 (the first fix pinned the date in only three of the four tests that use the golden ATS outputs).",
              "Pass an as_of date through every API that needs one, defaulting to the date only at the outermost call; add a test that runs the engines under two different dates.",
              4, 3, 2.0, harm=True, acceptance="engine modules read the clock only in one function"),
        _item("ENG-03", "engineering", "The code standard is not followed or enforced",
              f"{g['lines_over_100_chars']['total']} lines over 100 characters in {g['lines_over_100_chars']['files']} of {g['modules']} modules, and {len(g['print_calls_in_engines'])} print() calls in engine modules, "
              "although docs/CODE_STANDARDS.md says otherwise.",
              "Either enforce the standard (flake8 and black in CI, fix the print calls) or change it to a limit the code already meets.", 2, 3, 1.0,
              decision="Owner: enforce or relax the standard", acceptance="CI runs flake8 with the chosen limit and passes", depends=["ENG-01"]),
        _item("ENG-04", "engineering", "Line endings differ between machines",
              ("No .gitattributes file exists. On Day 62 `git status` listed 7 files as modified although only their line endings differed, and Git warned 'LF will be replaced by CRLF' when adding new files." if not g["gitattributes_present"] else "Day 64 measured 0 .gitattributes files and 7 files listed as modified for line endings only. Fixed on Day 65: .gitattributes exists (* text=auto) and the dataset test compares files without regard to line endings."),
              "Add `* text=auto` and normalise once.", 2, 3, 0.25, acceptance="git status shows no changes that are line endings only"),
        _item("ENG-05", "engineering", "Some modules have no test file of their own",
              f"{len(g['modules_without_a_matching_test_file'])} of {g['modules']} modules have no test file named after them (some are covered by another file, for example the batch and parsing services).",
              "Measure coverage with pytest-cov and add tests where a module is not exercised.", 2, 2, 2.0, acceptance="a coverage report is produced in CI"),
        _item("ENG-07", "engineering", "No sandbox exists for running candidate code",
              "The machine-test engine never runs code (by design); real results need a runner.", "Design a container or microVM runner with no network and hard limits before any code runs.",
              3, 3, 10.0, links=["S2"], acceptance="a sandbox design is reviewed"),
        _item("GOV-01", "governance", "Tenant isolation, storage and the gateway are designs, not systems",
              "Carried forward from Days 55 and 59: gaps G1 to G3 (role matrix, job store, tenant isolation for the service role), no gateway, queue or job store.",
              "Build or choose the gateway and job store; fix G1 to G3 before any real data enters.", 4, 3, 10.0, links=["F1", "F4", "F7"], acceptance="an authenticated request reaches a service through the gateway"),
        _item("GOV-02", "governance", "No legal review of consent, retention or fairness",
              "Retention periods and consent rules are proposed defaults; no bias audit exists on real data.", "Commission a legal review and a bias audit before real use.",
              4, 3, 5.0, links=["F6", "S4"], acceptance="a written review exists", decision="Owner: who commissions it"),
    ]
    for it in items:
        if it["id"] in {"ACC-13", "ACC-14", "ENG-07", "GOV-01", "GOV-02"}:
            it["basis"] = "design"                               # a fact about the design or an earlier day's finding, not a number measured by a probe here
    gates = {"GOV-01", "GOV-02", "ACC-13"}                      # must be done before any real candidate data is used, whatever their score
    for it in items:
        it["gate_before_real_use"] = it["id"] in gates
        it["priority_score"] = priority_score(it)
        it["priority"] = priority_band(it)
    return items


def merge_feedback(items: List[Dict[str, Any]], log_path: Path = FEEDBACK_LOG) -> Dict[str, Any]:
    """Add one triage item per recorded reviewer comment. Returns the entries used. Nothing is invented: an empty log adds nothing."""
    entries = json.loads(log_path.read_text(encoding="utf-8")).get("entries", []) if log_path.exists() else []
    for n, e in enumerate(entries, start=1):
        area = e.get("kind", "accuracy") if e.get("kind") in AREAS else "accuracy"
        item = _item(f"FB-{n:03d}", area, f"Reviewer comment ({e.get('stage', 'general')})", e.get("comment", ""), e.get("suggestion", "needs triage"),
                     int(e.get("severity", 3)), 2, 2.0, acceptance="triage with the reviewer")
        item["from_reviewer"] = f"{e.get('reviewer', 'unnamed')} ({e.get('role', 'reviewer')}), {e.get('date', '')}"
        item["priority_score"], item["priority"] = priority_score(item), priority_band(item)
        items.append(item)
    return {"entries": entries, "count": len(entries)}


def acceptance_targets(ev: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Measurements the probes already make, with the value that would count as fixed and whether it is met today."""
    a, u, g = ev["accuracy"], ev["ux"], ev["engineering"]
    rep = u["reports"]
    t = [
        ("T1", "ACC-01", "DOCX and PDF of the same resume differ by at most 0.5 point", len(a["format_invariance"]["differing_by_more_than_half_a_point"]), "<=", 0, "candidates differing"),
        ("T2", "ACC-02", "No screening negative control scores 40 or more", sum(1 for k in ("screening_gibberish", "screening_dont_know", "screening_off_topic") if a["negative_controls"][k] >= 40), "<=", 0, "controls at 40 or more"),
        ("T3", "ACC-03", "No HR negative control scores 40 or more", sum(1 for k in ("hr_gibberish", "hr_one_word", "hr_off_topic") if a["negative_controls"][k] >= 40), "<=", 0, "controls at 40 or more"),
        ("T4", "ACC-05", "Round disagreement is flagged for fewer than half the candidates", a["round_disagreement_flagged"], "<", a["candidates"] / 2, "candidates flagged"),
        ("T5", "ACC-06/07", "No harmless edit loses 3 or more points", len(a["robustness"]["losing_3_or_more"]), "<=", 0, "edits losing points"),
        ("T6", "UX-01", "Reordered technical answers keep their score", round(abs(u["pitfalls"]["technical_answers_in_order"] - u["pitfalls"]["technical_same_answers_reordered"]), 1), "<=", 0, "points of difference"),
        ("T7", "UX-02", "No report has a cut-off summary line", rep["reports_with_cut_off_summary_lines"], "<=", 0, "reports affected"),
        ("T8", "UX-03", "Every error message says what is allowed and names a field", len(u["error_messages"]["error_not_actionable"]) + len(u["error_messages"]["error_without_field"]), "<=", 0, "messages to fix"),
        ("T9", "ACC-10", "'Six months' reads as 0.5 years", u["pitfalls"]["six_months_read_as_years"], "==", 0.5, "years returned"),
        ("T10", "ENG-02", "Engine modules read the clock in at most one place", len(g["wall_clock_reads"]), "<=", 1, "reads"),
        ("T11", "ENG-01", "A CI workflow exists", 1 if g["ci_workflow_present"] else 0, "==", 1, "1 = present"),
    ]
    ops = {"<=": lambda x, y: x <= y, "<": lambda x, y: x < y, "==": lambda x, y: x == y}
    return [{"id": tid, "improvement": item, "target": text, "current": cur, "operator": op, "goal": goal, "unit": unit, "met": bool(ops[op](cur, goal))}
            for tid, item, text, cur, op, goal, unit in t]


SCORECARD = [
    # (area, score 1-5, author's judgement, evidence key)
    ("ATS (resume scoring)", 3, "Sound structure and explainable components, and it ignores personal details; but wrapped skill lines, unknown skills and heading variants cost real points (ACC-01, 04, 06, 07).", "accuracy.format_invariance, robustness"),
    ("Screening call", 2, "Good conversation flow and safe handling of dropped calls; but nonsense scores about 56 and real answers barely differ (ACC-02, 09, 10).", "accuracy.negative_controls, score_spread"),
    ("HR interview", 2, "Fair on fluent, relevant answers; off-topic answers score 75 (ACC-03).", "accuracy.negative_controls"),
    ("Technical interview", 3, "Separates candidates well (spread wide, strongest rank agreement with the final score) and rejects nonsense; order-dependence and domain balance need work (UX-01, ACC-08, ACC-11).", "accuracy.negative_controls, rank_agreement"),
    ("Machine test", 4, "Clear design, never runs candidate code, flags over-fitting and integrity; Python only (ACC-14).", "walkthrough"),
    ("Decision and aggregation", 3, "Safe by construction (no automated rejection, rules move toward review) but the disagreement rule is over-sensitive on the raw scale (ACC-05).", "accuracy.round_disagreement_flagged"),
    ("Governance and security", 3, "Rules, audit and consent logic are built and tested; nothing enforces them yet and a legal review is missing (GOV-01, 02).", "carried from Days 55, 59"),
    ("Observability", 3, "A complete design and prototype; no shipper, store or alert manager.", "Day 61"),
    ("Documentation", 4, "Handbook, architecture, onboarding and one document per day; generated numbers are tested.", "Days 62, 63"),
    ("Tests and delivery", 3, "About 2,059 tests and golden files; but no CI, wall-clock dependence, and a style standard that is not enforced (ENG-01 to 05).", "engineering"),
    ("Performance", 4, "Scoring is cheap (a few milliseconds per stage); only first-request cost and PDF reading stand out (PERF-01, 02).", "performance_measured"),
]

WAVES = [
    {"id": "Wave 0", "name": "Quick wins", "when": "this week (each under a day)", "goal": "Stop avoidable surprises and make every later change safer.",
     "items": ["ENG-01", "ENG-04", "ACC-10", "UX-04", "UX-03", "PERF-02"],
     "exit": "CI runs on 3.11 and 3.12; T9, T11 met; line endings stable."},
    {"id": "Wave 1", "name": "Correctness", "when": "weeks 1 to 4 (one developer)", "goal": "Remove every way the system can give a candidate a wrong or unfair result.",
     "items": ["ACC-01", "ACC-02", "ACC-03", "ACC-04", "ACC-05", "UX-01", "ENG-02"],
     "exit": "T1, T2, T3, T4, T6, T10 met on a fresh run of the review script; the demo dataset is re-run and its results re-read."},
    {"id": "Wave 2", "name": "Quality of scoring and reports", "when": "weeks 5 to 8 (one developer)", "goal": "Better separation between candidates and reports a recruiter reads in a minute.",
     "items": ["ACC-06", "ACC-07", "ACC-08", "ACC-09", "ACC-11", "UX-02", "ENG-03", "ENG-05", "PERF-01"],
     "exit": "T5, T7, T8 met; style standard enforced in CI; coverage reported."},
    {"id": "Wave 3", "name": "Needs data, policy or the backend", "when": "after handover", "goal": "The items that cannot be finished inside this repository.",
     "items": ["ACC-12", "ACC-13", "ACC-14", "ENG-07", "GOV-01", "GOV-02"],
     "exit": "Decisions recorded (job-hopping policy, who owns calibration data, who commissions the legal review)."},
]


def action_plan(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The waves with each item's priority and effort filled in, plus the total effort of the wave."""
    by_id = {i["id"]: i for i in items}
    plan = []
    for w in WAVES:
        rows = [by_id[x] for x in w["items"]]
        plan.append(dict(w, rows=[{"id": r["id"], "title": r["title"], "priority": r["priority"], "effort_days": r["effort_days"], "depends_on": r["depends_on"],
                                   "decision_needed": r["decision_needed"], "acceptance": r["acceptance"]} for r in rows],
                         effort_days=round(sum(r["effort_days"] for r in rows), 1)))
    return plan


DECISIONS = [
    ("D1", "Make the common ATS scale the default (ACC-05)?", "It changes outcomes: 7 of the 30 demo candidates move from hold to selected. It needs a new golden file and an owner's approval."),
    ("D2", "When an answer has no relevant content, score it low or mark it 'needs review' (ACC-02, 03)?", "Both stop nonsense scoring well; 'needs review' keeps the human in the loop for a noisy line."),
    ("D3", "Adopt CI on every push (ENG-01)?", "It would have caught two of this week's problems."),
    ("D4", "Enforce the 100-character standard or relax it (ENG-03)?", "The code breaches it in most modules."),
    ("D5", "Is job-hopping a recruiter judgement or a system flag (ACC-12)?", "A policy choice with fairness implications."),
    ("D6", "Who owns the labelled outcomes needed for calibration (ACC-13)?", "Without them no weight can be defended."),
]
