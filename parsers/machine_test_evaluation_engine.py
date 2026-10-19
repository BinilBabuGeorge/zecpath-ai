"""
Machine Test AI Design (Day 50)

WHAT THIS DAY BUILDS, AND THE ONE DECISION THAT SHAPES EVERYTHING:
a machine test means evaluating code a candidate wrote. Running
untrusted code is the dangerous part -- it needs real isolation
(a container or microVM with no network, CPU/memory/time limits and an
ephemeral filesystem). This project has no such sandbox, and an
`exec()` call inside a scoring service is not a substitute for one.

So this engine NEVER RUNS CANDIDATE CODE. It does two safe things:
  1. Scores EXECUTION RESULTS -- pass/fail per test case, runtimes --
     that a future sandbox runner would hand it (the contract is
     specified here: CaseResult / ExecutionRun).
  2. Analyses code STATICALLY, with `ast.parse` only (parsing never
     executes anything), for code quality.
A test (test_engine_never_executes_candidate_code) proves a snippet that
would write a file if run does not write it when analysed.

THE FOUR TASK TYPES (brief) AND HOW EACH IS EVALUATED:
    coding        execution results + runtime + static quality + process
    debugging     same, with weight shifted to correctness and process
    file_based    execution results over produced output files + quality
    system_design NOT executable. Scored by a keyword/rubric PROXY
                  (component coverage + reasoning markers), always
                  flagged for human review -- keyword rubrics are
                  gameable and this engine says so.

THE FIVE SCORED METRICS (the brief's four, plus its time-based logic):
    correctness      weighted pass fraction; hidden cases count 1.5x so
                     hard-coding the visible samples does not pay
    efficiency       measured runtime vs the reference solution's, on
                     the test inputs. NOT big-O analysis -- that is not
                     done. Needs a passing solution, so it is gated.
    code_quality     Python only (AST): function length, nesting depth,
                     cyclomatic complexity, naming, docstrings, bad
                     practices. Other languages: not assessed. Counts at
                     half value when nothing passes.
    problem_solving  a PROCESS PROXY from the snapshot/run timeline
                     (did they run tests repeatedly, improve, recover
                     from errors). It is not a measure of reasoning.
    time             speed of the final submission relative to the task
                     limit. A weak signal, so low weight, and GATED.

DESIGN RULES:
  1. Fast and wrong earns nothing: efficiency and time are multiplied by
     the weighted pass fraction, and code quality counts at half value
     (QUALITY_FLOOR) for a solution that passes nothing. When a
     reference runtime exists but no case works, efficiency scores 0 --
     it is not "not assessed", which would shift its weight onto the
     other metrics.
  2. A metric that cannot be assessed (no reference runtime, non-Python
     code, no timeline) is reported as not assessed and its weight is
     redistributed proportionally -- never silently scored as zero.
     Same pattern as Day 13's ATS scorer and Day 41's unified scorer.
  3. Scores are normalized across difficulty the way Day 47 does: every
     metric is a 0-100 ratio, task time limits are per task, and the
     overall score is a difficulty-weighted average (basics 1.0,
     intermediate 1.5, advanced 2.0).
  4. Evidence after the deadline is ignored. An approved accommodation
     (`extension_multiplier` >= 1.0) scales the deadline.
  5. `automated_decision` is always "none". The report is an input to
     human review and later aggregation (PRD Phase 70), never a verdict.
  6. A Day 49 integrity tag, if supplied, is carried through unchanged
     and can only ADD a human-review requirement -- it never alters a
     score.
  7. Thresholds and weights are reasoned, not calibrated -- no labelled
     machine-test data exists, the same caveat every scoring day since
     Day 34 has stated.

INPUT CONTRACT:  list of TaskAttempt (task + snapshots + runs [+ design text]).
OUTPUT CONTRACT: MachineTestReport; .to_dict() / .to_summary_text().
"""

from __future__ import annotations

import ast
import math
import re
import statistics
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from parsers.technical_interview_question_bank import DifficultyTier

# ---------------------------------------------------------------------------
# Tunable parameters -- reasoned, NOT calibrated against labelled data
# ---------------------------------------------------------------------------

METRICS = ("correctness", "efficiency", "code_quality", "problem_solving", "time")

DIFFICULTY_WEIGHT: Dict[DifficultyTier, float] = {
    DifficultyTier.BASICS: 1.0,
    DifficultyTier.INTERMEDIATE: 1.5,
    DifficultyTier.ADVANCED: 2.0,
}

HIDDEN_CASE_WEIGHT_MULTIPLIER = 1.5
OVERFIT_VISIBLE_FULL = 1.0         # all visible cases pass...
OVERFIT_HIDDEN_MAX = 0.5           # ...while under half the hidden ones do
OVERFIT_MIN_HIDDEN_CASES = 2

