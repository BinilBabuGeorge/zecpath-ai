"""
Final Recommendation AI (Day 52)

WHAT THIS DAY BUILDS: the last step of the scoring pipeline. Day 51
combined five rounds into a Hiring Fit Score; this module turns that,
plus integrity (Day 49) and behavioral (Day 48) risk factors, into one of
three decision categories -- SELECTED, HOLD_REVIEW, REJECTED -- with a
confidence score and a full, explainable rule trace.

THE DECISION THIS DAY HAS TO MAKE ABOUT "AUTOMATED HIRING OUTCOMES":
the brief says "automated hiring outcomes". This design automates the
RECOMMENDATION and keeps one hard line on the OUTCOME, enforced in code
rather than only written in a document:

    - A REJECTION can never be applied automatically. The policy object
      refuses to be configured otherwise (ValueError), and the
      candidate-facing notice for an unconfirmed rejection says "under
      review", not "rejected". A named human must confirm it.
    - A SELECTED outcome may be auto-advanced ONLY if an explicit policy
      enables it (default: off), confidence is high, no rule blocked it
      and no review reason exists. Even then it is a low-harm, reversible
      move to the next stage.
    - Every human override is recorded with the reviewer and a mandatory
      note.
Why: a wrongly rejected candidate is the costly, hard-to-reverse error;
the weights and thresholds here are reasoned, not calibrated (no labelled
hiring-outcome data exists); and employment is a category that
regulators in several places treat as high-risk or subject to rules about
solely-automated decisions (general awareness, not legal advice -- real
deployment needs legal review and a bias audit first). Day 41 and Day 51
already took this stance ("a rejection is never automatic"); this day
makes it enforceable.

RULE + SCORE HYBRID LOGIC (the brief's term):
  1. SCORE sets a base band from the Hiring Fit Score, using the 70 / 50
     thresholds carried unchanged from Day 2 -> Day 41 -> Day 51.
  2. RULES then guard that band. Rules can only move an outcome toward
     human review, never toward rejection:
       R1 evidence complete?      incomplete        -> HOLD (pending evidence)
       R2 critical-round floors   a skill round < 40 blocks SELECTED
       R3 integrity gate          MEDIUM/HIGH       blocks SELECTED
       R4 Day 51 review reasons   borderline / disagreement / round review
                                                    blocks SELECTED
       R5 selection confidence    < 55              blocks SELECTED
       R6 rejection confidence    < 50              REJECTED -> HOLD
                                  (not enough evidence to recommend rejection)
       R7 rejection needs human   always recorded; never auto-applicable
  A compensatory average hides a critical weakness; R2 is the guard
  against "great overall, but failed the core skill".

CONFIDENCE (0-100) -- WHAT IT IS AND IS NOT: a measure of how ROBUST the
evidence behind the score band is, built from four 0-1 components --
margin from the nearest threshold (35%), evidence coverage (25%),
agreement between rounds (20%) and stability when any one round is left
out (20%) -- multiplied by a risk multiplier (and capped at 60 while any round is
missing, so an incomplete candidate never reads as high confidence). It is NOT a probability of
a good hire and it is NOT calibrated: there is no outcome data to
calibrate it against. It tells a reviewer how much to trust the number,
nothing more.

RISK FACTORS (behavior, integrity):
  - INTEGRITY (Day 49): MEDIUM/HIGH blocks SELECTED and lowers confidence.
  - BEHAVIOR (Day 48): latency spikes and uneven pacing only LOWER
    confidence (never change a category on their own). Verbal hesitation is
    shown but deliberately NOT used: it penalises nervous and non-native
    speakers, a fairness risk Day 48 itself named. This follows Day 49's
    rule that behavioral signals can corroborate, never accuse.
  Because both only push toward review, no combination of risk factors can
  turn a non-rejected candidate into a rejected one (tested exhaustively).

EXPLAINABILITY: every decision carries the base score band, the final
outcome, the ordered rule trace (fired or not, with the effect), reasons,
the confidence breakdown, risk factors, and "what would change this"
conditions. The candidate-facing notice never contains scores, risk
factors or the word integrity.

HONESTY: thresholds, floors and multipliers are reasoned, not calibrated.
No bias audit of the decisions has been done; no notification, storage or
appeal workflow is built; the machine-test input still depends on a
sandbox that does not exist yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from parsers.cross_round_aggregation_engine import (
    DISAGREEMENT_SPREAD,
    HOLD_THRESHOLD,
    SELECTED_THRESHOLD,
    CrossRoundCandidateScore,
    RoundStatus,
)

DECISION_SCHEMA_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Configuration -- reasoned, NOT calibrated
# ---------------------------------------------------------------------------

CRITICAL_ROUND_FLOORS: Dict[str, Dict[str, float]] = {
    "technical": {"technical_interview": 40.0, "machine_test": 40.0},
    "non_technical": {"hr_interview": 40.0},
}

MARGIN_FULL_AT = 15.0           # points away from a threshold for full margin credit
CONFIDENCE_WEIGHTS = {"margin": 0.35, "coverage": 0.25, "agreement": 0.20, "stability": 0.20}
CONFIDENCE_HIGH = 75.0
CONFIDENCE_MEDIUM = 50.0

PROVISIONAL_CONFIDENCE_CAP = 60.0   # a score with a missing round can never read as "high" confidence

MIN_SELECT_CONFIDENCE = 55.0
MIN_REJECT_CONFIDENCE = 50.0
AUTO_MIN_CONFIDENCE = 75.0

INTEGRITY_MULTIPLIER = {"clear": 1.0, "low": 0.95, "medium": 0.80, "high": 0.60}
BEHAVIOR_MULTIPLIER = {"none": 1.0, "low": 0.95, "medium": 0.90}
_INTEGRITY_SEVERITY = {"clear": 0, "low": 1, "medium": 2, "high": 3}

BEHAVIOR_SPIKE_COUNT = 2        # latency spikes at/above this count as one behavior signal
BEHAVIOR_FOCUS_FLOOR = 50.0     # pacing-consistency score below this counts as one behavior signal

_INTEGRITY_REASON_PREFIX = "Interview integrity tag"
_REJECTION_REASON_PREFIX = "Rejection recommendations"


class DecisionOutcome(str, Enum):
    SELECTED = "selected"
    HOLD_REVIEW = "hold_review"
    REJECTED = "rejected"


class HoldKind(str, Enum):
    PENDING_EVIDENCE = "pending_evidence"                    # rounds still to complete
    MID_SCORE = "mid_score"                                  # score sits in the review band
    SELECTION_BLOCKED = "selection_blocked"                  # score says select, a rule says look first
    INSUFFICIENT_EVIDENCE_TO_REJECT = "insufficient_evidence_to_reject"


@dataclass
class DecisionPolicy:
    """What the engine may do without a person. Defaults are recommend-only.
    The REJECTED outcome can never be made automatic."""
    selected_threshold: float = SELECTED_THRESHOLD
    hold_threshold: float = HOLD_THRESHOLD
    min_select_confidence: float = MIN_SELECT_CONFIDENCE
    min_reject_confidence: float = MIN_REJECT_CONFIDENCE
    auto_min_confidence: float = AUTO_MIN_CONFIDENCE
    auto_apply: Dict[DecisionOutcome, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.hold_threshold >= self.selected_threshold:
            raise ValueError("hold_threshold must be below selected_threshold.")
        for outcome, enabled in self.auto_apply.items():
            if enabled and outcome is not DecisionOutcome.SELECTED:
                raise ValueError("Only a SELECTED outcome may ever be auto-applied; rejections and holds always need a person.")


@dataclass
class RuleResult:
    rule_id: str
    description: str
    fired: bool
    effect: str
    detail: str = ""

    def to_dict(self) -> Dict:
        return dict(self.__dict__)


@dataclass
class RiskFactor:
    category: str                # "integrity" | "behavior"
    level: str                   # none | clear | low | medium | high
    effect: str                  # blocks_selection | lowers_confidence | informational
    detail: str

    def to_dict(self) -> Dict:
        return dict(self.__dict__)


@dataclass
class ConfidenceBreakdown:
    margin: float
    coverage: float
    agreement: float
    stability: float
    risk_multiplier: float
    score: float
    band: str
    note: str = ("Robustness of the evidence behind the score band -- not a probability of a good hire, "
                 "and not calibrated (no hiring-outcome data exists).")

    def to_dict(self) -> Dict:
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in self.__dict__.items()}


# ---------------------------------------------------------------------------
# Candidate-facing notices -- no scores, no risk factors, no mention of integrity
# ---------------------------------------------------------------------------

NOTICES: Dict[DecisionOutcome, str] = {
    DecisionOutcome.SELECTED: ("Thank you for taking part in our interview process. We are pleased to move you forward, "
                               "and a member of our team will be in touch with your next steps."),
    DecisionOutcome.HOLD_REVIEW: ("Thank you for completing our interview process. Your application is currently under review "
                                  "and we will be in touch as soon as we have an update."),
    DecisionOutcome.REJECTED: ("Thank you for the time and effort you put into our interview process. After careful review, "
                               "we have decided not to move forward with your application at this time."),
}


# ---------------------------------------------------------------------------
# The decision object (candidate decision output format)
# ---------------------------------------------------------------------------

DECISION_FIELDS = (
    "schema_version", "candidate_id", "role_type", "experience_level", "outcome", "hold_kind", "score_band",
    "hiring_fit_percentage", "confidence", "risk_factors", "rule_trace", "reasons", "what_would_change",
    "automation_eligible", "requires_human_confirmation", "automated_action", "evidence_coverage",
    "not_implemented", "caveats",
)

NOT_IMPLEMENTED: Dict[str, str] = {
    "confidence_calibration": "No hiring-outcome data exists, so confidence cannot be calibrated into a probability.",
    "decision_bias_audit": "No disparate-impact audit of these decisions by group has been done; required before any automation.",
    "notification_delivery": "Notices are generated as text only; sending them (PRD Phases 21, 46, 72) is not built.",
    "audit_persistence_and_appeals": "Audit records are returned as data; storing them and an appeal workflow are not built.",
    "legal_review": "Not reviewed against employment or automated-decision regulation; required before real use.",
}

CAVEATS: List[str] = [
    "Thresholds, floors and multipliers are reasoned, not calibrated.",
    "The outcome is a recommendation: nothing is rejected without a named person confirming it.",
    "Confidence measures how robust the evidence is, not how likely the candidate is to succeed.",
    "Risk factors can only move a decision toward human review, never toward rejection.",
    "The decision inherits every upstream limit (for example, the machine-test round rests on a sandbox that does not exist yet).",
]


@dataclass
class CandidateDecision:
    candidate_id: Optional[str]
    role_type: str
    experience_level: str
    outcome: DecisionOutcome
    hold_kind: Optional[HoldKind]
    score_band: DecisionOutcome                # what the score alone says, before the rules
    hiring_fit_percentage: Optional[float]
    confidence: ConfidenceBreakdown
    risk_factors: List[RiskFactor]
    rule_trace: List[RuleResult]
    reasons: List[str]
    what_would_change: List[str]
    automation_eligible: bool
    evidence_coverage: float
    schema_version: str = DECISION_SCHEMA_VERSION
    automated_action: str = "none"             # the engine never acts; see finalize_*
    not_implemented: Dict[str, str] = field(default_factory=lambda: dict(NOT_IMPLEMENTED))
    caveats: List[str] = field(default_factory=lambda: list(CAVEATS))

    @property
    def requires_human_confirmation(self) -> bool:
        return not self.automation_eligible

    def candidate_notice(self) -> str:
        """What the candidate may be told NOW. An unconfirmed rejection reads as 'under review'."""
        shown = DecisionOutcome.HOLD_REVIEW if self.outcome is DecisionOutcome.REJECTED else self.outcome
        return NOTICES[shown]

    def to_dict(self) -> Dict:
        return {
            "schema_version": self.schema_version, "candidate_id": self.candidate_id, "role_type": self.role_type,
            "experience_level": self.experience_level, "outcome": self.outcome.value,
            "hold_kind": self.hold_kind.value if self.hold_kind else None, "score_band": self.score_band.value,
            "hiring_fit_percentage": self.hiring_fit_percentage, "confidence": self.confidence.to_dict(),
            "risk_factors": [r.to_dict() for r in self.risk_factors], "rule_trace": [r.to_dict() for r in self.rule_trace],
            "reasons": self.reasons, "what_would_change": self.what_would_change,
            "automation_eligible": self.automation_eligible, "requires_human_confirmation": self.requires_human_confirmation,
            "automated_action": self.automated_action, "evidence_coverage": round(self.evidence_coverage, 4),
            "not_implemented": self.not_implemented, "caveats": self.caveats,
        }

    def explain(self) -> str:
        fit = "n/a" if self.hiring_fit_percentage is None else f"{self.hiring_fit_percentage}%"
        lines = [
            f"Recommendation for {self.candidate_id or 'this candidate'}: {self.outcome.value.upper().replace('_', ' / ')}"
            + (f" ({self.hold_kind.value.replace('_', ' ')})" if self.hold_kind else "")
            + f" -- Hiring Fit {fit}, confidence {self.confidence.score:g}/100 ({self.confidence.band}).",
        ]
        if self.hold_kind is not HoldKind.PENDING_EVIDENCE:
            lines.append(f"The score alone says {self.score_band.value.upper().replace('_', ' / ')}.")
        fired = [r for r in self.rule_trace if r.fired]
        if fired:
            lines.append("Rules that changed or constrained the outcome: " + "; ".join(f"{r.rule_id} ({r.detail})" for r in fired) + ".")
        lines += self.reasons
        if self.what_would_change:
            lines.append("What would change this: " + " | ".join(self.what_would_change))
        lines.append("Human confirmation required." if self.requires_human_confirmation
                     else "Eligible for auto-advance under the active policy (a low-harm, reversible move).")
        return "\n".join(lines)

    def to_summary_text(self) -> str:
        lines = [
            "Final Recommendation (decision support -- not an automated decision)",
            "=" * 68,
            f"Candidate: {self.candidate_id or '(unspecified)'} | {self.role_type} | {self.experience_level}",
            f"Outcome: {self.outcome.value.upper()}" + (f" [{self.hold_kind.value}]" if self.hold_kind else "")
            + f" | score band: {self.score_band.value} | fit: {self.hiring_fit_percentage}",
            f"Confidence: {self.confidence.score:g}/100 ({self.confidence.band}) | coverage {self.evidence_coverage:.0%}",
            f"Human confirmation required: {'YES' if self.requires_human_confirmation else 'no (auto-advance eligible)'}",
            "", "Rule trace:",
        ]
        lines += [f"  [{'FIRED' if r.fired else 'ok   '}] {r.rule_id}: {r.description}" + (f" -> {r.detail}" if r.detail else "") for r in self.rule_trace]
        if self.risk_factors:
            lines += ["", "Risk factors:"] + [f"  - {r.category}: {r.level} ({r.effect}) {r.detail}" for r in self.risk_factors]
        return "\n".join(lines)


@dataclass
class HumanReview:
    reviewer_id: str
    final_outcome: DecisionOutcome
    note: str = ""


@dataclass
class FinalizedDecision:
    candidate_id: Optional[str]
    engine_outcome: DecisionOutcome
    final_outcome: DecisionOutcome
    decided_by: str                  # "human:<id>" | "policy:auto_advance"
    overridden: bool
    note: str
    candidate_notice: str

    def audit_record(self) -> Dict:
        return {"candidate_id": self.candidate_id, "engine_outcome": self.engine_outcome.value,
                "final_outcome": self.final_outcome.value, "decided_by": self.decided_by,
                "overridden": self.overridden, "note": self.note}


# ---------------------------------------------------------------------------
# Risk factors and confidence
# ---------------------------------------------------------------------------

def _worst_integrity(score: CrossRoundCandidateScore, integrity_report) -> Optional[str]:
    tags = [score.integrity_risk_tag]
    if integrity_report is not None:
        tags.append(getattr(integrity_report.risk_tag, "value", integrity_report.risk_tag))
    tags = [str(t) for t in tags if t]
    return max(tags, key=lambda t: _INTEGRITY_SEVERITY.get(t, 0)) if tags else None


def assess_risk_factors(score: CrossRoundCandidateScore, integrity_report=None, behavior_report=None) -> List[RiskFactor]:
    factors: List[RiskFactor] = []
    tag = _worst_integrity(score, integrity_report)
    if tag:
        detail = ""
        if integrity_report is not None and integrity_report.flags:
            detail = "flags: " + ", ".join(f.code for f in integrity_report.flags)
        severe = tag in ("medium", "high")
        factors.append(RiskFactor("integrity", tag, "blocks_selection" if severe else "informational", detail))

    if behavior_report is not None:
        points, notes = 0, []
        if behavior_report.distraction.spike_count >= BEHAVIOR_SPIKE_COUNT:
            points += 1
            notes.append(f"{behavior_report.distraction.spike_count} response-time spikes")
        if behavior_report.focus.focus_level_score < BEHAVIOR_FOCUS_FLOOR:
            points += 1
            notes.append(f"uneven pacing (focus {behavior_report.focus.focus_level_score:g}/100)")
        level = "none" if points == 0 else "low" if points == 1 else "medium"
        notes.append(f"verbal hesitation {behavior_report.verbal_hesitation.average_hesitation_rate_per_100_words:g}/100 words shown but "
                     "NOT used (fairness: it penalises nervous and non-native speakers)")
        factors.append(RiskFactor("behavior", level, "lowers_confidence" if points else "informational", "; ".join(notes)))
    return factors


def _band(fit: float, policy: DecisionPolicy) -> DecisionOutcome:
    if fit >= policy.selected_threshold:
        return DecisionOutcome.SELECTED
    return DecisionOutcome.HOLD_REVIEW if fit >= policy.hold_threshold else DecisionOutcome.REJECTED


def compute_confidence(score: CrossRoundCandidateScore, factors: List[RiskFactor], policy: DecisionPolicy) -> ConfidenceBreakdown:
    if score.hiring_fit_percentage is None:
        return ConfidenceBreakdown(0.0, 0.0, 0.0, 0.0, 1.0, 0.0, "low")
    fit = score.hiring_fit_percentage
    margin = min(1.0, min(abs(fit - policy.selected_threshold), abs(fit - policy.hold_threshold)) / MARGIN_FULL_AT)

    # Agreement among rounds the profile did not deliberately down-weight (same rule as Day 51).
    comparable = [c.score for c in score.contributions
                  if c.status is RoundStatus.SCORED and c.adjusted_weight >= c.base_weight - 1e-9]
    spread = (max(comparable) - min(comparable)) if len(comparable) >= 2 else 0.0
    agreement = max(0.0, 1.0 - spread / (2.0 * DISAGREEMENT_SPREAD))

    base_band = _band(fit, policy)
    others = [v for v in score.sensitivity.values() if v is not None]
    stability = (sum(1 for v in others if _band(v, policy) is base_band) / len(others)) if others else 0.5

    w = CONFIDENCE_WEIGHTS
    base = w["margin"] * margin + w["coverage"] * score.coverage + w["agreement"] * agreement + w["stability"] * stability

    multiplier = 1.0
    for f in factors:
        multiplier *= (INTEGRITY_MULTIPLIER if f.category == "integrity" else BEHAVIOR_MULTIPLIER).get(f.level, 1.0)
    value = round(100.0 * base * multiplier, 1)
    if score.provisional:
        value = min(value, PROVISIONAL_CONFIDENCE_CAP)
    band = "high" if value >= CONFIDENCE_HIGH else "medium" if value >= CONFIDENCE_MEDIUM else "low"
    return ConfidenceBreakdown(margin, score.coverage, agreement, stability, multiplier, value, band)


# ---------------------------------------------------------------------------
# The decision
# ---------------------------------------------------------------------------

def decide(
    score: CrossRoundCandidateScore,
    integrity_report=None,
    behavior_report=None,
    policy: Optional[DecisionPolicy] = None,
) -> CandidateDecision:
    """Turn a Day 51 score plus risk factors into a recommended outcome with a full rule trace."""
    policy = policy or DecisionPolicy()
    factors = assess_risk_factors(score, integrity_report, behavior_report)
    confidence = compute_confidence(score, factors, policy)
    fit = score.hiring_fit_percentage
    trace: List[RuleResult] = []
    reasons: List[str] = []
    change: List[str] = []

    # R1 -- evidence complete?
    incomplete = score.provisional or fit is None
    trace.append(RuleResult("R1_EVIDENCE_COMPLETE", "Every applicable round has evidence", incomplete,
                            "forces HOLD" if incomplete else "none",
                            f"waiting on {', '.join(score.missing_rounds) or 'any round'}" if incomplete else ""))
    if incomplete:
        reasons.append(f"The decision is pending: still waiting on {', '.join(score.missing_rounds) or 'any scored round'}. "
                       "A provisional score is not comparable with a complete one.")
        change.append(f"Complete the remaining round(s): {', '.join(score.missing_rounds) or 'all'}.")
        return _build(score, policy, factors, confidence, trace, reasons, change, DecisionOutcome.HOLD_REVIEW,
                      HoldKind.PENDING_EVIDENCE, DecisionOutcome.HOLD_REVIEW)

    band = _band(fit, policy)

    # R2 -- critical-round floors
    floors = CRITICAL_ROUND_FLOORS[score.role_type.value]
    below = [(c.round_name, c.score) for c in score.contributions
             if c.status is RoundStatus.SCORED and c.round_name in floors and c.score < floors[c.round_name]]
    r2_fired = bool(below) and band is DecisionOutcome.SELECTED
    trace.append(RuleResult("R2_CRITICAL_ROUND_FLOORS", "No critical round below its floor (applies when the score would select)", r2_fired,
                            "blocks SELECTED" if r2_fired else "none",
                            ", ".join(f"{n} {s:g} < {floors[n]:g}" for n, s in below) if r2_fired else ""))

    # R3 -- integrity gate
    integrity = next((f for f in factors if f.category == "integrity"), None)
    integrity_severe = bool(integrity and integrity.level in ("medium", "high"))
    r3_fired = integrity_severe and band is DecisionOutcome.SELECTED
    trace.append(RuleResult("R3_INTEGRITY_GATE", "No unresolved integrity concern (Day 49)", r3_fired,
                            "blocks SELECTED" if r3_fired else "none",
                            f"integrity tag {integrity.level.upper()}" if r3_fired else ""))

    # R4 -- Day 51 review reasons (borderline, disagreement, a round that asked for review)
    other_reasons = [r for r in score.human_review_reasons
                     if not r.startswith(_INTEGRITY_REASON_PREFIX) and not r.startswith(_REJECTION_REASON_PREFIX)]
    trace.append(RuleResult("R4_REVIEW_FLAGS", "No unresolved review flag from the aggregate score (Day 51)",
                            bool(other_reasons) and band is DecisionOutcome.SELECTED,
                            "blocks SELECTED" if other_reasons and band is DecisionOutcome.SELECTED else "none",
                            f"{len(other_reasons)} flag(s)" if other_reasons else ""))

    # R5 -- selection confidence floor
    low_select = confidence.score < policy.min_select_confidence
    trace.append(RuleResult("R5_SELECT_CONFIDENCE_FLOOR", f"Confidence >= {policy.min_select_confidence:g} to select",
                            low_select and band is DecisionOutcome.SELECTED,
                            "blocks SELECTED" if low_select and band is DecisionOutcome.SELECTED else "none",
                            f"confidence {confidence.score:g}" if low_select and band is DecisionOutcome.SELECTED else ""))

    # R6 -- rejection confidence floor
    low_reject = confidence.score < policy.min_reject_confidence
    trace.append(RuleResult("R6_REJECT_CONFIDENCE_FLOOR", f"Confidence >= {policy.min_reject_confidence:g} to recommend rejection",
                            low_reject and band is DecisionOutcome.REJECTED,
                            "REJECTED -> HOLD" if low_reject and band is DecisionOutcome.REJECTED else "none",
                            f"confidence {confidence.score:g}" if low_reject and band is DecisionOutcome.REJECTED else ""))

    blockers: List[str] = []
    if below and band is DecisionOutcome.SELECTED:
        blockers.append("a critical skill round is below its floor (" + ", ".join(f"{n} {s:g}" for n, s in below) + ")")
        change.append("Resolve the weak critical round: " + ", ".join(n for n, _ in below) + ".")
    if integrity_severe and band is DecisionOutcome.SELECTED:
        blockers.append(f"the interview integrity tag is {integrity.level.upper()}")
        change.append("A reviewer clears the integrity concern after looking at the session.")
    if other_reasons and band is DecisionOutcome.SELECTED:
        blockers.append("the aggregate score raised review flags: " + " ".join(other_reasons))
        change.append("A reviewer resolves the flagged review reason(s).")
    if low_select and band is DecisionOutcome.SELECTED:
        blockers.append(f"confidence is only {confidence.score:g} (below {policy.min_select_confidence:g})")
        change.append("More or steadier evidence raises confidence.")

    if band is DecisionOutcome.SELECTED:
        if blockers:
            outcome, hold = DecisionOutcome.HOLD_REVIEW, HoldKind.SELECTION_BLOCKED
            reasons.append(f"The score ({fit}%) would select this candidate, but selection is held for review because " + "; ".join(b.rstrip(".") for b in blockers) + ".")
        else:
            outcome, hold = DecisionOutcome.SELECTED, None
            reasons.append(f"Hiring Fit {fit}% clears the selection threshold ({policy.selected_threshold:g}) with no rule blocking it.")
    elif band is DecisionOutcome.HOLD_REVIEW:
        outcome, hold = DecisionOutcome.HOLD_REVIEW, HoldKind.MID_SCORE
        reasons.append(f"Hiring Fit {fit}% is in the review band ({policy.hold_threshold:g}-{policy.selected_threshold:g}).")
        change.append(f"Reaching {policy.selected_threshold:g} (+{policy.selected_threshold - fit:.1f} points) with no flags would select; "
                      f"falling below {policy.hold_threshold:g} would move toward rejection.")
    else:
        if low_reject:
            outcome, hold = DecisionOutcome.HOLD_REVIEW, HoldKind.INSUFFICIENT_EVIDENCE_TO_REJECT
            reasons.append(f"The score ({fit}%) is below {policy.hold_threshold:g}, but confidence is only {confidence.score:g}, so there is not "
                           "enough evidence to recommend rejection; a person should review.")
        else:
            outcome, hold = DecisionOutcome.REJECTED, None
            reasons.append(f"Hiring Fit {fit}% is below the hold threshold ({policy.hold_threshold:g}).")
        change.append(f"Reaching {policy.hold_threshold:g} (+{policy.hold_threshold - fit:.1f} points) would move this to review.")

    trace.append(RuleResult("R7_REJECTION_NEEDS_HUMAN", "A rejection is never applied without a named person", outcome is DecisionOutcome.REJECTED,
                            "human confirmation mandatory" if outcome is DecisionOutcome.REJECTED else "none",
                            "nothing is rejected automatically" if outcome is DecisionOutcome.REJECTED else ""))

    for f in factors:
        if f.category == "behavior" and f.effect == "lowers_confidence":
            reasons.append(f"Behavioral timing signals ({f.detail.split('; ')[0]}) lowered confidence; they never change the category by themselves.")
        if f.category == "integrity" and f.effect == "informational" and f.level == "low":
            reasons.append("A low integrity tag was recorded; it is informational only.")
    if integrity_severe and band is not DecisionOutcome.SELECTED:
        reasons.append(f"The integrity tag is {integrity.level.upper()}: the reviewer should look at the session before acting on this outcome.")

    return _build(score, policy, factors, confidence, trace, reasons, change, outcome, hold, band)


def _build(score, policy, factors, confidence, trace, reasons, change, outcome, hold, band) -> CandidateDecision:
    eligible = (
        outcome is DecisionOutcome.SELECTED
        and policy.auto_apply.get(DecisionOutcome.SELECTED, False)
        and confidence.score >= policy.auto_min_confidence
        and not score.human_review_required
    )
    return CandidateDecision(
        candidate_id=score.candidate_id, role_type=score.role_type.value, experience_level=score.experience_level.value,
        outcome=outcome, hold_kind=hold, score_band=band, hiring_fit_percentage=score.hiring_fit_percentage,
        confidence=confidence, risk_factors=factors, rule_trace=trace, reasons=reasons, what_would_change=change,
        automation_eligible=eligible, evidence_coverage=score.coverage,
    )


# ---------------------------------------------------------------------------
# Finalization -- where a decision becomes real, and who made it
# ---------------------------------------------------------------------------

def finalize_with_human(decision: CandidateDecision, review: HumanReview) -> FinalizedDecision:
    """A named person confirms or overrides the engine's outcome. An override needs a written reason."""
    if not review.reviewer_id or not review.reviewer_id.strip():
        raise ValueError("A named reviewer is required.")
    overridden = review.final_outcome is not decision.outcome
    if overridden and not review.note.strip():
        raise ValueError("Overriding the engine's recommendation requires a note explaining why.")
    return FinalizedDecision(decision.candidate_id, decision.outcome, review.final_outcome, f"human:{review.reviewer_id.strip()}",
                             overridden, review.note.strip(), NOTICES[review.final_outcome])


def finalize_automatically(decision: CandidateDecision) -> FinalizedDecision:
    """Only a policy-eligible SELECTED decision may be finalized without a person (auto-advance)."""
    if not decision.automation_eligible:
        raise ValueError("This decision is not eligible for automatic finalization; a person must confirm it.")
    return FinalizedDecision(decision.candidate_id, decision.outcome, decision.outcome, "policy:auto_advance", False,
                             "Auto-advanced under an explicit policy.", NOTICES[DecisionOutcome.SELECTED])
