import json
import os
import tempfile

import pytest

from parsers.integrity_detection_engine import IntegrityRiskTag
from parsers.machine_test_evaluation_engine import (
    DIFFICULTY_WEIGHT,
    MAX_OUTPUT_TAIL_CHARS,
    TYPE_WEIGHTS,
    CaseResult,
    CaseSpec,
    CodeSnapshot,
    ExecutionRun,
    MachineTestTask,
    MachineTestType,
    TaskAttempt,
    analyze_python_quality,
    assess_problem_solving,
    build_machine_test_report,
    efficiency_from_ratio,
    evaluate_design_writeup,
    evaluate_task,
    time_score_raw,
)
from parsers.technical_interview_question_bank import DifficultyTier

CLEAN_CODE = '''
def add(a, b):
    """Return the sum of a and b."""
    return a + b
'''

CASE_IDS = ["v1", "v2", "h1", "h2"]


def make_task(task_type=MachineTestType.CODING, difficulty=DifficultyTier.INTERMEDIATE, language="python",
              reference=100.0, limit=1000.0):
    cases = [CaseSpec("v1"), CaseSpec("v2"), CaseSpec("h1", visible=False), CaseSpec("h2", visible=False)]
    return MachineTestTask("t1", task_type, "Sum numbers", difficulty, limit, language, cases, reference_runtime_ms=reference)


def make_run(ts, passed, runtime=100.0, compile_error=False, timeouts=()):
    results = [CaseResult(cid, cid in passed and cid not in timeouts, runtime if cid in passed else None, cid in timeouts)
               for cid in CASE_IDS]
    return ExecutionRun(ts, results, compile_error=compile_error)


def snaps(*stamps, code=CLEAN_CODE):
    return [CodeSnapshot(t, code) for t in stamps]


def good_attempt(**task_kw):
    return TaskAttempt(make_task(**task_kw), snaps(50, 150, 250),
                       [make_run(100, {"v1"}), make_run(300, set(CASE_IDS))], submitted_at=300)


def metric(evaluation, name):
    return next(m for m in evaluation.metrics if m.name == name)


# ---------------------------------------------------------------------------
# Task and capture model
# ---------------------------------------------------------------------------

def test_every_task_type_weight_row_sums_to_one():
    for row in TYPE_WEIGHTS.values():
        assert sum(row.values()) == pytest.approx(1.0)


def test_executable_task_requires_cases_and_design_task_requires_components():
    with pytest.raises(ValueError):
        MachineTestTask("x", MachineTestType.CODING, "t", DifficultyTier.BASICS, 100)
    with pytest.raises(ValueError):
        MachineTestTask("x", MachineTestType.SYSTEM_DESIGN, "t", DifficultyTier.BASICS, 100)


def test_non_positive_time_limit_rejected():
    with pytest.raises(ValueError):
        make_task(limit=0)


def test_extension_multiplier_cannot_shorten_time():
    with pytest.raises(ValueError):
        TaskAttempt(make_task(), extension_multiplier=0.8)


def test_stdout_and_stderr_capture_is_truncated_to_the_tail():
    run = ExecutionRun(1.0, [], stdout_tail="a" * 5000 + "END", stderr_tail="b" * 10)
    assert len(run.stdout_tail) == MAX_OUTPUT_TAIL_CHARS
    assert run.stdout_tail.endswith("END")


def test_capture_summary_reports_sizes_not_content():
    attempt = TaskAttempt(make_task(), snaps(10, 20), [make_run(15, {"v1"})])
    summary = attempt.capture_summary()
    assert summary["snapshot_count"] == 2 and summary["run_count"] == 1
    assert summary["snapshot_total_chars"] == 2 * len(CLEAN_CODE)
    assert all(isinstance(v, int) for v in summary.values())


# ---------------------------------------------------------------------------
# Correctness
# ---------------------------------------------------------------------------

def test_all_cases_passing_gives_full_correctness():
    ev = evaluate_task(TaskAttempt(make_task(), snaps(10), [make_run(20, set(CASE_IDS))]))
    assert metric(ev, "correctness").score == 100.0


def test_hidden_cases_weigh_more_than_visible_ones():
    visible_only = evaluate_task(TaskAttempt(make_task(), snaps(10), [make_run(20, {"v1", "v2"})]))
    hidden_only = evaluate_task(TaskAttempt(make_task(), snaps(10), [make_run(20, {"h1", "h2"})]))
    assert metric(visible_only, "correctness").score == 40.0      # 2 / (2 + 3)
    assert metric(hidden_only, "correctness").score == 60.0       # 3 / 5


