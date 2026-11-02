"""Day 57 -- the edge-case sweep as a permanent regression gate, plus tests of the sweep machinery itself."""
import dataclasses
import json
import math
from pathlib import Path

import pytest

from parsers.pipeline_simulation import build_matcher
from parsers.stability_checks import EdgeCase, build_cases, find_bad_numbers, run_case, run_sweep, summarise

SAMPLES = Path("data/samples")


@pytest.fixture(scope="module")
def sweep():
    m = build_matcher(SAMPLES)
    cases = build_cases(m, (SAMPLES / "jds/jd_01_mern_developer.txt").read_text(encoding="utf-8"), (SAMPLES / "resumes/resume_01_mern_developer.txt").read_text(encoding="utf-8"))
    return cases, run_sweep(cases)


def test_the_whole_sweep_passes_after_day_57(sweep):
    cases, results = sweep
    failures = [(r.id, r.status, r.detail) for r in results if not r.passed]
    assert len(cases) >= 80 and failures == []


def test_the_sweep_covers_every_area(sweep):
    areas = {r.area for r in sweep[1]}
    assert areas == {"ats", "experience", "upload", "screening", "hr", "technical", "aggregation", "service"}


def test_recorded_baseline_shows_what_the_sweep_found_before_the_fixes():
    before = json.loads(Path("data/results/day57_edge_sweep_before.json").read_text(encoding="utf-8"))
    after = json.loads(Path("data/results/day57_edge_sweep_after.json").read_text(encoding="utf-8"))
    assert before["code_state"] == "before_day57" and before["summary"]["failed"] == 31 and before["summary"]["cases"] == 80
    assert after["summary"]["failed"] == 0 and after["summary"]["cases"] == before["summary"]["cases"]
    assert {c["id"] for c in before["cases"]} == {c["id"] for c in after["cases"]}


# ---------------------------------------------------------------- the machinery
def test_runner_classifies_ok_crash_rejected_and_silently_accepted():
    ok = run_case(EdgeCase("a", "t", "d", lambda: {"score": 50.0}))
    crash = run_case(EdgeCase("b", "t", "d", lambda: {}["missing"]))
    clean = run_case(EdgeCase("c", "t", "d", lambda: (_ for _ in ()).throw(ValueError("bad")), "reject"))
    silent = run_case(EdgeCase("d", "t", "d", lambda: "fine", "reject"))
    wrong_type = run_case(EdgeCase("e", "t", "d", lambda: (_ for _ in ()).throw(KeyError("k")), "either"))
    unexpected_error = run_case(EdgeCase("f", "t", "d", lambda: (_ for _ in ()).throw(ValueError("x")), "graceful"))
    assert [r.status for r in (ok, crash, clean, silent, wrong_type, unexpected_error)] == ["ok", "crash", "rejected_cleanly", "silently_accepted", "crash", "crash"]


def test_runner_flags_nan_out_of_range_scores_and_custom_check_problems():
    assert run_case(EdgeCase("a", "t", "d", lambda: {"x": float("nan")})).status == "bad_output"
    assert run_case(EdgeCase("b", "t", "d", lambda: {"overall_score": 140.0})).status == "bad_output"
    assert run_case(EdgeCase("c", "t", "d", lambda: 1, "graceful", lambda r: "nope")).detail == "nope"


def test_runner_reports_a_timeout_instead_of_hanging(monkeypatch):
    import time
    from parsers import stability_checks
    monkeypatch.setattr(stability_checks, "TIMEOUT_SECONDS", 0.2)
    assert run_case(EdgeCase("slow", "t", "d", lambda: time.sleep(2))).status == "timeout"


def test_find_bad_numbers_walks_dataclasses_lists_and_dicts_and_ignores_weights():
    @dataclasses.dataclass
    class Inner:
        total_score: float
        weight: float = 5.0
    found = find_bad_numbers({"items": [Inner(150.0), Inner(50.0)], "hiring_fit_percentage": -3, "ok_score": 99.9, "std_score": 0.0})
    assert len(found) == 2 and any("150" in f for f in found) and any("-3" in f for f in found)
    assert find_bad_numbers({"a": [math.inf]}) and find_bad_numbers("text") == [] and find_bad_numbers(None) == []


def test_summarise():
    rs = [run_case(EdgeCase("a", "x", "d", lambda: 1)), run_case(EdgeCase("b", "x", "d", lambda: {}["k"])), run_case(EdgeCase("c", "y", "d", lambda: 1))]
    s = summarise(rs)
    assert s["cases"] == 3 and s["failed"] == 1 and s["by_area"]["x"] == {"cases": 2, "failed": 1} and s["by_status"]["crash"] == 1