EFFICIENCY_FULL_CREDIT_RATIO = 1.5   # runtime within 1.5x of the reference = full credit
EFFICIENCY_ZERO_CREDIT_RATIO = 10.0  # 10x slower or worse = no credit

TIME_FULL_CREDIT_FRACTION = 0.5      # finishing within half the limit = full credit
TIME_SCORE_AT_LIMIT = 60.0           # finishing exactly at the limit still earns 60

MAX_FUNCTION_LINES = 40
MAX_NESTING_DEPTH = 3
MAX_COMPLEXITY = 10
MAX_SNAPSHOT_CHARS = 100_000         # larger snapshots are not analysed
MAX_OUTPUT_TAIL_CHARS = 2000         # stdout/stderr capture is truncated to its tail

QUALITY_FLOOR = 0.5                  # code quality counts at half value for a solution that passes nothing

DESIGN_MIN_WORDS = 30
DESIGN_SHORT_CAP = 30.0
DESIGN_REASONING_TARGET = 4          # distinct reasoning markers for full reasoning credit

BAND_STRONG = 75.0
BAND_MODERATE = 50.0

# Base weights per task type; each row sums to 1.0. A weight of 0 means
# "not applicable to this task type" (distinct from "not assessable",
# which is decided per attempt and triggers redistribution).
TYPE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "coding":        {"correctness": 0.45, "efficiency": 0.20, "code_quality": 0.15, "problem_solving": 0.10, "time": 0.10},
    "debugging":     {"correctness": 0.55, "efficiency": 0.00, "code_quality": 0.15, "problem_solving": 0.20, "time": 0.10},
    "file_based":    {"correctness": 0.55, "efficiency": 0.05, "code_quality": 0.15, "problem_solving": 0.15, "time": 0.10},
    "system_design": {"correctness": 0.60, "efficiency": 0.00, "code_quality": 0.00, "problem_solving": 0.30, "time": 0.10},
}


# ---------------------------------------------------------------------------
# Task and capture model (input/output capture: snapshots + execution results)
# ---------------------------------------------------------------------------

class MachineTestType(str, Enum):
    CODING = "coding"
    DEBUGGING = "debugging"
    FILE_BASED = "file_based"
    SYSTEM_DESIGN = "system_design"


@dataclass
class CaseSpec:
    """One test case of a task. Hidden cases are never shown to the candidate."""
    case_id: str
    visible: bool = True
    weight: float = 1.0


@dataclass
class MachineTestTask:
    task_id: str
    task_type: MachineTestType
    title: str
    difficulty: DifficultyTier
    time_limit_seconds: float
    language: str = "python"
    cases: List[CaseSpec] = field(default_factory=list)
    reference_runtime_ms: Optional[float] = None     # reference solution's runtime, measured by the sandbox
    design_components: Dict[str, List[str]] = field(default_factory=dict)   # component -> accepted keywords

    def __post_init__(self) -> None:
        if self.time_limit_seconds <= 0:
            raise ValueError("time_limit_seconds must be > 0.")
        if self.task_type is MachineTestType.SYSTEM_DESIGN:
            if not self.design_components:
                raise ValueError("A system_design task needs design_components.")
        elif not self.cases:
            raise ValueError("An executable task needs at least one test case.")


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    runtime_ms: Optional[float] = None
    timed_out: bool = False


def _tail(text: str) -> str:
    return text[-MAX_OUTPUT_TAIL_CHARS:] if len(text) > MAX_OUTPUT_TAIL_CHARS else text


@dataclass
class ExecutionRun:
    """One sandbox execution of the candidate's code. Captured, never scored
    from stdout/stderr -- those are kept (truncated to their tail) for the
    human reviewer only."""
    timestamp: float                       # seconds since task start
    results: List[CaseResult] = field(default_factory=list)
    compile_error: bool = False
    stdout_tail: str = ""
    stderr_tail: str = ""

    def __post_init__(self) -> None:
        self.stdout_tail = _tail(self.stdout_tail)
        self.stderr_tail = _tail(self.stderr_tail)


@dataclass
class CodeSnapshot:
    """The candidate's code at a moment in time (code snapshot capture)."""
    timestamp: float
    code: str
    trigger: str = "interval"              # "interval" | "run" | "submit"