def test_compile_error_in_final_run_scores_zero_correctness():
    ev = evaluate_task(TaskAttempt(make_task(), snaps(10), [make_run(20, set(CASE_IDS), compile_error=True)]))
    assert metric(ev, "correctness").score == 0.0


def test_missing_case_in_run_counts_as_failed():
    run = ExecutionRun(20, [CaseResult("v1", True, 50.0)])
    ev = evaluate_task(TaskAttempt(make_task(), snaps(10), [run]))
    assert metric(ev, "correctness").score == 20.0                 # 1 / 5


def test_no_runs_scores_zero_correctness_with_explanation():
    ev = evaluate_task(TaskAttempt(make_task(), snaps(10)))
    assert metric(ev, "correctness").score == 0.0
    assert "No execution results" in metric(ev, "correctness").explanation


def test_passing_visible_but_failing_hidden_raises_overfit_flag_and_review():
    ev = evaluate_task(TaskAttempt(make_task(), snaps(10), [make_run(20, {"v1", "v2"})]))
    assert "PASSES_VISIBLE_FAILS_HIDDEN" in [f.code for f in ev.flags]
    assert ev.human_review_required


def test_failing_some_visible_cases_does_not_raise_overfit_flag():
    ev = evaluate_task(TaskAttempt(make_task(), snaps(10), [make_run(20, {"v1"})]))
    assert "PASSES_VISIBLE_FAILS_HIDDEN" not in [f.code for f in ev.flags]


# ---------------------------------------------------------------------------
# Deadline handling
# ---------------------------------------------------------------------------

def test_runs_after_the_deadline_are_ignored_and_flagged():
    attempt = TaskAttempt(make_task(limit=100), snaps(10), [make_run(50, {"v1"}), make_run(150, set(CASE_IDS))])
    ev = evaluate_task(attempt)
    assert metric(ev, "correctness").score == 20.0                 # the late full-pass run does not count
    assert "EVIDENCE_AFTER_DEADLINE_IGNORED" in [f.code for f in ev.flags]


def test_extension_multiplier_extends_the_deadline():
    attempt = TaskAttempt(make_task(limit=100), snaps(10), [make_run(150, set(CASE_IDS))], extension_multiplier=2.0)
    assert metric(evaluate_task(attempt), "correctness").score == 100.0


def test_explicit_late_submission_is_flagged_gets_no_time_credit_and_needs_review():
    attempt = TaskAttempt(make_task(limit=100), snaps(10), [make_run(50, set(CASE_IDS))], submitted_at=130)
    ev = evaluate_task(attempt)
    assert "LATE_SUBMISSION" in [f.code for f in ev.flags]
    assert metric(ev, "time").score == 0.0
    assert ev.human_review_required


# ---------------------------------------------------------------------------
# Efficiency
# ---------------------------------------------------------------------------

def test_efficiency_ratio_boundaries():
    assert efficiency_from_ratio(1.0) == 100.0
    assert efficiency_from_ratio(1.5) == 100.0
    assert efficiency_from_ratio(10.0) == 0.0
    assert efficiency_from_ratio(50.0) == 0.0
    assert efficiency_from_ratio(3.0) == pytest.approx(63.5, abs=0.1)


def test_efficiency_is_gated_by_pass_fraction_so_fast_and_wrong_earns_little():
    wrong = evaluate_task(TaskAttempt(make_task(), snaps(10), [make_run(20, {"v1"}, runtime=10.0)]))
    right = evaluate_task(TaskAttempt(make_task(), snaps(10), [make_run(20, set(CASE_IDS), runtime=10.0)]))
    assert metric(right, "efficiency").score == 100.0
    assert metric(wrong, "efficiency").score == pytest.approx(20.0)   # 100 * 0.2 pass fraction


def test_timeouts_reduce_efficiency():
    ev = evaluate_task(TaskAttempt(make_task(), snaps(10), [make_run(20, set(CASE_IDS), runtime=100.0, timeouts=("h2",))]))
    assert metric(ev, "efficiency").score < 100.0


def test_efficiency_not_assessed_without_reference_runtime_and_weight_redistributed():
    ev = evaluate_task(TaskAttempt(make_task(reference=None), snaps(10), [make_run(20, set(CASE_IDS))], submitted_at=20))
    eff = metric(ev, "efficiency")
    assert not eff.assessed and eff.effective_weight == 0.0
    assert sum(m.effective_weight for m in ev.metrics) == pytest.approx(1.0)


