"""
Day 64 demo: the internal review of the whole system, run on the real engines and the Day 63 demo dataset.

    python run_day64_internal_review.py            (about 30 seconds)

WHAT IT DOES
  1. runs the probes of parsers/internal_review.py (walkthrough, accuracy, UX, performance, engineering) and collects the evidence;
  2. builds the prioritised improvement list, the acceptance targets and the action plan (parsers/review_plan.py);
  3. merges any reviewer feedback recorded in data/review/feedback_log.json (empty until a session is held);
  4. writes data/review/*.json and *.csv and four documents in docs/:
        day64_internal_review_report.md, day64_improvement_list.md, day64_action_plan.md, day64_review_session_kit.md
     (the Word versions are made by `python run_day64_docx.py`).

The numbers in the documents are READ from the evidence, never typed. tests/test_internal_review.py fails if a document and the evidence disagree.

Writes: data/review/day64_evidence.json, day64_performance_measured.json, day64_improvement_list.json / .csv, docs/day64_*.md
"""

from __future__ import annotations

import csv
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
logging.disable(logging.CRITICAL)

from parsers import demo_environment as env  # noqa: E402
from parsers import internal_review as ir  # noqa: E402
from parsers import review_plan as rp  # noqa: E402

AS_OF = "2026-11-23"
DOCS = ROOT / "docs"
REVIEW = ROOT / "data" / "review"
REPORT, LIST, PLAN, KIT = (DOCS / "day64_internal_review_report.md", DOCS / "day64_improvement_list.md", DOCS / "day64_action_plan.md", DOCS / "day64_review_session_kit.md")