@dataclass
class TaskAttempt:
    task: MachineTestTask
    snapshots: List[CodeSnapshot] = field(default_factory=list)
    runs: List[ExecutionRun] = field(default_factory=list)
    design_text: str = ""
    submitted_at: Optional[float] = None
    extension_multiplier: float = 1.0      # approved accommodation; never below 1.0

    def __post_init__(self) -> None:
        if self.extension_multiplier < 1.0:
            raise ValueError("extension_multiplier must be >= 1.0 (accommodations extend time, never shorten it).")

    @property
    def deadline(self) -> float:
        return self.task.time_limit_seconds * self.extension_multiplier

    def capture_summary(self) -> Dict:
        """What was captured, for storage/audit. Sizes, not content."""
        return {
            "snapshot_count": len(self.snapshots),
            "snapshot_total_chars": sum(len(s.code) for s in self.snapshots),
            "run_count": len(self.runs),
            "stdout_stderr_tail_chars": sum(len(r.stdout_tail) + len(r.stderr_tail) for r in self.runs),
            "design_text_chars": len(self.design_text),
        }


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------

@dataclass
class EvaluationFlag:
    code: str
    message: str

    def to_dict(self) -> Dict:
        return {"code": self.code, "message": self.message}


@dataclass
class MetricScore:
    name: str
    score: Optional[float]          # 0-100, None when not assessed
    base_weight: float
    effective_weight: float = 0.0
    assessed: bool = False
    explanation: str = ""

    def to_dict(self) -> Dict:
        return {"name": self.name, "score": self.score, "base_weight": self.base_weight,
                "effective_weight": round(self.effective_weight, 4), "assessed": self.assessed,
                "explanation": self.explanation}


@dataclass
class TaskEvaluation:
    task_id: str
    task_type: MachineTestType
    difficulty: DifficultyTier
    metrics: List[MetricScore]
    task_score: float
    flags: List[EvaluationFlag]
    human_review_required: bool
    human_review_reasons: List[str]

    def to_dict(self) -> Dict:
        return {
            "task_id": self.task_id, "task_type": self.task_type.value, "difficulty": self.difficulty.value,
            "task_score": self.task_score, "metrics": [m.to_dict() for m in self.metrics],
            "flags": [f.to_dict() for f in self.flags],
            "human_review_required": self.human_review_required,
            "human_review_reasons": self.human_review_reasons,
        }


# ---------------------------------------------------------------------------
# Evidence selection (deadline handling)
# ---------------------------------------------------------------------------

def _valid_runs(attempt: TaskAttempt) -> List[ExecutionRun]:
    return sorted((r for r in attempt.runs if r.timestamp <= attempt.deadline), key=lambda r: r.timestamp)


def _valid_snapshots(attempt: TaskAttempt) -> List[CodeSnapshot]:
    return sorted((s for s in attempt.snapshots if s.timestamp <= attempt.deadline), key=lambda s: s.timestamp)


# ---------------------------------------------------------------------------
# Correctness
# ---------------------------------------------------------------------------

@dataclass
class PassBreakdown:
    fraction: float                  # weighted pass fraction, 0-1
    passed: int
    total: int
    visible_fraction: Optional[float]
    hidden_fraction: Optional[float]
    hidden_total: int


def _pass_breakdown(task: MachineTestTask, run: Optional[ExecutionRun]) -> PassBreakdown:
    """Weighted pass fraction. A case missing from the run counts as failed;
    a compile error fails everything; hidden cases weigh more."""
    results = {} if run is None or run.compile_error else {r.case_id: r for r in run.results}
    w_total = w_pass = 0.0
    vis_total = vis_pass = hid_total = hid_pass = 0.0
    passed = 0
    for case in task.cases:
        w = case.weight * (1.0 if case.visible else HIDDEN_CASE_WEIGHT_MULTIPLIER)
        ok = bool(results.get(case.case_id) and results[case.case_id].passed)
        w_total += w
        if ok:
            w_pass += w
            passed += 1
        if case.visible:
            vis_total += case.weight
            vis_pass += case.weight if ok else 0.0
        else:
            hid_total += case.weight
            hid_pass += case.weight if ok else 0.0
    n_hidden = sum(1 for c in task.cases if not c.visible)
    return PassBreakdown(
        fraction=w_pass / w_total if w_total else 0.0, passed=passed, total=len(task.cases),
        visible_fraction=vis_pass / vis_total if vis_total else None,
        hidden_fraction=hid_pass / hid_total if hid_total else None, hidden_total=n_hidden,
    )


# ---------------------------------------------------------------------------
# Efficiency
# ---------------------------------------------------------------------------

def efficiency_from_ratio(ratio: float) -> float:
    """Log-linear: full credit within 1.5x of the reference runtime, none at 10x."""
    if ratio <= EFFICIENCY_FULL_CREDIT_RATIO:
        return 100.0
    if ratio >= EFFICIENCY_ZERO_CREDIT_RATIO:
        return 0.0
    lo, hi = math.log10(EFFICIENCY_FULL_CREDIT_RATIO), math.log10(EFFICIENCY_ZERO_CREDIT_RATIO)
    return round(100.0 * (1.0 - (math.log10(ratio) - lo) / (hi - lo)), 1)


# ---------------------------------------------------------------------------
# Time-based scoring
# ---------------------------------------------------------------------------

