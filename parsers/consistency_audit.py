"""
Consistency Audit (Day 54) -- "improve consistency across rounds"

Consistency cannot be improved until it can be measured, so this module
makes two kinds of checks executable instead of leaving them as claims in
documents:

1. PROPERTY AUDIT -- invariants the aggregate (Day 51), the decision (Day
   52) and the ATS alignment (Day 54) must satisfy on every input, checked
   over dense deterministic grids (no randomness, so a failure reproduces):
     - raising any round's score never lowers the Hiring Fit
     - if every round has the same score v, the Hiring Fit is v
     - the order the rounds are supplied in does not matter
     - scores on 0-10 or 0-1 scales give the same result as 0-100
     - the Hiring Fit lies between the lowest and highest round score
     - Day 52's score band always equals Day 51's recommendation
     - a SELECTED decision never carries an unresolved review reason
     - the ATS alignment is strictly increasing, bounded, zone-preserving
   A failing property returns a concrete counterexample.

2. THRESHOLD REGISTRY -- every cut-off that decides something, where it
   lives, and the RELATIONSHIPS between them that must hold (a "strength"
   must score at least as high as a selection, a critical-round floor must
   sit below the hold threshold, and so on). A registry that is checked is
   how two modules end up disagreeing about what "good" means without
   anyone noticing, which is what happened with the ATS scale.

The audit found real things; see the Day 54 optimization report. A relationship
that does NOT hold is returned as a finding, not hidden or "fixed" silently.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from parsers import cross_round_aggregation_engine as agg
from parsers import final_recommendation_engine as dec
from parsers import hiring_report_generator as rep
from parsers import scoring_calibration as cal
from parsers import ranking_engine as ats_rank
from parsers.cross_round_aggregation_engine import ROUND_NAMES, RoundResult, compute_cross_round_score
from parsers.final_recommendation_engine import decide
from parsers.hr_interview_question_bank import ExperienceLevel, RoleType

TECH, NON_TECH = RoleType.TECHNICAL, RoleType.NON_TECHNICAL
EXPERIENCED, FRESHER = ExperienceLevel.EXPERIENCED, ExperienceLevel.FRESHER
LEVELS = (20.0, 50.0, 80.0)
TOLERANCE = 1e-6


@dataclass
class PropertyResult:
    name: str
    description: str
    passed: bool
    cases_checked: int
    counterexample: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "description": self.description, "passed": self.passed,
                "cases_checked": self.cases_checked, "counterexample": self.counterexample}


def _rounds(values: Dict[str, Optional[float]], scale: str = "0-100") -> List[RoundResult]:
    return [RoundResult(n, v, scale=scale) for n, v in values.items() if v is not None]


def _vectors():
    for combo in itertools.product(LEVELS, repeat=len(ROUND_NAMES)):
        yield dict(zip(ROUND_NAMES, combo))


def _profiles():
    return [(TECH, EXPERIENCED), (TECH, FRESHER), (NON_TECH, EXPERIENCED), (NON_TECH, FRESHER)]


def _check(name: str, description: str, cases: Callable[[], Any]) -> PropertyResult:
    """`cases` is a generator that yields None for each passing case and a counterexample dict for a failure."""
    count = 0
    for outcome in cases():
        count += 1
        if outcome is not None:
            return PropertyResult(name, description, False, count, outcome)
    return PropertyResult(name, description, True, count)


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------

def prop_monotone() -> PropertyResult:
    def cases():
        for role, exp in _profiles():
            for vec in _vectors():
                base = compute_cross_round_score(_rounds(vec), role, exp).hiring_fit_percentage
                for name in ROUND_NAMES:
                    bumped = dict(vec)
                    bumped[name] = vec[name] + 10.0
                    up = compute_cross_round_score(_rounds(bumped), role, exp).hiring_fit_percentage
                    yield None if up + TOLERANCE >= base else {"role": role.value, "experience": exp.value, "scores": vec, "raised": name, "before": base, "after": up}
    return _check("monotone_in_each_round", "Raising any single round's score never lowers the Hiring Fit.", cases)


def prop_equal_scores() -> PropertyResult:
    def cases():
        for role, exp in _profiles():
            for v in range(0, 101, 10):
                fit = compute_cross_round_score(_rounds({n: float(v) for n in ROUND_NAMES}), role, exp).hiring_fit_percentage
                yield None if abs(fit - v) <= 0.011 else {"role": role.value, "experience": exp.value, "all_rounds": v, "fit": fit}
    return _check("equal_scores_give_that_score", "If every round scores v, the Hiring Fit is v (profile weights must not invent or lose points).", cases)


def prop_order_invariance() -> PropertyResult:
    def cases():
        sample = [v for i, v in enumerate(_vectors()) if i % 17 == 0]
        for role, exp in _profiles():
            for vec in sample:
                forward = compute_cross_round_score(_rounds(vec), role, exp, "c").to_dict()
                reverse = compute_cross_round_score(list(reversed(_rounds(vec))), role, exp, "c").to_dict()
                yield None if forward == reverse else {"role": role.value, "scores": vec}
    return _check("round_order_does_not_matter", "The order in which round results are supplied does not change the result.", cases)


def prop_scale_invariance() -> PropertyResult:
    def cases():
        for vec in (v for i, v in enumerate(_vectors()) if i % 23 == 0):
            for scale, divisor in (("0-10", 10.0), ("0-1", 100.0)):
                a = compute_cross_round_score(_rounds(vec), TECH, EXPERIENCED).hiring_fit_percentage
                b = compute_cross_round_score(_rounds({k: v / divisor for k, v in vec.items()}, scale), TECH, EXPERIENCED).hiring_fit_percentage
                yield None if abs(a - b) <= TOLERANCE else {"scale": scale, "scores": vec, "fit_100": a, "fit_scaled": b}
    return _check("scale_conversion_is_exact", "A score given on a 0-10 or 0-1 scale gives the same Hiring Fit as the equivalent 0-100 score.", cases)


def prop_fit_within_range() -> PropertyResult:
    def cases():
        for role, exp in _profiles():
            for vec in _vectors():
                c = compute_cross_round_score(_rounds(vec), role, exp)
                scored = [x.score for x in c.contributions if x.score is not None]
                fit = c.hiring_fit_percentage
                yield None if min(scored) - 0.011 <= fit <= max(scored) + 0.011 else {"scores": vec, "fit": fit}
    return _check("fit_between_lowest_and_highest_round", "The Hiring Fit lies between the lowest and the highest scored round.", cases)


def prop_band_agreement() -> PropertyResult:
    names = {"selected": "selected", "hold": "hold_review", "rejected": "rejected"}
    def cases():
        for role, exp in _profiles():
            for vec in _vectors():
                s = compute_cross_round_score(_rounds(vec), role, exp, "c")
                d = decide(s)
                yield None if names[s.recommendation] == d.score_band.value else {"scores": vec, "day51": s.recommendation, "day52_band": d.score_band.value}
    return _check("day51_and_day52_bands_agree", "Day 52's score band always equals Day 51's recommendation for a complete candidate.", cases)


def prop_selected_is_clean() -> PropertyResult:
    def cases():
        for role, exp in _profiles():
            for vec in _vectors():
                for tag in (None, "low", "medium", "high"):
                    s = compute_cross_round_score(_rounds(vec), role, exp, "c", integrity_risk_tag=tag)
                    d = decide(s)
                    ok = d.outcome is not dec.DecisionOutcome.SELECTED or (not s.human_review_required and (tag in (None, "low")))
                    yield None if ok else {"scores": vec, "integrity": tag, "outcome": d.outcome.value, "review_reasons": s.human_review_reasons}
    return _check("selected_never_carries_a_review_reason", "A SELECTED decision never coexists with an unresolved review reason or a MEDIUM/HIGH integrity tag.", cases)


def prop_alignment() -> PropertyResult:
    def cases():
        for category in (None, "tech", "business", "creative"):
            cuts = ats_rank.CATEGORY_THRESHOLDS.get(category, ats_rank.DEFAULT_THRESHOLDS) if category else ats_rank.DEFAULT_THRESHOLDS
            prev = -1.0
            for raw in [x / 4 for x in range(0, 401)]:
                a = cal.align_ats_score(raw, category)
                ok = 0.0 <= a <= 100.0 and a >= prev - 1e-9
                if raw >= cuts["shortlist"]:
                    ok = ok and a >= cal.COMMON_SELECTED - 1e-9
                elif raw >= cuts["review"]:
                    ok = ok and cal.COMMON_HOLD - 1e-9 <= a < cal.COMMON_SELECTED + 1e-9
                else:
                    ok = ok and a < cal.COMMON_HOLD
                prev = a
                yield None if ok else {"category": category, "raw": raw, "aligned": a}
    return _check("ats_alignment_is_monotone_bounded_zone_preserving", "The ATS alignment never reorders candidates, stays within 0-100, and keeps every ATS zone in the matching aggregate band.", cases)


PROPERTIES: List[Callable[[], PropertyResult]] = [
    prop_monotone, prop_equal_scores, prop_order_invariance, prop_scale_invariance, prop_fit_within_range,
    prop_band_agreement, prop_selected_is_clean, prop_alignment,
]


def run_property_audit() -> List[PropertyResult]:
    return [p() for p in PROPERTIES]


# ---------------------------------------------------------------------------
# Threshold registry
# ---------------------------------------------------------------------------

@dataclass
class ThresholdEntry:
    name: str
    value: float
    location: str
    meaning: str

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class RelationshipResult:
    statement: str
    holds: bool
    detail: str
    finding: str = ""            # filled when it does NOT hold

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


def threshold_registry() -> List[ThresholdEntry]:
    tech, biz = ats_rank.CATEGORY_THRESHOLDS["tech"], ats_rank.CATEGORY_THRESHOLDS["business"]
    pol = dec.DecisionPolicy()
    return [
        ThresholdEntry("selected_threshold", agg.SELECTED_THRESHOLD, "cross_round_aggregation_engine", "Hiring Fit at/above this is recommended for selection"),
        ThresholdEntry("hold_threshold", agg.HOLD_THRESHOLD, "cross_round_aggregation_engine", "Hiring Fit below this is recommended for rejection"),
        ThresholdEntry("borderline_margin", agg.BORDERLINE_MARGIN, "cross_round_aggregation_engine", "Within this of a threshold -> human review"),
        ThresholdEntry("disagreement_spread", agg.DISAGREEMENT_SPREAD, "cross_round_aggregation_engine", "Round scores this far apart -> human review"),
        ThresholdEntry("critical_floor_technical_round", dec.CRITICAL_ROUND_FLOORS["technical"]["technical_interview"], "final_recommendation_engine", "A skill round below this blocks selection"),
        ThresholdEntry("critical_floor_hr_round_nontech", dec.CRITICAL_ROUND_FLOORS["non_technical"]["hr_interview"], "final_recommendation_engine", "HR round below this blocks selection (non-technical)"),
        ThresholdEntry("min_select_confidence", pol.min_select_confidence, "final_recommendation_engine", "Confidence below this blocks selection"),
        ThresholdEntry("min_reject_confidence", pol.min_reject_confidence, "final_recommendation_engine", "Confidence below this turns a rejection into a review"),
        ThresholdEntry("auto_min_confidence", pol.auto_min_confidence, "final_recommendation_engine", "Confidence needed for auto-advance"),
        ThresholdEntry("strength_min", rep.STRENGTH_MIN, "hiring_report_generator", "A score at/above this is reported as a strength"),
        ThresholdEntry("weakness_max", rep.WEAKNESS_MAX, "hiring_report_generator", "A score below this is reported as a weakness"),
        ThresholdEntry("ats_shortlist_tech", tech["shortlist"], "ranking_engine", "RAW ATS score for SHORTLIST (tech)"),
        ThresholdEntry("ats_shortlist_business", biz["shortlist"], "ranking_engine", "RAW ATS score for SHORTLIST (business)"),
        ThresholdEntry("ats_review", tech["review"], "ranking_engine", "RAW ATS score for REVIEW"),
        ThresholdEntry("ats_skill_floor", ats_rank.SKILL_RELEVANCE_FLOOR, "ranking_engine", "ATS skill match below this is an automatic REJECT"),
    ]


def check_threshold_relationships() -> List[RelationshipResult]:
    pol = dec.DecisionPolicy()
    tech = ats_rank.CATEGORY_THRESHOLDS["tech"]
    floors = [v for group in dec.CRITICAL_ROUND_FLOORS.values() for v in group.values()]
    checks = [
        ("hold threshold is below the selection threshold", agg.HOLD_THRESHOLD < agg.SELECTED_THRESHOLD,
         f"{agg.HOLD_THRESHOLD:g} < {agg.SELECTED_THRESHOLD:g}", ""),
        ("Day 52 policy defaults equal Day 51's thresholds", (pol.selected_threshold, pol.hold_threshold) == (agg.SELECTED_THRESHOLD, agg.HOLD_THRESHOLD),
         f"({pol.selected_threshold:g}, {pol.hold_threshold:g}) vs ({agg.SELECTED_THRESHOLD:g}, {agg.HOLD_THRESHOLD:g})", ""),
        ("a reported 'strength' scores at least as high as a selection", rep.STRENGTH_MIN >= agg.SELECTED_THRESHOLD,
         f"{rep.STRENGTH_MIN:g} >= {agg.SELECTED_THRESHOLD:g}", ""),
        ("a reported 'weakness' is exactly a below-hold score", rep.WEAKNESS_MAX == agg.HOLD_THRESHOLD,
         f"{rep.WEAKNESS_MAX:g} == {agg.HOLD_THRESHOLD:g}", ""),
        ("every critical-round floor sits below the hold threshold", all(f < agg.HOLD_THRESHOLD for f in floors),
         f"floors {sorted(set(floors))} < {agg.HOLD_THRESHOLD:g}", ""),
        ("borderline margins around the two thresholds do not overlap", 2 * agg.BORDERLINE_MARGIN < agg.SELECTED_THRESHOLD - agg.HOLD_THRESHOLD,
         f"2 x {agg.BORDERLINE_MARGIN:g} < {agg.SELECTED_THRESHOLD - agg.HOLD_THRESHOLD:g}", ""),
        ("the ATS review cutoff is below its shortlist cutoff (every category)", all(c["review"] < c["shortlist"] for c in ats_rank.CATEGORY_THRESHOLDS.values()),
         "review < shortlist for each category", ""),
        ("the ATS shortlist cutoff is on the SAME scale as the selection threshold",
         tech["shortlist"] >= agg.SELECTED_THRESHOLD, f"raw ATS shortlist {tech['shortlist']:g} vs aggregate selection {agg.SELECTED_THRESHOLD:g}",
         "FINDING (fixed, opt-in): the raw ATS score is on a compressed scale, so an ATS shortlist never reaches the aggregate's selection bar. "
         "Use ats_scale='zone_aligned' (scoring_calibration.align_ats_score)."),
        ("rejecting needs at least as much confidence as selecting (Day 52's own stated rationale)", pol.min_reject_confidence >= pol.min_select_confidence,
         f"min_reject_confidence {pol.min_reject_confidence:g} vs min_select_confidence {pol.min_select_confidence:g}",
         "FINDING (not changed; existing tests pin it): Day 52 says shaky evidence must never be enough to recommend rejection because a wrong "
         "rejection costs more, yet the rejection floor (50) is BELOW the selection floor (55). Recommended: DecisionPolicy(min_reject_confidence=60)."),
    ]
    return [RelationshipResult(s, bool(ok), detail, "" if ok else finding) for s, ok, detail, finding in checks]
