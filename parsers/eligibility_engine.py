"""
Eligibility Decision Engine (Day 21)

Answers a narrower, more consequential question than Day 20's zone
classification: not "how good is this candidate overall" but "does this
specific candidate qualify to receive an AI screening CALL for this
specific job" (PRD Phase 3 -- "Candidate Eligibility & Call Trigger
Engine"). Getting this wrong has a real-world cost either way: calling
someone who can't legally/practically do the job wastes their time and
the company's; failing to call someone who could have makes a bad hiring
decision by omission.

Design principle: HARD GATES first, SCORE SECOND. A candidate missing a
mandatory skill or outside a hard experience floor is REJECTED regardless
of how high their overall ATS score is -- a high score built on other
components can't compensate for missing a hard requirement (e.g. a
security clearance-adjacent skill, or a legally-required minimum years
of experience for a specific client contract). This mirrors real
recruiting practice: score-based ranking is for choosing among qualified
candidates, not for deciding who's qualified in the first place.

Explicitly reuses Day 20's zone classification (`ranking_engine.
classify_zone`) as the score-based signal, rather than reinventing
thresholds -- this is the literal "connect eligibility logic with ATS
outputs" task, and it means every calibration lesson from Days 17 and 20
(category-aware thresholds, the skill-relevance floor) applies here too
instead of being silently bypassed by a second, uncoordinated scoring
path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from parsers.ats_scoring_engine import ATSScoreResult
from parsers.ranking_engine import classify_zone
from parsers.experience_parser import parse_experience, compute_total_experience
from parsers.section_extractor import extract_resume_sections

# ---------------------------------------------------------------------------
# Rule configuration format
# ---------------------------------------------------------------------------

@dataclass
class EligibilityRules:
    """One job's eligibility configuration -- the recruiter-facing
    "rule configuration format" deliverable. Every field is optional
    except job_id: an unset field means "no constraint on this axis,"
    not "reject everyone" -- a recruiter who only cares about mandatory
    skills shouldn't have to also specify an experience range.

    Fully JSON-serializable (see to_dict/from_dict) so this can be saved
    as a per-job config file and loaded back without any code changes.
    """
    job_id: str
    min_ats_score: Optional[float] = None
    # None = defer entirely to ranking_engine.classify_zone()'s
    # category-aware thresholds (Day 20) rather than a flat cutoff --
    # this is the recommended default, since a flat score-agnostic-of-
    # category cutoff reintroduces exactly the bug Day 20 fixed.
    mandatory_skills: List[str] = field(default_factory=list)
    # HARD gate: every skill listed here must appear in the ATS result's
    # matched_skills for the candidate to be eligible at all, regardless
    # of overall score. Match is case-insensitive against the canonical
    # skill names skill_extractor produces (e.g. "React.js", not "react").
    min_experience_years: Optional[float] = None
    max_experience_years: Optional[float] = None
    # max_experience_years intentionally has no default cap and is rarely
    # worth setting -- Day 20 established that penalizing candidates for
    # having MORE experience than a junior-scoped JD asked for is a bug,
    # not a feature. Only set this for roles with a genuine reason to cap
    # seniority (e.g. a role explicitly scoped as entry-level-only).
    allowed_locations: Optional[List[str]] = None
    # Case-insensitive substring match against the resume's Location
    # field. None = any location acceptable (default -- most roles
    # shouldn't hard-gate on location without a specific reason).
    require_availability: bool = False
    # NOT IMPLEMENTED as an active gate -- see evaluate_eligibility()'s
    # docstring for why. Kept in the schema so the rule format is
    # complete against the Day 21 brief's four parameter categories;
    # always produces a note in the result rather than silently
    # pretending to check something it can't.

    def to_dict(self) -> Dict:
        return {
            "job_id": self.job_id,
            "min_ats_score": self.min_ats_score,
            "mandatory_skills": self.mandatory_skills,
            "min_experience_years": self.min_experience_years,
            "max_experience_years": self.max_experience_years,
            "allowed_locations": self.allowed_locations,
            "require_availability": self.require_availability,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "EligibilityRules":
        return cls(
            job_id=d["job_id"],
            min_ats_score=d.get("min_ats_score"),
            mandatory_skills=list(d.get("mandatory_skills", [])),
            min_experience_years=d.get("min_experience_years"),
            max_experience_years=d.get("max_experience_years"),
            allowed_locations=d.get("allowed_locations"),
            require_availability=d.get("require_availability", False),
        )


# ---------------------------------------------------------------------------
# Candidate eligibility result structure
# ---------------------------------------------------------------------------

@dataclass
class EligibilityResult:
    """The per-candidate output -- deliberately a different vocabulary
    (ELIGIBLE/REVIEW/REJECTED) from ranking_engine's zones (SHORTLIST/
    REVIEW/REJECT), even though the underlying score classification is
    reused, because these answer different questions: ranking_engine
    asks "is this a strong candidate," this asks "does this candidate
    get a screening call for THIS job's specific hard requirements."
    A REJECT from ranking_engine and a REJECTED here can have entirely
    different causes -- this result's `reasons` list always says which.
    """
    candidate_id: str
    job_id: str
    tag: str  # "ELIGIBLE" | "REVIEW" | "REJECTED"
    overall_score: float
    score_zone: str  # the underlying ranking_engine zone, for traceability
    reasons: List[str] = field(default_factory=list)
    gates_applied: Dict[str, bool] = field(default_factory=dict)
    # e.g. {"mandatory_skills": True, "experience_range": True, "location": False}
    # -- True means the gate PASSED. A gate absent from this dict means
    # it wasn't configured for this job (not evaluated, not "passed").


LOCATION_PATTERN = re.compile(r"^Location:\s*(.+)$", re.MULTILINE | re.IGNORECASE)


def extract_candidate_location(resume_text: str) -> Optional[str]:
    """Pulls the raw Location: field value, if present. Not used for
    scoring (fairness_engine masks this exact field before semantic
    comparison, Day 15) -- eligibility is the one place in this system
    where location is a deliberate, explicit, recruiter-configured input
    rather than an accidental bias vector, which is why it's read here
    independently rather than reusing fairness_engine's masking path.
    """
    match = LOCATION_PATTERN.search(resume_text)
    return match.group(1).strip() if match else None


def validate_rules_against_dictionary(rules: EligibilityRules) -> List[str]:
    """Catches a real, easy-to-make mistake: a `mandatory_skills` entry
    that doesn't exactly match any canonical skill name in
    skill_dictionary.py silently rejects EVERY candidate for that job,
    with no error and no obvious symptom other than "nobody is ever
    eligible." Found this exact bug while writing this module's own
    example config ("Salesforce CRM" instead of the dictionary's
    canonical "Salesforce") -- this validator exists specifically
    because that mistake is easy to make and expensive to miss.

    Call this when LOADING a rule config (e.g. right after
    `EligibilityRules.from_dict()`), not on every `evaluate_eligibility()`
    call -- evaluation should stay fast and side-effect-free; validation
    is a one-time, load-time concern.
    """
    from difflib import get_close_matches
    from parsers.skill_dictionary import SKILL_DICTIONARY

    canonical_names = list(SKILL_DICTIONARY.keys())
    canonical_lower = {name.lower(): name for name in canonical_names}

    warnings = []
    for skill in rules.mandatory_skills:
        if skill.lower() not in canonical_lower:
            suggestions = get_close_matches(skill, canonical_names, n=3, cutoff=0.6)
            suggestion_text = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
            warnings.append(
                f"mandatory_skills entry '{skill}' does not exactly match any canonical "
                f"skill name -- every candidate will be REJECTED for this job until fixed."
                f"{suggestion_text}"
            )
    return warnings


# ---------------------------------------------------------------------------
# The decision engine
# ---------------------------------------------------------------------------

def evaluate_eligibility(
    candidate_id: str,
    resume_text: str,
    result: ATSScoreResult,
    rules: EligibilityRules,
) -> EligibilityResult:
    """Hard gates first, score second -- see module docstring.

    Availability: NOT evaluated as an active gate even if
    `rules.require_availability` is True. This project's resumes (and
    the resume schema generally) don't capture availability/notice
    period -- per the product's own design (see the PRD's Phase 5 AI
    screening questions), notice period is explicitly something asked
    LIVE on the AI call, not present on the resume beforehand. Building
    a gate against data that doesn't exist would mean either silently
    always-passing (dishonest -- looks like it checked something it
    didn't) or fabricating a signal. Neither is acceptable; instead this
    always adds an explicit reason string when the rule is set, so
    nobody mistakes silence for "checked and fine."
    """
    reasons: List[str] = []
    gates: Dict[str, bool] = {}

    # --- Hard gate 1: mandatory skills -------------------------------
    if rules.mandatory_skills:
        skill_component = next((c for c in result.components if c.name == "skill_match"), None)
        matched = set(s.lower() for s in (skill_component.details.get("matched_skills", []) if skill_component else []))
        missing_mandatory = [s for s in rules.mandatory_skills if s.lower() not in matched]
        gates["mandatory_skills"] = not missing_mandatory
        if missing_mandatory:
            reasons.append(f"Missing mandatory skill(s): {', '.join(missing_mandatory)}")

    # --- Hard gate 2: experience range --------------------------------
    if rules.min_experience_years is not None or rules.max_experience_years is not None:
        sections = extract_resume_sections(resume_text)
        entries = parse_experience(sections["experience"])
        summary = compute_total_experience(entries)
        years = summary.total_years

        below_min = rules.min_experience_years is not None and years < rules.min_experience_years
        above_max = rules.max_experience_years is not None and years > rules.max_experience_years
        gates["experience_range"] = not below_min and not above_max

        if below_min:
            reasons.append(f"Experience ({years:.1f}y) below minimum ({rules.min_experience_years}y)")
        if above_max:
            reasons.append(f"Experience ({years:.1f}y) above maximum ({rules.max_experience_years}y) -- role explicitly capped")

    # --- Soft gate: location (downgrades, never hard-rejects) --------
    location_softfail = False
    if rules.allowed_locations:
        candidate_location = extract_candidate_location(resume_text)
        if candidate_location is None:
            gates["location"] = False
            location_softfail = True
            reasons.append("No location information found on resume")
        else:
            match = any(loc.lower() in candidate_location.lower() for loc in rules.allowed_locations)
            gates["location"] = match
            if not match:
                location_softfail = True
                reasons.append(f"Location '{candidate_location}' not in allowed list: {', '.join(rules.allowed_locations)}")

    # --- Availability: documented non-gate, always noted when configured ---
    if rules.require_availability:
        reasons.append(
            "Availability/notice-period NOT evaluated -- not captured on resumes "
            "by this system's design; ask on the AI screening call instead."
        )

    # --- Hard-gate failure short-circuits to REJECTED, regardless of score ---
    hard_gate_failed = not gates.get("mandatory_skills", True) or not gates.get("experience_range", True)
    if hard_gate_failed:
        return EligibilityResult(
            candidate_id=candidate_id, job_id=rules.job_id, tag="REJECTED",
            overall_score=result.overall_score, score_zone="n/a (hard gate failed before scoring was consulted)",
            reasons=reasons, gates_applied=gates,
        )

    # --- Score-based classification, reusing Day 20's calibrated zones ---
    if rules.min_ats_score is not None:
        zone = "shortlist" if result.overall_score >= rules.min_ats_score else "reject"
        reasons.append(f"Custom min_ats_score={rules.min_ats_score} applied (overrides category-aware default threshold)")
    else:
        skill_component = next((c for c in result.components if c.name == "skill_match"), None)
        skill_score = skill_component.score if skill_component else None
        zone = classify_zone(result.overall_score, role_category=result.role_category, skill_match_score=skill_score)

    tag_map = {"shortlist": "ELIGIBLE", "review": "REVIEW", "reject": "REJECTED"}
    tag = tag_map[zone]

    # Location soft-fail downgrades ELIGIBLE -> REVIEW, never forces REJECTED --
    # a location mismatch is negotiable (remote work, relocation) in a way a
    # missing mandatory skill or a hard experience floor is not.
    if location_softfail and tag == "ELIGIBLE":
        tag = "REVIEW"

    if not reasons:
        reasons.append(f"Passed all configured gates; score-based zone: {zone}")

    return EligibilityResult(
        candidate_id=candidate_id, job_id=rules.job_id, tag=tag,
        overall_score=result.overall_score, score_zone=zone,
        reasons=reasons, gates_applied=gates,
    )
