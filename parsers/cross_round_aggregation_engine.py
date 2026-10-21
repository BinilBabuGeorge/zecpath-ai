"""
Cross-Round Aggregation Engine (Day 51)

WHAT THIS DAY ADDS: Day 41's `unified_scoring_engine` combined three
rounds (ATS, screening, HR interview). Since then the project built two
more -- the technical interview (Day 47) and the machine test (Day 50)
-- so there are now FIVE round outputs and nothing that combines them.
This engine does, producing the PRD's "Hiring Fit Score (%)" (Phases 70
and 71: cross-round aggregation, final recommendation, hiring fit %).

ADDITIVE, NOT A REWRITE: Day 41's module is untouched. This one extends
the same ideas to five rounds and keeps its numbers where they still
apply: the 70 / 50 recommendation thresholds are carried over unchanged
(a test pins them to Day 41's constants so drift is caught), and for a
non-technical, experienced candidate the result reproduces Day 41's
three-round score exactly (also tested). For technical roles the weights
are deliberately different -- see below.

THE WEIGHTING SYSTEM (per role, then per candidate profile):
    technical role       ats .10  screening .10  hr .20  technical .30  machine_test .30
    non-technical role   ats .25  screening .15  hr .60  technical 0    machine_test 0
Technical roles put 60% on the two rounds that test real skill, because
by the time a candidate reaches them the ATS keyword match has already
done its filtering job (range restriction makes it a weak discriminator
late in the funnel). Non-technical roles are exactly Day 41's profile.

NORMALIZING ACROSS CANDIDATE PROFILES -- what that means here, honestly:
  1. Scale: every round score is validated and converted to 0-100
     (`normalize_score`); out-of-range or NaN input is rejected loudly
     rather than clamped.
  2. Experience profile: a FRESHER has little work history, so the ATS
     round (resume/experience match) scores them low for reasons unrelated
     to ability. For freshers the ATS weight is halved and the two
     skill-test rounds get x1.15, then weights are renormalised to 1.
     The adjustment is listed in every score object.
  3. Applicability: a round the role does not use (technical rounds for a
     non-technical role) is NOT_APPLICABLE -- distinct from MISSING (the
     role needs it but it has not happened).
  4. Comparability: a score from 3 of 5 rounds is not comparable with one
     from all 5, so a candidate with any applicable round missing gets a
     PROVISIONAL fit and the recommendation "incomplete"; ranking only
     includes complete candidates, within one role type.
Cohort-relative normalization (z-scores/percentiles against other
candidates) is NOT done: it needs real cohort data this project does not
have, and it would make one candidate's score depend on who else applied.

EVIDENCE, NOT NUMBERS: several earlier engines return 0.0 when a round
had nothing to score (e.g. Day 47 with no scoreable answers). Treating
that as a real zero would silently punish the candidate, so the adapters
(`round_from_*`) read each result's evidence and report such a round as
MISSING instead.

TRANSPARENCY (the brief's explicit requirement): every score object
carries the weight profile id, the adjustments applied, per-round raw
score / base weight / adjusted weight / effective weight / contribution,
the formula, a leave-one-out SENSITIVITY (what the fit would be without
each round), flags, and a plain-language `explain()`.

The round-disagreement check ignores any round the profile deliberately
down-weighted (a fresher's ATS), so the fresher adjustment is not undone
by a second penalty in the form of a mandatory review.

SAFETY RULES: `automated_decision` is always "none". `recommendation`
is advice for a person. A "rejected" recommendation ALWAYS requires human
review. Review is also required for: a borderline score, a Day 49
integrity tag of MEDIUM/HIGH, a round that itself asked for review
(e.g. Day 50's keyword-scored system-design task), and strong
disagreement between rounds. Integrity tags and review flags never change
a number.

HONESTY: weights and thresholds are reasoned, not calibrated -- no
labelled hiring-outcome data exists, the same caveat every scoring day
since Day 34 has stated. The aggregate inherits every upstream limit; the
machine-test round, for instance, currently rests on results from a
sandbox that has not been built.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Dict, List, Mapping, Optional, Sequence

from parsers.hr_interview_question_bank import ExperienceLevel, RoleType

if TYPE_CHECKING:  # adapters are duck-typed; these imports are for readers and type checkers only
    from parsers.ats_scoring_engine import ATSScoreResult
    from parsers.hr_interview_scoring_engine import HRInterviewScoreReport
    from parsers.machine_test_evaluation_engine import MachineTestReport
    from parsers.screening_scoring_engine import ScreeningScoreResult
    from parsers.technical_skill_scoring_engine import TechnicalEvaluationReport

# ---------------------------------------------------------------------------
# Configuration -- reasoned, NOT calibrated against labelled data
# ---------------------------------------------------------------------------

ROUND_NAMES = ("ats", "screening", "hr_interview", "technical_interview", "machine_test")

SELECTED_THRESHOLD = 70.0    # carried over unchanged from Day 2 via Day 41
HOLD_THRESHOLD = 50.0        # carried over unchanged from Day 2 via Day 41
BORDERLINE_MARGIN = 3.0      # within this of a threshold -> a person should look
DISAGREEMENT_SPREAD = 35.0   # highest minus lowest round score at/above this -> flag

CONFIG_VERSION = "v1"

ROLE_WEIGHT_PROFILES: Dict[RoleType, Dict[str, float]] = {
    RoleType.TECHNICAL: {"ats": 0.10, "screening": 0.10, "hr_interview": 0.20, "technical_interview": 0.30, "machine_test": 0.30},
    RoleType.NON_TECHNICAL: {"ats": 0.25, "screening": 0.15, "hr_interview": 0.60, "technical_interview": 0.0, "machine_test": 0.0},
}

EXPERIENCE_MULTIPLIERS: Dict[ExperienceLevel, Dict[str, float]] = {
    ExperienceLevel.FRESHER: {"ats": 0.5, "technical_interview": 1.15, "machine_test": 1.15},
    ExperienceLevel.EXPERIENCED: {},
}

EXPERIENCE_REASONS: Dict[str, str] = {
    "ats": "limited work history makes resume/experience matching less informative",
    "technical_interview": "skill evidence matters more when there is little work history",
    "machine_test": "skill evidence matters more when there is little work history",
}

SCALES: Dict[str, float] = {"0-100": 100.0, "0-10": 10.0, "0-1": 1.0}

_INTEGRITY_SEVERITY = {"clear": 0, "low": 1, "medium": 2, "high": 3}
_INTEGRITY_REASON_PREFIX = "Interview integrity tag"    # Day 50's wording; the aggregator adds its own single line instead

NOT_IMPLEMENTED: Dict[str, str] = {
    "cohort_percentile_normalization": "Needs real cohort data, and would make a candidate's score depend on who else applied.",
    "calibration_against_hiring_outcomes": "No labelled hiring-outcome data exists; weights and thresholds are reasoned, not fitted.",
    "aggregate_fairness_analysis": "No disparate-impact analysis of the final score by group has been done.",
    "live_service_wiring": "Not connected to a database or API; scores are computed from result objects handed in.",
}

CAVEATS: List[str] = [
    "Weights and the 70/50 thresholds are reasoned, not calibrated; no labelled hiring-outcome data exists.",
    "The recommendation is advice for a person. Nothing here selects or rejects anyone automatically.",
    "An average can hide disagreement between rounds: read the per-round contributions and the sensitivity, not just the headline.",
    "A score is only as trustworthy as its weakest round (for example, machine-test results still depend on a sandbox that has not been built).",
    "The fresher adjustment is a judgement call: it is listed in every score and can be overridden with custom weights.",
    "Provisional scores (missing rounds) are not comparable with complete ones.",
]


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def normalize_score(value: float, scale: str = "0-100") -> float:
    """Convert a round's native score to 0-100. Bad input is rejected, never clamped."""
    if scale not in SCALES:
        raise ValueError(f"Unknown scale '{scale}'. Supported: {', '.join(SCALES)}.")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or math.isnan(value):
        raise ValueError("Score must be a real number.")
    if value < 0 or value > SCALES[scale]:
        raise ValueError(f"Score {value} is outside the {scale} scale.")
    return round(value / SCALES[scale] * 100.0, 4)


