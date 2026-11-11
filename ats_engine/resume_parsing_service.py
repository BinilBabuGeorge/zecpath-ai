"""
Resume Parsing Service (Day 59)

WHY THIS EXISTS. Day 59 asks for a "Resume parsing API". Until now there was no such thing behind the stable boundary: the four
Day 57 services cover ATS scoring, screening, interviews and decisions, while resume reading lived in loose functions
(`extract_resume`, `extract_skills`, `parse_experience`, `parse_education`, `parse_certifications`) and `parsers/resume_parser.py`
is still a Day 1 stub. This service wraps those existing functions; it adds NO parsing logic of its own.

Input  : candidate_id (pseudonymous ref), file_ref (a key inside the resume store), file_type (pdf | docx),
         as_of_date (optional ISO date, what "Present" means for a current job)
Output : cleaned text, sections found, skills, experience, education, certifications, warnings

It follows the Day 57 contract: `run(payload)` never raises and always returns a success or an error envelope. The upload error
codes (`unsupported_type`, `file_not_found`, `empty_file`, `corrupt_file`) reach the caller as the envelope's `error.code`.

WHAT IT DELIBERATELY DOES NOT RETURN: name, email or phone. The text carries them (it is the resume), but the structured fields do
not, because the ATS never uses them, Day 15 masks them for fairness, and the audit log forbids them. Identity belongs to the
backend's identity store, not to an AI output (see docs/day59_ai_integration_document.md, decision D3).

THE FILE. The service never opens a path the caller chose. `file_ref` is resolved through `resolver` (default: inside
`MEDIA_STORAGE_PATH`) and anything that resolves outside the store (`../`, an absolute path) is refused. A production resolver
would fetch the object from encrypted storage with a service credential; none exists yet, so the default is local files.
"""

from __future__ import annotations

import copy
import hashlib
from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from utils.base_service import BaseAIService, ServiceInputError
from utils.config import MEDIA_STORAGE_PATH
from utils.perf import BoundedLRU

SUPPORTED_FILE_TYPES = ("pdf", "docx")
MAX_FILE_REF_CHARS = 512

# PERFORMANCE (Day 60): parsing the same file again (a retried job, a re-uploaded CV, a re-score after a job description changes) repeats
# work that is 87% pdfplumber for a PDF. The parse is a pure function of the file's BYTES, the file type and the "as of" date, so the
# result is cached under a hash of exactly those (never under the file name, which can be reused for a different file). Bounded by
# entries and by bytes; each caller gets its own copy, with its own candidate_id.
_PARSE_CACHE = BoundedLRU("resume_parse", max_items=256, max_bytes=16_000_000, sizeof=lambda v: 4000 + 3 * len(v.get("cleaned_text", "")))


def default_file_resolver(file_ref: str) -> str:
    """Resolve a store key to a local path, refusing anything outside the resume store."""
    root = Path(MEDIA_STORAGE_PATH).resolve()
    target = (root / file_ref).resolve()
    if target != root and root not in target.parents:
        raise ServiceInputError("invalid_input", "'file_ref' must point inside the resume store.", "file_ref")
    return str(target)


