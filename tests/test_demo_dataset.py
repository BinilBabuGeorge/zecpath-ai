"""
Day 63 tests: the demo dataset is consistent, reproducible, synthetic, and runs end to end through the real engines

WHAT IS CHECKED
  * the files are all there and the counts are right (6 jobs, 30 candidates, 30 resumes as DOCX/PDF, 16 technical candidates, 4 edge files);
  * the dataset is internally consistent (every candidate has the rounds their role needs, and none they should not have);
  * it is REPRODUCIBLE: rebuilding it gives the same inputs (text resumes, answers, machine-test attempts, PDFs);
  * it is SYNTHETIC: every e-mail is example.com, every phone is in the fake range;
  * the machine-test results stored in it are the real behaviour of the stored code (re-executed here);
  * every resume goes through the REAL upload path; the edge files are refused politely;
  * the end-to-end run finishes for all 30 candidates with no error, no automated rejection, a report each, and the safety rules hold
    (a rejection always needs a human; an integrity tag stops a selection; a dropped call is held, not rejected);
  * the findings printed by the run are computed from the run, and the Day 63 document quotes the same numbers as the run.

WHAT IS NOT PINNED. Individual scores and outcomes are not asserted, because a legitimate change to a weight should not break the demo
dataset's tests; the properties above must hold whatever the weights are.
"""

import json
import re
import tempfile
from datetime import date
from pathlib import Path

from parsers import demo_dataset_answers as ans
from parsers import demo_dataset_builder as builder
from parsers import demo_environment as env
from parsers.demo_dataset_content import JOBS, PERSONAS

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "data" / "demo_dataset"
DOC = ROOT / "docs" / "day63_demo_dataset.md"
OUTCOMES = {"selected", "hold_review", "rejected"}
NO_HEADINGS_IDS = {"DC-13", "DC-25"}          # resumes written without section headings: the parser reads no experience (finding F3)

_DS = None
_RUNS = None


def _ds():
    global _DS
    if _DS is None:
        _DS = env.load_dataset()
    return _DS


def _runs():
    global _RUNS
    if _RUNS is None:
        _RUNS = env.run_environment(_ds())
    return _RUNS


def _read(rel):
    return json.loads((BASE / rel).read_text(encoding="utf-8"))


# ------------------------------------------------------------------------------------------------------------ files and counts
def test_the_dataset_has_the_promised_files_and_counts():
    m = _read("manifest.json")["summary"]
    assert (m["jobs"], m["candidates"], m["technical_candidates"], m["edge_files"]) == (6, 30, 16, 4)
    assert len(list((BASE / "resumes").glob("*.docx"))) == m["resumes_docx"] == 20
    assert len(list((BASE / "resumes").glob("*.pdf"))) == m["resumes_pdf"] == 10
    assert len(list((BASE / "resumes_text").glob("*.txt"))) == 30
    assert len(list((BASE / "jobs").glob("JOB-*.txt"))) == 6
    assert len(_ds()["candidates"]) == len(PERSONAS) == 30 and len(JOBS) == 6


def test_the_dataset_is_internally_consistent():
    assert env.verify_dataset(_ds()) == []


def test_every_job_family_and_role_type_is_present():
    jobs = _ds()["jobs"]
    assert {j["role_type"] for j in jobs.values()} == {"technical", "non_technical"}
    assert {j["domain"] for j in jobs.values() if j["domain"]} == {"mern", "java", "devops"}
    per_job = {}
    for c in _ds()["candidates"]:
        per_job[c["job_id"]] = per_job.get(c["job_id"], 0) + 1
    assert set(per_job) == set(jobs) and min(per_job.values()) >= 3


def test_resumes_cover_the_quality_range_and_layouts_the_brief_asks_for():
    styles = {c["resume_style"] for c in _ds()["candidates"]}
    assert {"standard", "stuffed", "minimal", "no_headings", "bias_header", "typos"} <= styles
    qualities = {c["resume_quality"].split(" ")[0] for c in _ds()["candidates"]}
    assert {"excellent", "good", "average", "poor"} <= qualities
    assert len({c["scenario"] for c in _ds()["candidates"]}) == 30           # every scenario is different


def test_expectations_are_written_down_for_every_candidate_and_use_real_outcomes():
    for c in _ds()["candidates"]:
        assert c["expected_outcomes"] and set(c["expected_outcomes"]) <= OUTCOMES, c["id"]
        assert len(c["expected_rationale"]) > 20, c["id"]
    note = (BASE / "candidates.json").read_text(encoding="utf-8")
    assert "design intent" in note and "before the pipeline was run" in note