@dataclass
class RoundResult:
    """One round's headline result. `score=None` means the round has no evidence."""
    round_name: str
    score: Optional[float] = None
    scale: str = "0-100"
    review_reasons: List[str] = field(default_factory=list)
    integrity_risk_tag: Optional[str] = None
    note: str = ""

    def __post_init__(self) -> None:
        if self.round_name not in ROUND_NAMES:
            raise ValueError(f"Unknown round '{self.round_name}'. Expected one of {ROUND_NAMES}.")
        if self.score is not None:
            normalize_score(self.score, self.scale)          # validates

    @property
    def normalized(self) -> Optional[float]:
        return None if self.score is None else normalize_score(self.score, self.scale)


class RoundStatus(str, Enum):
    SCORED = "scored"
    MISSING = "missing"                  # the role needs this round and it has no evidence yet
    NOT_APPLICABLE = "not_applicable"    # the role does not use this round


# ---------------------------------------------------------------------------
# Adapters: read each earlier engine's result object, judge its EVIDENCE
# ---------------------------------------------------------------------------

def _no_evidence(name: str, note: str) -> RoundResult:
    return RoundResult(name, None, note=note)


def round_from_ats(result: Optional["ATSScoreResult"]) -> RoundResult:
    if result is None:
        return _no_evidence("ats", "No ATS result provided.")
    if not any(getattr(c, "available", False) for c in result.components):
        return _no_evidence("ats", "ATS result has no available component, so its score is not evidence.")
    return RoundResult("ats", result.overall_score, note=f"ATS role category: {result.role_category}")


