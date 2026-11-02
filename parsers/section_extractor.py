"""
Section extraction (originally Day 12) -- pulls Skills/Experience/
Responsibilities blocks out of resume and JD text.
"""

import re
from typing import Dict, List

RESUME_LABELS = ["Summary", "Skills", "Experience", "Education", "Certifications"]
JD_LABELS = ["About the Role", "Required Skills", "Good to Have", "Education",
             "Responsibilities", "Salary Range"]

# Day 57: only the exact labels above used to be recognised, so the usual wording ("Technical Skills", "Work Experience" on a
# resume; "Requirements", "Must Have", "Key Responsibilities" in a job description) made a whole section invisible: the same
# resume scored 14.9 under "Technical Skills" and 50.7 under "Skills". An alias counts only when it is the WHOLE line
# (case and a trailing colon ignored) -- never a phrase inside a sentence.
RESUME_ALIASES = {
    "Summary": ["professional summary", "career summary", "career objective", "objective", "profile", "professional profile", "about me", "summary of qualifications"],
    "Skills": ["technical skills", "key skills", "core skills", "skills & tools", "skills and tools", "technical proficiency", "technical expertise",
               "technologies", "tech stack", "core competencies", "areas of expertise", "skills summary", "skill set", "skillset"],
    "Experience": ["work experience", "professional experience", "employment history", "work history", "career history", "relevant experience",
                   "professional background", "employment experience"],
    "Education": ["academic background", "academic qualifications", "educational qualifications", "education & qualifications",
                  "education and qualifications", "qualifications", "academics", "education details"],
    "Certifications": ["certificates", "licenses & certifications", "licenses and certifications", "certifications & courses", "professional certifications"],
}
JD_ALIASES = {
    "About the Role": ["job description", "role overview", "overview", "about the job", "job summary", "about this role"],
    "Required Skills": ["requirements", "key requirements", "required qualifications", "skills required", "must have", "must-have", "must haves",
                        "what we are looking for", "what we're looking for", "technical requirements", "required experience and skills", "skills & requirements"],
    "Good to Have": ["nice to have", "nice-to-have", "preferred skills", "preferred qualifications", "bonus skills", "plus points", "desirable", "good to have skills"],
    "Responsibilities": ["key responsibilities", "roles and responsibilities", "roles & responsibilities", "duties", "what you will do", "what you'll do",
                         "job responsibilities", "job duties"],
    "Education": ["educational qualifications", "education & qualifications", "education and qualifications"],
    "Salary Range": ["compensation", "salary", "pay range", "salary & benefits"],
}


def normalize_headings(text: str, labels: List[str], aliases: Dict[str, List[str]]) -> str:
    """Rewrite any whole-line heading that is a known label or alias to 'Label:'."""
    lookup = {a: label for label, names in aliases.items() for a in names}
    lookup.update({l.lower(): l for l in labels})
    out = []
    for line in text.split("\n"):
        key = line.strip().rstrip(":").strip().lower()
        label = lookup.get(key)
        out.append(f"{label}:" if label else line)
    return "\n".join(out)


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
    text = normalize_headings(text, RESUME_LABELS, RESUME_ALIASES)
    skills = _extract_inline_field(text, "Skills") or _extract_block(text, "Skills", RESUME_LABELS)
    experience = _extract_block(text, "Experience", RESUME_LABELS)
    return {"skills": skills, "experience": experience, "overall": text.strip()}


def extract_jd_sections(text: str) -> Dict[str, str]:
    if not isinstance(text, str):
        raise TypeError(f"job description text must be a string, got {type(text).__name__}")
    text = normalize_headings(text, JD_LABELS, JD_ALIASES)
    required = _extract_block(text, "Required Skills", JD_LABELS)
    nice_to_have = _extract_block(text, "Good to Have", JD_LABELS)
    responsibilities = _extract_block(text, "Responsibilities", JD_LABELS)
    return {
        "skills": (required + "\n" + nice_to_have).strip(),
        "experience": responsibilities,
        "overall": text.strip(),
    }
