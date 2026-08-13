"""
Experience Relevance Scoring Module (Day 10)

Scores how relevant a candidate's parsed work history (Day 10's own
experience_parser) is to a target job title, combining:
  - title similarity  (does the role's title match the target role?)
  - skill overlap      (does the role's description mention skills the
                         target job requires? -- reuses Day 9's extractor)
  - recency weighting  (a role held 5 years ago counts less than the
                         candidate's current role)

Public API:
    score_experience_relevance(entries, target_title, required_skills) -> RelevanceResult
"""

from __future__ import annotations

import re
import difflib
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

from parsers.experience_parser import ExperienceEntry
from parsers.skill_extractor import extract_skills

# ---------------------------------------------------------------------------
# Title normalization (same approach as Day 6's role synonym detection,
# reimplemented locally so this module has no cross-day import dependency)
# ---------------------------------------------------------------------------

ROLE_SYNONYM_PATTERNS = [
    (re.compile(r"mern\s*stack\s*developer|frontend\s*engineer\s*\(mern\)|full[\s-]?stack\s*developer\s*\(mern\)", re.I), "MERN Stack Developer"),
    (re.compile(r"\bsales\s*executive\b|\bbusiness\s*development\s*executive\b|\bbde\b", re.I), "Sales Executive"),
    (re.compile(r"\bproduct\s*manager\b", re.I), "Product Manager"),
    (re.compile(r"\bsenior\s*product\s*manager\b", re.I), "Product Manager"),
    (re.compile(r"\bassociate\s*product\s*manager\b", re.I), "Product Manager"),
    (re.compile(r"\bdata\s*analyst\b", re.I), "Data Analyst"),
    (re.compile(r"\bdata\s*scientist\b", re.I), "Data Scientist"),
]


def normalize_title(title: str) -> str:
    for pattern, canonical in ROLE_SYNONYM_PATTERNS:
        if pattern.search(title):
            return canonical
    return title.strip()


def title_similarity(title_a: str, title_b: str) -> float:
    """1.0 if titles normalize to the same canonical role; otherwise a
    string-similarity ratio on the normalized (lowercased) titles."""
    norm_a, norm_b = normalize_title(title_a), normalize_title(title_b)
    if norm_a.lower() == norm_b.lower():
        return 1.0
    return difflib.SequenceMatcher(None, norm_a.lower(), norm_b.lower()).ratio()


# ---------------------------------------------------------------------------
# Recency weighting
# ---------------------------------------------------------------------------

def _recency_weight(entry: ExperienceEntry, today: Optional[date] = None) -> float:
    """1.0 for the candidate's current role; decays the further in the
    past a role ended. Floors at 0.3 so old-but-relevant experience still
    counts for something rather than being zeroed out."""
    today = today or date.today()
    if entry.is_current:
        return 1.0
    years_since_ended = max(0.0, (today - entry.end_date).days / 365.25)
    weight = 1.0 - 0.15 * years_since_ended  # -0.15 per year since the role ended
    return max(0.3, round(weight, 2))


# ---------------------------------------------------------------------------
# Skill overlap
# ---------------------------------------------------------------------------

def _skill_overlap_ratio(description: str, required_skill_names: List[str]) -> float:
    if not required_skill_names or not description.strip():
        return 0.0
    found = {s.name for s in extract_skills(description)}
    required = set(required_skill_names)
    if not required:
        return 0.0
    return len(found & required) / len(required)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

@dataclass
class RoleRelevance:
    title: str
    company: str
    title_similarity: float
    skill_overlap: float
    recency_weight: float
    role_score: float  # 0-100


@dataclass
class RelevanceResult:
    target_title: str
    overall_score: float  # 0-100
    role_breakdown: List[RoleRelevance] = field(default_factory=list)


def score_experience_relevance(
    entries: List[ExperienceEntry],
    target_title: str,
    required_skills: Optional[List[str]] = None,
) -> RelevanceResult:
    """Score how relevant a candidate's experience is to a target job."""
    required_skills = required_skills or []
    breakdown: List[RoleRelevance] = []

    if not entries:
        return RelevanceResult(target_title=target_title, overall_score=0.0, role_breakdown=[])

    weighted_sum = 0.0
    weight_total = 0.0

    for entry in entries:
        t_sim = title_similarity(entry.title, target_title)
        skill_overlap = _skill_overlap_ratio(entry.description, required_skills)
        recency = _recency_weight(entry)

        # Title match matters most, skill overlap secondary
        role_score = round((0.65 * t_sim + 0.35 * skill_overlap) * 100, 1)

        breakdown.append(RoleRelevance(
            title=entry.title, company=entry.company,
            title_similarity=round(t_sim, 2), skill_overlap=round(skill_overlap, 2),
            recency_weight=recency, role_score=role_score,
        ))

        weighted_sum += role_score * recency
        weight_total += recency

    overall = round(weighted_sum / weight_total, 1) if weight_total else 0.0
    return RelevanceResult(target_title=target_title, overall_score=overall, role_breakdown=breakdown)


if __name__ == "__main__":
    import sys
    from parsers.experience_parser import parse_experience

    with open(sys.argv[1], "r", encoding="utf-8") as f:
        text = f.read()
    target = sys.argv[2] if len(sys.argv) > 2 else "Product Manager"
    skills = sys.argv[3].split(",") if len(sys.argv) > 3 else []

    entries = parse_experience(text)
    result = score_experience_relevance(entries, target, skills)

    print(f"Target role: {result.target_title}")
    print(f"Overall relevance: {result.overall_score}/100\n")
    for r in result.role_breakdown:
        print(f"  {r.role_score:5.1f}  {r.title} @ {r.company}  "
              f"(title_sim={r.title_similarity}, skills={r.skill_overlap}, recency={r.recency_weight})")