def round_from_screening(result: Optional["ScreeningScoreResult"]) -> RoundResult:
    if result is None:
        return _no_evidence("screening", "No screening result provided.")
    if not result.question_scores:
        return _no_evidence("screening", "Screening scored no answers (its 0.0 is not a real score).")
    return RoundResult("screening", result.total_score, note=f"{len(result.question_scores)} screening answer(s) scored")


def round_from_hr(report: Optional["HRInterviewScoreReport"]) -> RoundResult:
    if report is None:
        return _no_evidence("hr_interview", "No HR interview report provided.")
    if report.num_questions_answered <= 0:
        return _no_evidence("hr_interview", "HR interview had no answered questions (its 0.0 is not a real score).")
    return RoundResult("hr_interview", report.overall_hr_score, note=f"{report.num_questions_answered} HR answer(s) scored")


def round_from_technical(report: Optional["TechnicalEvaluationReport"]) -> RoundResult:
    if report is None:
        return _no_evidence("technical_interview", "No technical evaluation report provided.")
    if not report.answer_evaluations:
        return _no_evidence("technical_interview", "Technical interview had no scoreable answers (its 0.0 is not a real score).")
    return RoundResult("technical_interview", report.overall_score, note=f"{len(report.answer_evaluations)} technical answer(s) scored")


def round_from_machine_test(report: Optional["MachineTestReport"]) -> RoundResult:
    """Carries the machine test's own review reasons and Day 49 integrity tag forward.
    Its integrity-tag reason is dropped here because the aggregator adds one consolidated line."""
    if report is None:
        return _no_evidence("machine_test", "No machine test report provided.")
    if not report.tasks:
        return _no_evidence("machine_test", "Machine test contains no evaluated tasks.")
    reasons = [r for r in report.human_review_reasons if _INTEGRITY_REASON_PREFIX not in r]
    return RoundResult("machine_test", report.overall_score, review_reasons=reasons,
                       integrity_risk_tag=report.integrity_risk_tag,
                       note=f"difficulty-weighted over {len(report.tasks)} task(s)")


# ---------------------------------------------------------------------------
# Weights
# ---------------------------------------------------------------------------

def _validate_weights(weights: Mapping[str, float]) -> Dict[str, float]:
    if set(weights) != set(ROUND_NAMES):
        raise ValueError(f"Weights must define exactly these rounds: {ROUND_NAMES}.")
    if any(w < 0 for w in weights.values()):
        raise ValueError("Weights must be >= 0.")
    if abs(sum(weights.values()) - 1.0) > 0.001:
        raise ValueError(f"Weights must sum to 1.0, got {sum(weights.values()):.4f}.")
    return dict(weights)


