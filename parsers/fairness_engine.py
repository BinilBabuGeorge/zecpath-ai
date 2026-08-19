"""
Fairness, Normalization & Bias Reduction (Day 15)

Concrete finding this day is built around: Day 12's semantic matcher
compares the FULL raw resume text (via section_extractor's "overall"
field) against the JD at 20% weight -- see semantic_matcher.COMPONENT_
WEIGHTS. That raw text includes the candidate's name, email, phone,
and location, so those tokens are literally part of a cosine-similarity
calculation that's supposed to measure job fit. Measured effect on a
real sample: stripping the header shifts the "overall" TF-IDF
sub-score by ~0.007 on a resume/JD pair -- small per-candidate, but
systematic, and it's a bias vector with zero legitimate signal in it
(a name or phone number matching JD text by coincidence is noise, not
relevance).

This module addresses the five Day 15 tasks:
  1. normalize_resume_text()      -- standard formatting before parsing
  2. detect_keyword_stuffing() /
     fairness_adjusted_weights()  -- reduce over-dependence on keywords
  3. normalize_scores_batch()     -- scoring normalization across a batch
  4. mask_pii()                   -- mask non-essential personal attributes
  5. evaluate_bias_indicators()   -- bias indicator evaluation / reporting

It does not replace Day 13/14 -- score_with_fairness() wraps
score_candidate() as an opt-in fairer pipeline, so existing behavior
stays available and testable side by side.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from parsers.ats_scoring_engine import (
    ATSScoreResult, WEIGHT_PROFILES, score_candidate, infer_role_category,
)
from parsers.section_extractor import extract_jd_sections
from parsers.skill_extractor import extract_skills

# ---------------------------------------------------------------------------
# 1. Resume normalization to a standard format
# ---------------------------------------------------------------------------

_BULLET_CHARS = ["•", "◦", "▪", "‣", "*", "●"]


def normalize_resume_text(text: str) -> str:
    """Standardize formatting quirks that vary between resumes for
    reasons that have nothing to do with candidate quality, so
    downstream parsing and TF-IDF tokenization see consistent input:
      - all line endings -> \\n
      - every bullet variant -> "-"
      - trailing whitespace stripped from every line
      - 3+ blank lines collapsed to a single blank line
      - tabs -> single space
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\t", " ")

    lines = []
    for line in text.split("\n"):
        stripped = line.rstrip()
        for bullet in _BULLET_CHARS:
            if stripped.lstrip().startswith(bullet):
                indent = len(stripped) - len(stripped.lstrip())
                stripped = " " * indent + "-" + stripped.lstrip()[len(bullet):]
                break
        lines.append(stripped)

    normalized = "\n".join(lines)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    normalized = re.sub(r"[ ]{2,}", " ", normalized)
    return normalized.strip() + "\n"


# ---------------------------------------------------------------------------
# 4. Masking non-essential personal attributes
# ---------------------------------------------------------------------------

# Fields that carry no job-relevant signal but do carry bias risk
# (name/photo can proxy for gender, ethnicity, religion, age; location
# can proxy for regional/caste background in some contexts). None of
# these affect skill/experience/education parsing -- they're masked
# purely to keep them out of the semantic "overall" comparison and any
# future human-in-the-loop screening view.
PII_FIELD_PATTERNS: Dict[str, str] = {
    "Name": r"^Name:\s*(.+)$",
    "Email": r"^Email:\s*(.+)$",
    "Phone": r"^Phone:\s*(.+)$",
    "Location": r"^Location:\s*(.+)$",
    "Gender": r"^Gender:\s*(.+)$",
    "Date of Birth": r"^(?:Date of Birth|DOB):\s*(.+)$",
    "Age": r"^Age:\s*(.+)$",
    "Marital Status": r"^Marital Status:\s*(.+)$",
    "Religion": r"^Religion:\s*(.+)$",
    "Nationality": r"^Nationality:\s*(.+)$",
    "Father's/Husband's Name": r"^(?:Father's Name|Husband's Name):\s*(.+)$",
    "Photo": r"^Photo:\s*(.+)$",
}

REDACTED = "[REDACTED]"