# ------------------------------------------------------------------------------------------------------------ synthetic and private
def test_the_dataset_is_synthetic_only():
    emails, phones = set(), set()
    for f in (BASE / "resumes_text").glob("*.txt"):
        text = f.read_text(encoding="utf-8")
        emails |= set(re.findall(r"[\w.+-]+@[\w.-]+", text))
        phones |= set(re.findall(r"\+\d{2}-\d{5}-\d{5}", text))
    assert emails and all(e.endswith("@example.com") for e in emails)
    assert phones and all(p.startswith("+91-90000-") for p in phones)
    assert "SYNTHETIC" in (BASE / "manifest.json").read_text(encoding="utf-8")


# ------------------------------------------------------------------------------------------------------------ reproducible
def test_rebuilding_the_dataset_gives_the_same_inputs():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "demo_dataset"
        builder.build_dataset(out)
        for rel in ("candidates.json", "manifest.json", "jobs/jobs.json", "responses/screening_responses.json", "responses/hr_responses.json",
                    "responses/technical_responses.json", "machine_test/tasks.json", "machine_test/submissions.json", "integrity/browser_events.json"):
            assert (out / rel).read_bytes() == (BASE / rel).read_bytes(), rel
        for f in sorted((BASE / "resumes_text").glob("*.txt")) + sorted((BASE / "jobs").glob("JOB-*.txt")):
            assert (out / f.relative_to(BASE)).read_bytes() == f.read_bytes(), f.name
        for f in (BASE / "resumes").glob("*.pdf"):
            assert (out / "resumes" / f.name).read_bytes() == f.read_bytes(), f.name


# ------------------------------------------------------------------------------------------------------------ resumes go through the real upload path
def test_every_resume_is_read_by_the_real_upload_path_and_holds_the_candidates_name():
    from parsers.pipeline_simulation import upload_resume

    for c in _ds()["candidates"]:
        text, _ = upload_resume(BASE / c["resume_file"])
        assert c["name"] in text, c["id"]
        source = (BASE / "resumes_text" / (Path(c["resume_file"]).stem + ".txt")).read_text(encoding="utf-8")
        assert "".join(text.split()) == "".join(source.split()), c["id"]     # same words, whatever the file format does with blank lines and wrapping


def test_the_edge_files_are_refused_with_a_named_error():
    results = env.edge_file_results()
    assert len(results) == 4 and all(r["result"] == "error" and "ResumeUploadError" in r["error"] for r in results)


def test_years_on_each_resume_match_what_the_parser_reads_except_the_two_headingless_ones():
    from parsers import experience_parser
    from parsers.pipeline_simulation import frozen_today

    with frozen_today(date.fromisoformat(_ds()["as_of"])):
        for c in _ds()["candidates"]:
            text = (BASE / "resumes_text" / (Path(c["resume_file"]).stem + ".txt")).read_text(encoding="utf-8")
            years = experience_parser.compute_total_experience(experience_parser.parse_experience(text)).total_years
            if c["id"] in NO_HEADINGS_IDS:
                assert years == 0.0, c["id"]
            else:
                assert abs(years - c["years_on_resume"]) <= 0.7, (c["id"], years, c["years_on_resume"])


# ------------------------------------------------------------------------------------------------------------ machine test results are real
def test_stored_machine_test_results_are_what_the_stored_code_really_does():
    tasks = {t["task_id"]: t for t in ans.TASKS}
    for cid, attempts in _ds()["submissions"].items():
        for task_id, attempt in attempts.items():
            task = tasks[task_id]
            for run in attempt["runs"]:
                snap = max((s for s in attempt["snapshots"] if s["timestamp"] <= run["timestamp"]), key=lambda s: s["timestamp"])
                compile_error, results, _ = builder.execute_cases(snap["code"], task["function"], task["cases"])
                assert run["compile_error"] == compile_error, (cid, task_id)
                assert [(r["case_id"], r["passed"]) for r in run["results"]] == results, (cid, task_id)


def test_the_five_code_qualities_behave_as_labelled():
    task_a = ans.TASKS[0]
    passed = {}
    for variant in ("strong", "partial", "slow", "overfit", "weak"):
        compile_error, results, _ = builder.execute_cases(ans.CODE["MT-A"][variant], task_a["function"], task_a["cases"])
        passed[variant] = (compile_error, sum(ok for _, ok in results))
    assert passed["strong"] == (False, 6) and passed["slow"] == (False, 6)       # slow is correct, just slow
    assert passed["partial"][1] == 4 and passed["overfit"][1] == 3 and passed["weak"][0] is True
    visible_only = [cid for cid, ok in builder.execute_cases(ans.CODE["MT-A"]["overfit"], task_a["function"], task_a["cases"])[1] if ok]
    assert {"A-v1", "A-v2"} <= set(visible_only)                                  # the overfit solution passes exactly what the candidate could see