def resolve_weights(role_type: RoleType, experience_level: ExperienceLevel,
                    custom_weights: Optional[Mapping[str, float]] = None):
    """Returns (base_weights, adjusted_weights, adjustment_notes, profile_id).
    Custom weights are used exactly as given: no experience adjustment is applied to an explicit override."""
    if custom_weights is not None:
        w = _validate_weights(custom_weights)
        return w, dict(w), ["Custom weights supplied; used as given (no experience adjustment)."], "custom"

    base = _validate_weights(ROLE_WEIGHT_PROFILES[role_type])
    multipliers = EXPERIENCE_MULTIPLIERS[experience_level]
    scaled = {r: base[r] * multipliers.get(r, 1.0) for r in ROUND_NAMES}
    total = sum(scaled.values())
    adjusted = {r: scaled[r] / total for r in ROUND_NAMES}
    notes = [f"{experience_level.value.capitalize()} profile: {r} weight x{m} ({EXPERIENCE_REASONS[r]})."
             for r, m in multipliers.items() if base[r] > 0]
    if notes:
        notes.append("Weights renormalised to sum to 1.")
    return base, adjusted, notes, f"{role_type.value}/{experience_level.value}/{CONFIG_VERSION}"


def _fit(adjusted: Mapping[str, float], scores: Mapping[str, Optional[float]], exclude: Optional[str] = None) -> Optional[float]:
    live = {r: s for r, s in scores.items() if s is not None and adjusted[r] > 0 and r != exclude}
    total = sum(adjusted[r] for r in live)
    if total <= 0:
        return None
    return sum(s * adjusted[r] for r, s in live.items()) / total


# ---------------------------------------------------------------------------
# Output object
# ---------------------------------------------------------------------------

@dataclass
class RoundContribution:
    round_name: str
    status: RoundStatus
    score: Optional[float]            # 0-100
    base_weight: float                # role profile
    adjusted_weight: float            # after the experience adjustment
    effective_weight: float           # after redistributing missing / not-applicable rounds
    contribution: float               # score x effective weight
    note: str = ""

    def to_dict(self) -> Dict:
        return {"round_name": self.round_name, "status": self.status.value, "score": self.score,
                "base_weight": round(self.base_weight, 4), "adjusted_weight": round(self.adjusted_weight, 4),
                "effective_weight": round(self.effective_weight, 4), "contribution": self.contribution, "note": self.note}


@dataclass
class ScoreFlag:
    code: str
    message: str

    def to_dict(self) -> Dict:
        return {"code": self.code, "message": self.message}