def time_score_raw(time_taken: float, effective_limit: float) -> float:
    """100 within half the limit, falling linearly to 60 at the limit. Beyond
    the limit there is no valid submission to score (handled by the caller)."""
    frac = time_taken / effective_limit
    if frac <= TIME_FULL_CREDIT_FRACTION:
        return 100.0
    if frac >= 1.0:
        return TIME_SCORE_AT_LIMIT
    span = 1.0 - TIME_FULL_CREDIT_FRACTION
    return round(100.0 - (frac - TIME_FULL_CREDIT_FRACTION) / span * (100.0 - TIME_SCORE_AT_LIMIT), 1)


# ---------------------------------------------------------------------------
# Code quality -- STATIC analysis only. ast.parse never executes anything.
# ---------------------------------------------------------------------------

@dataclass
class QualityFinding:
    code: str
    line: Optional[int]
    message: str
    penalty: float

    def to_dict(self) -> Dict:
        return {"code": self.code, "line": self.line, "message": self.message, "penalty": self.penalty}


@dataclass
class CodeQualityResult:
    assessed: bool
    score: Optional[float]
    findings: List[QualityFinding]
    informational: List[str]           # shown to a human, never scored
    note: str = ""


_SNAKE = re.compile(r"^_{0,2}[a-z][a-z0-9_]*$|^_$")
_PASCAL = re.compile(r"^_?[A-Z][A-Za-z0-9]*$")
_CONSTANT = re.compile(r"^_?[A-Z][A-Z0-9_]*$")
_SANDBOX_MODULES = {"subprocess", "socket", "ctypes", "requests", "urllib", "http"}
_CAPS = {"LONG_FUNCTION": 20.0, "DEEP_NESTING": 15.0, "HIGH_COMPLEXITY": 20.0,
         "NAMING": 10.0, "MISSING_DOCSTRING": 10.0, "BAD_PRACTICE": 25.0}


def _depth(stmts: Sequence[ast.stmt], depth: int) -> int:
    """Statement-level nesting depth. An `elif` is a nested If in the AST but
    reads as the same level, so it is not counted as extra nesting."""
    best = depth
    for s in stmts:
        if isinstance(s, ast.If):
            best = max(best, _depth(s.body, depth + 1))
            if len(s.orelse) == 1 and isinstance(s.orelse[0], ast.If):
                best = max(best, _depth(s.orelse, depth))
            else:
                best = max(best, _depth(s.orelse, depth + 1))
        elif isinstance(s, (ast.For, ast.AsyncFor, ast.While)):
            best = max(best, _depth(s.body, depth + 1), _depth(s.orelse, depth + 1))
        elif isinstance(s, (ast.With, ast.AsyncWith)):
            best = max(best, _depth(s.body, depth + 1))
        elif isinstance(s, ast.Try):
            for block in (s.body, s.orelse, s.finalbody):
                best = max(best, _depth(block, depth + 1))
            for handler in s.handlers:
                best = max(best, _depth(handler.body, depth + 1))
    return best


def _complexity(fn: ast.AST) -> int:
    """Cyclomatic complexity: 1 + decision points."""
    total = 1
    for node in ast.walk(fn):
        if isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.IfExp)):
            total += 1
        elif isinstance(node, ast.BoolOp):
            total += len(node.values) - 1
    return total


def _is_mutable_default(node: ast.AST) -> bool:
    if isinstance(node, (ast.List, ast.Dict, ast.Set)):
        return True
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"list", "dict", "set"}