def test_efficiency_scores_zero_not_redistributed_when_nothing_works():
    ev = evaluate_task(TaskAttempt(make_task(), snaps(10), [make_run(20, set(CASE_IDS), compile_error=True)]))
    eff = metric(ev, "efficiency")
    assert eff.assessed and eff.score == 0.0 and eff.effective_weight > 0.0


def test_code_quality_counts_at_half_value_when_nothing_passes():
    wrong = evaluate_task(TaskAttempt(make_task(), snaps(10), [make_run(20, set())]))
    right = evaluate_task(TaskAttempt(make_task(), snaps(10), [make_run(20, set(CASE_IDS))]))
    assert metric(right, "code_quality").score == 100.0
    assert metric(wrong, "code_quality").score == 50.0


def test_fast_wrong_attempt_scores_far_below_a_correct_one():
    wrong = evaluate_task(TaskAttempt(make_task(), snaps(10), [make_run(20, set())], submitted_at=20))
    right = evaluate_task(TaskAttempt(make_task(), snaps(10), [make_run(20, set(CASE_IDS))], submitted_at=20))
    assert wrong.task_score < 15.0 and right.task_score > 80.0


# ---------------------------------------------------------------------------
# Time-based scoring
# ---------------------------------------------------------------------------

def test_time_score_boundaries():
    assert time_score_raw(40, 100) == 100.0
    assert time_score_raw(50, 100) == 100.0
    assert time_score_raw(75, 100) == 80.0
    assert time_score_raw(100, 100) == 60.0


def test_time_score_is_gated_by_correctness():
    wrong = evaluate_task(TaskAttempt(make_task(), snaps(10), [make_run(20, set())], submitted_at=20))
    assert metric(wrong, "time").score == 0.0


def test_time_score_uses_the_extended_deadline():
    base = TaskAttempt(make_task(limit=100), snaps(10), [make_run(60, set(CASE_IDS))], submitted_at=60)
    extended = TaskAttempt(make_task(limit=100), snaps(10), [make_run(60, set(CASE_IDS))], submitted_at=60, extension_multiplier=2.0)
    assert metric(evaluate_task(extended), "time").score > metric(evaluate_task(base), "time").score


# ---------------------------------------------------------------------------
# Code quality (static analysis only)
# ---------------------------------------------------------------------------

def test_clean_code_scores_100():
    assert analyze_python_quality(CLEAN_CODE).score == 100.0


def test_syntax_error_and_empty_code_score_zero():
    assert analyze_python_quality("def broken(:\n  pass").score == 0.0
    assert analyze_python_quality("   \n").score == 0.0


def test_null_bytes_are_handled_without_crashing():
    assert analyze_python_quality("x = 1\x00").score == 0.0


def test_oversized_snapshot_is_not_assessed():
    result = analyze_python_quality("x = 1\n" * 30_000)
    assert result.assessed is False and result.score is None


def test_long_function_is_flagged():
    body = "\n".join(f"    x{i} = {i}" for i in range(45))
    result = analyze_python_quality(f"def big():\n    \"\"\"doc\"\"\"\n{body}\n    return 0\n")
    assert "LONG_FUNCTION" in [f.code for f in result.findings]


def test_deep_nesting_is_flagged_but_elif_chain_is_not():
    deep = "def f(a):\n    '''d'''\n    for i in a:\n        if i:\n            while i:\n                if i > 1:\n                    return i\n"
    elif_chain = "def g(a):\n    '''d'''\n    if a == 1:\n        return 1\n    elif a == 2:\n        return 2\n    elif a == 3:\n        return 3\n    elif a == 4:\n        return 4\n    return 0\n"
    assert "DEEP_NESTING" in [f.code for f in analyze_python_quality(deep).findings]
    assert "DEEP_NESTING" not in [f.code for f in analyze_python_quality(elif_chain).findings]


def test_high_cyclomatic_complexity_is_flagged():
    branches = "\n".join(f"    if a == {i}:\n        return {i}" for i in range(12))
    result = analyze_python_quality(f"def f(a):\n    '''d'''\n{branches}\n    return 0\n")
    assert "HIGH_COMPLEXITY" in [f.code for f in result.findings]


def test_naming_violations_are_flagged_and_constants_are_allowed():
    result = analyze_python_quality("MAX_SIZE = 3\ndef computeTotal(xs):\n    '''d'''\n    myVar = 1\n    return myVar\n")
    messages = " ".join(f.message for f in result.findings if f.code == "NAMING")
    assert "computeTotal" in messages and "myVar" in messages and "MAX_SIZE" not in messages


