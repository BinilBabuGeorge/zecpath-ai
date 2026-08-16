"""
Section extraction for Day 12's semantic matcher -- pulls out the specific
blocks of text (Skills, Experience, Responsibilities) that get compared
component-by-component, rather than comparing whole documents.
"""

import re
from typing import Dict, List

RESUME_LABELS = ["Summary", "Skills", "Experience", "Education", "Certifications"]
JD_LABELS = ["About the Role", "Required Skills", "Good to Have", "Education",
             "Responsibilities", "Salary Range"]


def _extract_block(text: str, label: str, all_labels: List[str]) -> str:
    """Extract the text between 'Label:' and the next known label."""
    others = [l for l in all_labels if l != label]
    pattern = rf"^{re.escape(label)}:\s*\n?(.*?)(?=^(?:{'|'.join(re.escape(l) for l in others)}):|\Z)"
    match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else ""


def _extract_inline_field(text: str, label: str) -> str:
    """Extract 'Label: value' on a single line (e.g. 'Skills: React, Node')."""
    match = re.search(rf"^{re.escape(label)}:\s*(.+)$", text, re.MULTILINE | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def extract_resume_sections(text: str) -> Dict[str, str]:
    """Returns {skills, experience, overall} for a resume."""
    skills = _extract_inline_field(text, "Skills") or _extract_block(text, "Skills", RESUME_LABELS)
    experience = _extract_block(text, "Experience", RESUME_LABELS)
    return {
        "skills": skills,
        "experience": experience,
        "overall": text.strip(),
    }


def extract_jd_sections(text: str) -> Dict[str, str]:
    """Returns {skills, experience, overall} for a JD (experience maps to
    Responsibilities, since that's the JD's closest equivalent)."""
    required = _extract_block(text, "Required Skills", JD_LABELS)
    nice_to_have = _extract_block(text, "Good to Have", JD_LABELS)
    responsibilities = _extract_block(text, "Responsibilities", JD_LABELS)
    return {
        "skills": (required + "\n" + nice_to_have).strip(),
        "experience": responsibilities,
        "overall": text.strip(),
    }
