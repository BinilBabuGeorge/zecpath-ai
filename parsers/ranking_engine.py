"""
Candidate Ranking & Shortlisting Engine (Day 14)

Takes the explainable per-candidate scores produced by Day 13's
ats_scoring_engine.score_candidate() across every applicant for a job,
and turns them into what a recruiter actually needs to act on:
  - Candidates sorted by overall score, highest first
  - Each candidate placed into one of three zones (shortlist / review /
    reject) using configurable thresholds
  - A ready-to-use "top N" shortlist for a job
  - A flattened, recruiter-friendly view of each row (no nested dataclasses)

This module does NOT re-score anything -- it consumes ATSScoreResult
objects that ats_scoring_engine already produced and organizes them.

Public API:
    rank_candidates(scored, thresholds=None)          -> List[RankedCandidate]
    top_candidates(ranked, n)                          -> List[RankedCandidate]
    filter_by_zone(ranked, zone)                        -> List[RankedCandidate]
    to_recruiter_view(ranked)                           -> List[Dict]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from parsers.ats_scoring_engine import ATSScoreResult

# ---------------------------------------------------------------------------
# Configurable shortlisting thresholds.
#
# A score >= SHORTLIST cutoff goes straight to the shortlist zone.
# A score >= REVIEW cutoff (but below SHORTLIST) goes to manual review --
# it's not strong enough to auto-advance, but too promising to auto-reject.
# Anything below REVIEW is auto-rejected.
# ---------------------------------------------------------------------------

DEFAULT_THRESHOLDS: Dict[str, float] = {
    "shortlist": 55.0,
    "review": 25.0,
}
# Chosen from the observed score distribution of Day 13's engine on the
# sample dataset (real overall scores range roughly 8-63): a clean
# domain match lands around 50-63, a genuinely weak or cross-domain
# mismatch lands under 25. Recruiters can override per job via the
# `thresholds` argument -- these are sane defaults, not hard-coded law.

ZONE_ORDER = ["shortlist", "review", "reject"]


@dataclass
class RankedCandidate:
    rank: int
    candidate_id: str
    jd_id: str
    overall_score: float
    role_category: str
    zone: str                    # "shortlist" | "review" | "reject"
    explanation: str
    missing_data_notes: List[str] = field(default_factory=list)
    top_component: str = ""      # name of the strongest-contributing component
    result: Optional[ATSScoreResult] = None   # full breakdown, kept for drill-down


# ---------------------------------------------------------------------------
# Zone classification
# ---------------------------------------------------------------------------

def classify_zone(score: float, thresholds: Optional[Dict[str, float]] = None) -> str:
    """Map a 0-100 overall score to a shortlisting zone using the given
    (or default) thresholds. Boundaries are inclusive on the lower edge
    of each zone, i.e. a score exactly at the shortlist cutoff shortlists."""
    t = thresholds or DEFAULT_THRESHOLDS
    if score >= t["shortlist"]:
        return "shortlist"
    if score >= t["review"]:
        return "review"
    return "reject"


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

def rank_candidates(
    scored: Sequence[tuple],
    thresholds: Optional[Dict[str, float]] = None,
) -> List[RankedCandidate]:
    """Sort a batch of (candidate_id, jd_id, ATSScoreResult) tuples by
    overall_score descending and assign rank + shortlisting zone to each.

    Ties are broken by candidate_id (alphabetical) so ranking is
    deterministic and reproducible across runs.
    """
    ordered = sorted(scored, key=lambda row: (-row[2].overall_score, row[0]))

    ranked: List[RankedCandidate] = []
    for i, (candidate_id, jd_id, result) in enumerate(ordered, start=1):
        zone = classify_zone(result.overall_score, thresholds)
        top = max(result.components, key=lambda c: c.contribution)
        ranked.append(RankedCandidate(
            rank=i,
            candidate_id=candidate_id,
            jd_id=jd_id,
            overall_score=result.overall_score,
            role_category=result.role_category,
            zone=zone,
            explanation=result.explanation,
            missing_data_notes=result.missing_data_notes,
            top_component=top.name,
            result=result,
        ))
    return ranked


# ---------------------------------------------------------------------------
# Convenience views
# ---------------------------------------------------------------------------

def top_candidates(ranked: List[RankedCandidate], n: int = 5) -> List[RankedCandidate]:
    """Top N candidates overall, regardless of zone (ranked list is
    already sorted, so this is just a slice) -- useful for a recruiter
    who wants to eyeball the best applicants even if none cleared the
    shortlist cutoff."""
    return ranked[:n]


def filter_by_zone(ranked: List[RankedCandidate], zone: str) -> List[RankedCandidate]:
    """All candidates in a single zone (e.g. the auto-shortlist, or the
    review queue that needs a human look), preserving rank order."""
    if zone not in ZONE_ORDER:
        raise ValueError(f"Unknown zone '{zone}' -- expected one of {ZONE_ORDER}")
    return [r for r in ranked if r.zone == zone]


def zone_counts(ranked: List[RankedCandidate]) -> Dict[str, int]:
    """Quick summary of how many candidates landed in each zone --
    e.g. for a dashboard tile or a log line."""
    counts = {z: 0 for z in ZONE_ORDER}
    for r in ranked:
        counts[r.zone] += 1
    return counts


def to_recruiter_view(ranked: List[RankedCandidate]) -> List[Dict]:
    """Flatten each RankedCandidate into a plain dict with only the
    fields a recruiter needs at a glance -- no nested dataclasses, no
    component-level detail. This is the "recruiter-friendly output"
    deliverable: something that maps directly onto a table/CSV row."""
    rows = []
    for r in ranked:
        rows.append({
            "rank": r.rank,
            "candidate": r.candidate_id,
            "job": r.jd_id,
            "score": r.overall_score,
            "zone": r.zone.upper(),
            "role_category": r.role_category,
            "strongest_factor": r.top_component,
            "flags": "; ".join(n.split(" -- ")[0] for n in r.missing_data_notes) or "-",
        })
    return rows