def test_missing_docstring_penalty_scales_with_the_share_of_functions():
    one_of_two = analyze_python_quality("def a():\n    '''d'''\n    return 1\ndef b():\n    return 2\n")
    two_of_two = analyze_python_quality("def a():\n    return 1\ndef b():\n    return 2\n")
    assert two_of_two.score < one_of_two.score < 100.0


def test_bad_practices_are_flagged():
    code = ("from os import *\ndef f(x=[]):\n    '''d'''\n    try:\n        return eval(x)\n    except:\n        return None\n")
    codes = [f.code for f in analyze_python_quality(code).findings]
    assert codes.count("BAD_PRACTICE") == 4      # wildcard import, mutable default, eval, bare except


def test_bad_practice_deduction_is_capped():
    code = "def f(x=[]):\n    '''d'''\n    try:\n        return eval(x)\n    except:\n        return exec(x)\n"
    # 4 bad practices would deduct 46, but the BAD_PRACTICE category is capped at 25.
    assert analyze_python_quality(code).score == 75.0


def test_process_and_network_apis_are_informational_only():
    result = analyze_python_quality("import subprocess\nimport os\ndef f():\n    '''d'''\n    os.system('ls')\n")
    assert len(result.informational) == 2
    assert result.score == 100.0                 # informational never reduces the score


def test_engine_never_executes_candidate_code():
    folder = tempfile.mkdtemp()
    target = os.path.join(folder, "should_not_exist.txt")
    code = f"open({target!r}, 'w').write('executed')\nraise SystemExit(1)\n"
    analyze_python_quality(code)
    attempt = TaskAttempt(make_task(), [CodeSnapshot(5, code)], [make_run(10, set(CASE_IDS))])
    evaluate_task(attempt)
    assert not os.path.exists(target)


def test_non_python_language_quality_not_assessed_and_weight_redistributed():
    ev = evaluate_task(TaskAttempt(make_task(language="javascript"), snaps(10), [make_run(20, set(CASE_IDS))], submitted_at=20))
    quality = metric(ev, "code_quality")
    assert not quality.assessed and quality.effective_weight == 0.0
    assert sum(m.effective_weight for m in ev.metrics) == pytest.approx(1.0)


def test_sandbox_relevant_api_in_final_snapshot_requires_review_without_changing_quality_score():
    code = "import socket\ndef f():\n    '''d'''\n    return 1\n"
    ev = evaluate_task(TaskAttempt(make_task(), [CodeSnapshot(5, code)], [make_run(10, set(CASE_IDS))]))
    assert ev.human_review_required
    assert metric(ev, "code_quality").score == 100.0


# ---------------------------------------------------------------------------
# Problem-solving approach (process proxy)
# ---------------------------------------------------------------------------

def test_iterating_and_improving_scores_higher_than_a_single_blind_run():
    iterating = TaskAttempt(make_task(), snaps(10, 20, 30), [make_run(15, {"v1"}), make_run(25, {"v1", "v2", "h1"}), make_run(35, set(CASE_IDS))])
    single = TaskAttempt(make_task(), snaps(10), [make_run(15, {"v1"})])
    assert assess_problem_solving(iterating).score > assess_problem_solving(single).score


def test_regressions_between_runs_reduce_the_score():
    steady = TaskAttempt(make_task(), snaps(10), [make_run(15, {"v1"}), make_run(25, {"v1", "v2"})])
    regressing = TaskAttempt(make_task(), snaps(10), [make_run(15, {"v1", "v2"}), make_run(25, {"v1"})])
    assert assess_problem_solving(regressing).score < assess_problem_solving(steady).score


def test_recovering_from_a_compile_error_is_noticed():
    attempt = TaskAttempt(make_task(), snaps(10), [make_run(15, set(), compile_error=True), make_run(25, {"v1"})])
    assert any("Recovered" in s for s in assess_problem_solving(attempt).signals)


def test_no_timeline_means_problem_solving_not_assessed():
    result = assess_problem_solving(TaskAttempt(make_task()))
    assert result.assessed is False and result.score is None


# ---------------------------------------------------------------------------
# System design (keyword proxy, always reviewed)
# ---------------------------------------------------------------------------

COMPONENTS = {"load balancer": ["load balancer"], "database": ["database", "postgres"], "cache": ["cache", "redis"]}
GOOD_DESIGN = ("We put a load balancer in front of stateless API servers because that lets us scale horizontally. "
               "A Postgres database stores users; a Redis cache absorbs hot reads, which is a trade-off between latency "
               "and consistency. The cache is a bottleneck risk, however we can use replicas for failover.")


def design_task():
    return MachineTestTask("d1", MachineTestType.SYSTEM_DESIGN, "URL shortener", DifficultyTier.ADVANCED, 1800, design_components=COMPONENTS)


