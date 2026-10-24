"""
Hiring Intelligence Report Generator (Day 53)

WHAT THIS DAY BUILDS: Days 13-52 produce a lot of structured data -- ATS
components, screening scores, HR and technical results, a machine-test
report, behavioral and integrity signals, an aggregate score (Day 51) and
a recommendation (Day 52) -- but a recruiter cannot read any of it in
under a minute. This module is the final translation layer: it takes
those result objects and assembles ONE recruiter-facing report with the
five insight areas the brief names (ATS summary, screening results, HR
insights, technical performance, behavioral flags) and the four
highlights (strengths, weaknesses, risk indicators, final
recommendation), in a format built to be skimmed first and studied second.

REUSE, NOT RECOMPUTATION: the recommendation, hiring fit, confidence,
rule trace, risk factors and review reasons are READ from Day 52's
`CandidateDecision` and Day 51's `CrossRoundCandidateScore`; this module
never re-decides anything. If the two do not belong together (different
candidate, or a fit that does not match), it raises rather than printing
a report whose pieces disagree. Day 31's `ScreeningReport` and Day 39's
`InterviewSummaryReport` are optional extras: when supplied, their
highlights and strengths/weaknesses are used instead of being re-derived.

TEXT GENERATION, STATED HONESTLY: like Day 39, "AI-generated" here means
TEMPLATE-BASED sentences chosen by score band -- deterministic and
rule-based. There is no language model anywhere in this project and this
day does not add one. Every strength, weakness and risk indicator carries
its source round, the metric, the score and a short evidence string, so
a recruiter can see where each statement came from; nothing is asserted
without a number behind it.

DESIGN CHOICES FOR A RECRUITER:
  1. One-screen executive summary first: recommendation, fit, confidence,
     top strengths, top concerns, evidence coverage, next step.
  2. Missing evidence is shown as "not yet available", never as a zero.
  3. Strengths (score >= 75) and weaknesses (score < 50) are capped at
     three per source and sorted by how extreme they are, so the report
     stays digestible.
  4. Risk indicators carry a severity (high / medium / low / info) and
     are sorted worst-first. Behavioral timing signals are weak evidence
     and are capped at LOW severity; verbal hesitation is displayed with
     the note that the decision does not use it (Day 52's fairness choice).
  5. The report carries what it can and cannot tell you: limitations,
     not-implemented items and caveats are part of every export.
  6. It is marked CONFIDENTIAL -- RECRUITER USE ONLY. It is not a
     candidate-facing document (Day 52's candidate notices are).
  7. It contains scores and short evidence only -- no transcripts, no
     answers, and no demographic fields exist in its data model.

EXPORT-READY: one internal document model is rendered to three formats so
they cannot drift apart -- JSON (stable, versioned schema), Markdown, and
a self-contained HTML page (no scripts, no external resources, print
stylesheet for A4). PDF is produced by printing the HTML to PDF from any
browser; native PDF generation is NOT built (it would add a library
dependency this project does not have). All candidate-derived text is
escaped for the target format, so a hostile skill name or candidate id
cannot inject markup. A content fingerprint (a hash of the report
contents, excluding the timestamp) identifies a report; it is not a
digital signature.

PREVIEW VIEW: `to_preview_dict()` returns only the basic outcome and
score, shaped for the PRD's pay-to-unlock model (Phases 23 / 48 / 73 /
100). Enforcing that access, and payment, are NOT built.

HONESTY: thresholds (75 / 50), severity mapping and wording are reasoned,
not validated with recruiters; no usability testing of the format has
been done; the report inherits every upstream limit (for example the
machine-test round rests on a sandbox that does not exist yet).
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from parsers.cross_round_aggregation_engine import ROUND_NAMES, CrossRoundCandidateScore, RoundStatus
from parsers.final_recommendation_engine import CandidateDecision, DecisionOutcome, HoldKind

REPORT_SCHEMA_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Configuration -- reasoned, not validated with recruiters
# ---------------------------------------------------------------------------

STRENGTH_MIN = 75.0
WEAKNESS_MAX = 50.0
MAX_FINDINGS_PER_SOURCE = 3
SUMMARY_TOP_N = 3
MAX_LISTED_SKILLS = 8
MAX_LISTED_FINDINGS = 8          # rows shown per strengths/weaknesses table in Markdown/HTML; JSON keeps all

ROUND_TITLES: Dict[str, str] = {
    "ats": "ATS resume match",
    "screening": "Screening call",
    "hr_interview": "HR interview",
    "technical_interview": "Technical interview",
    "machine_test": "Machine test",
}

OUTCOME_LABELS: Dict[DecisionOutcome, str] = {
    DecisionOutcome.SELECTED: "SELECTED (recommended)",
    DecisionOutcome.HOLD_REVIEW: "HOLD / REVIEW",
    DecisionOutcome.REJECTED: "REJECTION RECOMMENDED (needs human confirmation)",
}

HOLD_LABELS: Dict[HoldKind, str] = {
    HoldKind.PENDING_EVIDENCE: "waiting on remaining rounds",
    HoldKind.MID_SCORE: "score is in the review band",
    HoldKind.SELECTION_BLOCKED: "score would select, but a flagged item needs review first",
    HoldKind.INSUFFICIENT_EVIDENCE_TO_REJECT: "score is low but evidence is too weak to recommend rejection",
}

CONFIDENTIALITY_NOTICE = "CONFIDENTIAL -- RECRUITER USE ONLY. Not for sharing with the candidate."

LIMITATIONS: List[str] = [
    "This is decision support. The recommendation is advice for a recruiter; nothing is rejected without a named person confirming it.",
    "Strengths, weaknesses and risk indicators are rule-based (score thresholds), not written by a language model.",
    "Thresholds and weights are reasoned, not calibrated; no hiring-outcome data exists to validate them.",
    "A confidence value measures how robust the evidence is, not how likely the candidate is to succeed.",
    "The report is only as trustworthy as its weakest round (for example, machine-test results still depend on a sandbox that has not been built).",
    "Behavioral timing signals are weak evidence and never change a recommendation by themselves.",
    "No bias audit of these recommendations by group has been done.",
]

NOT_IMPLEMENTED: Dict[str, str] = {
    "native_pdf_export": "Print the HTML export to PDF from a browser; native PDF generation is not built.",
    "access_control_and_payment": "The preview view exists, but enforcing pay-to-unlock access (PRD Phases 23/48/73/100) is not built.",
    "recruiter_usability_testing": "The layout has not been tested with real recruiters.",
    "report_delivery_and_storage": "Reports are generated as data and files; delivery, storage and audit logging are not built.",
    "bias_audit": "No disparate-impact analysis of the recommendations has been done.",
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class FindingKind(str, Enum):
    STRENGTH = "strength"
    WEAKNESS = "weakness"


class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


_SEVERITY_ORDER = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2, Severity.INFO: 3}


@dataclass
class Finding:
    kind: FindingKind
    source: str            # round name
    area: str              # the metric / skill / component
    score: float           # 0-100
    evidence: str          # short, template-built

    def to_dict(self) -> Dict:
        return {"kind": self.kind.value, "source": self.source, "area": self.area, "score": self.score, "evidence": self.evidence}


@dataclass
class RiskIndicator:
    severity: Severity
    category: str          # integrity | behavior | evidence | consistency | scoring | machine_test | confidence
    message: str
    source: str

    def to_dict(self) -> Dict:
        return {"severity": self.severity.value, "category": self.category, "message": self.message, "source": self.source}


@dataclass
class RoundSection:
    round_name: str
    title: str
    status: str                    # scored | missing | not_applicable
    score: Optional[float]
    effective_weight: float
    contribution: float
    headline: str
    key_facts: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {"round_name": self.round_name, "title": self.title, "status": self.status, "score": self.score,
                "effective_weight": round(self.effective_weight, 4), "contribution": self.contribution,
                "headline": self.headline, "key_facts": self.key_facts, "notes": self.notes}


@dataclass
class HiringIntelligenceReport:
    """The full candidate AI profile report (Day 53 deliverable)."""
    schema_version: str
    report_id: str
    generated_at: str
    candidate_id: Optional[str]
    candidate_label: str
    role_title: Optional[str]
    role_type: str
    experience_level: str
    recommendation: Dict[str, Any]
    executive_summary: List[str]
    strengths: List[Finding]
    weaknesses: List[Finding]
    risk_indicators: List[RiskIndicator]
    rounds: List[RoundSection]
    behavioral_flags: List[str]
    score_breakdown: Dict[str, Any]
    screening_highlights: Dict[str, List[str]]
    rule_trace: List[Dict[str, Any]]
    about: Dict[str, Any]
    confidentiality: str = CONFIDENTIALITY_NOTICE

    # -- structured views ----------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version, "report_id": self.report_id, "generated_at": self.generated_at,
            "confidentiality": self.confidentiality,
            "candidate": {"id": self.candidate_id, "label": self.candidate_label, "role_title": self.role_title,
                          "role_type": self.role_type, "experience_level": self.experience_level},
            "recommendation": self.recommendation, "executive_summary": self.executive_summary,
            "strengths": [f.to_dict() for f in self.strengths], "weaknesses": [f.to_dict() for f in self.weaknesses],
            "risk_indicators": [r.to_dict() for r in self.risk_indicators],
            "rounds": [r.to_dict() for r in self.rounds], "behavioral_flags": self.behavioral_flags,
            "score_breakdown": self.score_breakdown, "screening_highlights": self.screening_highlights,
            "rule_trace": self.rule_trace, "about": self.about,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def to_preview_dict(self) -> Dict[str, Any]:
        """Basic outcome and score only -- the shape the PRD's pay-to-unlock model asks for.
        Enforcing access is not built."""
        return {
            "schema_version": self.schema_version, "report_id": self.report_id, "candidate_id": self.candidate_id,
            "outcome": self.recommendation["outcome"], "hiring_fit_percentage": self.recommendation["hiring_fit_percentage"],
            "access_level": "preview", "note": "Full report (strengths, weaknesses, risks, round detail) requires unlocking.",
        }

    # -- rendered views --------------------------------------------------------
    def to_markdown(self) -> str:
        return _render_markdown(_build_blocks(self))

    def to_html(self) -> str:
        return _render_html(self, _build_blocks(self))

    def to_text_summary(self) -> str:
        """The executive summary alone, as plain text (for an email or chat preview)."""
        return "\n".join(self.executive_summary)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _fmt(x: float) -> str:
    return f"{x:g}"


def _skills(names: Sequence[str]) -> str:
    shown = list(names)[:MAX_LISTED_SKILLS]
    more = len(names) - len(shown)
    return ", ".join(shown) + (f" (+{more} more)" if more > 0 else "")


def _classify(source: str, area: str, score: float, evidence: str) -> Optional[Finding]:
    if score >= STRENGTH_MIN:
        return Finding(FindingKind.STRENGTH, source, area, round(score, 1), evidence)
    if score < WEAKNESS_MAX:
        return Finding(FindingKind.WEAKNESS, source, area, round(score, 1), evidence)
    return None


def _cap(findings: List[Finding]) -> List[Finding]:
    """At most MAX_FINDINGS_PER_SOURCE of each kind, most extreme first."""
    strengths = sorted((f for f in findings if f.kind is FindingKind.STRENGTH), key=lambda f: (-f.score, f.area))
    weaknesses = sorted((f for f in findings if f.kind is FindingKind.WEAKNESS), key=lambda f: (f.score, f.area))
    return strengths[:MAX_FINDINGS_PER_SOURCE] + weaknesses[:MAX_FINDINGS_PER_SOURCE]


# ---------------------------------------------------------------------------
# Round extractors: key facts + findings + risk indicators from the real result objects
# ---------------------------------------------------------------------------

def _from_ats(ats) -> Tuple[List[str], List[Finding], List[RiskIndicator], List[str]]:
    facts, findings, risks, notes = [], [], [], []
    facts.append(f"Role category used for weighting: {ats.role_category}.")
    for c in ats.components:
        if not c.available:
            facts.append(f"{c.name}: not available ({c.details.get('reason', 'no data')}).")
            continue
        facts.append(f"{c.name}: {_fmt(c.score)}/100 (effective weight {c.effective_weight:.0%}).")
        evidence = f"{c.name} component scored {_fmt(c.score)}/100"
        if c.name == "skill_match" and "required_count" in c.details:
            evidence = f"Matched {c.details['matched_count']} of {c.details['required_count']} required skills"
            if c.details.get("missing_skills"):
                evidence += f"; missing: {_skills(c.details['missing_skills'])}"
            if c.details.get("matched_skills"):
                facts.append(f"Matched skills: {_skills(c.details['matched_skills'])}.")
            if c.details.get("missing_skills"):
                facts.append(f"Missing skills: {_skills(c.details['missing_skills'])}.")
        f = _classify("ats", c.name, c.score, evidence)
        if f:
            findings.append(f)
    notes += list(ats.missing_data_notes)
    return facts, findings, risks, notes


def _from_screening(screening) -> Tuple[List[str], List[Finding], List[RiskIndicator], List[str]]:
    facts, findings, risks, notes = [], [], [], []
    facts.append(f"{len(screening.question_scores)} screening answer(s) scored; overall {_fmt(screening.total_score)}/100.")
    by_category: Dict[str, List[float]] = {}
    for q in screening.question_scores:
        by_category.setdefault(q.question_category, []).append(q.weighted_total)
    for category, values in sorted(by_category.items()):
        avg = sum(values) / len(values)
        facts.append(f"{category}: {_fmt(round(avg, 1))}/100.")
        f = _classify("screening", category, avg, f"Screening answer on '{category}' scored {_fmt(round(avg, 1))}/100")
        if f:
            findings.append(f)
    for finding in screening.consistency_findings[:MAX_FINDINGS_PER_SOURCE]:
        risks.append(RiskIndicator(Severity.LOW, "consistency", f"Screening consistency: {finding}", "screening"))
    return facts, findings, risks, notes


def _from_hr(hr, interview_summary) -> Tuple[List[str], List[Finding], List[RiskIndicator], List[str]]:
    facts, findings, risks, notes = [], [], [], []
    facts.append(f"{hr.num_questions_answered} HR answer(s) scored; overall {_fmt(hr.overall_hr_score)}/100.")
    facts.append(f"Average relevance {_fmt(hr.avg_relevance)}, communication {_fmt(hr.avg_communication)}, confidence {_fmt(hr.avg_confidence)} (each /100).")
    facts.append(f"Answer-consistency issue rate: {hr.consistency.issue_rate:.0%}.")
    if interview_summary is not None:
        for s in interview_summary.strengths:
            findings.append(Finding(FindingKind.STRENGTH, "hr_interview", s.component, round(s.score, 1), s.note))
        for w in interview_summary.weaknesses:
            findings.append(Finding(FindingKind.WEAKNESS, "hr_interview", w.component, round(w.score, 1), w.note))
        facts.append(f"Interview summary band: {interview_summary.performance_band}.")
        notes.append(f"Culture-fit indicator ({interview_summary.cultural_fit.band}): {interview_summary.cultural_fit.note}")
        for flag in interview_summary.risk_flags:
            risks.append(RiskIndicator(Severity.LOW, "consistency", f"{flag.label}: {flag.detail}", "hr_interview"))
    else:
        for area, value in (("relevance", hr.avg_relevance), ("communication", hr.avg_communication), ("confidence", hr.avg_confidence)):
            f = _classify("hr_interview", area, value, f"Average {area} across HR answers: {_fmt(value)}/100")
            if f:
                findings.append(f)
    for finding in hr.consistency.findings[:MAX_FINDINGS_PER_SOURCE]:
        risks.append(RiskIndicator(Severity.LOW, "consistency", f"HR answers: {finding}", "hr_interview"))
    return facts, findings, risks, notes


def _from_technical(technical) -> Tuple[List[str], List[Finding], List[RiskIndicator], List[str]]:
    facts, findings, risks, notes = [], [], [], []
    facts.append(f"{len(technical.answer_evaluations)} technical answer(s) scored; overall {_fmt(technical.overall_score)}/100.")
    for skill, value in sorted(technical.skill_breakdown.items()):
        facts.append(f"{skill}: {_fmt(value)}/100.")
        f = _classify("technical_interview", skill, value, f"Skill '{skill}' scored {_fmt(value)}/100 across the technical answers")
        if f:
            findings.append(f)
    counts: Dict[str, int] = {}
    for e in technical.answer_evaluations:
        key = getattr(e.classification, "value", str(e.classification))
        counts[key] = counts.get(key, 0) + 1
    if counts:
        facts.append("Answer depth: " + ", ".join(f"{n} {k}" for k, n in sorted(counts.items())) + ".")
        total = sum(counts.values())
        if counts.get("shallow", 0) / total > 0.5:          # a MAJORITY of shallow answers; keeps the score strictly below the weakness bar
            findings.append(Finding(FindingKind.WEAKNESS, "technical_interview", "answer_depth",
                                    round(100.0 * (1 - counts["shallow"] / total), 1),
                                    f"{counts['shallow']} of {total} technical answers were shallow"))
    return facts, findings, risks, notes


_MACHINE_FLAG_SEVERITY = {
    "PASSES_VISIBLE_FAILS_HIDDEN": Severity.MEDIUM, "SANDBOX_RELEVANT_API": Severity.LOW, "DESIGN_PROXY_SCORING": Severity.LOW,
    "DESIGN_TOO_SHORT": Severity.LOW, "LATE_SUBMISSION": Severity.LOW, "EVIDENCE_AFTER_DEADLINE_IGNORED": Severity.INFO,
}


def _from_machine_test(report) -> Tuple[List[str], List[Finding], List[RiskIndicator], List[str]]:
    facts, findings, risks, notes = [], [], [], []
    facts.append(f"{len(report.tasks)} task(s); overall {_fmt(report.overall_score)}/100 ({report.score_band} band, difficulty-weighted).")
    for t in report.tasks:
        facts.append(f"{t.task_id} ({t.task_type.value}, {t.difficulty.value}): {_fmt(t.task_score)}/100.")
        for m in t.metrics:
            if m.base_weight <= 0:
                continue
            if not m.assessed:
                facts.append(f"{t.task_id} / {m.name}: not assessed.")
                continue
            f = _classify("machine_test", f"{t.task_id}: {m.name}", m.score, f"{m.name} on '{t.task_id}' scored {_fmt(m.score)}/100")
            if f:
                findings.append(f)
        for flag in t.flags:
            risks.append(RiskIndicator(_MACHINE_FLAG_SEVERITY.get(flag.code, Severity.LOW), "machine_test",
                                       f"{t.task_id}: {flag.message}", "machine_test"))
    notes.append("Execution results come from a sandbox runner that does not exist yet; treat machine-test scores as provisional in a real deployment.")
    return facts, findings, risks, notes


# ---------------------------------------------------------------------------
# Behavioral flags (Day 48 + Day 49), as the recruiter should read them
# ---------------------------------------------------------------------------

def _behavioral_flags(decision: CandidateDecision, behavior, integrity) -> List[str]:
    lines: List[str] = []
    if behavior is not None:
        lines.append(f"Response-time spikes: {behavior.distraction.spike_count} (pacing consistency {_fmt(behavior.focus.focus_level_score)}/100).")
        lines.append(f"Verbal hesitation: {_fmt(behavior.verbal_hesitation.average_hesitation_rate_per_100_words)} per 100 words -- "
                     "shown for information only and NOT used in the recommendation (it penalises nervous and non-native speakers).")
    if integrity is not None:
        flags = ", ".join(f.code for f in integrity.flags) or "none"
        lines.append(f"Interview integrity tag: {integrity.risk_tag.value.upper()} (browser-event flags: {flags}).")
    for rf in decision.risk_factors:
        if rf.category == "integrity" and integrity is None:
            lines.append(f"Interview integrity tag: {rf.level.upper()}.")
        if rf.category == "behavior" and behavior is None:
            lines.append(f"Behavioral timing level: {rf.level} ({rf.detail}).")
    lines.append("Behavioral timing signals are weak evidence: they can lower confidence but never change a recommendation by themselves.")
    return lines


def _risk_indicators(decision: CandidateDecision, score: CrossRoundCandidateScore, round_risks: List[RiskIndicator]) -> List[RiskIndicator]:
    risks: List[RiskIndicator] = list(round_risks)
    for rf in decision.risk_factors:
        if rf.category == "integrity" and rf.level in ("low", "medium", "high"):
            sev = {"high": Severity.HIGH, "medium": Severity.MEDIUM, "low": Severity.LOW}[rf.level]
            risks.append(RiskIndicator(sev, "integrity", f"Interview integrity tag {rf.level.upper()}" + (f" ({rf.detail})" if rf.detail else "")
                                       + "; a reviewer should look at the session.", "integrity"))
        elif rf.category == "behavior" and rf.level in ("low", "medium"):
            risks.append(RiskIndicator(Severity.LOW if rf.level == "medium" else Severity.INFO, "behavior",
                                       f"Behavioral timing signals ({rf.level}): " + rf.detail.split("; ")[0] + ". Weak evidence; lowers confidence only.",
                                       "behavior"))
    for flag in score.flags:
        if flag.code == "MISSING_ROUNDS":
            risks.append(RiskIndicator(Severity.MEDIUM, "evidence", flag.message, "aggregate"))
        elif flag.code == "ROUND_DISAGREEMENT":
            risks.append(RiskIndicator(Severity.MEDIUM, "scoring", flag.message + " An average hides this.", "aggregate"))
        elif flag.code == "BORDERLINE":
            risks.append(RiskIndicator(Severity.LOW, "scoring", flag.message, "aggregate"))
        elif flag.code == "ROUND_NOT_APPLICABLE_IGNORED":
            risks.append(RiskIndicator(Severity.INFO, "scoring", flag.message, "aggregate"))
    if decision.confidence.band == "low":
        risks.append(RiskIndicator(Severity.MEDIUM, "confidence", f"Confidence in this recommendation is low ({_fmt(decision.confidence.score)}/100).", "decision"))
    seen, unique = set(), []
    for r in sorted(risks, key=lambda r: (_SEVERITY_ORDER[r.severity], r.category, r.message)):
        if (r.category, r.message) not in seen:
            seen.add((r.category, r.message))
            unique.append(r)
    return unique


# ---------------------------------------------------------------------------
# Recommendation block and next steps
# ---------------------------------------------------------------------------

def _next_steps(decision: CandidateDecision) -> List[str]:
    if decision.outcome is DecisionOutcome.SELECTED:
        steps = ["Confirm the selection and move the candidate to the next stage."]
    elif decision.outcome is DecisionOutcome.REJECTED:
        steps = ["Confirm or override this recommendation: it is advice, and nothing is rejected automatically.",
                 "Until you confirm, the candidate sees only 'under review'."]
    elif decision.hold_kind is HoldKind.PENDING_EVIDENCE:
        steps = ["Wait for the remaining round(s) before deciding; a provisional score is not comparable with a complete one."]
    elif decision.hold_kind is HoldKind.MID_SCORE:
        steps = ["Use recruiter judgement: a mid score is neither a yes nor a no. Weigh the strengths and weaknesses below."]
    elif decision.hold_kind is HoldKind.SELECTION_BLOCKED:
        steps = ["Review the flagged items under Risk indicators before advancing this candidate."]
    else:
        steps = ["The evidence is too weak to support a rejection; review the rounds before deciding."]
    return steps + list(decision.what_would_change)


def _recommendation_block(decision: CandidateDecision, score: CrossRoundCandidateScore) -> Dict[str, Any]:
    return {
        "outcome": decision.outcome.value, "outcome_label": OUTCOME_LABELS[decision.outcome],
        "hold_kind": decision.hold_kind.value if decision.hold_kind else None,
        "hold_explanation": HOLD_LABELS[decision.hold_kind] if decision.hold_kind else None,
        "score_band": decision.score_band.value, "hiring_fit_percentage": decision.hiring_fit_percentage,
        "confidence_score": decision.confidence.score, "confidence_band": decision.confidence.band,
        "evidence_coverage": round(decision.evidence_coverage, 4), "requires_human_confirmation": decision.requires_human_confirmation,
        "reasons": list(decision.reasons), "next_steps": _next_steps(decision),
        "automated_action": decision.automated_action,
    }


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def _diverse_top(findings: List[Finding], n: int, strongest_first: bool) -> List[Finding]:
    """Top-n for the executive summary, preferring BREADTH: the best item from each round first, then the
    next best overall. Otherwise one chatty round (e.g. the machine test) fills the whole summary."""
    key = (lambda f: (-f.score, f.source, f.area)) if strongest_first else (lambda f: (f.score, f.source, f.area))
    ordered = sorted(findings, key=key)
    picked: List[Finding] = []
    seen = set()
    for f in ordered:
        if f.source not in seen and len(picked) < n:
            picked.append(f)
            seen.add(f.source)
    for f in ordered:
        if len(picked) >= n:
            break
        if f not in picked:
            picked.append(f)
    return sorted(picked, key=key)


def _executive_summary(label: str, role_title: Optional[str], decision: CandidateDecision, strengths: List[Finding],
                       weaknesses: List[Finding], risks: List[RiskIndicator], score: CrossRoundCandidateScore, steps: List[str]) -> List[str]:
    fit = "n/a" if decision.hiring_fit_percentage is None else f"{decision.hiring_fit_percentage}%"
    kind = f" ({HOLD_LABELS[decision.hold_kind]})" if decision.hold_kind else ""
    lines = [f"{label}{' -- ' + role_title if role_title else ''}: {OUTCOME_LABELS[decision.outcome]}{kind}. "
             f"Hiring Fit {fit}, confidence {_fmt(decision.confidence.score)}/100 ({decision.confidence.band})."]
    if decision.reasons:
        lines.append("Why: " + decision.reasons[0])
    top_s = _diverse_top(strengths, SUMMARY_TOP_N, strongest_first=True)
    lines.append("Strongest areas: " + ("; ".join(f"{f.area} ({_fmt(f.score)}, {ROUND_TITLES[f.source]})" for f in top_s) if top_s
                                       else f"none at or above {_fmt(STRENGTH_MIN)}."))
    concerns = [f"{f.area} ({_fmt(f.score)}, {ROUND_TITLES[f.source]})" for f in _diverse_top(weaknesses, SUMMARY_TOP_N, strongest_first=False)]
    concerns += [r.message.split(";")[0].rstrip(".") for r in risks if r.severity in (Severity.HIGH, Severity.MEDIUM)][:SUMMARY_TOP_N]
    lines.append("Main concerns: " + ("; ".join(concerns[:SUMMARY_TOP_N + 2]) if concerns else "none flagged."))
    scored = sum(1 for c in score.contributions if c.status is RoundStatus.SCORED)
    applicable = sum(1 for c in score.contributions if c.status is not RoundStatus.NOT_APPLICABLE)
    lines.append(f"Evidence: {scored} of {applicable} applicable rounds scored (coverage {decision.evidence_coverage:.0%}).")
    lines.append("Next step: " + steps[0])
    return lines


def _fingerprint(payload: Dict[str, Any]) -> str:
    stripped = {k: v for k, v in payload.items() if k not in ("generated_at", "report_id")}
    return hashlib.sha256(json.dumps(stripped, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


def generate_hiring_report(
    decision: CandidateDecision,
    score: CrossRoundCandidateScore,
    *,
    ats=None,
    screening=None,
    hr=None,
    technical=None,
    machine_test=None,
    behavior=None,
    integrity=None,
    screening_report=None,
    interview_summary=None,
    candidate_label: Optional[str] = None,
    role_title: Optional[str] = None,
    generated_at: Optional[str] = None,
) -> HiringIntelligenceReport:
    """Assemble the recruiter report. `decision` (Day 52) and `score` (Day 51) are the authorities for the
    recommendation and the scores; the optional round result objects add evidence and detail."""
    if decision.candidate_id != score.candidate_id:
        raise ValueError("The decision and the score belong to different candidates.")
    if decision.hiring_fit_percentage != score.hiring_fit_percentage:
        raise ValueError("The decision was not built from this score (hiring fit differs).")

    extractors = {
        "ats": (ats, lambda o: _from_ats(o)),
        "screening": (screening, lambda o: _from_screening(o)),
        "hr_interview": (hr, lambda o: _from_hr(o, interview_summary)),
        "technical_interview": (technical, lambda o: _from_technical(o)),
        "machine_test": (machine_test, lambda o: _from_machine_test(o)),
    }
    contributions = {c.round_name: c for c in score.contributions}
    rounds: List[RoundSection] = []
    findings: List[Finding] = []
    round_risks: List[RiskIndicator] = []

    for name in ROUND_NAMES:
        c = contributions[name]
        obj, extract = extractors[name]
        facts: List[str] = []
        notes: List[str] = []
        if c.status is RoundStatus.NOT_APPLICABLE:
            headline = "Not used for this role."
        elif c.status is RoundStatus.MISSING:
            headline = "Not yet available: no evidence for this round, so it is NOT counted as zero."
        else:
            headline = f"{_fmt(c.score)}/100 (counts for {c.effective_weight:.0%} of the Hiring Fit, {_fmt(c.contribution)} points)."
            if obj is not None:
                f_facts, f_findings, f_risks, f_notes = extract(obj)
                facts, notes = f_facts, f_notes
                findings += _cap(f_findings)
                round_risks += f_risks
            else:
                notes.append("Detailed results for this round were not supplied; only its score is shown.")
        if c.note:
            notes.append(c.note)
        rounds.append(RoundSection(name, ROUND_TITLES[name], c.status.value, c.score, c.effective_weight, c.contribution, headline, facts, notes))

    strengths = [f for f in findings if f.kind is FindingKind.STRENGTH]
    weaknesses = [f for f in findings if f.kind is FindingKind.WEAKNESS]
    risks = _risk_indicators(decision, score, round_risks)
    recommendation = _recommendation_block(decision, score)
    label = candidate_label or (decision.candidate_id if decision.candidate_id else "Candidate")

    highlights: Dict[str, List[str]] = {}
    if screening_report is not None:
        h = screening_report.highlights
        highlights["confirmed_skills"] = list(h.confirmed_skills)
        highlights["salary_expectation"] = [", ".join(f"{k}: {v}" for k, v in d.items() if v is not None) for d in h.salary_expectation]
        highlights["availability"] = [", ".join(f"{k}: {v}" for k, v in d.items() if v is not None) for d in h.availability]
        highlights["missing_data"] = list(screening_report.missing_data)

    breakdown = {
        "weight_profile_id": score.weight_profile_id, "formula": score.formula, "adjustments": list(score.adjustments),
        "contributions": [c.to_dict() for c in score.contributions], "sensitivity": dict(score.sensitivity),
        "coverage": round(score.coverage, 4),
    }
    about = {
        "how_to_read": "Start with the executive summary; the sections below give the evidence behind each statement.",
        "text_generation": "Template-based and rule-driven; no language model is used.",
        "thresholds": {"strength_min": STRENGTH_MIN, "weakness_max": WEAKNESS_MAX, "max_findings_per_source": MAX_FINDINGS_PER_SOURCE},
        "limitations": list(LIMITATIONS), "not_implemented": dict(NOT_IMPLEMENTED), "caveats": list(decision.caveats),
    }

    report = HiringIntelligenceReport(
        schema_version=REPORT_SCHEMA_VERSION, report_id="", generated_at=generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        candidate_id=decision.candidate_id, candidate_label=label, role_title=role_title, role_type=decision.role_type,
        experience_level=decision.experience_level, recommendation=recommendation,
        executive_summary=_executive_summary(label, role_title, decision, strengths, weaknesses, risks, score, recommendation["next_steps"]),
        strengths=sorted(strengths, key=lambda f: (-f.score, f.source, f.area)), weaknesses=sorted(weaknesses, key=lambda f: (f.score, f.source, f.area)),
        risk_indicators=risks, rounds=rounds, behavioral_flags=_behavioral_flags(decision, behavior, integrity),
        score_breakdown=breakdown, screening_highlights=highlights, rule_trace=[r.to_dict() for r in decision.rule_trace], about=about,
    )
    report.report_id = "HIR-" + _fingerprint(report.to_dict())
    return report


# ---------------------------------------------------------------------------
# One document model, three renderers
# ---------------------------------------------------------------------------

Block = Tuple[str, Any]     # ("h1"|"h2"|"p"|"ul"|"table"|"callout", payload)


def _findings_blocks(findings: List[Finding], empty_text: str, noun: str) -> List[Block]:
    if not findings:
        return [("p", empty_text)]
    shown = findings[:MAX_LISTED_FINDINGS]
    blocks: List[Block] = [("table", (["Area", "Score", "Source", "Evidence"],
                                      [[f.area, _fmt(f.score), ROUND_TITLES[f.source], f.evidence] for f in shown]))]
    hidden = len(findings) - len(shown)
    if hidden > 0:
        blocks.append(("p", f"{hidden} more {noun}(s) not shown here; the JSON export lists all {len(findings)}."))
    return blocks


def _build_blocks(r: HiringIntelligenceReport) -> List[Block]:
    rec = r.recommendation
    blocks: List[Block] = [
        ("h1", f"Hiring Intelligence Report -- {r.candidate_label}"),
        ("callout", r.confidentiality),
        ("table", (["Field", "Value"], [
            ["Report ID", r.report_id], ["Generated", r.generated_at], ["Role", r.role_title or "(not specified)"],
            ["Role type / experience", f"{r.role_type} / {r.experience_level}"],
        ])),
        ("h2", "Executive summary"),
        ("ul", list(r.executive_summary)),
        ("h2", "Recommendation"),
        ("table", (["Item", "Value"], [
            ["Outcome", rec["outcome_label"] + (f" -- {rec['hold_explanation']}" if rec["hold_explanation"] else "")],
            ["Hiring Fit", "n/a" if rec["hiring_fit_percentage"] is None else f"{rec['hiring_fit_percentage']}%"],
            ["Confidence", f"{_fmt(rec['confidence_score'])}/100 ({rec['confidence_band']})"],
            ["Evidence coverage", f"{rec['evidence_coverage']:.0%}"],
            ["Human confirmation required", "Yes" if rec["requires_human_confirmation"] else "No (auto-advance eligible under policy)"],
        ])),
        ("p", "Why:"), ("ul", list(rec["reasons"])),
        ("p", "Suggested next steps:"), ("ul", list(rec["next_steps"])),
        ("h2", "Strengths"),
    ]
    blocks += _findings_blocks(r.strengths, f"No area scored at or above {_fmt(STRENGTH_MIN)}.", "strength")
    blocks.append(("h2", "Weaknesses"))
    blocks += _findings_blocks(r.weaknesses, f"No area scored below {_fmt(WEAKNESS_MAX)}.", "weakness")
    blocks.append(("h2", "Risk indicators"))
    blocks.append(("table", (["Severity", "Category", "Indicator", "Source"],
                             [[x.severity.value.upper(), x.category, x.message, x.source] for x in r.risk_indicators]))
                  if r.risk_indicators else ("p", "No risk indicators were raised."))
    blocks.append(("h2", "Behavioral flags"))
    blocks.append(("ul", list(r.behavioral_flags)))
    blocks.append(("h2", "Round-by-round results"))
    for s in r.rounds:
        blocks.append(("h3", s.title))
        blocks.append(("p", s.headline))
        if s.key_facts:
            blocks.append(("ul", list(s.key_facts)))
        for n in s.notes:
            blocks.append(("p", "Note: " + n))
    if r.screening_highlights:
        blocks.append(("h2", "Screening highlights"))
        rows = [[k.replace("_", " ").capitalize(), "; ".join(v) if v else "(none stated)"] for k, v in r.screening_highlights.items()]
        blocks.append(("table", (["Item", "Detail"], rows)))
    sb = r.score_breakdown
    blocks += [("h2", "How the Hiring Fit was calculated"), ("p", f"Weight profile: {sb['weight_profile_id']}. {sb['formula']}.")]
    if sb["adjustments"]:
        blocks.append(("ul", list(sb["adjustments"])))
    blocks.append(("table", (["Round", "Status", "Score", "Weight", "Points"],
                             [[ROUND_TITLES[c["round_name"]], c["status"], "-" if c["score"] is None else _fmt(c["score"]),
                               f"{c['effective_weight']:.0%}", _fmt(c["contribution"])] for c in sb["contributions"]])))
    if sb["sensitivity"]:
        blocks.append(("p", "Hiring Fit if a round were left out: " + "; ".join(f"without {ROUND_TITLES[k]}: {_fmt(v)}%" for k, v in sb["sensitivity"].items() if v is not None) + "."))
    blocks.append(("h2", "Decision rule trace"))
    blocks.append(("table", (["Rule", "Fired", "Effect", "Detail"],
                             [[t["rule_id"], "YES" if t["fired"] else "no", t["effect"], t["detail"]] for t in r.rule_trace])))
    blocks += [("h2", "About this report"), ("p", r.about["how_to_read"]), ("p", r.about["text_generation"]),
               ("p", "Limitations:"), ("ul", list(r.about["limitations"])),
               ("p", "Not implemented:"), ("ul", [f"{k.replace('_', ' ')}: {v}" for k, v in r.about["not_implemented"].items()])]
    return blocks


_MD_SPECIAL = re.compile(r"([\\`*_\[\]<>|])")


def _md(text: Any) -> str:
    return _MD_SPECIAL.sub(r"\\\1", str(text)).replace("\n", " ").replace("\r", " ")


def _render_markdown(blocks: List[Block]) -> str:
    out: List[str] = []
    for kind, payload in blocks:
        if kind in ("h1", "h2", "h3"):
            out.append(f"{'#' * int(kind[1])} {_md(payload)}\n")
        elif kind == "p":
            out.append(f"{_md(payload)}\n")
        elif kind == "callout":
            out.append(f"> **{_md(payload)}**\n")
        elif kind == "ul":
            out.append("\n".join(f"- {_md(item)}" for item in payload) + "\n")
        elif kind == "table":
            header, rows = payload
            out.append("| " + " | ".join(_md(h) for h in header) + " |")
            out.append("|" + "|".join("---" for _ in header) + "|")
            out += ["| " + " | ".join(_md(c) for c in row) + " |" for row in rows]
            out.append("")
    return "\n".join(out)


_HTML_CSS = """
body{font-family:Arial,Helvetica,sans-serif;color:#1a1a1a;max-width:880px;margin:24px auto;padding:0 16px;line-height:1.45}
h1{font-size:22px;margin:0 0 8px}h2{font-size:17px;border-bottom:2px solid #d9dee7;padding-bottom:4px;margin-top:26px}h3{font-size:14px;margin:16px 0 4px}
.confidential{background:#fff4e5;border:1px solid #f0b86e;padding:8px 12px;font-weight:bold;margin:8px 0}
.banner{border-left:8px solid #6b7785;background:#f3f5f8;padding:10px 14px;margin:12px 0}
.banner.selected{border-color:#2e7d32}.banner.hold_review{border-color:#b26a00}.banner.rejected{border-color:#b3261e}
.banner .outcome{font-size:18px;font-weight:bold}
table{border-collapse:collapse;width:100%;margin:8px 0}th,td{border:1px solid #c9d0da;padding:5px 8px;text-align:left;vertical-align:top;font-size:13px}th{background:#e9edf3}
ul{margin:4px 0 8px 18px}li{margin:2px 0}
@page{size:A4;margin:16mm}@media print{body{margin:0;max-width:none}h2{page-break-after:avoid}table,section{page-break-inside:avoid}}
"""


def _render_html(r: HiringIntelligenceReport, blocks: List[Block]) -> str:
    esc = html.escape
    rec = r.recommendation
    parts: List[str] = []
    in_section = False
    for kind, payload in blocks:
        if kind == "h1":
            parts.append(f"<h1>{esc(payload)}</h1>")
        elif kind == "h2":
            if in_section:
                parts.append("</section>")
            parts.append(f"<section><h2>{esc(payload)}</h2>")
            in_section = True
            if payload == "Executive summary":
                fit = "n/a" if rec["hiring_fit_percentage"] is None else f"{rec['hiring_fit_percentage']}%"
                parts.append(f"<div class=\"banner {esc(rec['outcome'])}\"><div class=\"outcome\">{esc(rec['outcome_label'])}</div>"
                             f"<div>Hiring Fit {esc(fit)} &middot; confidence {esc(_fmt(rec['confidence_score']))}/100 ({esc(rec['confidence_band'])})"
                             f" &middot; evidence coverage {rec['evidence_coverage']:.0%}</div></div>")
        elif kind == "h3":
            parts.append(f"<h3>{esc(payload)}</h3>")
        elif kind == "p":
            parts.append(f"<p>{esc(payload)}</p>")
        elif kind == "callout":
            parts.append(f"<div class=\"confidential\">{esc(payload)}</div>")
        elif kind == "ul":
            parts.append("<ul>" + "".join(f"<li>{esc(str(i))}</li>" for i in payload) + "</ul>")
        elif kind == "table":
            header, rows = payload
            parts.append("<table><thead><tr>" + "".join(f"<th>{esc(str(h))}</th>" for h in header) + "</tr></thead><tbody>"
                         + "".join("<tr>" + "".join(f"<td>{esc(str(c))}</td>" for c in row) + "</tr>" for row in rows) + "</tbody></table>")
    if in_section:
        parts.append("</section>")
    return ("<!DOCTYPE html>\n<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>{esc('Hiring Intelligence Report - ' + r.candidate_label)}</title><style>{_HTML_CSS}</style></head><body>\n"
            + "\n".join(parts) + "\n</body></html>\n")


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

_EXPORTERS = {"json": ("json", lambda r: r.to_json()), "md": ("md", lambda r: r.to_markdown()), "html": ("html", lambda r: r.to_html())}


def export_report(report: HiringIntelligenceReport, directory: str, formats: Sequence[str] = ("json", "md", "html")) -> Dict[str, str]:
    """Write the report to `directory` in the requested formats and return {format: path}.
    File names come from the report fingerprint, never from candidate-supplied text."""
    unknown = [f for f in formats if f not in _EXPORTERS]
    if unknown:
        raise ValueError(f"Unsupported format(s): {unknown}. Supported: {sorted(_EXPORTERS)}. For PDF, print the HTML export from a browser.")
    os.makedirs(directory, exist_ok=True)
    written: Dict[str, str] = {}
    for fmt in formats:
        ext, render = _EXPORTERS[fmt]
        path = os.path.join(directory, f"{report.report_id}.{ext}")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(render(report))
        written[fmt] = path
    return written
