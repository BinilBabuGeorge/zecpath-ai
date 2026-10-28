"""
Evaluation Harness (Day 54)

WHAT THIS IS: the reusable measuring tool behind Day 54's "analyze false
positives / negatives" and "improve scoring thresholds" tasks. Earlier
days each carried their own one-off confusion-matrix code (Day 17's
`run_day17_testing`, Day 30's screening test); this module is the single,
tested version, so every accuracy claim in the optimization report comes
from the same arithmetic.

WHAT IT DELIBERATELY DOES NOT DO: tune anything on its own. The project
has two small labelled datasets (12 ATS resume/job pairs, ~20 + 52
screening answers) and no hiring-outcome data. Searching thresholds on
sets that small is how you manufacture a number that looks like
improvement and is really memorisation, so this module is built around
the checks that expose that:

  - `wilson_interval`: an honest confidence interval for an accuracy
    measured on n cases ("83% of 12" is 55%-95%, not "83%").
  - `compare_runs`: separates cases a change FIXED from cases it newly
    BROKE, so a headline gain cannot hide a regression.
  - `sweep_parameters` / `plateau`: how many parameter settings tie for
    best. A wide plateau means the choice does not matter and the current
    value is safe; a single sharp peak means the value is fitted to the
    data.
  - `leave_one_out`: re-picks the parameters with each case held out and
    scores the held-out case. The gap between in-sample accuracy and
    leave-one-out accuracy is the over-fitting the in-sample number hides.
  - `cost_weighted_error`: false positives and false negatives are rarely
    equally costly (wrongly rejecting a good candidate is worse than
    wrongly reviewing a weak one); this makes the asymmetry explicit.

All functions are pure and deterministic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Hashable, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Basic statistics
# ---------------------------------------------------------------------------

def wilson_interval(successes: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    """Wilson score interval for a proportion. Far better behaved than the normal
    approximation for the small n and extreme proportions this project deals in.
    Returns (0.0, 1.0) when n is 0 (nothing is known)."""
    if n < 0 or successes < 0 or successes > n:
        raise ValueError("Need 0 <= successes <= n.")
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


# ---------------------------------------------------------------------------
# Classification evaluation
# ---------------------------------------------------------------------------

@dataclass
class ClassMetrics:
    precision: float
    recall: float
    f1: float
    support: int
    false_positives: int      # predicted this class, truly something else
    false_negatives: int      # truly this class, predicted something else

    def to_dict(self) -> Dict[str, Any]:
        return {"precision": round(self.precision, 3), "recall": round(self.recall, 3), "f1": round(self.f1, 3),
                "support": self.support, "false_positives": self.false_positives, "false_negatives": self.false_negatives}


@dataclass
class EvaluationResult:
    n: int
    correct: int
    accuracy: float
    accuracy_ci: Tuple[float, float]
    confusion: Dict[str, Dict[str, int]]                # confusion[true][predicted]
    per_class: Dict[str, ClassMetrics]
    errors: List[Dict[str, Any]]                        # {"id", "true", "predicted"}

    def to_dict(self) -> Dict[str, Any]:
        return {"n": self.n, "correct": self.correct, "accuracy": round(self.accuracy, 4),
                "accuracy_ci_95": [round(self.accuracy_ci[0], 3), round(self.accuracy_ci[1], 3)],
                "confusion": self.confusion, "per_class": {k: v.to_dict() for k, v in self.per_class.items()},
                "errors": self.errors}


def evaluate_predictions(
    y_true: Sequence[str], y_pred: Sequence[str], labels: Optional[Sequence[str]] = None, ids: Optional[Sequence[Hashable]] = None,
) -> EvaluationResult:
    """Accuracy, a confusion matrix, per-class precision / recall / F1 and the list of errors."""
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have the same length.")
    if ids is not None and len(ids) != len(y_true):
        raise ValueError("ids must match y_true in length.")
    classes = list(labels) if labels is not None else sorted(set(y_true) | set(y_pred))
    missing = (set(y_true) | set(y_pred)) - set(classes)
    if missing:
        raise ValueError(f"Labels not in the declared label set: {sorted(missing)}")

    confusion = {t: {p: 0 for p in classes} for t in classes}
    errors: List[Dict[str, Any]] = []
    for i, (t, p) in enumerate(zip(y_true, y_pred)):
        confusion[t][p] += 1
        if t != p:
            errors.append({"id": ids[i] if ids is not None else i, "true": t, "predicted": p})

    n = len(y_true)
    correct = n - len(errors)
    per_class: Dict[str, ClassMetrics] = {}
    for c in classes:
        tp = confusion[c][c]
        fp = sum(confusion[t][c] for t in classes if t != c)
        fn = sum(confusion[c][p] for p in classes if p != c)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        per_class[c] = ClassMetrics(precision, recall, f1, tp + fn, fp, fn)
    return EvaluationResult(n, correct, (correct / n) if n else 0.0, wilson_interval(correct, n), confusion, per_class, errors)


# ---------------------------------------------------------------------------
# Comparing two runs: what a change fixed, and what it broke
# ---------------------------------------------------------------------------

@dataclass
class RunComparison:
    fixed: List[Hashable]
    newly_broken: List[Hashable]
    still_wrong: List[Hashable]
    still_right: List[Hashable]

    @property
    def net_change(self) -> int:
        return len(self.fixed) - len(self.newly_broken)

    def to_dict(self) -> Dict[str, Any]:
        return {"fixed": self.fixed, "newly_broken": self.newly_broken, "still_wrong": self.still_wrong,
                "still_right": len(self.still_right), "net_change": self.net_change}


def compare_runs(truth: Dict[Hashable, str], before: Dict[Hashable, str], after: Dict[Hashable, str]) -> RunComparison:
    """Per-case comparison of two sets of predictions against the same truth. A headline accuracy gain
    can hide a regression; this lists both sides."""
    if not (set(truth) == set(before) == set(after)):
        raise ValueError("truth, before and after must cover exactly the same cases.")
    fixed, broken, wrong, right = [], [], [], []
    for k in truth:
        was, now = before[k] == truth[k], after[k] == truth[k]
        (right if was and now else broken if was and not now else fixed if now else wrong).append(k)
    return RunComparison(fixed, broken, wrong, right)


# ---------------------------------------------------------------------------
# Asymmetric error cost
# ---------------------------------------------------------------------------

def cost_weighted_error(y_true: Sequence[str], y_pred: Sequence[str], costs: Dict[Tuple[str, str], float], default_cost: float = 1.0) -> float:
    """Mean cost per case. `costs[(true, predicted)]` overrides `default_cost` (applied to any error not listed);
    a correct prediction always costs 0."""
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have the same length.")
    if not y_true:
        return 0.0
    return sum(0.0 if t == p else costs.get((t, p), default_cost) for t, p in zip(y_true, y_pred)) / len(y_true)


# ---------------------------------------------------------------------------
# Parameter sweeps, plateaus and leave-one-out
# ---------------------------------------------------------------------------

Params = Dict[str, float]
ClassifyFn = Callable[[Any, Params], str]


@dataclass
class SweepPoint:
    params: Params
    correct: int
    n: int

    @property
    def accuracy(self) -> float:
        return self.correct / self.n if self.n else 0.0


def param_grid(**axes: Sequence[float]) -> List[Params]:
    """Cartesian product of named axes, in a deterministic order."""
    grid: List[Params] = [{}]
    for name in sorted(axes):
        grid = [{**g, name: v} for g in grid for v in axes[name]]
    return grid


def sweep_parameters(items: Sequence[Any], truth: Sequence[str], classify: ClassifyFn, grid: Sequence[Params]) -> List[SweepPoint]:
    """Accuracy of `classify(item, params)` at every grid point."""
    if len(items) != len(truth):
        raise ValueError("items and truth must have the same length.")
    return [SweepPoint(dict(p), sum(1 for it, t in zip(items, truth) if classify(it, p) == t), len(items)) for p in grid]


def plateau(points: Sequence[SweepPoint]) -> List[SweepPoint]:
    """Every grid point that ties for the best accuracy."""
    if not points:
        return []
    best = max(p.correct for p in points)
    return [p for p in points if p.correct == best]


def _central(points: Sequence[SweepPoint]) -> SweepPoint:
    """Deterministic, unbiased tie-break: the point whose parameter values are closest to the plateau's mean."""
    names = sorted(points[0].params)
    means = {n: sum(p.params[n] for p in points) / len(points) for n in names}
    return min(points, key=lambda p: (sum((p.params[n] - means[n]) ** 2 for n in names), tuple(p.params[n] for n in names)))