def test_design_coverage_and_reasoning_are_scored():
    result = evaluate_design_writeup(GOOD_DESIGN, COMPONENTS)
    assert result.coverage_score == 100.0 and result.missing == []
    assert result.reasoning_score == 100.0


def test_design_missing_components_lower_coverage():
    result = evaluate_design_writeup("We use a database " + "filler word " * 20, COMPONENTS)
    assert result.covered == ["database"] and result.coverage_score == pytest.approx(33.3, abs=0.1)


def test_short_design_writeup_is_capped():
    result = evaluate_design_writeup("load balancer database cache", COMPONENTS)
    assert result.too_short and result.coverage_score == 30.0


def test_design_task_always_requires_human_review_and_flags_the_proxy():
    ev = evaluate_task(TaskAttempt(design_task(), design_text=GOOD_DESIGN, submitted_at=900))
    assert ev.human_review_required
    assert "DESIGN_PROXY_SCORING" in [f.code for f in ev.flags]
    assert not metric(ev, "code_quality").assessed and not metric(ev, "efficiency").assessed


def test_design_time_is_gated_by_coverage_and_weights_sum_to_one():
    ev = evaluate_task(TaskAttempt(design_task(), design_text="database " + "pad " * 40, submitted_at=100))
    assert metric(ev, "time").score == pytest.approx(33.3, abs=0.1)
    assert sum(m.effective_weight for m in ev.metrics) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Whole-test report
# ---------------------------------------------------------------------------

def test_overall_score_is_difficulty_weighted():
    easy = good_attempt(difficulty=DifficultyTier.BASICS)
    hard = TaskAttempt(make_task(difficulty=DifficultyTier.ADVANCED), snaps(10), [make_run(20, set())], submitted_at=20)
    report = build_machine_test_report([easy, hard])
    e, h = report.tasks
    expected = (e.task_score * DIFFICULTY_WEIGHT[DifficultyTier.BASICS] + h.task_score * DIFFICULTY_WEIGHT[DifficultyTier.ADVANCED]) / 3.0
    assert report.overall_score == pytest.approx(expected, abs=0.05)


def test_score_band_thresholds():
    strong = build_machine_test_report([good_attempt()])
    weak = build_machine_test_report([TaskAttempt(make_task(), snaps(10), [make_run(20, set())], submitted_at=20)])
    assert strong.score_band in ("strong", "moderate") and weak.score_band == "limited"
    assert weak.overall_score < strong.overall_score


def test_report_never_makes_an_automated_decision_and_lists_what_is_not_implemented():
    report = build_machine_test_report([good_attempt()])
    assert report.automated_decision == "none"
    assert {"sandboxed_code_execution", "complexity_analysis", "plagiarism_or_ai_generated_code_detection",
            "non_python_code_quality", "screen_recording_and_paste_detection"} == set(report.not_implemented)
    assert "sandboxed_code_execution" in report.to_summary_text()


def test_integrity_tag_adds_review_but_never_changes_the_score():
    clear = build_machine_test_report([good_attempt()], integrity_risk_tag=IntegrityRiskTag.CLEAR)
    high = build_machine_test_report([good_attempt()], integrity_risk_tag=IntegrityRiskTag.HIGH)
    assert high.overall_score == clear.overall_score
    assert high.human_review_required and high.integrity_risk_tag == "high"
    assert any("integrity tag" in r.lower() for r in high.human_review_reasons)


def test_low_or_missing_integrity_tag_adds_no_review_requirement():
    for tag in (None, "low", IntegrityRiskTag.LOW):
        assert not build_machine_test_report([good_attempt()], integrity_risk_tag=tag).human_review_required


def test_a_clean_straightforward_attempt_needs_no_review():
    assert not build_machine_test_report([good_attempt()]).human_review_required


def test_empty_attempt_list_is_rejected():
    with pytest.raises(ValueError):
        build_machine_test_report([])


def test_report_is_json_serializable_and_complete():
    report = build_machine_test_report([good_attempt(), TaskAttempt(design_task(), design_text=GOOD_DESIGN, submitted_at=900)])
    data = json.loads(json.dumps(report.to_dict()))
    for key in ("overall_score", "score_band", "automated_decision", "tasks", "capture_summary", "not_implemented", "caveats"):
        assert key in data


def test_reports_do_not_share_mutable_defaults():
    a, b = build_machine_test_report([good_attempt()]), build_machine_test_report([good_attempt()])
    a.caveats.append("x")
    a.not_implemented["x"] = "y"
    assert "x" not in b.caveats and "x" not in b.not_implemented