class ResumeParsingService(BaseAIService):
    service_name = "resume_parsing_service"

    def __init__(self, resolver: Optional[Callable[[str], str]] = None) -> None:
        super().__init__()
        self._resolver = resolver or default_file_resolver

    def process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        candidate_id = self._get_text(payload, "candidate_id")
        file_ref = self._get_text(payload, "file_ref")
        if len(file_ref) > MAX_FILE_REF_CHARS:
            raise ServiceInputError("too_large", f"'file_ref' is longer than {MAX_FILE_REF_CHARS} characters.", "file_ref")
        if payload.get("file_type") is None:
            raise ServiceInputError("missing_field", "'file_type' is required.", "file_type")
        file_type = self._get_choice(payload, "file_type", SUPPORTED_FILE_TYPES, default="pdf")
        as_of = self._get_as_of(payload)

        path = self._resolver(file_ref)
        if Path(path).suffix.lower().lstrip(".") != file_type:
            raise ServiceInputError("invalid_input", f"'file_ref' does not end in .{file_type}, which does not match 'file_type'.", "file_type")

        self.logger.info("Parsing a %s resume for candidate %s", file_type, candidate_id)
        cache_key = self._cache_key(path, file_type, as_of)
        if cache_key is not None:
            hit = _PARSE_CACHE.get_or_compute(cache_key, lambda: self._parse_file(path, file_type, as_of))
            parsed = copy.deepcopy(hit)
        else:
            parsed = self._parse_file(path, file_type, as_of)
        response = self._base_response()
        response["candidate_id"] = candidate_id
        response.update(parsed)
        return response

    @staticmethod
    def _cache_key(path: str, file_type: str, as_of: Optional[date]):
        """A hash of the file's bytes plus the file type and the resolved date, or None if the file cannot be read (the normal error
        path then reports it exactly as before)."""
        try:
            data = Path(path).read_bytes()
        except OSError:
            return None
        if not data:
            return None
        return (hashlib.blake2b(data, digest_size=20).hexdigest(), file_type, (as_of or date.today()).isoformat())

    def _parse_file(self, path: str, file_type: str, as_of: Optional[date]) -> Dict[str, Any]:
        """Everything in the response that depends only on the file (not on the caller)."""
        from parsers.education_parser import parse_certifications, parse_education
        from parsers.experience_parser import compute_total_experience, parse_experience, reference_date
        from parsers.resume_extractor import ResumeUploadError, extract_resume
        from parsers.skill_extractor import extract_skills

        try:
            extracted = extract_resume(path)
        except ResumeUploadError as exc:
            raise ServiceInputError(exc.code, str(exc), "file_ref") from exc

        warnings: List[str] = list(extracted.warnings)
        skills, entries_out, education, certs = [], [], [], []
        total_years = 0.0
        total_months = 0
        gaps: List[Dict[str, str]] = []
        overlap_count = 0
        if extracted.has_text:
            text = extracted.cleaned_text
            skills = extract_skills(text)
            with reference_date(as_of):
                summary = compute_total_experience(parse_experience(text))
            total_years, total_months = summary.total_years, summary.total_months
            entries_out = summary.entries
            gaps = [{"start": a.isoformat(), "end": b.isoformat()} for a, b in summary.gaps]
            overlap_count = len(summary.overlaps)
            warnings.extend(summary.warnings)
            education = parse_education(text)
            certs = parse_certifications(text)

        return {
            "file_type": file_type,
            "as_of_date": (as_of or date.today()).isoformat(),
            "has_text": extracted.has_text,
            "line_count": extracted.line_count,
            "detected_sections": list(extracted.detected_sections),
            "cleaned_text": extracted.cleaned_text,
            "skills": [{"name": s.name, "group": s.group, "category": s.category, "confidence": s.confidence,
                        "method": s.method, "mentions": list(s.mentions)} for s in skills],
            "experience": {
                "total_years": total_years, "total_months": total_months,
                "entries": [{"title": e.title, "company": e.company, "start_year": e.start_year, "start_month": e.start_month,
                             "end_year": e.end_year, "end_month": e.end_month, "is_current": e.is_current,
                             "description": e.description} for e in entries_out],
                "gaps": gaps, "overlap_count": overlap_count,
            },
            "education": [{"raw_degree": e.raw_degree, "degree": e.degree, "level": e.level, "field_of_study": e.field_of_study,
                           "institution": e.institution, "year": e.year} for e in education],
            "certifications": [{"name": c.name, "issuer": c.issuer, "year": c.year, "category": c.category} for c in certs],
            "warnings": warnings,
        }

    @staticmethod
    def _get_as_of(payload: Dict[str, Any]) -> Optional[date]:
        raw = payload.get("as_of_date")
        if raw is None:
            return None
        if not isinstance(raw, str):
            raise ServiceInputError("invalid_input", "'as_of_date' must be an ISO date text such as 2026-11-01.", "as_of_date")
        try:
            return date.fromisoformat(raw)
        except ValueError as exc:
            raise ServiceInputError("invalid_input", "'as_of_date' must be an ISO date such as 2026-11-01.", "as_of_date") from exc


if __name__ == "__main__":
    print(ResumeParsingService().run({"candidate_id": "C001", "file_ref": "none.pdf", "file_type": "pdf"}))
