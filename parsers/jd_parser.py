"""
Job Description Parsing System (Day 6)

Converts a raw job description (plain text, already extracted by the
Day 5 resume/JD text extraction engine) into a structured JobProfile
object matching schemas/job_description_schema.json (Day 4).

Public API:
    parse_jd(raw_text: str) -> dict   # JobProfile-shaped dict
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Skill synonym normalization
# ---------------------------------------------------------------------------
# Maps many written variations of the same skill to one canonical name, so
# "ReactJS", "React.js", and "React" all become the same SkillObject.name,
# and can be matched directly against a candidate's parsed skills (Day 4/5).

SKILL_SYNONYMS: Dict[str, str] = {
    "react": "React.js", "reactjs": "React.js", "react.js": "React.js", "react js": "React.js",
    "node": "Node.js", "nodejs": "Node.js", "node.js": "Node.js", "node js": "Node.js",
    "express": "Express.js", "expressjs": "Express.js", "express.js": "Express.js",
    "mongodb": "MongoDB", "mongo db": "MongoDB", "mongo": "MongoDB",
    "typescript": "TypeScript", "ts": "TypeScript",
    "javascript": "JavaScript", "js": "JavaScript",
    "git": "Git", "github": "GitHub", "git / github": "Git",
    "rest api design": "REST APIs", "rest apis": "REST APIs", "rest api": "REST APIs",
    "docker": "Docker",
    "salesforce crm": "Salesforce", "salesforce": "Salesforce",
    "cold calling": "Cold Calling",
    "negotiation skills": "Negotiation", "negotiation": "Negotiation",
    "lead generation": "Lead Generation",
    "crm": "CRM",
}

# Category assignment for common skills — mirrors SkillObject.category in Day 4 schema
SKILL_CATEGORY: Dict[str, str] = {
    "React.js": "technical", "Node.js": "technical", "Express.js": "technical",
    "MongoDB": "technical", "TypeScript": "technical", "JavaScript": "technical",
    "REST APIs": "technical", "Docker": "tool", "Git": "tool", "GitHub": "tool",
    "Salesforce": "tool", "CRM": "tool",
    "Cold Calling": "soft", "Negotiation": "soft", "Lead Generation": "soft",
}

# ---------------------------------------------------------------------------
# Role / designation normalization
# ---------------------------------------------------------------------------
# Maps job-title variations seen across different employers to one canonical
# family name, so the ATS/Decision services can group similar postings.

ROLE_SYNONYMS: List[tuple] = [
    (re.compile(r"mern\s*stack\s*developer|frontend\s*engineer\s*\(mern\)|full[\s-]?stack\s*developer\s*\(mern\)", re.I), "MERN Stack Developer"),
    (re.compile(r"\bsales\s*executive\b|\bbusiness\s*development\s*executive\b|\bbde\b", re.I), "Sales Executive"),
]


def normalize_role(job_title: str) -> str:
    """Return the canonical role family name for a job title, or the
    original title unchanged if no known variation matches."""
    for pattern, canonical in ROLE_SYNONYMS:
        if pattern.search(job_title):
            return canonical
    return job_title.strip()


def normalize_skill(raw_skill: str) -> Dict[str, str]:
    """Map a raw skill string to a canonical SkillObject {name, category}."""
    key = raw_skill.strip().lower()
    canonical = SKILL_SYNONYMS.get(key, raw_skill.strip())
    category = SKILL_CATEGORY.get(canonical, "domain")
    return {"name": canonical, "category": category}


# ---------------------------------------------------------------------------
# Field extraction helpers
# ---------------------------------------------------------------------------

def _extract_line_field(text: str, label: str) -> Optional[str]:
    """Extract the value after 'Label: value' on its own line."""
    match = re.search(rf"^{re.escape(label)}:\s*(.+)$", text, re.MULTILINE | re.IGNORECASE)
    return match.group(1).strip() if match else None


def _extract_block(text: str, label: str, next_labels: List[str]) -> List[str]:
    """Extract bullet lines under a 'Label:' block, stopping at the next
    known section label. Returns a list of cleaned bullet strings."""
    pattern = rf"^{re.escape(label)}:\s*\n(.*?)(?=^(?:{'|'.join(re.escape(l) for l in next_labels)}):|\Z)"
    match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE | re.DOTALL)
    if not match:
        return []
    block = match.group(1)
    lines = []
    for raw_line in block.split("\n"):
        line = raw_line.strip().lstrip("-").strip()
        if line:
            lines.append(line)
    return lines


def _parse_experience(exp_str: Optional[str]) -> Dict[str, Optional[float]]:
    """Parse strings like '2-4 years', '1-3 yrs' into {minYears, maxYears}."""
    if not exp_str:
        return {"minYears": None, "maxYears": None}
    match = re.search(r"(\d+(?:\.\d+)?)\s*[-to]+\s*(\d+(?:\.\d+)?)", exp_str)
    if match:
        return {"minYears": float(match.group(1)), "maxYears": float(match.group(2))}
    single = re.search(r"(\d+(?:\.\d+)?)", exp_str)
    if single:
        return {"minYears": float(single.group(1)), "maxYears": None}
    return {"minYears": None, "maxYears": None}


def _parse_salary(salary_str: Optional[str]) -> Optional[Dict]:
    """Parse strings like '\u20b98,00,000 - \u20b914,00,000 per annum',
    '900000 - 1500000 INR', or 'Rs. 400000 to Rs. 700000' into
    {min, max, currency}."""
    if not salary_str:
        return None
    numbers = re.findall(r"[\d,]+", salary_str)
    numbers = [int(n.replace(",", "")) for n in numbers if n.replace(",", "").isdigit()]
    if len(numbers) < 2:
        return None
    currency = "INR" if re.search(r"inr|rs\.?|\u20b9|rupee", salary_str, re.I) else "USD"
    return {"min": numbers[0], "max": numbers[1], "currency": currency}


def _parse_employment_type(raw: Optional[str]) -> str:
    if not raw:
        return "full-time"
    normalized = raw.strip().lower().replace(" ", "-")
    valid = {"full-time", "part-time", "contract", "internship"}
    return normalized if normalized in valid else "full-time"


def _parse_education(edu_lines: List[str]) -> Dict:
    if not edu_lines:
        return {}
    text = " ".join(edu_lines)
    mandatory = "preferred" not in text.lower()
    return {"degree": text, "mandatory": mandatory}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

ALL_LABELS = [
    "Job Title", "Department", "Location", "Experience Required", "Employment Type",
    "About the Role", "Required Skills", "Good to Have", "Education",
    "Responsibilities", "Salary Range",
]


def parse_jd(raw_text: str, job_id: str = "JOB-UNKNOWN") -> Dict:
    """Parse raw JD text into a JobProfile-shaped dict (Day 4 schema)."""
    text = raw_text.replace("\r\n", "\n")

    job_title = _extract_line_field(text, "Job Title") or "Unknown Role"
    department = _extract_line_field(text, "Department") or ""
    location = _extract_line_field(text, "Location") or ""
    experience_raw = _extract_line_field(text, "Experience Required")
    employment_type_raw = _extract_line_field(text, "Employment Type")
    salary_raw = _extract_line_field(text, "Salary Range")

    required_skills_raw = _extract_block(text, "Required Skills", ALL_LABELS)
    nice_to_have_raw = _extract_block(text, "Good to Have", ALL_LABELS)
    education_lines = _extract_block(text, "Education", ALL_LABELS)
    responsibilities = _extract_block(text, "Responsibilities", ALL_LABELS)

    # Some JDs list multiple skills separated by commas on one line
    def _split_skills(lines: List[str]) -> List[str]:
        result = []
        for line in lines:
            result.extend(s.strip() for s in line.split(",") if s.strip())
        return result

    required_skills = [normalize_skill(s) for s in _split_skills(required_skills_raw)]
    nice_to_have_skills = [normalize_skill(s) for s in _split_skills(nice_to_have_raw)]

    profile = {
        "jobId": job_id,
        "jobTitle": normalize_role(job_title),
        "jobTitleOriginal": job_title,
        "department": department,
        "location": location,
        "employmentType": _parse_employment_type(employment_type_raw),
        "experienceRequired": _parse_experience(experience_raw),
        "requiredSkills": required_skills,
        "niceToHaveSkills": nice_to_have_skills,
        "educationRequired": _parse_education(education_lines),
        "responsibilities": responsibilities,
        "salaryRange": _parse_salary(salary_raw),
    }
    return profile


if __name__ == "__main__":
    import sys
    import json
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        raw = f.read()
    result = parse_jd(raw, job_id="JOB-DEMO")
    print(json.dumps(result, indent=2))