def mask_pii(resume_text: str) -> Tuple[str, List[str]]:
    """Redact the VALUE of each non-essential personal field found,
    keeping the label so line structure and section boundaries are
    unaffected (Skills:/Experience:/Education: parsing is untouched).
    Returns (masked_text, field_names_detected) -- never the actual
    values, so a bias report built from this is safe to log or store.
    """
    masked_text = resume_text
    detected: List[str] = []

    for field_name, pattern in PII_FIELD_PATTERNS.items():
        match = re.search(pattern, masked_text, re.MULTILINE | re.IGNORECASE)
        if match and match.group(1).strip():
            detected.append(field_name)
            masked_text = re.sub(
                pattern, lambda m, f=field_name: m.group(0).split(":")[0] + f": {REDACTED}",
                masked_text, count=1, flags=re.MULTILINE | re.IGNORECASE,
            )

    return masked_text, detected


# ---------------------------------------------------------------------------
# 2. Reducing over-dependence on keywords
# ---------------------------------------------------------------------------

STUFFING_REPEAT_THRESHOLD = 5  # calibrated against the sample dataset: legitimate
# resumes here top out at 4 natural mentions of one skill (once each in
# Skills/Summary/Experience/Certifications); 5+ is used as the flag point
# so ordinary, honestly-written resumes aren't caught by the check.


def detect_keyword_stuffing(resume_text: str) -> Dict[str, int]:
    """Count LITERAL mentions of each recognized skill using
    skill_extractor's own synonym-aware matching (ExtractedSkill.mentions
    records every literal occurrence, not just a deduplicated set) --
    so a skill written as "React", "ReactJS", and "React.js" in the
    same resume is still counted as one repeated skill, the same way
    skill_match itself would recognize it.
    Synthetic "(via '<stack>' stack)" entries (e.g. a MERN mention
    implying React/Node/Express/MongoDB) are excluded -- they're a
    single inferred skill, not a textual repetition, and counting them
    would falsely flag an ordinary resume that just happens to name
    its stack once.
    skill_match dedupes matches into a set today, so raw repetition
    doesn't inflate that score -- but this is a separate integrity
    signal a recruiter should still see: heavy literal repetition
    usually means a resume was edited specifically to game keyword
    scanners rather than to describe real work.
    Returns {skill_name: mention_count} for skills at/above the
    threshold only -- empty dict means nothing suspicious found.
    """
    skills = extract_skills(resume_text)
    stuffed = {}
    for s in skills:
        literal_mentions = [m for m in s.mentions if not m.startswith("(via '")]
        if len(literal_mentions) >= STUFFING_REPEAT_THRESHOLD:
            stuffed[s.name] = len(literal_mentions)
    return stuffed


def fairness_adjusted_weights(
    base_weights: Dict[str, float], dampen_skill_by: float = 0.30,
) -> Dict[str, float]:
    """Shift a fraction of skill_match's weight to the other three
    components, proportionally to their existing weights. Reduces how
    much a single component built on exact keyword matching can
    dominate the overall score -- complements detect_keyword_stuffing,
    which flags text-level gaming; this addresses the scoring formula
    itself. Opt-in: callers pick this explicitly, Day 13's default
    WEIGHT_PROFILES are unchanged.
    """
    if not 0.0 <= dampen_skill_by <= 1.0:
        raise ValueError("dampen_skill_by must be between 0.0 and 1.0")

    shifted_amount = base_weights["skill_match"] * dampen_skill_by
    others = [k for k in base_weights if k != "skill_match"]
    others_total = sum(base_weights[k] for k in others)

    adjusted = dict(base_weights)
    adjusted["skill_match"] = round(base_weights["skill_match"] - shifted_amount, 4)
    for k in others:
        share = (base_weights[k] / others_total) if others_total else (1 / len(others))
        adjusted[k] = round(base_weights[k] + shifted_amount * share, 4)

    return adjusted


# ---------------------------------------------------------------------------
# 3. Scoring normalization
# ---------------------------------------------------------------------------

@dataclass
class NormalizedScore:
    candidate_id: str
    raw_score: float
    normalized_score: float   # 0-100 min-max within the batch
    percentile: float         # 0-100, share of the batch scored <= this candidate


def normalize_scores_batch(scored: Sequence[Tuple[str, ATSScoreResult]]) -> List[NormalizedScore]:
    """Raw overall scores aren't comparable across role categories --
    Day 13's own weight profiles mean a strong tech match and a strong
    business match don't land on the same numeric scale (observed on
    the sample dataset: tech ceiling ~50-55, business ceiling ~61-63).
    Min-max normalizing within a batch makes "top of the pool" mean
    the same thing regardless of which JD/category a candidate was
    scored against, which matters the moment recruiters compare
    candidates across departments or roles.
    """
    if not scored:
        return []

    raw_scores = [r.overall_score for _, r in scored]
    lo, hi = min(raw_scores), max(raw_scores)
    span = hi - lo

    results = []
    for candidate_id, result in scored:
        if span == 0:
            normalized = 100.0  # every candidate tied -- treat as equal, not zero
        else:
            normalized = round((result.overall_score - lo) / span * 100, 1)
        rank_le = sum(1 for s in raw_scores if s <= result.overall_score)
        percentile = round(rank_le / len(raw_scores) * 100, 1)
        results.append(NormalizedScore(
            candidate_id=candidate_id, raw_score=result.overall_score,
            normalized_score=normalized, percentile=percentile,
        ))
    return results