@dataclass
class CrossRoundCandidateScore:
    """The unified candidate score object (Day 51 deliverable)."""
    candidate_id: Optional[str]
    role_type: RoleType
    experience_level: ExperienceLevel
    weight_profile_id: str
    hiring_fit_percentage: Optional[float]
    recommendation: str                       # selected | hold | rejected | incomplete
    provisional: bool
    coverage: float                           # share of applicable weight that has evidence, 0-1
    contributions: List[RoundContribution]
    missing_rounds: List[str]
    not_applicable_rounds: List[str]
    adjustments: List[str]
    sensitivity: Dict[str, Optional[float]]   # hiring fit if that round were left out
    flags: List[ScoreFlag]
    human_review_required: bool
    human_review_reasons: List[str]
    integrity_risk_tag: Optional[str]
    automated_decision: str = "none"
    formula: str = "hiring_fit = sum(score_r x effective_weight_r) over scored rounds; effective_weight_r = adjusted_weight_r / sum(adjusted_weight of scored rounds)"
    not_implemented: Dict[str, str] = field(default_factory=lambda: dict(NOT_IMPLEMENTED))
    caveats: List[str] = field(default_factory=lambda: list(CAVEATS))

    def to_dict(self) -> Dict:
        return {
            "candidate_id": self.candidate_id, "role_type": self.role_type.value,
            "experience_level": self.experience_level.value, "weight_profile_id": self.weight_profile_id,
            "hiring_fit_percentage": self.hiring_fit_percentage, "recommendation": self.recommendation,
            "provisional": self.provisional, "coverage": round(self.coverage, 4),
            "automated_decision": self.automated_decision,
            "human_review_required": self.human_review_required, "human_review_reasons": self.human_review_reasons,
            "integrity_risk_tag": self.integrity_risk_tag,
            "formula": self.formula, "adjustments": self.adjustments,
            "contributions": [c.to_dict() for c in self.contributions],
            "missing_rounds": self.missing_rounds, "not_applicable_rounds": self.not_applicable_rounds,
            "sensitivity": self.sensitivity, "flags": [f.to_dict() for f in self.flags],
            "not_implemented": self.not_implemented, "caveats": self.caveats,
        }

    def explain(self) -> str:
        """Plain-language account of how the number was produced."""
        if self.hiring_fit_percentage is None:
            return f"No round has been scored for {self.candidate_id or 'this candidate'} yet, so there is no Hiring Fit Score."
        scored = [c for c in self.contributions if c.status is RoundStatus.SCORED]
        top = max(scored, key=lambda c: c.contribution)
        lines = [
            f"Hiring Fit Score {self.hiring_fit_percentage}% for {self.candidate_id or 'this candidate'} "
            f"({self.role_type.value} role, {self.experience_level.value}; weight profile {self.weight_profile_id}).",
            "It is a weighted average of the rounds below: " + "; ".join(
                f"{c.round_name} {c.score:g} at {c.effective_weight:.0%} weight = {c.contribution:g} points" for c in scored) + ".",
            f"The largest contribution came from {top.round_name} ({top.contribution:g} points).",
        ]
        if self.adjustments:
            lines.append("Weight adjustments: " + " ".join(self.adjustments))
        if self.not_applicable_rounds:
            lines.append("Not used for this role: " + ", ".join(self.not_applicable_rounds) + ".")
        if self.missing_rounds:
            lines.append(f"PROVISIONAL: still waiting on {', '.join(self.missing_rounds)}; the remaining weights were "
                         f"scaled up, so this number is not comparable with a complete one (coverage {self.coverage:.0%}).")
        real = {k: v for k, v in self.sensitivity.items() if v is not None}
        if real:
            swing = max(real.items(), key=lambda kv: abs(kv[1] - self.hiring_fit_percentage))
            delta = swing[1] - self.hiring_fit_percentage
            if abs(delta) < 0.5:
                lines.append("No single round changes the score by more than half a point, so the result does not lean on any one round.")
            else:
                lines.append(f"Without {swing[0]} the score would be {swing[1]:.1f}% ({delta:+.1f}): the round the result leans on most.")
        lines.append(f"Recommendation: {self.recommendation.upper()} (advice for a person, not a decision).")
        if self.human_review_reasons:
            lines.append("Needs human review because: " + " | ".join(self.human_review_reasons))
        return "\n".join(lines)

    def to_summary_text(self) -> str:
        head = "PROVISIONAL " if self.provisional else ""
        fit = "n/a" if self.hiring_fit_percentage is None else f"{self.hiring_fit_percentage}%"
        lines = [
            "Cross-Round Hiring Intelligence Score",
            "=" * 40,
            f"Candidate: {self.candidate_id or '(unspecified)'} | {self.role_type.value} role | {self.experience_level.value}",
            f"{head}Hiring Fit Score: {fit} -> recommendation: {self.recommendation.upper()} (coverage {self.coverage:.0%})",
            f"Automated decision: none. Human review required: {'YES' if self.human_review_required else 'no'}.",
            "", "Rounds:",
        ]
        for c in self.contributions:
            if c.status is RoundStatus.NOT_APPLICABLE:
                lines.append(f"  - {c.round_name}: not applicable for this role")
            elif c.status is RoundStatus.MISSING:
                lines.append(f"  - {c.round_name}: MISSING (profile weight {c.adjusted_weight:.0%})")
            else:
                lines.append(f"  - {c.round_name}: {c.score:g} x {c.effective_weight:.1%} = {c.contribution:g}")
        for f in self.flags:
            lines.append(f"  ! {f.code}: {f.message}")
        if self.human_review_reasons:
            lines += ["", "Review reasons:"] + [f"  - {r}" for r in self.human_review_reasons]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _index_rounds(rounds: Sequence[RoundResult]) -> Dict[str, RoundResult]:
    indexed: Dict[str, RoundResult] = {}
    for r in rounds:
        if r.round_name in indexed:
            raise ValueError(f"Round '{r.round_name}' was supplied more than once.")
        indexed[r.round_name] = r
    return indexed


