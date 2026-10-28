"""
Scoring Calibration (Day 54) -- putting the ATS round on the same scale as the others

THE DEFECT THIS FIXES (found on Day 54, introduced on Day 51):
Day 51's aggregate treats every round's 0-100 score as comparable. For the
ATS round it is not. The ATS engine's scores structurally top out well
below 100 -- Day 17 and Day 20 documented that its weight profiles cap a
genuinely strong match at roughly 50-60 -- which is why the ATS has its OWN
zone cutoffs (shortlist at 47 for tech and 55 for business, review at 25)
instead of the aggregate's 70 / 50.

Measured on the project's 12 human-labelled resume/job pairs: reading the
raw ATS score through the aggregate's 70 / 50 bands agrees with the human
zone in only 6 of 12 pairs, and NONE of the 4 pairs a human shortlisted
reaches 70. A candidate the ATS itself shortlisted therefore enters the
aggregate looking "mediocre", drags the Hiring Fit down, and trips the
round-disagreement flag against rounds that DO use the full 0-100 range.

THE FIX: a monotone, piecewise-linear alignment anchored on the cutoffs the
ATS already has, not on new fitted numbers:

    raw 0                 -> 0
    raw = review cutoff   -> 50   (the aggregate's hold threshold)
    raw = shortlist cutoff-> 70   (the aggregate's selection threshold)
    raw 100               -> 100

so "the ATS says shortlist" and "the aggregate says selectable" mean the
same thing. Properties (tested over a dense grid): strictly increasing,
continuous, bounded 0-100, and zone-preserving -- an ATS shortlist always
lands at >= 70, a review at 50-70, a reject below 50. It never reorders
candidates; it only changes the scale.

WHAT THIS IS NOT: a re-fit. No new threshold is learned from the 12 pairs.
It is also not validated against hiring outcomes (none exist). And it only
addresses the ATS round: the screening, HR, technical and machine-test
rounds may have their own scale quirks that cannot be checked without
labelled data.

OPT-IN: the default for the aggregate stays "raw" so no earlier day's
results change silently; pass `ats_scale="zone_aligned"` to use it. The
recommendation in the Day 54 report is to switch the default after review.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from parsers.ranking_engine import CATEGORY_THRESHOLDS, DEFAULT_THRESHOLDS, SKILL_RELEVANCE_FLOOR

# The aggregate's bands (Day 2 -> Day 41 -> Day 51). Imported lazily by callers' tests against
# Day 51's own constants so the two cannot drift apart.
COMMON_HOLD = 50.0
COMMON_SELECTED = 70.0

ATS_SCALES = ("raw", "zone_aligned")

# Just under the hold threshold: where an ATS skill-floor rejection lands on the common scale.
FLOOR_CAP = COMMON_HOLD - 0.01


def _anchors(role_category: Optional[str]) -> List[Tuple[float, float]]:
    cuts: Dict[str, float] = CATEGORY_THRESHOLDS.get(role_category, DEFAULT_THRESHOLDS) if role_category else DEFAULT_THRESHOLDS
    review, shortlist = float(cuts["review"]), float(cuts["shortlist"])
    if not 0.0 < review < shortlist < 100.0:
        raise ValueError(f"ATS cutoffs must satisfy 0 < review < shortlist < 100, got review={review}, shortlist={shortlist}.")
    return [(0.0, 0.0), (review, COMMON_HOLD), (shortlist, COMMON_SELECTED), (100.0, 100.0)]


def align_ats_score(raw: float, role_category: Optional[str] = None, skill_match_score: Optional[float] = None) -> float:
    """Map a raw ATS score (0-100) onto the common scale, anchored on the ATS's own zone cutoffs.

    `skill_match_score` (optional) lets the alignment honour the ATS's hard skill-relevance floor: the ATS
    rejects any candidate whose skill match is below SKILL_RELEVANCE_FLOOR regardless of the overall score
    (Day 20), so such a candidate must land BELOW the aggregate's hold threshold, not wherever the overall
    score happens to put them. Without this, three of the project's labelled REJECT pairs would be read as
    REVIEW -- the first draft of this function made exactly that mistake."""
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or raw != raw:
        raise ValueError("raw ATS score must be a real number.")
    if raw < 0 or raw > 100:
        raise ValueError(f"raw ATS score {raw} is outside 0-100.")
    pts = _anchors(role_category)
    aligned = 100.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if raw <= x1:
            aligned = round(y0 + (raw - x0) / (x1 - x0) * (y1 - y0), 2)
            break
    if skill_match_score is not None and skill_match_score < SKILL_RELEVANCE_FLOOR:
        aligned = min(aligned, FLOOR_CAP)
    return aligned


def describe_alignment(raw: float, role_category: Optional[str] = None, skill_match_score: Optional[float] = None) -> str:
    """One plain sentence for the audit trail / recruiter report."""
    cuts = CATEGORY_THRESHOLDS.get(role_category, DEFAULT_THRESHOLDS) if role_category else DEFAULT_THRESHOLDS
    text = (f"Raw ATS score {raw:g} aligned to {align_ats_score(raw, role_category, skill_match_score):g} on the common scale "
            f"(ATS shortlist cutoff {cuts['shortlist']:g} = {COMMON_SELECTED:g}, review cutoff {cuts['review']:g} = {COMMON_HOLD:g}).")
    if skill_match_score is not None and skill_match_score < SKILL_RELEVANCE_FLOOR:
        text += f" Capped below {COMMON_HOLD:g} because the ATS skill match ({skill_match_score:g}) is under its relevance floor ({SKILL_RELEVANCE_FLOOR:g})."
    return text