def analyze_python_quality(code: str) -> CodeQualityResult:
    """Explainable static quality score for Python source. Never executes the code."""
    if not code.strip():
        return CodeQualityResult(True, 0.0, [QualityFinding("EMPTY_SUBMISSION", None, "No code was submitted.", 100.0)], [])
    if len(code) > MAX_SNAPSHOT_CHARS:
        return CodeQualityResult(False, None, [], [], f"Snapshot exceeds {MAX_SNAPSHOT_CHARS} characters; not analysed.")
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError, MemoryError) as exc:
        line = getattr(exc, "lineno", None)
        return CodeQualityResult(True, 0.0, [QualityFinding("SYNTAX_ERROR", line, "The code does not parse.", 100.0)], [])

    findings: List[QualityFinding] = []
    informational: List[str] = []
    functions = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]

    for fn in functions:
        length = (fn.end_lineno or fn.lineno) - fn.lineno + 1
        if length > MAX_FUNCTION_LINES:
            findings.append(QualityFinding("LONG_FUNCTION", fn.lineno, f"'{fn.name}' is {length} lines (limit {MAX_FUNCTION_LINES}).", 5.0))
        nest = _depth(fn.body, 0)
        if nest > MAX_NESTING_DEPTH:
            findings.append(QualityFinding("DEEP_NESTING", fn.lineno, f"'{fn.name}' nests {nest} levels deep (limit {MAX_NESTING_DEPTH}).", 5.0))
        cx = _complexity(fn)
        if cx > MAX_COMPLEXITY:
            findings.append(QualityFinding("HIGH_COMPLEXITY", fn.lineno, f"'{fn.name}' has cyclomatic complexity {cx} (limit {MAX_COMPLEXITY}).", 5.0))
        for default in fn.args.defaults + [d for d in fn.args.kw_defaults if d is not None]:
            if _is_mutable_default(default):
                findings.append(QualityFinding("BAD_PRACTICE", fn.lineno, f"'{fn.name}' uses a mutable default argument.", 8.0))

    # Naming: functions and variables snake_case, classes PascalCase, constants UPPER_CASE.
    bad_names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not (node.name.startswith("__") and node.name.endswith("__")) and not _SNAKE.match(node.name):
                bad_names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            if not _PASCAL.match(node.name):
                bad_names.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            if not (_SNAKE.match(node.id) or _CONSTANT.match(node.id)):
                bad_names.add(node.id)
    for name in sorted(bad_names):
        findings.append(QualityFinding("NAMING", None, f"'{name}' does not follow Python naming conventions.", 2.0))

    if functions:
        undocumented = [f for f in functions if ast.get_docstring(f) is None]
        if undocumented:
            share = len(undocumented) / len(functions)
            findings.append(QualityFinding("MISSING_DOCSTRING", None,
                                           f"{len(undocumented)} of {len(functions)} function(s) have no docstring.", round(10.0 * share, 2)))

    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            findings.append(QualityFinding("BAD_PRACTICE", node.lineno, "Bare 'except:' hides errors.", 8.0))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
            findings.append(QualityFinding("BAD_PRACTICE", node.lineno, f"Use of {node.func.id}().", 15.0))
        elif isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names):
            findings.append(QualityFinding("BAD_PRACTICE", node.lineno, "Wildcard import.", 5.0))

    # Informational only: things a sandbox must contain and a human should glance at.
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in _SANDBOX_MODULES:
                    informational.append(f"Imports '{alias.name}' (process/network capable) at line {node.lineno}.")
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in _SANDBOX_MODULES:
            informational.append(f"Imports from '{node.module}' (process/network capable) at line {node.lineno}.")
        elif isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "os" and f.attr in {"system", "popen"}:
                informational.append(f"Calls os.{f.attr}() at line {node.lineno}.")
            elif isinstance(f, ast.Name) and f.id == "__import__":
                informational.append(f"Calls __import__() at line {node.lineno}.")

    totals: Dict[str, float] = {}
    for f in findings:
        totals[f.code] = totals.get(f.code, 0.0) + f.penalty
    deduction = sum(min(v, _CAPS.get(k, 100.0)) for k, v in totals.items())
    return CodeQualityResult(True, round(max(0.0, 100.0 - deduction), 1), findings, informational)


# ---------------------------------------------------------------------------
# Problem-solving approach -- a process proxy from the capture timeline
# ---------------------------------------------------------------------------

@dataclass
class ApproachResult:
    assessed: bool
    score: Optional[float]
    signals: List[str]


def assess_problem_solving(attempt: TaskAttempt) -> ApproachResult:
    runs, snaps = _valid_runs(attempt), _valid_snapshots(attempt)
    if not runs and not snaps:
        return ApproachResult(False, None, ["No snapshots or runs were captured."])

    fractions = [_pass_breakdown(attempt.task, r).fraction for r in runs]
    score, signals = 20.0, []

    if len(runs) >= 2:
        score += 25
        signals.append(f"Ran the tests {len(runs)} times (checked own work while iterating).")
    elif len(runs) == 1:
        score += 10
        signals.append("Ran the tests once.")
    else:
        signals.append("Never ran the tests.")

    if fractions:
        if fractions[0] >= 1.0:
            score += 25
            signals.append("Passed everything on the first run.")
        elif fractions[-1] > fractions[0]:
            score += 25
            signals.append(f"Improved from {fractions[0]:.0%} to {fractions[-1]:.0%} passing across runs.")

    if any(r.compile_error for r in runs[:-1]) and not runs[-1].compile_error:
        score += 10
        signals.append("Recovered from a compile/syntax error.")

    if len(snaps) >= 3:
        score += 15
        signals.append(f"Built the solution incrementally ({len(snaps)} snapshots).")

    regressions = sum(1 for a, b in zip(fractions, fractions[1:]) if b < a)
    if regressions:
        score -= min(20, 5 * regressions)
        signals.append(f"Pass rate dropped between runs {regressions} time(s).")

    return ApproachResult(True, round(max(0.0, min(100.0, score)), 1), signals)