def test_every_technical_candidate_has_answers_for_the_tier_the_question_bank_will_choose():
    for cid, rec in _ds()["technical"].items():
        assert (rec["domain"], rec["tier"]) in ans.TECH_BANK and len(rec["answers"]) == 5, cid


# ------------------------------------------------------------------------------------------------------------ end to end
def test_all_thirty_candidates_finish_the_pipeline_without_error():
    runs = _runs()
    assert len(runs) == 30 and all(not r.errors for r in runs)
    assert all(r.report is not None and r.decision is not None for r in runs)
    assert all(0 <= r.score.hiring_fit_percentage <= 100 and r.outcome in OUTCOMES for r in runs)


def test_technical_candidates_have_all_five_rounds_and_the_others_have_three():
    for r in _runs():
        technical = r.candidate["role_type"] == "technical"
        assert (r.machine_report is not None) is technical and (r.journey.technical is not None) is technical, r.candidate["id"]
        assert r.score.provisional is False and r.score.missing_rounds == [], r.candidate["id"]


def test_a_rejection_never_happens_without_a_human():
    runs = _runs()
    assert all(r.decision.requires_human_confirmation for r in runs if r.outcome == "rejected")
    assert all(r.decision.automated_action == "none" for r in runs)
    assert env.summarise(runs)["automated_rejections"] == 0


def test_the_safety_rules_hold_on_the_demo_candidates():
    by_id = {r.candidate["id"]: r for r in _runs()}
    assert by_id["DC-09"].integrity_report.risk_tag.value in ("medium", "high") and by_id["DC-09"].outcome != "selected"
    assert by_id["DC-30"].journey.screening is not None and by_id["DC-30"].outcome != "rejected"
    assert by_id["DC-04"].machine_report.overall_score < 25 and by_id["DC-04"].outcome in ("rejected", "hold_review")


def test_the_run_writes_every_simulated_output_and_one_report_per_candidate():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        summary = env.write_outputs(_runs(), out)
        for name in ("ats_results.json", "screening_outputs.json", "interview_results.json", "machine_test_results.json", "pipeline_results.json",
                     "pipeline_results.csv", "summary.json"):
            assert (out / name).exists(), name
        assert len(list((out / "reports").glob("DC-*.md"))) == 30
        assert len(json.loads((out / "ats_results.json").read_text(encoding="utf-8"))) == 30
        assert len(json.loads((out / "machine_test_results.json").read_text(encoding="utf-8"))) == 16
        assert summary["candidates"] == 30 and sum(summary["outcomes"].values()) == 30


def test_the_committed_simulated_results_match_a_fresh_run():
    committed = _read("simulated/summary.json")
    fresh = env.summarise(_runs())
    for key in ("candidates", "outcomes", "ats_zones", "expected_outcome_met", "expected_outcome_missed", "integrity_tags"):
        assert committed[key] == fresh[key], f"{key}: run python run_day63_demo_dataset.py to refresh data/demo_dataset/simulated/"


# ------------------------------------------------------------------------------------------------------------ findings and document
def test_the_findings_are_computed_from_the_run():
    findings = env.probe_findings(_runs(), _ds())
    assert [f["id"] for f in findings] == [f"F{i}" for i in range(1, 11)]
    assert all(f["statement"] and f["evidence"] for f in findings)
    f4 = next(f for f in findings if f["id"] == "F4")
    assert f4["evidence"]["difference"] < 0.5                                       # personal details do not move the ATS score
    f10 = next(f for f in findings if f["id"] == "F10")
    from parsers import answer_intent_engine
    assert f10["evidence"]["returned"] == answer_intent_engine.extract_experience_years("I have six months of internship experience")


def test_the_day63_document_quotes_the_numbers_of_the_run():
    text = DOC.read_text(encoding="utf-8")
    s = env.summarise(_runs())
    assert f"{s['expected_outcome_met']} of {s['candidates']}" in text
    for outcome, n in s["outcomes"].items():
        assert f"| {outcome} | {n} |" in text, outcome
    for cid in s["expected_outcome_missed"]:
        assert cid in text, cid
