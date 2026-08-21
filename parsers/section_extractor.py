"""
Section extraction (originally Day 12) -- pulls Skills/Experience/
Responsibilities blocks out of resume and JD text.
"""

import re
from typing import Dict, List

RESUME_LABELS = ["Summary", "Skills", "Experience", "Education", "Certifications"]
JD_LABELS = ["About the Role", "Required Skills", "Good to Have", "Education",
             "Responsibilities", "Salary Range"]


def _extract_block(text: str, label: str, all_labels: List[str]) -> str:
    others = [l for l in all_labels if l != label]
    pattern = rf"^{re.escape(label)}:\s*\n?(.*?)(?=^(?:{'|'.join(re.escape(l) for l in others)}):|\Z)"
    match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else ""


def _extract_inline_field(text: str, label: str) -> str:
    match = re.search(rf"^{re.escape(label)}:\s*(.+)$", text, re.MULTILINE | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def extract_resume_sections(text: str) -> Dict[str, str]:
    # STABILITY (Day 18): None or a non-string resume_text used to crash 4+
    # calls deep inside re.search() with an opaque "expected string or
    # bytes-like object, got 'NoneType'" TypeError -- reproducible, verified
    # in this session. Validating at the entry point instead gives a clear,
    # immediate error pointing at the actual problem (useful for a future
    # API layer converting this into a clean 400 response, per Day 16's
    # error-standard design) rather than a stack trace through internals.
    if not isinstance(text, str):
        raise TypeError(f"resume text must be a string, got {type(text).__name__}")
    skills = _extract_inline_field(text, "Skills") or _extract_block(text, "Skills", RESUME_LABELS)
    experience = _extract_block(text, "Experience", RESUME_LABELS)
    return {"skills": skills, "experience": experience, "overall": text.strip()}


def extract_jd_sections(text: str) -> Dict[str, str]:
    if not isinstance(text, str):
        raise TypeError(f"job description text must be a string, got {type(text).__name__}")
    required = _extract_block(text, "Required Skills", JD_LABELS)
    nice_to_have = _extract_block(text, "Good to Have", JD_LABELS)
    responsibilities = _extract_block(text, "Responsibilities", JD_LABELS)
    return {
        "skills": (required + "\n" + nice_to_have).strip(),
        "experience": responsibilities,
        "overall": text.strip(),
    }