# ---------------------------------------------------------------------------
# System-design write-up -- a keyword/rubric PROXY, always human-reviewed
# ---------------------------------------------------------------------------

_REASONING_MARKERS = ["trade-off", "tradeoff", "because", "alternatively", "however", "bottleneck",
                      "single point of failure", "failover", "scal", "consistency", "latency", "cost"]


@dataclass
class DesignResult:
    coverage_score: float
    reasoning_score: float
    covered: List[str]
    missing: List[str]
    markers_found: List[str]
    too_short: bool


def evaluate_design_writeup(text: str, components: Dict[str, List[str]]) -> DesignResult:
    lowered = text.lower()
    covered = [c for c, kws in components.items() if any(k.lower() in lowered for k in kws)]
    missing = [c for c in components if c not in covered]
    markers = [m for m in _REASONING_MARKERS if m in lowered]
    coverage = 100.0 * len(covered) / len(components)
    reasoning = min(100.0, 100.0 * len(markers) / DESIGN_REASONING_TARGET)
    too_short = len(text.split()) < DESIGN_MIN_WORDS
    if too_short:
        coverage, reasoning = min(coverage, DESIGN_SHORT_CAP), min(reasoning, DESIGN_SHORT_CAP)
    return DesignResult(round(coverage, 1), round(reasoning, 1), covered, missing, markers, too_short)


# ---------------------------------------------------------------------------
# Per-task evaluation
# ---------------------------------------------------------------------------

def _redistribute(metrics: List[MetricScore]) -> None:
    """Proportional redistribution among assessed metrics with non-zero base weight."""
    live = [m for m in metrics if m.assessed and m.base_weight > 0]
    total = sum(m.base_weight for m in live)
    for m in metrics:
        m.effective_weight = (m.base_weight / total) if (m in live and total > 0) else 0.0


