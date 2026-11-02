"""
ATS AI Service (Day 2 Process 1.0)
Input:  resume text + job description (or, legacy, a list of required keywords)
Output: ATS score, zone, and per-component breakdown

DAY 57: this service used to be a Day 2 placeholder that counted keyword matches, so the number it returned had nothing in
common with the ATS engine the rest of the project uses. It is now wired to the real engine (`parsers.ats_scoring_engine`).

TWO MODES, reported in `scoring_mode` so a caller can never confuse them:
  * "ats_engine"       -- `job_description` given: the real ATS score (0-100, raw scale) and zone.
  * "keyword_coverage" -- only `job_requirements` given: the original percentage of listed keywords found. DEPRECATED, kept so
                          existing callers keep working; it is NOT comparable with an ats_engine score.

SCORE STABILITY: the real engine's TF-IDF vocabulary is fitted on a corpus, and the score depends on it (measured: fitting on
the job description alone moves a score by up to 5.5 points; fitting on resume + job description moves it by at most 0.8
against a 20-document corpus). Per request the vocabulary is therefore fitted on exactly the resume and job description given,
so the same pair always scores the same regardless of earlier requests. Pass `matcher=` to use a shared corpus for batch work.
"""

from typing import Any, Dict, Optional

from utils.base_service import BaseAIService, MAX_ITEMS, ServiceInputError


class ATSService(BaseAIService):
    service_name = "ats_ai_service"

    def __init__(self, matcher: Optional[Any] = None) -> None:
        super().__init__()
        self._matcher = matcher

    def process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        resume_text = self._get_text(payload, "resume_text", required=False, allow_empty=True) or ""
        job_description = self._get_text(payload, "job_description", required=False)
        requirements = self._get_list(payload, "job_requirements")

        if job_description is not None:
            return self._score_with_engine(resume_text, job_description)
        if requirements is not None:
            return self._keyword_coverage(resume_text, requirements)
        raise ServiceInputError("missing_field", "Provide 'job_description' (real ATS scoring) or 'job_requirements' (deprecated keyword coverage).", "job_description")

    # -- real ATS ---------------------------------------------------------------------------------
    def _score_with_engine(self, resume_text: str, job_description: str) -> Dict[str, Any]:
        from parsers.ats_scoring_engine import score_candidate
        from parsers.cross_round_aggregation_engine import ats_zone_of
        from parsers.resume_extractor import normalize_section_headings
        from parsers.semantic_matcher import SemanticMatcher

        self.logger.info("Scoring resume (%d chars) against a job description (%d chars)", len(resume_text), len(job_description))
        warnings = []
        if not resume_text.strip():
            warnings.append("The resume text is empty, so there is nothing to score.")
        # Uploaded files are heading-normalised at extraction; resume text sent straight to the API must be too, or a
        # resume headed "Technical Skills" is scored as having none (Day 57).
        resume_text = normalize_section_headings(resume_text)
        try:
            matcher = self._matcher or SemanticMatcher([resume_text or " ", job_description])
            result = score_candidate(resume_text, job_description, matcher)
        except ValueError as exc:
            if "vocabulary" in str(exc):          # scikit-learn: the texts hold nothing but stop words / symbols
                raise ServiceInputError("invalid_input", "The job description has no usable words to compare against.", "job_description") from exc
            raise
        if not any(c.name == "skill_match" and getattr(c, "available", False) for c in result.components):
            warnings.append("No skills could be compared (the job description has no recognisable requirements section, or the resume lists no skills), "
                            "so the score reflects missing structure rather than a mismatch and the zone is capped at 'review'.")
        response = self._base_response()
        response.update({
            "scoring_mode": "ats_engine",
            "ats_score": round(result.overall_score, 2),
            "zone": ats_zone_of(result),
            "role_category": result.role_category,
            "components": [{"name": c.name, "score": round(c.score, 2) if c.score is not None else None, "available": bool(getattr(c, "available", True))}
                          for c in result.components],
            "warnings": warnings,
        })
        return response

    # -- deprecated keyword coverage --------------------------------------------------------------
    def _keyword_coverage(self, resume_text: str, requirements: list) -> Dict[str, Any]:
        if any(not isinstance(r, str) for r in requirements):
            raise ServiceInputError("invalid_input", "'job_requirements' must be a list of text items.", "job_requirements")
        self.logger.info("Keyword coverage of resume against %d requirements (deprecated mode)", len(requirements))
        matched_keywords = [kw for kw in requirements if kw.lower() in resume_text.lower()]
        score = round(100 * len(matched_keywords) / max(len(requirements), 1), 2)
        response = self._base_response()
        response.update({
            "scoring_mode": "keyword_coverage",
            "matched_keywords": matched_keywords,
            "ats_score": score,
            "warnings": ["Deprecated mode: this is the percentage of listed keywords found, NOT an ATS engine score. Send 'job_description' for the real score."],
        })
        return response


if __name__ == "__main__":
    demo_payload = {
        "resume_text": "Experienced MERN stack developer skilled in React and Node.js",
        "job_description": "We need a MERN developer with React, Node.js and MongoDB experience.",
    }
    print(ATSService().run(demo_payload))