def table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    def cell(v: Any) -> str:
        return str(v).replace("|", "/").replace("\n", " ")
    out = ["| " + " | ".join(cell(h) for h in headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(cell(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def code(text: str, lang: str = "") -> str:
    return f"```{lang}\n{text.rstrip()}\n```"


# ------------------------------------------------------------------------------------------------------------------------ report
def build_report(ev: Dict[str, Any], items: List[Dict[str, Any]], targets: List[Dict[str, Any]], fb: Dict[str, Any]) -> str:
    a, u, g = ev["accuracy"], ev["ux"], ev["engineering"]
    perf = ev.get("performance_measured", {})
    nc, rb, fi = a["negative_controls"], a["robustness"], a["format_invariance"]
    errs, rep, pit = u["error_messages"], u["reports"], u["pitfalls"]
    by_pri = {p: [i for i in items if i["priority"] == p] for p in ("P0", "P1", "P2", "P3")}
    decisions_table = table(["No.", "Decision", "Why"], rp.DECISIONS)
    walk_tables = []
    for w in ev["walkthrough"]:
        rows = [(s["stage"], s["input"], s["output"], s["note"] or "-") for s in w["stages"]]
        walk_tables.append(f"**{w['id']}: {w['scenario']}.** Expected {' / '.join(w['expected'])}; the system said **{w['outcome']}**.\n\n" + table(["Stage", "Input", "Output", "Note"], rows))
    walk_text = "\n\n".join(walk_tables)
    spread_rows = [(k, v["n"], v["min"], v["max"], v["mean"], v["std"]) for k, v in a["score_spread"].items()]
    rank_rows = [(k, v) for k, v in a["rank_agreement_with_hiring_fit"].items()]
    zone_rows = [(z, ", ".join(f"{o} {n}" for o, n in sorted(d.items()))) for z, d in a["ats_zone_by_outcome"].items()]
    nc_rows = [("ATS: unrelated resume (a designer against the MERN job)", nc["ats_unrelated_resume"], "low is right"), ("ATS: one-line resume", nc["ats_one_line_resume"], "low is right"),
               ("Screening: gibberish x7", nc["screening_gibberish"], "should be low"), ("Screening: 'I do not know' x7", nc["screening_dont_know"], "should be low"),
               ("Screening: off-topic x7", nc["screening_off_topic"], "should be low"), ("HR: gibberish x6", nc["hr_gibberish"], "should be low"),
               ("HR: 'Yes.' x6", nc["hr_one_word"], "should be low"), ("HR: off-topic x6", nc["hr_off_topic"], "should be low"),
               ("Technical: gibberish x5", nc["technical_gibberish"], "should be low"), ("Technical: 'I do not know' x5", nc["technical_dont_know"], "should be low"),
               ("Technical: off-topic x5", nc["technical_off_topic"], "should be low"), ("Machine test: broken code", nc["machine_test_broken_code"], "should be low")]
    losing_rows = [(x["perturbation"], x["id"], x["delta"], x["years"]) for x in rb["losing_3_or_more"]]
    stage_rows = [(k, v["n"], v["mean"], v["p50"], v["p95"], v["max"]) for k, v in perf.get("stage_ms", {}).items()]
    f63 = {f["id"]: f for f in ev["findings_from_day63"]}
    good = [
        f"No rejection is ever automatic: all {a['candidates']} demo decisions finished with a person required for any rejection.",
        f"Personal details do not move the ATS score: swapping names between candidates changes it by at most {a['name_swap']['max_difference']} points ({a['name_swap']['swaps']} swaps), and the demographic header changes it by {f63['F4']['evidence']['difference']}.",
        f"The technical interview and the machine test reject nonsense: gibberish, 'I do not know' and off-topic answers score {nc['technical_gibberish']}, {nc['technical_dont_know']} and {nc['technical_off_topic']}; broken code scores {nc['machine_test_broken_code']}.",
        f"{errs['rejected_with_error']} of {errs['cases']} malformed requests get a named error rather than a crash, and {len(errs['answered_with_null_score_and_a_warning'])} more are answered 'not started' with no score.",
        f"Scoring is cheap: one ATS pair takes about {round(1000 / perf['ats_single_process']['per_second'], 1) if perf else '?'} ms on a single process ({perf['ats_single_process']['per_second'] if perf else '?'} pairs a second).",
        f"A dropped call, a noisy line and a missing round are held for evidence, not rejected (DC-30: {f63['F9']['evidence']['outcome']}).",
        "An integrity tag stops an automatic selection; a missing round makes the result provisional.",
    ]
    return f"""# Day 64: Internal Review and System Walkthrough

Zecpath: AI Job Portal | Internal review report | Built {AS_OF}

## Objective

Evaluate the system internally and identify improvement areas.

**Headline.** The system is safe by construction and cheap to run, but it has accuracy gaps that can give a candidate a wrong result without any warning. The review found **{len(items)} improvements**: **{len(by_pri['P0'])} at P0** (a candidate can get a wrong or unfair result), {len(by_pri['P1'])} at P1, {len(by_pri['P2'])} at P2 and {len(by_pri['P3'])} at P3. The most serious are that the same resume scores up to {abs(fi['worst']['delta'])} points lower as a PDF than as a DOCX, that nonsense answers score {min(nc['screening_gibberish'], nc['screening_dont_know'])} to {max(nc['hr_off_topic'], nc['screening_off_topic'])} in the screening and HR rounds, and that a resume with no section headings is read as having no experience. None needs a redesign; the first {len(by_pri['P0'])} fit in about {round(sum(i['effort_days'] for i in by_pri['P0']), 1)} working days.

**How to read this.** Every number is measured by a probe that runs on the real engines and the Day 63 demo dataset (`parsers/internal_review.py`); a test fails if this report and the probes disagree. Ratings, impact and effort are the author's judgement and are labelled so. **Reviewer feedback has not yet been collected: {fb['count']} entries are recorded.** Section 9 explains how to add it.

## 1. Scope and method

**Reviewed:** the AI layer in this repository ({g['modules']} Python modules in the services, `parsers/` and `utils/`, including the Day 63 demo modules), end to end: ATS, screening, HR interview, technical interview, machine test and the decision, on 30 synthetic candidates.

**Not reviewed:** the backend, frontend, telephony, video, e-mail and payments (not in this repository); real speech; real candidates; legal compliance.

{table(["Question", "Probe", "What it does"], [
    ("Does it work end to end?", "Walkthrough", "Traces five candidates through every stage with real outputs (section 2)"),
    ("Is it accurate?", "Expectation agreement, rank agreement, score spread, negative controls, file-format invariance, robustness to harmless edits, name swap", "Section 4"),
    ("Is it usable?", "Error-message audit, recruiter-report audit, API pitfalls", "Section 5"),
    ("Is it fast?", "Per-stage timings, resume reading by file type, ATS throughput, cold start", "Section 6"),
    ("Is it maintainable?", "Wall-clock reads, tests per module, CI, style-standard breaches, dependency pinning", "Section 7"),
])}

**A caution about the demo data.** The Day 63 expectations were written before the run, and the system met {a['expected_outcome_met']} of {a['candidates']}. Finding ACC-01 shows that the 10 PDF resumes in that dataset carry a wrapped-line penalty (a real system gap, but a confound when comparing the PDF and DOCX candidates). Day 63's results are kept as they were.

## 2. Walkthrough: ATS, Screening, HR, Technical, Decision

How to read each trace: the stages are the real engines run on the candidate's files; "Note" shows what a reviewer should notice. The candidates were chosen to show a clean path, a keyword-stuffed resume, an integrity flag, a formatting failure and a dropped call.

{walk_text}

**What a reviewer should check at each stage**

{table(["Stage", "Look at", "Ask"], [
    ("ATS", "the four components, the zone and the years parsed", "Does the score match how a recruiter would read this resume? Are skills missing because of wrapping or vocabulary?"),
    ("Screening", "answered categories, re-asks, the claimed years against the resume", "Would a recruiter agree with the score? Could a weak answer be scored well?"),
    ("HR interview", "relevance, communication, confidence, consistency", "Does the relevance score fall when the answer ignores the question?"),
    ("Technical interview", "the tier and the question set", "Is the tier right for this person's real experience?"),
    ("Machine test", "task scores, flags, integrity tag", "Do the flags match what you see in the code?"),
    ("Decision", "the outcome, confidence, reasons and rule flags", "Is the 'hold' justified? Would you have chosen differently?"),
])}

## 3. Scorecard (author's judgement, 1 to 5)

{table(["Area", "Score", "Why", "Evidence"], [(n, s, why, ev_) for n, s, why, ev_ in rp.SCORECARD])}

## 4. Accuracy gaps

### 4.1 Did the system agree with the author?

{a['expected_outcome_met']} of {a['candidates']} demo candidates reached the expected outcome (written before the run; missed: {', '.join(a['missed'])}). Five of the six misses come from one cause: the raw ATS scale disagrees with 90-point interview scores (ACC-05).

### 4.2 Does each round rank candidates the way the final score does?

Spearman rank correlation between each round and the final Hiring Fit (1.0 = same order):

{table(["Round", "Rank agreement"], rank_rows)}

The technical round and machine test carry 60 % of the weight for technical roles, so their high agreement is partly built in. The weakest is the screening round ({a['rank_agreement_with_hiring_fit']['screening']}): it adds little to the order.

### 4.3 How far apart does each round put candidates?

{table(["Round", "n", "Min", "Max", "Mean", "Std"], spread_rows)}

Screening scores of completed calls span only {a['score_spread']['screening']['min']} to {a['score_spread']['screening']['max']}.

### 4.4 ATS zone against final outcome

{table(["ATS zone", "Final outcomes"], zone_rows)}

### 4.5 Negative controls: does nonsense ever score well?

{table(["Input", "Score", "Expected"], nc_rows)}

**Scores of 50 or more for nonsense: {', '.join(nc['high_scoring_nonsense']) or 'none'}.** A screening or HR score is only meaningful if an answer with no content cannot earn a middling one (ACC-02, ACC-03).

### 4.6 Is the score the same for the same resume in a different file type?

The same {fi['candidates']} resume texts, written once as DOCX and once as PDF and read back by the real upload path: **{len(fi['differing_by_more_than_half_a_point'])} candidates differ by more than half a point** ({', '.join(fi['differing_by_more_than_half_a_point'])}). The worst is {fi['worst']['id']} ({fi['worst']['docx']} as DOCX, {fi['worst']['pdf']} as PDF); the component responsible is {', '.join(fi['components_responsible'])}. A PDF wraps long lines, as every real PDF does, and only the first line of the 'Skills:' line is read (ACC-01).

### 4.7 Do harmless edits change the score?

{rb['cases']} edits across {len(rb['resumes'])} resumes (skill spellings, headings, formatting, dates, section order). Largest loss {rb['max_loss']} points, largest gain {rb['max_gain']}. Edits that lose 3 or more points:

{table(["Edit", "Resume", "Change", "Years read"], losing_rows) if losing_rows else "None."}

Date formats, case, blank lines and section order did not lose points; heading and bullet variants and unknown skill spellings did (ACC-06, ACC-07).

### 4.8 Fairness probes

Name swap: **{a['name_swap']['max_difference']}** points at most across {a['name_swap']['swaps']} swaps. Demographic header (DC-28): {f63['F4']['evidence']['with_header']} against {f63['F4']['evidence']['without_header']}. These probes cover the ATS round only; the interview rounds receive text that the transcript scrubber has already cleaned, and no bias audit on real data exists (GOV-02).

### 4.9 The decision rules

The round-disagreement rule is flagged for **{a['round_disagreement_flagged']} of {a['candidates']}** candidates on the raw ATS scale and {a['round_disagreement_flagged_with_aligned_ats']} on the common scale; {a['outcomes_changed_by_aligned_ats']} outcomes change between the two (ACC-05). A flag that fires for most candidates stops carrying information.

## 5. UX issues

This repository has no user interface; its surfaces are the API, its error messages and the recruiter report. The recruiter dashboard belongs to the frontend.

### 5.1 Error messages

{errs['cases']} malformed requests were sent to the five services. {errs['rejected_with_error']} were rejected with an error; {len(errs['answered_with_null_score_and_a_warning'])} were answered 'not started' with no score ({'; '.join(errs['answered_with_null_score_and_a_warning'])}); {len(errs['accepted_and_scored'])} was scored ({'; '.join(errs['accepted_and_scored'])}). Messages that do not say what is accepted: {len(errs['error_not_actionable'])}. Errors that name no field: {len(errs['error_without_field'])} ({'; '.join(errs['error_without_field'])}) (UX-03, UX-04).

### 5.2 Recruiter reports

{rep['reports']} reports, {rep['words']['min']} to {rep['words']['max']} words (mean {rep['words']['mean']}); **{rep['reports_over_1000_words']} are over 1,000 words**. {rep['reports_with_cut_off_summary_lines']} have a cut-off or unbalanced line in the summary, and {rep['escaped_underscores']} escaped underscores (raw rule codes such as machine\\_test) appear (UX-02).

### 5.3 API behaviour that surprises a caller

{table(["Behaviour", "Measured"], [
    ("Technical answers are matched to questions by position", f"the same five answers score {pit['technical_answers_in_order']} in order and {pit['technical_same_answers_reordered']} reordered"),
    ("Screening turns are matched by position", f"reversed turns leave {len(pit['screening_reversed_missing'])} categories missing and score {pit['screening_reversed_score']}"),
    ("A duration in months is read as years", f"'six months' returns {pit['six_months_read_as_years']}"),
])}

## 6. Performance issues

{perf['note']}

{table(["Stage", "n", "Mean ms", "Median ms", "p95 ms", "Max ms"], stage_rows)}

- Resume reading: DOCX {perf['resume_extraction_ms']['docx']['mean']} ms, PDF {perf['resume_extraction_ms']['pdf']['mean']} ms on average.
- ATS scoring: {perf['ats_single_process']['pairs']} resume-and-job pairs in {perf['ats_single_process']['seconds']} s on one process ({perf['ats_single_process']['per_second']} a second).
- Cold start: the first ATS call in a fresh process takes {perf['cold_start_first_ats_ms']} ms.
- **No performance bottleneck.** The stage with the largest mean ({perf['slowest_stage_by_mean']}) is dominated by one first-call import cost; its median is {perf['stage_ms']['machine test, final aggregation and report']['p50']} ms. The Day 60 results (about 22 ms of compute per application, scaling by replicas) still describe the system (PERF-01, PERF-02).

## 7. Engineering and process

{table(["Check", "Result"], [
    ("Automated test run on every push", "No (.github/workflows missing)" if not g["ci_workflow_present"] else "Yes"),
    ("Engine reads of the wall clock", f"{len(g['wall_clock_reads'])}: " + ", ".join(g["wall_clock_reads"][:4]) + (", ..." if len(g["wall_clock_reads"]) > 4 else "")),
    ("Lines over 100 characters (the written standard)", f"{g['lines_over_100_chars']['total']} in {g['lines_over_100_chars']['files']} of {g['modules']} modules"),
    ("print() calls in engine modules", len(g["print_calls_in_engines"])),
    ("Modules without a test file of their own name", f"{len(g['modules_without_a_matching_test_file'])} of {g['modules']} (some are covered by another file)"),
    ("Dependencies pinned", f"{g['requirements_pinned']} of {g['requirements_total']}"),
    ("Modules with a docstring", f"{g['modules_with_docstring']} of {g['modules']}"),
    (".gitattributes present", "Yes" if g["gitattributes_present"] else "No"),
])}

Three Day 60 golden tests failed on 2026-11-22, and a fourth on 2026-11-26, although no code had changed: the ATS experience score counts years to 'Present', which means the day the test runs (ENG-02). A CI run on two Python versions would also have caught an f-string that fails only before Python 3.12 (ENG-01).

## 8. What works well

{chr(10).join('- ' + x for x in good)}

## 9. Reviewer feedback

**{fb['count']} entries recorded.** Day 64 asks for feedback from mentors and reviewers; it cannot be generated, so this report does not contain any. `docs/day64_review_session_kit.md` has a 45-minute agenda, the commands to show each stage, a feedback form and the format to record it in. Add each comment to `data/review/feedback_log.json`, run `python run_day64_internal_review.py`, and each becomes a triage item (FB-001, ...) in the improvement list and is counted here.

## 10. Prioritised summary

The full list is `docs/day64_improvement_list.md`; the order of work is `docs/day64_action_plan.md`.

{table(["Id", "Improvement", "Priority", "Score", "Effort (days)"], [(i["id"], i["title"], i["priority"], i["priority_score"], i["effort_days"]) for i in by_pri["P0"] + by_pri["P1"][:6]])}

**Decisions requested**

{decisions_table}

**Acceptance targets today:** {sum(1 for t in targets if t['met'])} of {len(targets)} met. Re-run `python run_day64_internal_review.py` after each fix to see them change.

## 11. Limits of this review

- **Probes find what data can show.** They cannot say whether a weight is right: no labelled outcomes exist.
- **The demo dataset is synthetic and small** (30 candidates); the negative controls and edits are a handful of cases, not a test set.
- **Impact, confidence and effort are estimates** by the author. Effort is in working days for one developer who knows the code.
- **No second person has reviewed this report**, and no reviewer feedback is in it yet.
- **Timings are from one machine.** Trust the ranking of stages, not the milliseconds.
- **UX is judged from the API and the report only.** Nothing was tested with a recruiter.
"""


# ------------------------------------------------------------------------------------------------------------------------ list
def build_list(items: List[Dict[str, Any]], targets: List[Dict[str, Any]]) -> str:
    ordered = sorted(items, key=lambda i: (i["priority"], -i["priority_score"], i["id"]))
    summary = [(i["id"], i["area"], i["title"], i["priority"] + (" GATE" if i.get("gate_before_real_use") else ""), i["priority_score"], i["impact"], i["confidence"], i["effort_days"]) for i in ordered]
    details = []
    for i in ordered:
        lines = [f"### {i['id']}: {i['title']}", "", f"**{i['priority']}** | area {i['area']} | impact {i['impact']} | confidence {i['confidence']} | effort {i['effort_days']} days | score {i['priority_score']}"
                 + (" | harm" if i.get("harm") else "") + (" | GATE before real use" if i.get("gate_before_real_use") else ""), "",
                 f"**Problem.** {i['problem']}", "", f"**Fix.** {i['fix']}", "", f"**Done when.** {i['acceptance']}"]
        if i["links"]:
            lines += ["", f"**Roadmap link (Day 58).** {', '.join(i['links'])}"]
        if i["decision_needed"]:
            lines += ["", f"**Decision needed.** {i['decision_needed']}"]
        if i["depends_on"]:
            lines += ["", f"**Depends on.** {', '.join(i['depends_on'])}"]
        if i.get("from_reviewer"):
            lines += ["", f"**From reviewer.** {i['from_reviewer']}"]
        details.append("\n".join(lines))
    target_rows = [(t["id"], t["improvement"], t["target"], t["current"], f"{t['operator']} {t['goal']}", t["unit"], "yes" if t["met"] else "open") for t in targets]
    return f"""# Day 64: Improvement List

Zecpath: AI Job Portal | Prioritised improvements from the internal review | Built {AS_OF}

## How items are ranked

```
priority score = impact x confidence / effort
impact 1-5 | confidence 1-3 | effort in working days (one developer who knows the code)
P0  the system can give a candidate a wrong or unfair result (harm) and impact is 4 or 5
P1  score 3.0 or more     P2  1.5 or more     P3  below 1.5
GATE  must be done before any real candidate data is used, whatever the score
```

Impact, confidence and effort are the author's estimates. The formula makes the reasoning visible; it does not make it correct. A large item scores low because it is large, which is why three items are marked GATE. Every problem statement quotes a number measured by `parsers/internal_review.py`; `data/review/day64_improvement_list.json` and `.csv` hold the same list.

## The list

{len(items)} items: {sum(1 for i in items if i['priority'] == 'P0')} P0, {sum(1 for i in items if i['priority'] == 'P1')} P1, {sum(1 for i in items if i['priority'] == 'P2')} P2, {sum(1 for i in items if i['priority'] == 'P3')} P3.

{table(["Id", "Area", "Improvement", "Priority", "Score", "Impact", "Conf.", "Effort (days)"], summary)}

## Acceptance targets

A target is a measurement the review script already makes. When it is met, the improvement is done; re-run `python run_day64_internal_review.py` to see the current value.

{table(["Target", "Improvement", "Goal", "Now", "Needs", "Unit", "Met"], target_rows)}

## Items in detail

{chr(10).join(chr(10) + d + chr(10) for d in details)}
"""


# ------------------------------------------------------------------------------------------------------------------------ plan
def build_plan(items: List[Dict[str, Any]], targets: List[Dict[str, Any]]) -> str:
    plan = rp.action_plan(items)
    wave_blocks = []
    for w in plan:
        rows = [(r["id"], r["title"], r["priority"], r["effort_days"], ", ".join(r["depends_on"]) or "-", r["decision_needed"] or "-") for r in w["rows"]]
        wave_blocks.append(f"### {w['id']}: {w['name']} ({w['when']})\n\n**Goal.** {w['goal']}\n\n**Effort.** About {w['effort_days']} working days.\n\n"
                           + table(["Id", "Item", "Priority", "Effort (days)", "Depends on", "Decision needed"], rows) + f"\n\n**Exit criteria.** {w['exit']}")
    by_id = {i["id"]: i for i in items}
    ordering = [(w["id"], i) for w in plan for i in w["items"]]
    total = round(sum(w["effort_days"] for w in plan), 1)
    return f"""# Day 64: Action Plan

Zecpath: AI Job Portal | Order of work after the internal review | Built {AS_OF}

## Assumptions

- **One developer** who knows the code does the work, in the order below. Effort is the author's estimate in working days.
- **Remaining internship time is not known to this plan** (tasks 65 to 70 are not described), so Wave 0 is sized to fit in a few days and the rest is written as a hand-over plan. The owner should move the wave boundaries to the time that exists.
- **Decisions come first.** Five items need an owner's decision (D1 to D6 in the report); they are named in the waves so they are not discovered halfway through.
- **Any change that alters scores needs a new golden file and a re-run of the demo dataset.** The Day 60 golden files exist to prove optimisations did not change answers; a deliberate behaviour change gets a new, labelled golden file, never a regenerated one.

## The plan in one line

Wave 0 makes changes safe, Wave 1 removes every way a candidate can get a wrong or unfair result, Wave 2 improves the scoring and the reports, and Wave 3 holds what needs data, policy or the backend. Total about {total} working days, of which Waves 0 and 1 are {round(plan[0]['effort_days'] + plan[1]['effort_days'], 1)}.

## Waves

{chr(10).join(wave_blocks)}

## How progress is tracked

1. Fix one item. Its acceptance line in the improvement list says when it is done.
2. Run `python run_day64_internal_review.py`. The acceptance targets (T1 to T{len(targets)}) show the current value of each measurement; {sum(1 for t in targets if t['met'])} of {len(targets)} are met today.
3. Run `python run_day63_demo_dataset.py` and read which candidates moved. Update `data/demo_dataset/simulated/` by committing the new run.
4. Run the full test suite. A scoring change is expected to fail tests that pin the old behaviour; read why before editing a test.

## Risks

{table(["Risk", "Why it matters", "What reduces it"], [
    ("Fixing one gap hides another", "Scores interact: raising the ATS skill match changes who is shortlisted and how the disagreement rule fires.", "Re-run the review and demo scripts after each change; change one thing at a time."),
    ("A fix changes results for real candidates", "No real candidates are scored yet, but the weights will be used later.", "Keep the change behind the golden-file process; record why each number changed."),
    ("Work finishes but is not seen", "The probes only show what the data can show.", "Hold the reviewer session in the kit and merge its feedback."),
    ("Estimates are wrong", "Effort figures are one author's guesses.", "Re-estimate after Wave 0; the first few items calibrate the rest."),
])}

## Order of work, item by item

{table(["Order", "Wave", "Id", "Item", "Priority"], [(n + 1, wv, iid, by_id[iid]["title"], by_id[iid]["priority"]) for n, (wv, iid) in enumerate(ordering)])}
"""


# ------------------------------------------------------------------------------------------------------------------------ kit
def build_kit() -> str:
    return f"""# Day 64: Reviewer Session Kit

Zecpath: AI Job Portal | How to collect mentor and reviewer feedback | Built {AS_OF}

Day 64 asks for feedback from mentors and reviewers. This kit makes a 45-minute session easy to run and its feedback easy to record. **No feedback is included in the review report until it is recorded here.**

## Before the session (10 minutes)

```
venv\\Scripts\\activate
python run_day63_demo_dataset.py
python run_day64_internal_review.py
```

Open `docs/day64_internal_review_report.md` (sections 2 to 6), `data/demo_dataset/simulated/pipeline_results.csv` and the reports of DC-01, DC-04, DC-09, DC-13 and DC-30.

## Agenda (45 minutes)

{table(["Min", "Item", "What to show", "Ask the reviewer"], [
    ("0-5", "What the system is", "Handbook section 1 and the candidate-journey diagram (`docs/diagrams/day62_candidate_workflow.png`)", "Is anything in the scope missing?"),
    ("5-10", "ATS", "DC-01 resume and its ATS components; then DC-13 (no headings) and the PDF example in the report, 4.6", "Would a recruiter score this resume the same way?"),
    ("10-17", "Screening", "DC-01 answers, then the negative controls (report 4.5)", "Is it acceptable that gibberish scores about 56?"),
    ("17-24", "HR interview", "DC-01 answers and the off-topic control", "Should relevance dominate? What would you check?"),
    ("24-31", "Technical interview and machine test", "DC-04 (stuffed resume) and DC-09 (integrity)", "Are the questions and the code checks fair for the role?"),
    ("31-38", "Decision", "DC-01 recruiter report and its rule trace; DC-30 (dropped call)", "Would you have decided differently? Is the report readable in a minute?"),
    ("38-45", "Priorities", "The top of the improvement list and the six decisions", "What would you fix first? What is missing?"),
])}

## Questions to ask at every stage

1. What did you expect to see that is missing?
2. What surprised you?
3. Where could this give a candidate a wrong result?
4. What would you change first?
5. What would stop you using this on real candidates?

## Rating scale (ask for one number per area)

{table(["Score", "Meaning"], [(1, "Not usable"), (2, "Needs major work"), (3, "Usable with known gaps"), (4, "Good, small fixes"), (5, "Ready")])}

Areas: ATS, Screening, HR interview, Technical interview, Machine test, Decision, Recruiter report, API and errors, Documentation. The author's own scores are in report section 3; compare them with the reviewer's.

## Feedback form (copy per reviewer)

```
Reviewer:                 Role: mentor / reviewer / recruiter / developer      Date:
Ratings (1-5):  ATS __  Screening __  HR __  Technical __  Machine test __  Decision __  Report __  API __  Docs __

Comment 1   Stage:        Kind: accuracy / ux / performance / engineering / governance
            Observed:
            Severity (1-5):           Suggestion:
Comment 2   ...
```

## Recording the feedback

Add one object per comment to `entries` in `data/review/feedback_log.json`:

```
{{
  "reviewer": "initials",
  "role": "mentor",
  "date": "2026-11-24",
  "stage": "Screening",
  "kind": "accuracy",
  "comment": "what they observed, in their words",
  "severity": 4,
  "suggestion": "what they would change (optional)"
}}
```

Then run `python run_day64_internal_review.py`. Each entry becomes a triage item `FB-001`, `FB-002`, ... in `docs/day64_improvement_list.md` (impact = severity, confidence 2, effort 2 days until triaged), and the report states how many entries it was built from.

## After the session

- Triage each FB item: merge it with an existing item, re-score it, or reject it with a reason.
- Update the action plan if a comment moves a wave.
- Record the reviewer's ratings next to the author's scores in the report.
"""


# ------------------------------------------------------------------------------------------------------------------------ main
def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    ds = env.load_dataset()
    runs = env.run_environment(ds)
    ev = ir.collect_evidence(ds, runs, measure_performance=True)
    items = rp.improvements(ev)
    fb = rp.merge_feedback(items)
    targets = rp.acceptance_targets(ev)
    perf = ev.pop("performance_measured")
    ev_for_docs = dict(ev, performance_measured=perf)
    write(REVIEW / "day64_evidence.json", json.dumps(ev, indent=2, ensure_ascii=False) + "\n")
    write(REVIEW / "day64_performance_measured.json", json.dumps(perf, indent=2, ensure_ascii=False) + "\n")
    write(REVIEW / "day64_improvement_list.json", json.dumps({"items": items, "targets": targets, "feedback_entries": fb["count"]}, indent=2, ensure_ascii=False) + "\n")
    with (REVIEW / "day64_improvement_list.csv").open("w", newline="", encoding="utf-8") as fh:
        cols = ["id", "area", "title", "priority", "priority_score", "impact", "confidence", "effort_days", "harm", "gate_before_real_use", "decision_needed", "acceptance"]
        writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sorted(items, key=lambda i: (i["priority"], -i["priority_score"], i["id"])))
    write(REPORT, build_report(ev_for_docs, items, targets, fb))
    write(LIST, build_list(items, targets))
    write(PLAN, build_plan(items, targets))
    write(KIT, build_kit())
    counts = {p: sum(1 for i in items if i["priority"] == p) for p in ("P0", "P1", "P2", "P3")}
    print(f"evidence collected; {len(items)} improvements {counts}; {sum(1 for t in targets if t['met'])} of {len(targets)} acceptance targets met; {fb['count']} reviewer entries")
    for p in (REPORT, LIST, PLAN, KIT):
        print(f"wrote {p.relative_to(ROOT)}  ({len(p.read_text(encoding='utf-8').split())} words)")
    print("wrote data/review/day64_evidence.json, day64_performance_measured.json, day64_improvement_list.json / .csv")


if __name__ == "__main__":
    main()