def compute_cross_round_score(
    rounds: Sequence[RoundResult],
    role_type: RoleType = RoleType.TECHNICAL,
    experience_level: ExperienceLevel = ExperienceLevel.EXPERIENCED,
    candidate_id: Optional[str] = None,
    custom_weights: Optional[Mapping[str, float]] = None,
    integrity_risk_tag=None,
) -> CrossRoundCandidateScore:
    """Combine the supplied round results into one Hiring Fit Score with full transparency.

    `integrity_risk_tag` may be Day 49's IntegrityRiskTag or its string value. It can add a
    review requirement; it never changes a number."""
    indexed = _index_rounds(rounds)
    base, adjusted, adjustments, profile_id = resolve_weights(role_type, experience_level, custom_weights)

    scores: Dict[str, Optional[float]] = {}
    status: Dict[str, RoundStatus] = {}
    flags: List[ScoreFlag] = []
    for name in ROUND_NAMES:
        supplied = indexed.get(name).normalized if name in indexed else None
        if adjusted[name] <= 0:
            status[name], scores[name] = RoundStatus.NOT_APPLICABLE, None
            if supplied is not None:
                flags.append(ScoreFlag("ROUND_NOT_APPLICABLE_IGNORED", f"A {name} score was supplied but this role does not use that round; it was ignored."))
        elif supplied is None:
            status[name], scores[name] = RoundStatus.MISSING, None
        else:
            status[name], scores[name] = RoundStatus.SCORED, supplied

    missing = [n for n in ROUND_NAMES if status[n] is RoundStatus.MISSING]
    not_applicable = [n for n in ROUND_NAMES if status[n] is RoundStatus.NOT_APPLICABLE]
    scored_names = [n for n in ROUND_NAMES if status[n] is RoundStatus.SCORED]
    scored_weight = sum(adjusted[n] for n in scored_names)
    coverage = scored_weight / sum(adjusted[n] for n in ROUND_NAMES if adjusted[n] > 0)

    raw_fit = _fit(adjusted, scores)
    fit = None if raw_fit is None else round(max(0.0, min(100.0, raw_fit)), 2)

    contributions: List[RoundContribution] = []
    for name in ROUND_NAMES:
        eff = adjusted[name] / scored_weight if status[name] is RoundStatus.SCORED and scored_weight > 0 else 0.0
        points = round(scores[name] * eff, 2) if scores[name] is not None else 0.0
        contributions.append(RoundContribution(name, status[name], scores[name], base[name], adjusted[name], eff, points,
                                               indexed[name].note if name in indexed else ""))

    sensitivity: Dict[str, Optional[float]] = {}
    if len(scored_names) >= 2:
        for name in scored_names:
            other = _fit(adjusted, scores, exclude=name)
            sensitivity[name] = None if other is None else round(other, 2)

    # --- recommendation and review logic -----------------------------------
    provisional = bool(missing) or fit is None
    if provisional:
        recommendation = "incomplete"
    elif fit >= SELECTED_THRESHOLD:
        recommendation = "selected"
    elif fit >= HOLD_THRESHOLD:
        recommendation = "hold"
    else:
        recommendation = "rejected"

    reasons: List[str] = []
    if missing:
        flags.append(ScoreFlag("MISSING_ROUNDS", f"Waiting on: {', '.join(missing)}. The fit shown is provisional."))
    for name in scored_names:
        reasons += [f"{name}: {r}" for r in indexed[name].review_reasons]

    # Disagreement is judged only among rounds the profile did NOT deliberately down-weight: a fresher's
    # thin resume is expected to differ from their skill scores, and flagging that would penalise them twice.
    comparable = [n for n in scored_names if adjusted[n] >= base[n] - 1e-9]
    if len(comparable) >= 2:
        spread = max(scores[n] for n in comparable) - min(scores[n] for n in comparable)
        if spread >= DISAGREEMENT_SPREAD:
            hi = max(comparable, key=lambda n: scores[n])
            lo = min(comparable, key=lambda n: scores[n])
            flags.append(ScoreFlag("ROUND_DISAGREEMENT", f"{hi} ({scores[hi]:g}) and {lo} ({scores[lo]:g}) differ by {spread:.0f} points."))
            reasons.append(f"Rounds disagree strongly ({hi} {scores[hi]:g} vs {lo} {scores[lo]:g}); an average hides that.")

    if not provisional and any(abs(fit - t) <= BORDERLINE_MARGIN for t in (SELECTED_THRESHOLD, HOLD_THRESHOLD)):
        flags.append(ScoreFlag("BORDERLINE", f"Hiring fit {fit} is within {BORDERLINE_MARGIN:g} points of a recommendation threshold."))
        reasons.append("Score is borderline: a small change in any round would change the recommendation.")

    if recommendation == "rejected":
        reasons.append("Rejection recommendations are always reviewed by a person; nothing is rejected automatically.")

    tags = [getattr(integrity_risk_tag, "value", integrity_risk_tag)] + [indexed[n].integrity_risk_tag for n in scored_names]
    tags = [str(t) for t in tags if t]
    worst = max(tags, key=lambda t: _INTEGRITY_SEVERITY.get(t, 0)) if tags else None
    if worst in ("medium", "high"):
        flags.append(ScoreFlag("INTEGRITY_REVIEW", f"Interview integrity tag is {worst.upper()} (Day 49)."))
        reasons.append(f"Interview integrity tag is {worst.upper()} (Day 49): review the session before relying on this score.")

    return CrossRoundCandidateScore(
        candidate_id=candidate_id, role_type=role_type, experience_level=experience_level, weight_profile_id=profile_id,
        hiring_fit_percentage=fit, recommendation=recommendation, provisional=provisional, coverage=coverage,
        contributions=contributions, missing_rounds=missing, not_applicable_rounds=not_applicable, adjustments=adjustments,
        sensitivity=sensitivity, flags=flags, human_review_required=bool(reasons), human_review_reasons=reasons,
        integrity_risk_tag=worst,
    )


