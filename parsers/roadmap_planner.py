"""
Roadmap Planner (Day 58)

WHAT THIS IS. The Day 58 roadmap is data (`data/roadmap/day58_feature_backlog.json`), and this module is what keeps that data
honest. It loads the backlog, orders it, and VALIDATES it, so the roadmap cannot quietly contradict itself or the project's own
rules: a feature cannot be scheduled before the things it depends on, nothing that is legally prohibited or scientifically
contradicted can be scheduled, a restricted feature must carry guardrails, and every module a feature says it builds on must
actually exist in the repository.

WHAT IT IS NOT. It does not decide what is worth building. `value`, `effort` and `feasibility` (1-5) are the author's estimates,
a judgement and not a measurement, and `priority_score` is a transparent way to sort them, not a forecast. Legal status and
dates are taken from the cited sources as of Nov 2026 and are NOT legal advice.

PRIORITY SCORE = 2 * value + feasibility - effort   (range -2 .. 14). Value counts double because a cheap feature nobody needs
should not outrank an expensive one everybody does. Features without a phase ("not recommended") have no score.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)

LEGAL_STATUSES = ("allowed", "restricted", "prohibited_in_recruitment_eu")
EVIDENCE_LEVELS = ("established", "validated", "plausible", "unvalidated", "contradicted")
LAST_EARLY_PHASE_FOR_DEADLINES = 2


@dataclass
class Feature:
    id: str
    title: str
    area: str
    audience: str
    summary: str
    builds_on: List[str]
    depends_on: List[str]
    legal_status: str
    evidence: str
    affect_inference: bool
    value: int
    effort: int
    feasibility: int
    phase: Optional[int]
    deadline: Optional[str]
    guardrails: List[str]
    success_metric: Optional[str]
    decision_needed: bool
    source_ids: List[str]

    @property
    def scheduled(self) -> bool:
        return self.phase is not None

    @property
    def priority_score(self) -> Optional[int]:
        return 2 * self.value + self.feasibility - self.effort if self.scheduled else None


@dataclass
class Backlog:
    note: str
    sources: Dict[str, str]
    phases: List[Dict[str, Any]]
    features: List[Feature]

    def by_id(self) -> Dict[str, Feature]:
        return {f.id: f for f in self.features}


def load_backlog(path: str | Path = "data/roadmap/day58_feature_backlog.json") -> Backlog:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return Backlog(raw.get("_note", ""), raw["sources"], raw["phases"], [Feature(**f) for f in raw["features"]])


def _find_cycle(by_id: Dict[str, Feature]) -> Optional[List[str]]:
    state: Dict[str, int] = {}
    stack: List[str] = []

    def visit(n: str) -> Optional[List[str]]:
        state[n] = 1
        stack.append(n)
        for d in by_id[n].depends_on:
            if d not in by_id:
                continue
            if state.get(d) == 1:
                return stack[stack.index(d):] + [d]
            if state.get(d) is None:
                found = visit(d)
                if found:
                    return found
        stack.pop()
        state[n] = 2
        return None
    for n in by_id:
        if state.get(n) is None:
            found = visit(n)
            if found:
                return found
    return None


def validate_backlog(backlog: Backlog, repo_root: Optional[str | Path] = None) -> List[str]:
    """Every problem found, as readable sentences. An empty list means the backlog is internally consistent."""
    problems: List[str] = []
    ids = [f.id for f in backlog.features]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        problems.append(f"duplicate feature id {dup}")
    by_id = {f.id: f for f in backlog.features}
    phase_numbers = {p["phase"] for p in backlog.phases}

    for f in backlog.features:
        where = f"{f.id} ({f.title[:40]})"
        for field_name in ("value", "effort", "feasibility"):
            v = getattr(f, field_name)
            if not isinstance(v, int) or isinstance(v, bool) or not 1 <= v <= 5:
                problems.append(f"{where}: {field_name} must be an integer 1-5, got {v!r}")
        if f.legal_status not in LEGAL_STATUSES:
            problems.append(f"{where}: unknown legal_status {f.legal_status!r}")
        if f.evidence not in EVIDENCE_LEVELS:
            problems.append(f"{where}: unknown evidence level {f.evidence!r}")
        if f.phase is not None and f.phase not in phase_numbers:
            problems.append(f"{where}: phase {f.phase} is not a defined phase")
        for d in f.depends_on:
            if d not in by_id:
                problems.append(f"{where}: depends on unknown feature {d}")
            elif d == f.id:
                problems.append(f"{where}: depends on itself")
        for s in f.source_ids:
            if s not in backlog.sources:
                problems.append(f"{where}: cites unknown source {s}")
        # the project's own rules
        if f.legal_status == "prohibited_in_recruitment_eu" and f.scheduled:
            problems.append(f"{where}: is prohibited in recruitment in the EU and must not be scheduled")
        if f.evidence == "contradicted" and f.scheduled:
            problems.append(f"{where}: its evidence is contradicted and it must not be scheduled")
        if f.affect_inference and f.scheduled:
            problems.append(f"{where}: infers emotion and must not be scheduled")
        if (f.legal_status == "prohibited_in_recruitment_eu" or f.affect_inference) and not f.decision_needed:
            problems.append(f"{where}: an unscheduled legal/ethical exclusion must be flagged decision_needed for the product owner")
        if f.legal_status == "restricted" and f.scheduled and not f.guardrails:
            problems.append(f"{where}: is restricted and scheduled but has no guardrails")
        if f.scheduled and not f.success_metric:
            problems.append(f"{where}: is scheduled but has no success metric")
        if f.deadline and f.scheduled and f.phase > LAST_EARLY_PHASE_FOR_DEADLINES:
            problems.append(f"{where}: has a regulatory deadline but is scheduled in phase {f.phase}")
        if f.deadline and not f.scheduled:
            problems.append(f"{where}: has a regulatory deadline but is not scheduled")
        if f.evidence == "unvalidated" and f.scheduled and not f.guardrails:
            problems.append(f"{where}: unvalidated evidence needs guardrails or a validation gate")
        for dep_id in f.depends_on:
            dep = by_id.get(dep_id)
            if dep is None:
                continue
            if f.scheduled and not dep.scheduled:
                problems.append(f"{where}: scheduled but depends on {dep_id}, which is not scheduled")
            elif f.scheduled and dep.scheduled and dep.phase > f.phase:
                problems.append(f"{where}: in phase {f.phase} but depends on {dep_id} in later phase {dep.phase}")
        if repo_root is not None:
            for path in f.builds_on:
                if not (Path(repo_root) / path).exists():
                    problems.append(f"{where}: builds on {path}, which does not exist")
    cycle = _find_cycle(by_id)
    if cycle:
        problems.append("dependency cycle: " + " -> ".join(cycle))
    return problems


def build_order(backlog: Backlog) -> List[Feature]:
    """Scheduled features in an order that respects both phase and dependencies; ties broken by priority then id."""
    by_id = backlog.by_id()
    scheduled = [f for f in backlog.features if f.scheduled]
    done: List[str] = []
    ordered: List[Feature] = []
    pending = sorted(scheduled, key=lambda f: (f.phase, -f.priority_score, f.id))
    while pending:
        progressed = False
        for f in list(pending):
            if all(d in done or not by_id[d].scheduled for d in f.depends_on if d in by_id):
                ordered.append(f); done.append(f.id); pending.remove(f); progressed = True
                break
        if not progressed:
            raise ValueError("cannot order the backlog: " + ", ".join(f.id for f in pending))
    return ordered


def roadmap_by_phase(backlog: Backlog) -> Dict[int, List[Feature]]:
    out: Dict[int, List[Feature]] = {p["phase"]: [] for p in backlog.phases}
    for f in build_order(backlog):
        out[f.phase].append(f)
    return out


def not_recommended(backlog: Backlog) -> List[Feature]:
    return [f for f in backlog.features if not f.scheduled]


def render_markdown(backlog: Backlog) -> str:
    lines: List[str] = []
    by_phase = roadmap_by_phase(backlog)
    for p in backlog.phases:
        fs = by_phase[p["phase"]]
        lines.append(f"### Phase {p['phase']} - {p['name']}")
        lines.append(f"Exit gate (proposed): {p['exit_gate']}")
        if fs:
            lines.append("| ID | Feature | Value | Effort | Feasibility | Priority | Depends on |")
            lines.append("|---|---|---|---|---|---|---|")
            for f in fs:
                lines.append(f"| {f.id} | {f.title} | {f.value} | {f.effort} | {f.feasibility} | {f.priority_score} | {', '.join(f.depends_on) or '-'} |")
        lines.append("")
    lines.append("### Not recommended (decision needed)")
    for f in not_recommended(backlog):
        lines.append(f"* {f.id}: {f.title} [{f.legal_status}; evidence {f.evidence}]")
    return "\n".join(lines)