# ---------------------------------------------------------------------------
# 5. Bias indicator evaluation
# ---------------------------------------------------------------------------

@dataclass
class BiasReport:
    pii_fields_detected: List[str] = field(default_factory=list)
    stuffed_skills: Dict[str, int] = field(default_factory=dict)
    risk_level: str = "low"       # "low" | "medium" | "high"
    notes: List[str] = field(default_factory=list)


def evaluate_bias_indicators(resume_text: str) -> BiasReport:
    """A defensible, heuristic bias-risk checklist -- NOT a statistical
    fairness audit. A real audit (demographic parity, equal
    opportunity, etc.) needs protected-attribute ground truth this
    system deliberately doesn't collect. What this CAN honestly do:
    flag known bias vectors (non-essential personal fields present in
    the raw resume) and integrity issues (keyword stuffing) so a
    recruiter knows what was cleaned up and why a score might look the
    way it does.
    """
    _, pii_fields = mask_pii(resume_text)
    stuffed = detect_keyword_stuffing(resume_text)

    flags = len(pii_fields) + len(stuffed)
    if flags == 0:
        risk = "low"
    elif flags <= 2:
        risk = "medium"
    else:
        risk = "high"

    notes = []
    if pii_fields:
        notes.append(f"{len(pii_fields)} non-essential personal field(s) found and masked before scoring: {', '.join(pii_fields)}.")
    if stuffed:
        notes.append(f"Possible keyword stuffing on: {', '.join(stuffed)} (repeated {STUFFING_REPEAT_THRESHOLD}+ times).")
    if not notes:
        notes.append("No bias indicators detected.")

    return BiasReport(pii_fields_detected=pii_fields, stuffed_skills=stuffed, risk_level=risk, notes=notes)


# ---------------------------------------------------------------------------
# Putting it together: the fairer scoring pipeline
# ---------------------------------------------------------------------------

@dataclass
class FairnessScoringResult:
    result: ATSScoreResult
    bias_report: BiasReport
    raw_overall_score: float          # score WITHOUT masking/normalization, for comparison
    score_delta: float                # masked - raw, should be small if masking is working correctly


def score_with_fairness(
    resume_text: str,
    jd_text: str,
    matcher,
    role_category: Optional[str] = None,
    use_fairness_weights: bool = False,
) -> FairnessScoringResult:
    """The fair-scoring pipeline: normalize -> mask PII -> (optionally)
    dampen keyword weight -> score. Also scores the untouched original
    for comparison, so score_delta lets a recruiter (or a test) verify
    masking removed bias vectors without silently changing a
    candidate's legitimate standing.
    """
    normalized = normalize_resume_text(resume_text)
    masked_text, pii_fields = mask_pii(normalized)
    bias_report = evaluate_bias_indicators(normalized)

    # Resolve the role category once so raw and fairness-weighted scoring
    # use the identical profile as their base -- otherwise an
    # auto-inferred category could silently diverge from the "default"
    # fallback used to build the fairness-adjusted weights.
    if role_category is None:
        role_category = infer_role_category(extract_jd_sections(jd_text)["skills"])

    raw_result = score_candidate(resume_text, jd_text, matcher, role_category=role_category)

    if use_fairness_weights:
        base = WEIGHT_PROFILES.get(role_category, WEIGHT_PROFILES["default"])
        temp_key = f"_fairness_temp_{id(resume_text)}_{id(jd_text)}"
        WEIGHT_PROFILES[temp_key] = fairness_adjusted_weights(base)
        try:
            fair_result = score_candidate(masked_text, jd_text, matcher, role_category=temp_key)
            fair_result.role_category = role_category  # report the real category, not the internal temp key
        finally:
            del WEIGHT_PROFILES[temp_key]
    else:
        fair_result = score_candidate(masked_text, jd_text, matcher, role_category=role_category)

    delta = round(fair_result.overall_score - raw_result.overall_score, 2)

    return FairnessScoringResult(
        result=fair_result, bias_report=bias_report,
        raw_overall_score=raw_result.overall_score, score_delta=delta,
    )
