"""
ATS Scoring Formula Engine (Day 13)

Combines four scoring parameters -- built across Days 9-12 -- into one
explainable, weighted candidate score:
  - Skill match        (Day 9's skill extractor)
  - Experience relevance (Day 10's experience parser + relevance scorer)
  - Education alignment  (Day 11's education parser + relevance scorer)
  - Semantic similarity  (Day 12's TF-IDF matcher)

Two things make this "explainable" rather than a black-box number:
  1. Every component's raw score, weight, and contribution to the final
     score is returned, not just the total.
  2. Missing data (no experience section, no education section) is
     detected and flagged rather than silently scored as zero -- the
     weight of a missing component is redistributed proportionally
     across the components that ARE available, and the result says so.

Public API:
    score_candidate(resume_text, jd_text, matcher, role_category=None) -> ATSScoreResult
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from parsers.skill_extractor import extract_skills
from parsers.experience_parser import parse_experience
from parsers.experience_relevance import score_experience_relevance
from parsers.education_parser import parse_education, parse_certifications
from parsers.education_relevance import score_education_relevance
from parsers.semantic_matcher import SemanticMatcher, compare_resume_to_jd
from parsers.section_extractor import extract_resume_sections, extract_jd_sections

# ---------------------------------------------------------------------------
# Configurable weight system: different role categories value the four
# scoring parameters differently. A technical role leans on skill match
# and experience; a creative role leans more on semantic similarity
# (project/portfolio descriptions rarely use exact keyword matches).
# ---------------------------------------------------------------------------

WEIGHT_PROFILES: Dict[str, Dict[str, float]] = {
    "tech":     {"skill_match": 0.35, "experience": 0.30, "semantic": 0.20, "education": 0.15},
    "business": {"skill_match": 0.25, "experience": 0.35, "semantic": 0.25, "education": 0.15},
    "creative": {"skill_match": 0.25, "experience": 0.25, "semantic": 0.30, "education": 0.20},
    "default":  {"skill_match": 0.30, "experience": 0.30, "semantic": 0.20, "education": 0.20},
}

# Default academic expectations used for the education component when the
# JD text doesn't specify them explicitly (kept simple and overridable).
DEFAULT_TARGET_DEGREE_LEVEL = "Bachelor's"


@dataclass
class ComponentResult:
    name: str
    score: float                 # 0-100
    base_weight: float           # weight before any redistribution
    effective_weight: float      # weight actually used (after redistribution)
    contribution: float          # score * effective_weight, i.e. points added to overall
    available: bool
    details: Dict = field(default_factory=dict)


@dataclass
class ATSScoreResult:
    overall_score: float
    role_category: str
    components: List[ComponentResult] = field(default_factory=list)
    missing_data_notes: List[str] = field(default_factory=list)
    explanation: str = ""


# ---------------------------------------------------------------------------
# Role category inference
# ---------------------------------------------------------------------------

def infer_role_category(jd_skills_text: str) -> str:
    """Infer tech/business/creative from the majority skill group found
    in the JD's required-skills text. Falls back to 'default' if no
    skills were recognized at all."""
    return _infer_role_category_from_skills(extract_skills(jd_skills_text))


def _infer_role_category_from_skills(skills: List) -> str:
    """Same logic as infer_role_category, operating on an already-
    extracted skill list. Split out so score_candidate() can reuse a
    skill extraction it already has instead of re-running extract_skills
    on identical JD text a second time (see PERFORMANCE note below)."""
    if not skills:
        return "default"

    counts: Dict[str, int] = {}
    for s in skills:
        counts[s.group] = counts.get(s.group, 0) + 1

    return max(counts, key=counts.get)


# ---------------------------------------------------------------------------
# Individual component scorers -- each returns (score_0_100, available, details)
# ---------------------------------------------------------------------------

def _score_skill_match(candidate_skills: List, required_skills: List) -> tuple:
    if not required_skills:
        return 0.0, False, {"reason": "JD has no recognizable required skills"}

    candidate_names = {s.name for s in candidate_skills}
    required_names = {s.name for s in required_skills}
    matched = candidate_names & required_names

    coverage = len(matched) / len(required_names)
    score = round(coverage * 100, 1)

    return score, True, {
        "matched_skills": sorted(matched),
        "missing_skills": sorted(required_names - candidate_names),
        "required_count": len(required_names),
        "matched_count": len(matched),
    }


def _score_experience(resume_text: str, target_title: str, required_skill_names: List[str]) -> tuple:
    entries = parse_experience(resume_text)
    if not entries:
        return 0.0, False, {"reason": "No work experience entries found on resume"}

    result = score_experience_relevance(entries, target_title, required_skill_names)
    return result.overall_score, True, {
        "role_count": len(entries),
        "role_breakdown": [
            {"title": r.title, "company": r.company, "role_score": r.role_score}
            for r in result.role_breakdown
        ],
    }


def _score_education(resume_text: str, target_fields: List[str], target_cert_categories: List[str]) -> tuple:
    education = parse_education(resume_text)
    certifications = parse_certifications(resume_text)

    if not education:
        return 0.0, False, {"reason": "No education entries found on resume", "certifications_found": len(certifications)}

    result = score_education_relevance(
        education, certifications, DEFAULT_TARGET_DEGREE_LEVEL, target_fields, target_cert_categories,
    )
    return result.overall_score, True, {
        "best_matching_degree": result.best_matching_degree,
        "degree_level_score": result.degree_level_score,
        "field_match_score": result.field_match_score,
        "certification_bonus": result.certification_bonus,
    }


def _score_semantic(resume_sections: Dict[str, str], jd_sections: Dict[str, str], matcher: SemanticMatcher) -> tuple:
    thresholds = {"strong": 1.0, "moderate": 1.0}  # classification unused here, only the raw score
    result = compare_resume_to_jd(resume_sections, jd_sections, matcher, thresholds)
    score = round(result.overall_score * 100, 1)
    return score, True, {"component_scores": result.component_scores}


# ---------------------------------------------------------------------------
# Weight redistribution for missing components
# ---------------------------------------------------------------------------

def _redistribute_weights(base_weights: Dict[str, float], availability: Dict[str, bool]) -> Dict[str, float]:
    """If a component is unavailable, its weight is redistributed
    proportionally across the components that ARE available, so the
    overall score is still a full 0-100 scale rather than silently
    capped below 100."""
    available_components = [c for c, avail in availability.items() if avail]
    if not available_components:
        return {c: 0.0 for c in base_weights}

    available_weight_sum = sum(base_weights[c] for c in available_components)
    if available_weight_sum == 0:
        # Degenerate case: available components all had 0 base weight -- split evenly
        even_share = 1.0 / len(available_components)
        return {c: (even_share if c in available_components else 0.0) for c in base_weights}

    return {
        c: (base_weights[c] / available_weight_sum if c in available_components else 0.0)
        for c in base_weights
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def score_candidate(
    resume_text: str,
    jd_text: str,
    matcher: SemanticMatcher,
    role_category: Optional[str] = None,
    target_fields: Optional[List[str]] = None,
    target_cert_categories: Optional[List[str]] = None,
) -> ATSScoreResult:
    """Score one candidate against one job, using a dynamic weight profile
    and returning a fully explainable breakdown."""
    target_fields = target_fields or []
    target_cert_categories = target_cert_categories or []

    resume_sections = extract_resume_sections(resume_text)
    jd_sections = extract_jd_sections(jd_text)

    # Job title for experience relevance -- pull from the JD's "Job Title:" line
    import re
    title_match = re.search(r"^Job Title:\s*(.+)$", jd_text, re.MULTILINE | re.IGNORECASE)
    target_title = title_match.group(1).strip() if title_match else "Unknown Role"

    if role_category is None:
        # PERFORMANCE (Day 18, verified in this session): jd_sections["skills"]
        # was previously passed as raw text to infer_role_category(),
        # _score_skill_match(), AND used again below for required_skill_names
        # -- extract_skills() (which includes an expensive difflib fuzzy-match
        # fallback) ran 3 separate times on the exact same string, every
        # single score_candidate() call. Extracted once here and reused.
        # See docs/day18_performance_report.md for the measured before/after.
        jd_required_skills = extract_skills(jd_sections["skills"])
        role_category = _infer_role_category_from_skills(jd_required_skills)
    else:
        jd_required_skills = extract_skills(jd_sections["skills"])
    base_weights = WEIGHT_PROFILES.get(role_category, WEIGHT_PROFILES["default"])

    required_skill_names = [s.name for s in jd_required_skills]
    candidate_skills = extract_skills(resume_sections["skills"])

    skill_score, skill_avail, skill_details = _score_skill_match(candidate_skills, jd_required_skills)
    exp_score, exp_avail, exp_details = _score_experience(resume_text, target_title, required_skill_names)
    edu_score, edu_avail, edu_details = _score_education(resume_text, target_fields, target_cert_categories)
    sem_score, sem_avail, sem_details = _score_semantic(resume_sections, jd_sections, matcher)

    scores = {"skill_match": skill_score, "experience": exp_score, "education": edu_score, "semantic": sem_score}
    availability = {"skill_match": skill_avail, "experience": exp_avail, "education": edu_avail, "semantic": sem_avail}
    details = {"skill_match": skill_details, "experience": exp_details, "education": edu_details, "semantic": sem_details}

    effective_weights = _redistribute_weights(base_weights, availability)

    components = []
    missing_notes = []
    overall = 0.0

    for name in ["skill_match", "experience", "education", "semantic"]:
        base_w = base_weights[name]
        eff_w = effective_weights[name]
        avail = availability[name]
        score = scores[name] if avail else 0.0
        contribution = round(score * eff_w, 1)
        overall += contribution

        components.append(ComponentResult(
            name=name, score=score, base_weight=base_w, effective_weight=round(eff_w, 3),
            contribution=contribution, available=avail, details=details[name],
        ))

        if not avail:
            reason = details[name].get("reason", "data unavailable")
            missing_notes.append(f"{name}: {reason} -- weight redistributed to other components")

    overall = round(overall, 1)

    top_component = max(components, key=lambda c: c.contribution)
    explanation = (
        f"Role category: '{role_category}'. Strongest contributor: {top_component.name} "
        f"({top_component.score}/100, contributing {top_component.contribution} points)."
    )
    if missing_notes:
        explanation += f" Note: {len(missing_notes)} component(s) had missing data -- see missing_data_notes."

    return ATSScoreResult(
        overall_score=overall, role_category=role_category, components=components,
        missing_data_notes=missing_notes, explanation=explanation,
    )
