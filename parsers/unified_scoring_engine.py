"""
Unified Scoring Engine (Day 41)

WHAT THIS DAY ADDS: `scoring/service.py`'s `DecisionScoringService` has
been a Day 2 skeleton since before any of the underlying engines
existed -- a flat weighted sum over five GUESSED field names
(`ats_score`, `screening_score`, `communication_score`,
`technical_score`, `behavior_score`) that only ever ran against a
hand-typed demo dict, never a real computed score. This day is the
first time genuine computed scores from all three rounds the project
actually built -- ATS (Days 9-20's `ats_scoring_engine`), Screening
(Day 26's `screening_scoring_engine`), and HR interview (Day 37's
`hr_interview_scoring_engine`) -- are combined for real, replacing
Day 2's guessed field set with the three genuine round outputs that
exist now, plus the configurable, role-aware weighting the brief
actually asks for.

REUSE, NOT REIMPLEMENTATION: this module takes each round's own
result object as input and reads its headline score --
`ATSScoreResult.overall_score`, `ScreeningScoreResult.total_score`,
`HRInterviewScoreReport.overall_hr_score` -- rather than recomputing
any of the resume parsing, question scoring, or interview evaluation
those numbers already represent. The missing-round weight
redistribution below reuses the PATTERN Day 13's `ats_scoring_engine`
already established internally for its own four components (missing
data gets its weight redistributed proportionally across what IS
available, flagged rather than silently zeroed) -- applied here one
level up, across whole ROUNDS instead of within one round.

TWO ROLE TAXONOMIES EXIST IN THIS PROJECT, STATED HONESTLY: Day 13's
ATS engine already has its own role-based weighting
(`tech`/`business`/`creative`/`default`, for weighting skill-match vs
experience vs education WITHIN the ATS score), and Day 33's HR
interview engine uses a separate `RoleType.TECHNICAL` /
`RoleType.NON_TECHNICAL` axis. This day's role-based adjustment is
CROSS-ROUND (how much to weight the whole ATS round vs the whole HR
interview round against each other), a different question from
either existing system, so it reuses HR's simpler two-value
`RoleType` directly rather than inventing a third taxonomy or trying
to force ATS's four-category one to answer a question it wasn't built
for. Reconciling the two taxonomies into one is explicitly out of
scope here -- named rather than silently ignored.

HIRING-FIT PERCENTAGE AND DECISION THRESHOLDS: the 0-100
`hiring_fit_percentage` and the selected/hold/rejected thresholds
(>=70 / >=50 / below) are carried over UNCHANGED from Day 2's original
`DecisionScoringService` stub -- these were the project's own
first-ever stated thresholds, and changing them now, with still no
labeled hiring-outcome data in this project, would just be swapping
one unvalidated number for another. Reusing the original numbers
rather than guessing new ones is the more honest choice.

ROLE-BASED CROSS-ROUND WEIGHTS: reasoned, not data-calibrated (the
same caveat stated on every scoring day since 34). Technical roles
weight the ATS round (skills/experience match) and the HR interview
round roughly evenly, with screening as a lighter-weight gate.
Non-technical roles weight the HR interview round -- where
communication and interpersonal signal actually show up -- more
heavily than the keyword-driven ATS round.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from parsers.hr_interview_question_bank import RoleType

_SELECTED_THRESHOLD = 70.0   # carried over unchanged from Day 2's DecisionScoringService
_HOLD_THRESHOLD = 50.0       # carried over unchanged from Day 2's DecisionScoringService

ROUND_NAMES = ("ats", "screening", "hr_interview")


@dataclass
class RoundWeights:
    ats: float
    screening: float
    hr_interview: float

    def validate(self) -> None:
        total = self.ats + self.screening + self.hr_interview
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"RoundWeights must sum to 1.0, got {total}")
        for name in ROUND_NAMES:
            value = getattr(self, name)
            if value < 0:
                raise ValueError(f"RoundWeights.{name} must be >= 0, got {value}")

    def as_dict(self) -> Dict[str, float]:
        return {"ats": self.ats, "screening": self.screening, "hr_interview": self.hr_interview}


# Cross-round weight profiles by role type -- see module docstring for
# the reasoning and the honest "not data-calibrated" caveat.
ROLE_WEIGHT_PROFILES: Dict[RoleType, RoundWeights] = {
    RoleType.TECHNICAL: RoundWeights(ats=0.40, screening=0.15, hr_interview=0.45),
    RoleType.NON_TECHNICAL: RoundWeights(ats=0.25, screening=0.15, hr_interview=0.60),
}


@dataclass
class RoundScores:
    """Each field is Optional because a candidate may not have
    completed every round yet -- see missing-round redistribution
    below rather than silently scoring an incomplete round as zero."""
    ats_score: Optional[float] = None
    screening_score: Optional[float] = None
    hr_interview_score: Optional[float] = None

    def as_dict(self) -> Dict[str, Optional[float]]:
        return {"ats": self.ats_score, "screening": self.screening_score, "hr_interview": self.hr_interview_score}


@dataclass
class ComponentContribution:
    round_name: str
    raw_score: Optional[float]
    base_weight: float
    effective_weight: float
    contribution: float
    included: bool


def _redistribute_weights(weights: RoundWeights, availability: Dict[str, bool]) -> Dict[str, float]:
    """Same PROPORTIONAL-REDISTRIBUTION pattern Day 13's ats_scoring_engine
    uses internally for its own missing components, applied here across
    whole rounds instead. A round's weight is only redistributed among
    the rounds that ARE available -- never silently dropped or treated
    as zero."""
    base = weights.as_dict()
    available = {k: v for k, v in base.items() if availability.get(k, False)}
    total_available = sum(available.values())
    if total_available <= 0:
        return {k: 0.0 for k in base}
    return {k: round(v / total_available, 6) for k, v in available.items()}


@dataclass
class UnifiedCandidateScore:
    candidate_id: Optional[str]
    role_type: RoleType
    hiring_fit_percentage: float
    decision: str
    weights_used: RoundWeights
    contributions: List[ComponentContribution]
    missing_rounds: List[str]

    def to_dict(self) -> Dict:
        return {
            "candidate_id": self.candidate_id,
            "role_type": self.role_type.value,
            "hiring_fit_percentage": self.hiring_fit_percentage,
            "decision": self.decision,
            "weights_used": self.weights_used.as_dict(),
            "missing_rounds": self.missing_rounds,
            "contributions": [
                {
                    "round_name": c.round_name, "raw_score": c.raw_score, "base_weight": c.base_weight,
                    "effective_weight": c.effective_weight, "contribution": c.contribution, "included": c.included,
                }
                for c in self.contributions
            ],
        }

    def to_summary_text(self) -> str:
        lines = [
            "Unified Hiring Intelligence Score",
            "=" * 40,
            f"Candidate: {self.candidate_id or '(unspecified)'}  |  Role type: {self.role_type.value}",
            f"Hiring-Fit Score: {self.hiring_fit_percentage}% -> Decision: {self.decision.upper()}",
            "",
            "Round contributions:",
        ]
        for c in self.contributions:
            status = f"raw={c.raw_score}" if c.included else "MISSING -- weight redistributed"
            lines.append(
                f"  - {c.round_name}: {status}, base_weight={c.base_weight}, "
                f"effective_weight={c.effective_weight}, contribution={c.contribution}"
            )
        if self.missing_rounds:
            lines.append("")
            lines.append(f"Missing rounds (weight redistributed proportionally): {', '.join(self.missing_rounds)}")
        return "\n".join(lines)


def compute_unified_score(
    round_scores: RoundScores,
    role_type: RoleType = RoleType.TECHNICAL,
    candidate_id: Optional[str] = None,
    weights: Optional[RoundWeights] = None,
) -> UnifiedCandidateScore:
    weights = weights or ROLE_WEIGHT_PROFILES[role_type]
    weights.validate()

    scores = round_scores.as_dict()
    availability = {k: (v is not None) for k, v in scores.items()}
    missing_rounds = [k for k, available in availability.items() if not available]

    effective_weights = _redistribute_weights(weights, availability)
    base_weights = weights.as_dict()

    contributions: List[ComponentContribution] = []
    weighted_total = 0.0
    for round_name in ROUND_NAMES:
        raw = scores[round_name]
        included = availability[round_name]
        eff_weight = effective_weights.get(round_name, 0.0)
        contribution = round((raw or 0.0) * eff_weight, 2) if included else 0.0
        weighted_total += contribution
        contributions.append(ComponentContribution(
            round_name=round_name, raw_score=raw, base_weight=base_weights[round_name],
            effective_weight=eff_weight, contribution=contribution, included=included,
        ))

    hiring_fit = round(max(0.0, min(100.0, weighted_total)), 2)
    decision = "selected" if hiring_fit >= _SELECTED_THRESHOLD else "hold" if hiring_fit >= _HOLD_THRESHOLD else "rejected"

    return UnifiedCandidateScore(
        candidate_id=candidate_id, role_type=role_type, hiring_fit_percentage=hiring_fit,
        decision=decision, weights_used=weights, contributions=contributions, missing_rounds=missing_rounds,
    )
