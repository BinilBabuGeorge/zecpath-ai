"""
Education Relevance Scoring Module (Day 11)

Scores how relevant a candidate's academic background is to a target job,
combining:
  - degree level match (does the candidate meet the required degree level?)
  - field of study match (is their field relevant to the role?)
  - certification bonus (do they hold certifications in a relevant category?)

Public API:
    score_education_relevance(education, certifications, target_level, target_fields, target_cert_categories) -> EducationRelevanceResult
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import List, Optional

from parsers.education_dictionary import DEGREE_LEVEL_RANK
from parsers.education_parser import EducationEntry, CertificationEntry


@dataclass
class EducationRelevanceResult:
    overall_score: float  # 0-100
    degree_level_score: float
    field_match_score: float
    certification_bonus: float
    best_matching_degree: Optional[str] = None
    matching_certifications: List[str] = field(default_factory=list)


def _degree_level_score(education: List[EducationEntry], target_level: Optional[str]) -> float:
    """1.0 if candidate meets or exceeds the required level, scaled down
    for each level short of it. 0.7 baseline if target_level isn't specified
    (can't penalize what wasn't asked for) or no education was parsed."""
    if not target_level or not education:
        return 0.7

    target_rank = DEGREE_LEVEL_RANK.get(target_level, 2)
    candidate_ranks = [DEGREE_LEVEL_RANK.get(e.level, 0) for e in education if e.level]
    if not candidate_ranks:
        return 0.5  # has an entry, but degree wasn't recognized -- partial credit

    best_rank = max(candidate_ranks)
    if best_rank >= target_rank:
        return 1.0
    shortfall = target_rank - best_rank
    return max(0.0, 1.0 - 0.35 * shortfall)


def _field_match_score(education: List[EducationEntry], target_fields: List[str]) -> float:
    """Best string-similarity between any of the candidate's fields of
    study and any of the target job's relevant fields."""
    if not target_fields:
        return 0.7  # no field requirement specified
    candidate_fields = [e.field_of_study for e in education if e.field_of_study]
    if not candidate_fields:
        return 0.3  # degree present but no field info to compare

    best = 0.0
    for cf in candidate_fields:
        for tf in target_fields:
            ratio = difflib.SequenceMatcher(None, cf.lower(), tf.lower()).ratio()
            best = max(best, ratio)
    return round(best, 2)


def _certification_bonus(certifications: List[CertificationEntry], target_cert_categories: List[str]) -> tuple:
    """Up to +15 points for holding at least one certification in a
    category relevant to the target job; +5 more per additional relevant
    cert, capped at +20 total."""
    if not target_cert_categories:
        return 0.0, []

    matches = [c.name for c in certifications if c.category in target_cert_categories]
    if not matches:
        return 0.0, []

    bonus = min(15 + 5 * (len(matches) - 1), 20)
    return float(bonus), matches


def score_education_relevance(
    education: List[EducationEntry],
    certifications: List[CertificationEntry],
    target_level: Optional[str] = None,
    target_fields: Optional[List[str]] = None,
    target_cert_categories: Optional[List[str]] = None,
) -> EducationRelevanceResult:
    target_fields = target_fields or []
    target_cert_categories = target_cert_categories or []

    degree_score = _degree_level_score(education, target_level)
    field_score = _field_match_score(education, target_fields)
    cert_bonus, matching_certs = _certification_bonus(certifications, target_cert_categories)

    # Base score: degree level matters most, field of study second
    base = (0.55 * degree_score + 0.45 * field_score) * 100
    overall = min(100.0, round(base + cert_bonus, 1))

    best_degree = None
    if education:
        best_degree = max(
            education,
            key=lambda e: DEGREE_LEVEL_RANK.get(e.level, 0),
        ).degree

    return EducationRelevanceResult(
        overall_score=overall,
        degree_level_score=round(degree_score * 100, 1),
        field_match_score=round(field_score * 100, 1),
        certification_bonus=cert_bonus,
        best_matching_degree=best_degree,
        matching_certifications=matching_certs,
    )


if __name__ == "__main__":
    import sys
    from parsers.education_parser import parse_education, parse_certifications

    with open(sys.argv[1], "r", encoding="utf-8") as f:
        text = f.read()

    education = parse_education(text)
    certifications = parse_certifications(text)

    target_level = sys.argv[2] if len(sys.argv) > 2 else "Bachelor's"
    target_fields = sys.argv[3].split(",") if len(sys.argv) > 3 else ["Computer Science"]
    target_cats = sys.argv[4].split(",") if len(sys.argv) > 4 else ["Software Development"]

    result = score_education_relevance(education, certifications, target_level, target_fields, target_cats)
    print(f"Overall education relevance: {result.overall_score}/100")
    print(f"  Degree level score: {result.degree_level_score} (best: {result.best_matching_degree})")
    print(f"  Field match score: {result.field_match_score}")
    print(f"  Certification bonus: +{result.certification_bonus} (matches: {result.matching_certifications})")
