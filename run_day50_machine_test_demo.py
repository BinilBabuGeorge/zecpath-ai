"""
Day 50 demo -- evaluates five machine-test scenarios to show the scoring
model actually differentiates candidates, then a full mixed test (coding +
debugging + file-based + system design) carrying a real Day 49 integrity
tag. Writes:
  - logs/day50_machine_test_run.log
  - data/results/day50_machine_test_report.json

HONESTY NOTE: no sandbox runner exists in this project, so the EXECUTION
RESULTS here (which cases passed, how long they took) are hand-written
stand-ins for what a sandbox would report, and the code snapshots are
hand-written too. The engine consuming them -- scoring, static analysis,
time logic, redistribution, flags -- is 100% real. The engine never runs
the candidate code; scenario F proves it.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile

from parsers.integrity_detection_engine import BrowserEvent, BrowserEventType as T, build_integrity_report
from parsers.machine_test_evaluation_engine import (
    CaseResult,
    CaseSpec,
    CodeSnapshot,
    ExecutionRun,
    MachineTestTask,
    MachineTestType,
    TaskAttempt,
    build_machine_test_report,
    evaluate_task,
)
from parsers.technical_interview_question_bank import DifficultyTier

LOG_PATH = "logs/day50_machine_test_run.log"
REPORT_PATH = "data/results/day50_machine_test_report.json"

os.makedirs("logs", exist_ok=True)
os.makedirs("data/results", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, mode="w"), logging.StreamHandler()],
)
log = logging.getLogger("day50_demo")

CASE_IDS = ["v1", "v2", "h1", "h2"]
LIMIT = 1800.0          # 30 minutes

CLEAN_SOLUTION = '''
def two_sum(numbers, target):
    """Return indices of two numbers adding up to target, or None."""
    seen = {}
    for index, value in enumerate(numbers):
        if target - value in seen:
            return seen[target - value], index
        seen[value] = index
    return None
'''

MESSY_SOLUTION = '''
def twoSum(nums, t, cache=[]):
    for i in range(len(nums)):
        for j in range(len(nums)):
            if i != j:
                if nums[i] + nums[j] == t:
                    if i < j:
                        try:
                            return i, j
                        except:
                            pass
    return None
'''

JS_SOLUTION = "function fix(a){ return a.filter(Boolean); }"

HOSTILE_SNIPPET = "import tempfile\nopen(%r, 'w').write('executed')\n"


def task(task_id, task_type, difficulty, language="python", reference=120.0):
    cases = [CaseSpec("v1"), CaseSpec("v2"), CaseSpec("h1", visible=False), CaseSpec("h2", visible=False)]
    return MachineTestTask(task_id, task_type, f"{task_id} ({task_type.value})", difficulty, LIMIT, language, cases,
                           reference_runtime_ms=reference)


def run(ts, passed, runtime=120.0, compile_error=False):
    results = [CaseResult(c, c in passed, runtime if c in passed else None) for c in CASE_IDS]
    return ExecutionRun(ts, results, compile_error=compile_error, stdout_tail="")


def scenario_a_strong():
    t = task("coding-two-sum", MachineTestType.CODING, DifficultyTier.INTERMEDIATE)
    snaps = [CodeSnapshot(120, "def two_sum(n, t):\n    pass\n"), CodeSnapshot(300, CLEAN_SOLUTION), CodeSnapshot(420, CLEAN_SOLUTION)]
    runs = [run(250, {"v1"}), run(430, set(CASE_IDS), runtime=130.0)]
    return "A. Strong candidate (iterates, correct, efficient, clean, fast)", TaskAttempt(t, snaps, runs, submitted_at=440)


def scenario_b_overfit():
    t = task("coding-two-sum", MachineTestType.CODING, DifficultyTier.INTERMEDIATE)
    snaps = [CodeSnapshot(200, CLEAN_SOLUTION)]
    runs = [run(210, {"v1", "v2"})]
    return "B. Passes the visible samples only (possible special-casing)", TaskAttempt(t, snaps, runs, submitted_at=220)


def scenario_c_slow_messy():
    t = task("coding-two-sum", MachineTestType.CODING, DifficultyTier.INTERMEDIATE)
    snaps = [CodeSnapshot(900, MESSY_SOLUTION), CodeSnapshot(1700, MESSY_SOLUTION)]
    runs = [run(1650, set(CASE_IDS), runtime=1100.0)]     # correct, but ~9x slower than the reference
    return "C. Correct but slow, messy and late (95% of the time limit)", TaskAttempt(t, snaps, runs, submitted_at=1710)


def scenario_d_fast_wrong():
    t = task("coding-two-sum", MachineTestType.CODING, DifficultyTier.INTERMEDIATE)
    snaps = [CodeSnapshot(60, CLEAN_SOLUTION)]
    runs = [run(70, set(), compile_error=False)]          # submits in 4% of the time, nothing passes
    return "D. Fast and wrong (submits at 4% of the limit, nothing passes)", TaskAttempt(t, snaps, runs, submitted_at=75)


def scenario_e_javascript():
    t = task("debug-filter", MachineTestType.DEBUGGING, DifficultyTier.BASICS, language="javascript", reference=None)
    snaps = [CodeSnapshot(100, JS_SOLUTION), CodeSnapshot(200, JS_SOLUTION), CodeSnapshot(300, JS_SOLUTION)]
    runs = [run(150, {"v1", "h1"}), run(320, set(CASE_IDS))]
    return "E. JavaScript debugging task (quality not assessable, weight redistributed)", TaskAttempt(t, snaps, runs, submitted_at=330)


def main() -> None:
    log.info("Starting Day 50 machine test demo (no candidate code is executed by this engine).")
    results, evals = {}, {}

    for build in (scenario_a_strong, scenario_b_overfit, scenario_c_slow_messy, scenario_d_fast_wrong, scenario_e_javascript):
        title, attempt = build()
        ev = evaluate_task(attempt)
        evals[build.__name__] = ev
        log.info("-" * 70)
        log.info("%s -> task score %s", title, ev.task_score)
        for m in ev.metrics:
            if m.base_weight > 0:
                log.info("   %-16s %s (effective weight %.2f) | %s", m.name, m.score if m.assessed else "not assessed", m.effective_weight, m.explanation)
        for f in ev.flags:
            log.info("   FLAG %s: %s", f.code, f.message)
        results[build.__name__] = {"title": title, **ev.to_dict()}

    # Scenario F: hostile code is analysed, never run.
    folder = tempfile.mkdtemp()
    target = os.path.join(folder, "proof_of_execution.txt")
    hostile = TaskAttempt(task("coding-hostile", MachineTestType.CODING, DifficultyTier.BASICS),
                          [CodeSnapshot(50, HOSTILE_SNIPPET % target)], [run(60, {"v1"})], submitted_at=70)
    evaluate_task(hostile)
    log.info("-" * 70)
    log.info("F. Hostile snippet that writes a file if executed: file exists after evaluation? %s", os.path.exists(target))

    # Full mixed test, carrying a REAL Day 49 integrity tag.
    events = [BrowserEvent(T.TAB_HIDDEN, 100), BrowserEvent(T.TAB_VISIBLE, 104),
              BrowserEvent(T.TAB_HIDDEN, 120), BrowserEvent(T.TAB_VISIBLE, 124),
              BrowserEvent(T.TAB_HIDDEN, 140), BrowserEvent(T.TAB_VISIBLE, 144)]
    integrity = build_integrity_report(events, session_end=1800)
    design = MachineTestTask("design-url-shortener", MachineTestType.SYSTEM_DESIGN, "Design a URL shortener", DifficultyTier.ADVANCED, LIMIT,
                             design_components={"load balancer": ["load balancer"], "database": ["database", "postgres"],
                                                "cache": ["cache", "redis"], "id generation": ["hash", "base62", "unique id"]})
    design_text = ("A load balancer fronts stateless API servers so we can scale horizontally. Short codes come from a base62 "
                   "counter, because hashing risks collisions. A Postgres database stores mappings; a Redis cache serves hot reads, "
                   "which is a trade-off between latency and consistency. The cache is a bottleneck risk, however replicas give failover.")
    attempts = [scenario_a_strong()[1], scenario_e_javascript()[1],
                TaskAttempt(design, design_text=design_text, submitted_at=1200)]
    with_tag = build_machine_test_report(attempts, integrity_risk_tag=integrity.risk_tag)
    without_tag = build_machine_test_report(attempts)
    log.info("=" * 70)
    log.info(with_tag.to_summary_text().replace("\n", " | "))
    print()
    print(with_tag.to_summary_text())
    results["full_mixed_test"] = with_tag.to_dict()

    # Sanity checks the demo itself verifies, not just claims:
    a, b, c, d, e = (evals[k] for k in ("scenario_a_strong", "scenario_b_overfit", "scenario_c_slow_messy",
                                          "scenario_d_fast_wrong", "scenario_e_javascript"))
    score = lambda ev, name: next(m for m in ev.metrics if m.name == name).score

    assert a.task_score > c.task_score > d.task_score
    log.info("Sanity check passed: strong (%s) > correct-but-slow-and-messy (%s) > fast-and-wrong (%s).", a.task_score, c.task_score, d.task_score)

    assert score(c, "correctness") == 100.0 and score(c, "efficiency") < 20.0 and score(c, "code_quality") < 70.0
    log.info("Sanity check passed: scenario C is fully correct yet efficiency and quality are marked down (correctness alone is not the whole score).")

    assert "PASSES_VISIBLE_FAILS_HIDDEN" in [f.code for f in b.flags] and b.human_review_required
    log.info("Sanity check passed: passing only the visible samples was flagged for review.")

    assert score(d, "time") == 0.0
    log.info("Sanity check passed: finishing at 4 percent of the limit with nothing passing earned zero time credit (fast and wrong earns nothing).")

    quality_js = next(m for m in e.metrics if m.name == "code_quality")
    assert not quality_js.assessed and abs(sum(m.effective_weight for m in e.metrics) - 1.0) < 1e-9
    log.info("Sanity check passed: JavaScript quality was 'not assessed' and the remaining weights still sum to 1.0.")

    assert not os.path.exists(target)
    log.info("Sanity check passed: the hostile snippet was analysed but never executed (no file written).")

    assert with_tag.overall_score == without_tag.overall_score and with_tag.human_review_required
    log.info("Sanity check passed: Day 49 integrity tag %s added a review requirement without changing the score (%s).",
             integrity.risk_tag.value.upper(), with_tag.overall_score)

    design_eval = with_tag.tasks[2]
    assert design_eval.human_review_required
    log.info("Sanity check passed: the system-design task is scored by a keyword proxy and always needs human review.")

    assert with_tag.automated_decision == "none"
    assert {"sandboxed_code_execution", "complexity_analysis"} <= set(with_tag.not_implemented)
    log.info("Sanity check passed: automated_decision is 'none' and the not-implemented list is present.")

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    log.info("Report written to %s", REPORT_PATH)


if __name__ == "__main__":
    main()