def evaluate_task(attempt: TaskAttempt) -> TaskEvaluation:
    task = attempt.task
    weights = TYPE_WEIGHTS[task.task_type.value]
    flags: List[EvaluationFlag] = []
    reasons: List[str] = []
    metrics = {name: MetricScore(name, None, weights[name]) for name in METRICS}

    runs, snaps = _valid_runs(attempt), _valid_snapshots(attempt)
    ignored = (len(attempt.runs) - len(runs)) + (len(attempt.snapshots) - len(snaps))
    if ignored:
        flags.append(EvaluationFlag("EVIDENCE_AFTER_DEADLINE_IGNORED", f"{ignored} run(s)/snapshot(s) after the deadline were not scored."))
    late = attempt.submitted_at is not None and attempt.submitted_at > attempt.deadline
    if late:
        flags.append(EvaluationFlag("LATE_SUBMISSION", "Submitted after the deadline."))
        reasons.append("Submission was late.")

    pass_fraction = 1.0   # gate for efficiency and time

    if task.task_type is MachineTestType.SYSTEM_DESIGN:
        design = evaluate_design_writeup(attempt.design_text, task.design_components)
        m = metrics["correctness"]
        m.score, m.assessed = design.coverage_score, True
        m.explanation = (f"Design coverage proxy: {len(design.covered)}/{len(task.design_components)} required components mentioned"
                         f" (missing: {', '.join(design.missing) or 'none'}).")
        a = metrics["problem_solving"]
        a.score, a.assessed = design.reasoning_score, True
        a.explanation = f"Reasoning-marker proxy: {len(design.markers_found)} distinct trade-off/reasoning term(s) found."
        pass_fraction = design.coverage_score / 100.0
        reasons.append("System-design scoring is a keyword proxy and can be gamed; a person must read the write-up.")
        flags.append(EvaluationFlag("DESIGN_PROXY_SCORING", "Scored by component keywords and reasoning markers only."))
        if design.too_short:
            flags.append(EvaluationFlag("DESIGN_TOO_SHORT", f"Write-up under {DESIGN_MIN_WORDS} words; scores capped."))
    else:
        final_run = runs[-1] if runs else None
        pb = _pass_breakdown(task, final_run)
        pass_fraction = pb.fraction

        c = metrics["correctness"]
        c.assessed = True
        c.score = round(pb.fraction * 100.0, 1)
        if final_run is None:
            c.explanation = "No execution results were captured before the deadline."
        elif final_run.compile_error:
            c.explanation = "The final run failed to compile; no cases could pass."
        else:
            c.explanation = f"{pb.passed}/{pb.total} cases passed in the final run (hidden cases weigh {HIDDEN_CASE_WEIGHT_MULTIPLIER}x)."
        if (pb.visible_fraction is not None and pb.hidden_fraction is not None and pb.hidden_total >= OVERFIT_MIN_HIDDEN_CASES
                and pb.visible_fraction >= OVERFIT_VISIBLE_FULL and pb.hidden_fraction < OVERFIT_HIDDEN_MAX):
            flags.append(EvaluationFlag("PASSES_VISIBLE_FAILS_HIDDEN",
                                        "Passes every visible case but fails most hidden ones -- possible special-casing of the samples."))
            reasons.append("Passes visible cases but fails hidden ones (possible hard-coding).")

        e = metrics["efficiency"]
        if task.reference_runtime_ms is None:
            e.explanation = "Not assessed: no reference runtime for this task."
        else:
            runtimes = ([r.runtime_ms for r in final_run.results if r.passed and r.runtime_ms is not None]
                        if final_run is not None and not final_run.compile_error else [])
            timeouts = sum(1 for r in final_run.results if r.timed_out) if final_run is not None and not final_run.compile_error else 0
            e.assessed = True
            if not runtimes:
                e.score = 0.0
                e.explanation = "No passing case to measure, so no efficiency credit (fast and wrong earns nothing)."
            else:
                ratio = statistics.median(runtimes) / task.reference_runtime_ms
                raw = efficiency_from_ratio(ratio) * (1.0 - timeouts / max(1, len(task.cases)))
                e.score = round(raw * pass_fraction, 1)
                e.explanation = (f"Median passing runtime is {ratio:.1f}x the reference ({timeouts} timeout(s)); raw {raw:.0f}, "
                                 f"multiplied by pass fraction {pass_fraction:.2f}. Measured on the test inputs, not a complexity analysis.")

        q = metrics["code_quality"]
        code = snaps[-1].code if snaps else ""
        if task.language.lower() != "python":
            q.explanation = f"Not assessed: static quality analysis supports Python only (task language: {task.language})."
        elif not snaps:
            q.explanation = "Not assessed: no code snapshot was captured."
        else:
            result = analyze_python_quality(code)
            if not result.assessed:
                q.explanation = f"Not assessed: {result.note}"
                reasons.append("Final snapshot was too large to analyse.")
            else:
                q.assessed = True
                q.score = round(result.score * (QUALITY_FLOOR + (1.0 - QUALITY_FLOOR) * pass_fraction), 1)
                top = "; ".join(f"{f.code}" + (f"@{f.line}" if f.line else "") for f in result.findings[:5]) or "no findings"
                q.explanation = (f"Static analysis of the final snapshot (code never executed): {top}. Raw {result.score}, "
                                 f"counted at {QUALITY_FLOOR + (1.0 - QUALITY_FLOOR) * pass_fraction:.0%} because the solution passes {pass_fraction:.0%}.")
            for note in result.informational:
                flags.append(EvaluationFlag("SANDBOX_RELEVANT_API", note))
            if result.informational:
                reasons.append("Code uses process/network-capable APIs.")

        p = metrics["problem_solving"]
        approach = assess_problem_solving(attempt)
        if approach.assessed:
            p.assessed, p.score = True, approach.score
            p.explanation = "Process proxy from the timeline: " + " ".join(approach.signals)
        else:
            p.explanation = "Not assessed: " + approach.signals[0]

    # Time-based scoring (shared by every task type), gated by correctness.
    t = metrics["time"]
    taken = None
    if attempt.submitted_at is not None and not late:
        taken = attempt.submitted_at
    elif attempt.submitted_at is None and task.task_type is not MachineTestType.SYSTEM_DESIGN:
        stamps = [r.timestamp for r in runs] + [s.timestamp for s in snaps]
        taken = max(stamps) if stamps else None
    if late:
        t.assessed, t.score = True, 0.0
        t.explanation = "Submitted after the deadline: no time credit."
    elif taken is None:
        t.explanation = "Not assessed: no submission time is available."
    else:
        raw = time_score_raw(taken, attempt.deadline)
        t.assessed, t.score = True, round(raw * pass_fraction, 1)
        t.explanation = (f"Finished at {taken / attempt.deadline:.0%} of the time limit; raw {raw:.0f}, multiplied by pass fraction "
                         f"{pass_fraction:.2f} (fast and wrong earns nothing).")

    ordered = [metrics[n] for n in METRICS]
    _redistribute(ordered)
    task_score = round(sum((m.score or 0.0) * m.effective_weight for m in ordered), 1)
    return TaskEvaluation(task.task_id, task.task_type, task.difficulty, ordered, task_score, flags, bool(reasons), reasons)


# ---------------------------------------------------------------------------
# Whole-test report
# ---------------------------------------------------------------------------

