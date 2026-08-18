"""
Education Relevance Scoring (originally Day 11)
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import List, Optional

from parsers.education_dictionary import DEGREE_LEVEL_RANK
from parsers.education_parser import EducationEntry, CertificationEntry


@dataclass
class EducationRelevanceResult:
    overall_score: float
    degree_level_score: float
    field_match_score: float
    certification_bonus: float
    best_matching_degree: Optional[str] = None
    matching_certifications: List[str] = field(default_factory=list)


def _degree_level_score(education: List[EducationEntry], target_level: Optional[str]) -> float:
    if not target_level or not education:
        return 0.7

    target_rank = DEGREE_LEVEL_RANK.get(target_level, 2)
    candidate_ranks = [DEGREE_LEVEL_RANK.get(e.level, 0) for e in education if e.level]
    if not candidate_ranks:
        return 0.5

    best_rank = max(candidate_ranks)
    if best_rank >= target_rank:
        return 1.0
    shortfall = target_rank - best_rank
    return max(0.0, 1.0 - 0.35 * shortfall)


def _field_match_score(education: List[EducationEntry], target_fields: List[str]) -> float:
    if not target_fields:
        return 0.7
    candidate_fields = [e.field_of_study for e in education if e.field_of_study]
    if not candidate_fields:
        return 0.3

    best = 0.0
    for cf in candidate_fields:
        for tf in target_fields:
            ratio = difflib.SequenceMatcher(None, cf.lower(), tf.lower()).ratio()
            best = max(best, ratio)
    return round(best, 2)


def _certification_bonus(certifications: List[CertificationEntry], target_cert_categories: List[str]) -> tuple:
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

    base = (0.55 * degree_score + 0.45 * field_score) * 100
    overall = min(100.0, round(base + cert_bonus, 1))

    best_degree = None
    if education:
        best_degree = max(education, key=lambda e: DEGREE_LEVEL_RANK.get(e.level, 0)).degree

    return EducationRelevanceResult(
        overall_score=overall, degree_level_score=round(degree_score * 100, 1),
        field_match_score=round(field_score * 100, 1), certification_bonus=cert_bonus,
        best_matching_degree=best_degree, matching_certifications=matching_certs,
    )