def compute_from_round_outputs(
    ats=None, screening=None, hr=None, technical=None, machine_test=None, **kwargs,
) -> CrossRoundCandidateScore:
    """Convenience: pass the earlier engines' own result objects (or None) and the adapters judge their evidence."""
    rounds = [round_from_ats(ats), round_from_screening(screening), round_from_hr(hr),
              round_from_technical(technical), round_from_machine_test(machine_test)]
    return compute_cross_round_score(rounds, **kwargs)


# ---------------------------------------------------------------------------
# Ranking -- a sorting aid, comparable candidates only
# ---------------------------------------------------------------------------

@dataclass
class RankedCandidate:
    rank: int
    candidate_id: Optional[str]
    hiring_fit_percentage: float
    recommendation: str
    experience_level: str
    human_review_required: bool
    integrity_risk_tag: Optional[str] = None

    def to_dict(self) -> Dict:
        return dict(self.__dict__)


@dataclass
class CandidateRanking:
    ranked: List[RankedCandidate]
    not_comparable: List[Dict[str, str]]

    def to_dict(self) -> Dict:
        return {"ranked": [r.to_dict() for r in self.ranked], "not_comparable": self.not_comparable}


def rank_candidates(scores: Sequence[CrossRoundCandidateScore]) -> CandidateRanking:
    """Rank COMPLETE candidates for one role type. Fresher and experienced candidates for the
    same role are comparable (their weights are already profile-adjusted); different role types
    are not. Ties share a rank. Incomplete candidates are listed separately with the reason."""
    if len({s.role_type for s in scores}) > 1:
        raise ValueError("Rank candidates within one role type; fit scores for different role types are not comparable.")
    comparable = [s for s in scores if not s.provisional and s.hiring_fit_percentage is not None]
    skipped = [{"candidate_id": str(s.candidate_id), "reason": f"incomplete (waiting on: {', '.join(s.missing_rounds) or 'any round'})"}
               for s in scores if s.provisional or s.hiring_fit_percentage is None]
    ordered = sorted(comparable, key=lambda s: (-s.hiring_fit_percentage, str(s.candidate_id)))
    ranked: List[RankedCandidate] = []
    for idx, s in enumerate(ordered):
        rank = ranked[-1].rank if idx and s.hiring_fit_percentage == ranked[-1].hiring_fit_percentage else idx + 1
        ranked.append(RankedCandidate(rank, s.candidate_id, s.hiring_fit_percentage, s.recommendation,
                                      s.experience_level.value, s.human_review_required, s.integrity_risk_tag))
    return CandidateRanking(ranked, skipped)