NOT_IMPLEMENTED: Dict[str, str] = {
    "sandboxed_code_execution": "This engine never runs candidate code. Execution results must come from an isolated sandbox runner "
                                "(no network, CPU/memory/time limits, ephemeral filesystem) that does not exist yet.",
    "complexity_analysis": "Efficiency is measured runtime versus a reference on the test inputs; no big-O inference is done.",
    "plagiarism_or_ai_generated_code_detection": "Not attempted; similarity and authorship detection are separate, unvalidated problems.",
    "non_python_code_quality": "AST quality analysis supports Python only; other languages are not assessed and their weight is redistributed.",
    "screen_recording_and_paste_detection": "PRD Phases 67-68 evidence (screen capture, copy-paste events) is not built; it would extend Day 49's event model.",
}

CAVEATS: List[str] = [
    "Scores are only as good as the test cases: weak or leaky tests produce misleading correctness scores.",
    "Time is a weak signal of skill; it carries low weight, is gated by correctness, and scales with approved accommodations.",
    "The problem-solving score is a process proxy from run/snapshot behaviour, not a measure of reasoning.",
    "System-design scoring uses keywords and can be gamed; it always needs human review.",
    "Weights and thresholds are reasoned, not calibrated -- no labelled machine-test data exists.",
    "Candidates must consent to code and snapshot capture; consent infrastructure does not exist yet (Day 43 finding).",
    "Captured code can contain personal data; retention and access controls are not built.",
]


@dataclass
class MachineTestReport:
    tasks: List[TaskEvaluation]
    overall_score: float
    score_band: str
    integrity_risk_tag: Optional[str]
    human_review_required: bool
    human_review_reasons: List[str]
    capture_summary: Dict[str, Dict]
    automated_decision: str = "none"
    not_implemented: Dict[str, str] = field(default_factory=lambda: dict(NOT_IMPLEMENTED))
    caveats: List[str] = field(default_factory=lambda: list(CAVEATS))

    def to_dict(self) -> Dict:
        return {
            "overall_score": self.overall_score, "score_band": self.score_band,
            "integrity_risk_tag": self.integrity_risk_tag, "automated_decision": self.automated_decision,
            "human_review_required": self.human_review_required, "human_review_reasons": self.human_review_reasons,
            "tasks": [t.to_dict() for t in self.tasks], "capture_summary": self.capture_summary,
            "not_implemented": self.not_implemented, "caveats": self.caveats,
        }

    def to_summary_text(self) -> str:
        lines = [
            "Machine Test Evaluation Report (static analysis + sandbox results only; no code executed here)",
            "=" * 76,
            f"Overall: {self.overall_score}/100 ({self.score_band} band, difficulty-weighted)",
            f"Integrity tag (Day 49, informational): {self.integrity_risk_tag or 'not supplied'}",
            f"Automated decision: none. Human review required: {'YES' if self.human_review_required else 'no'}.",
        ]
        for t in self.tasks:
            lines.append(f"\n[{t.task_type.value}/{t.difficulty.value}] {t.task_id}: {t.task_score}/100")
            for m in t.metrics:
                if m.base_weight <= 0:
                    continue
                shown = f"{m.score}" if m.assessed else "not assessed"
                lines.append(f"  - {m.name} (w={m.effective_weight:.2f}): {shown}")
            for f in t.flags:
                lines.append(f"  ! {f.code}: {f.message}")
        if self.human_review_reasons:
            lines += ["", "Review reasons:"] + [f"  - {r}" for r in self.human_review_reasons]
        lines += ["", "Not implemented:"] + [f"  - {k}: {v}" for k, v in self.not_implemented.items()]
        return "\n".join(lines)


def _band(score: float) -> str:
    return "strong" if score >= BAND_STRONG else "moderate" if score >= BAND_MODERATE else "limited"


def build_machine_test_report(attempts: Sequence[TaskAttempt], integrity_risk_tag=None) -> MachineTestReport:
    """Evaluate every task and aggregate with difficulty weights.

    `integrity_risk_tag` may be Day 49's IntegrityRiskTag or its string value.
    It is carried through and can add a review requirement; it never changes a score."""
    if not attempts:
        raise ValueError("At least one task attempt is required.")
    evaluations = [evaluate_task(a) for a in attempts]
    weights = [DIFFICULTY_WEIGHT[e.difficulty] for e in evaluations]
    overall = round(sum(e.task_score * w for e, w in zip(evaluations, weights)) / sum(weights), 1)

    tag = getattr(integrity_risk_tag, "value", integrity_risk_tag)
    reasons: List[str] = []
    for e in evaluations:
        reasons += [f"{e.task_id}: {r}" for r in e.human_review_reasons]
    if tag in ("medium", "high"):
        reasons.append(f"Interview integrity tag is {str(tag).upper()} (Day 49): review the session before relying on this score.")

    return MachineTestReport(
        tasks=evaluations, overall_score=overall, score_band=_band(overall), integrity_risk_tag=tag,
        human_review_required=bool(reasons), human_review_reasons=reasons,
        capture_summary={a.task.task_id: a.capture_summary() for a in attempts},
    )
