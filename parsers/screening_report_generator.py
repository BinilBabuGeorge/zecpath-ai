"""
AI Screening Report Generator (Day 28)

SCOPE, STATED HONESTLY UP FRONT: this module does NOT generate any new
text with an LLM. Every bullet in a report's strengths/risks/missing-
data sections is produced by a fixed template filled in from a real,
already-computed number or fact from Day 25/26/27 -- never freely
generated prose. That is a deliberate choice, not a limitation to
apologize for: a recruiter-facing report that claims to summarize an
AI evaluation should say only what the evaluation actually found,
in the evaluation's own numbers, not a paraphrase an LLM invented that
could drift from what was actually measured.

Nothing here is recomputed. This module's entire job is
aggregation and formatting of outputs that already exist:

    understand_answer()        (Day 25) -> StructuredAnswer, per turn
    score_screening_call()     (Day 26) -> ScreeningScoreResult
    build_communication_profile() (Day 27) -> CommunicationProfile
                                       |
                                       v
    generate_screening_report()  (Day 28, THIS module)
                                       |
                                       v
    ScreeningReport  --  .to_dict() (machine-readable)
                     --  .to_markdown() (recruiter-readable, exportable)

Every threshold used to decide what counts as a "strength" or a "risk"
(score >= 80, score < 50, hesitation rate > 10/100 words, etc.) is a
reasonable-but-arbitrary constant, exactly like Day 26's weight
profiles and Day 27's scoring formula -- named as constants here,
not buried as magic numbers, so a recruiter or a future engineer can
see and adjust the bar.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from parsers.answer_intent_engine import AnswerQuality, StructuredAnswer
from parsers.screening_scoring_engine import ScreeningScoreResult
from parsers.confidence_sentiment_engine import CommunicationProfile

# Thresholds -- named, adjustable, and documented as reasonable
# defaults rather than tuned values (same stance as Day 26/27).
_STRONG_ANSWER_THRESHOLD = 80.0
_WEAK_ANSWER_THRESHOLD = 50.0
_ELEVATED_HESITATION_RATE = 10.0     # per 100 words
_ELEVATED_UNCERTAINTY_RATE = 10.0    # per 100 words
_POSITIVE_SENTIMENT_THRESHOLD = 5.0  # matches Day 27's own label boundary
_NEGATIVE_SENTIMENT_THRESHOLD = -5.0
_RAW_TEXT_PREVIEW_LENGTH = 160


@dataclass
class ReportHighlights:
    salary_expectation: List[Dict] = field(default_factory=list)   # every non-None mention found, as stated
    availability: List[Dict] = field(default_factory=list)
    confirmed_skills: List[str] = field(default_factory=list)      # deduplicated union across all answers

    def to_dict(self) -> Dict:
        return {
            "salary_expectation": self.salary_expectation,
            "availability": self.availability,
            "confirmed_skills": self.confirmed_skills,
        }


@dataclass
class ScreeningReport:
    candidate_id: Optional[str]
    job_role: Optional[str]
    generated_at: str
    total_score: float
    communication_strength_score: float
    key_answers: List[Dict]
    strengths: List[str]
    risks: List[str]
    missing_data: List[str]
    highlights: ReportHighlights

    def to_dict(self) -> Dict:
        return {
            "candidate_id": self.candidate_id,
            "job_role": self.job_role,
            "generated_at": self.generated_at,
            "total_score": self.total_score,
            "communication_strength_score": self.communication_strength_score,
            "key_answers": self.key_answers,
            "strengths": self.strengths,
            "risks": self.risks,
            "missing_data": self.missing_data,
            "highlights": self.highlights.to_dict(),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def to_markdown(self) -> str:
        lines: List[str] = []
        lines.append(f"# Screening Report{f' — {self.candidate_id}' if self.candidate_id else ''}")
        if self.job_role:
            lines.append(f"**Role:** {self.job_role}")
        lines.append(f"**Generated:** {self.generated_at}")
        lines.append("")
        lines.append(f"**Total Screening Score:** {self.total_score} / 100")
        lines.append(f"**Communication Strength Score:** {self.communication_strength_score} / 100")
        lines.append("")

        lines.append("## Key Answers")
        lines.append("")
        lines.append("| Turn | Category | Quality | Score | Answer (preview) |")
        lines.append("|---|---|---|---|---|")
        for ka in self.key_answers:
            lines.append(f"| {ka['turn_id']} | {ka['category']} | {ka['quality']} | {ka['weighted_total']} | {ka['raw_text_preview']} |")
        lines.append("")

        lines.append("## Strengths")
        lines.append("")
        if self.strengths:
            for s in self.strengths:
                lines.append(f"- {s}")
        else:
            lines.append("- None identified against the current thresholds.")
        lines.append("")

        lines.append("## Risks")
        lines.append("")
        if self.risks:
            for r in self.risks:
                lines.append(f"- {r}")
        else:
            lines.append("- None identified.")
        lines.append("")

        lines.append("## Missing Data")
        lines.append("")
        if self.missing_data:
            for m in self.missing_data:
                lines.append(f"- {m}")
        else:
            lines.append("- None -- every question received a scorable answer.")
        lines.append("")

        lines.append("## Highlights")
        lines.append("")
        lines.append(f"- **Salary expectation (as stated by candidate):** {self.highlights.salary_expectation or 'Not stated / not extractable.'}")
        lines.append(f"- **Availability (as stated by candidate):** {self.highlights.availability or 'Not stated / not extractable.'}")
        lines.append(f"- **Confirmed skills mentioned:** {', '.join(self.highlights.confirmed_skills) if self.highlights.confirmed_skills else 'None mentioned.'}")
        lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section builders -- each one only restates facts already computed by
# Day 25/26/27, templated, never freely generated.
# ---------------------------------------------------------------------------

def _build_key_answers(answers: List[StructuredAnswer], scoring_result: ScreeningScoreResult) -> List[Dict]:
    scores_by_turn = {qs.turn_id: qs for qs in scoring_result.question_scores}
    key_answers = []
    for a in answers:
        qs = scores_by_turn.get(a.turn_id)
        preview = a.raw_text if len(a.raw_text) <= _RAW_TEXT_PREVIEW_LENGTH else a.raw_text[:_RAW_TEXT_PREVIEW_LENGTH] + "..."
        key_answers.append({
            "turn_id": a.turn_id,
            "category": a.question_category,
            "quality": a.quality.value,
            "weighted_total": qs.weighted_total if qs else None,
            "raw_text_preview": preview,
        })
    return key_answers


def _build_strengths(scoring_result: ScreeningScoreResult, communication_profile: CommunicationProfile) -> List[str]:
    strengths = []
    for qs in scoring_result.question_scores:
        if qs.quality == AnswerQuality.OK and qs.weighted_total >= _STRONG_ANSWER_THRESHOLD:
            strengths.append(f"Strong, complete answer on '{qs.question_category}' (score {qs.weighted_total}/100).")

    breakdown = communication_profile.component_breakdown
    if breakdown.get("avg_hesitation_rate_per_100_words", 0) == 0 and breakdown.get("avg_uncertainty_rate_per_100_words", 0) == 0:
        strengths.append("No hesitation or uncertainty markers detected across the call.")
    if breakdown.get("avg_sentiment_score", 0) > _POSITIVE_SENTIMENT_THRESHOLD:
        strengths.append(f"Positive overall sentiment expressed during screening (avg score {breakdown['avg_sentiment_score']}).")
    if communication_profile.contradiction_count == 0:
        strengths.append("No consistency conflicts detected across the candidate's answers.")

    return strengths


def _build_risks(scoring_result: ScreeningScoreResult, communication_profile: CommunicationProfile) -> List[str]:
    risks = []
    for qs in scoring_result.question_scores:
        if qs.quality != AnswerQuality.MISSING and qs.weighted_total < _WEAK_ANSWER_THRESHOLD:
            risks.append(f"Weak answer on '{qs.question_category}' (score {qs.weighted_total}/100, quality={qs.quality.value}).")

    for finding in communication_profile.contradiction_findings:
        risks.append(finding)

    breakdown = communication_profile.component_breakdown
    if breakdown.get("avg_hesitation_rate_per_100_words", 0) > _ELEVATED_HESITATION_RATE:
        risks.append(f"Elevated hesitation detected (avg rate {breakdown['avg_hesitation_rate_per_100_words']}/100 words).")
    if breakdown.get("avg_uncertainty_rate_per_100_words", 0) > _ELEVATED_UNCERTAINTY_RATE:
        risks.append(f"Elevated uncertainty language detected (avg rate {breakdown['avg_uncertainty_rate_per_100_words']}/100 words).")
    if breakdown.get("avg_sentiment_score", 0) < _NEGATIVE_SENTIMENT_THRESHOLD:
        risks.append(f"Negative overall sentiment expressed during screening (avg score {breakdown['avg_sentiment_score']}).")

    return risks


def _build_missing_data(answers: List[StructuredAnswer]) -> List[str]:
    missing = []
    for a in answers:
        if a.quality == AnswerQuality.MISSING:
            missing.append(f"No answer given for '{a.question_category}' ({a.turn_id}).")
        for note in a.notes:
            if "could not" in note.lower() or "could not extract" in note.lower() or "not found" in note.lower():
                missing.append(f"'{a.question_category}' ({a.turn_id}): {note}")
    return missing


def _build_highlights(answers: List[StructuredAnswer]) -> ReportHighlights:
    salary = [a.entities.salary_expectation for a in answers if a.entities.salary_expectation is not None]
    availability = [a.entities.availability for a in answers if a.entities.availability is not None]
    skills: List[str] = []
    for a in answers:
        for s in a.entities.skills:
            if s not in skills:
                skills.append(s)
    return ReportHighlights(salary_expectation=salary, availability=availability, confirmed_skills=skills)


# ---------------------------------------------------------------------------
# Entry point -- the "AI screening report builder" deliverable
# ---------------------------------------------------------------------------

def generate_screening_report(
    answers: List[StructuredAnswer],
    scoring_result: ScreeningScoreResult,
    communication_profile: CommunicationProfile,
    candidate_id: Optional[str] = None,
    job_role: Optional[str] = None,
) -> ScreeningReport:
    """Aggregates Day 25/26/27 output into one recruiter-facing report.
    Takes those three objects as-is; performs zero re-scoring or
    re-extraction -- purely aggregation, section-building, and
    formatting into the two exportable forms (.to_dict()/.to_json()
    for systems, .to_markdown() for recruiters).
    """
    return ScreeningReport(
        candidate_id=candidate_id, job_role=job_role,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        total_score=scoring_result.total_score,
        communication_strength_score=communication_profile.communication_strength_score,
        key_answers=_build_key_answers(answers, scoring_result),
        strengths=_build_strengths(scoring_result, communication_profile),
        risks=_build_risks(scoring_result, communication_profile),
        missing_data=_build_missing_data(answers),
        highlights=_build_highlights(answers),
    )