@dataclass
class LeaveOneOutResult:
    n: int
    in_sample_correct: int
    leave_one_out_correct: int
    per_case: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def in_sample_accuracy(self) -> float:
        return self.in_sample_correct / self.n if self.n else 0.0

    @property
    def leave_one_out_accuracy(self) -> float:
        return self.leave_one_out_correct / self.n if self.n else 0.0

    @property
    def optimism(self) -> float:
        """In-sample accuracy minus leave-one-out accuracy: how much of the headline number is memorisation."""
        return self.in_sample_accuracy - self.leave_one_out_accuracy

    def to_dict(self) -> Dict[str, Any]:
        return {"n": self.n, "in_sample_accuracy": round(self.in_sample_accuracy, 4),
                "leave_one_out_accuracy": round(self.leave_one_out_accuracy, 4), "optimism": round(self.optimism, 4),
                "leave_one_out_ci_95": [round(x, 3) for x in wilson_interval(self.leave_one_out_correct, self.n)]}


def leave_one_out(items: Sequence[Any], truth: Sequence[str], classify: ClassifyFn, grid: Sequence[Params]) -> LeaveOneOutResult:
    """For each case: pick the best parameters on all the OTHER cases, then score the held-out one. The
    in-sample figure uses the best parameters on all cases."""
    n = len(items)
    if n < 2:
        raise ValueError("Leave-one-out needs at least two cases.")
    full = plateau(sweep_parameters(items, truth, classify, grid))
    in_sample = full[0].correct if full else 0
    hits, per_case = 0, []
    for i in range(n):
        rest_items = [x for j, x in enumerate(items) if j != i]
        rest_truth = [t for j, t in enumerate(truth) if j != i]
        chosen = _central(plateau(sweep_parameters(rest_items, rest_truth, classify, grid)))
        predicted = classify(items[i], chosen.params)
        hits += predicted == truth[i]
        per_case.append({"index": i, "true": truth[i], "predicted": predicted, "chosen_params": chosen.params})
    return LeaveOneOutResult(n, in_sample, hits, per_case)
