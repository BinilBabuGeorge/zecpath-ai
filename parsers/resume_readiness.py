"""
Resume Readiness Check (Day 58 prototype)

WHAT THIS IS. The working prototype behind the Day 58 innovation proposal: a candidate-facing check that answers ONE question --
"can the system read my resume?" It is stateless (nothing is stored), uses only modules the project already has (heading
normalisation and section extraction from Day 57, the experience parser, the skill extractor), and runs in milliseconds.

WHY IT EARNS A PROTOTYPE. Day 57 found that the same resume scored 14.9 or 50.8 depending only on whether its skills section was
headed "Technical Skills" or "Skills": a candidate could be silently shut out by formatting. After the fix, the engine reads
the common wordings, but any section it cannot recognise is still invisible, and the candidate never finds out. This check
tells them, at the moment they can fix it.

DESIGN RULES (each is a decision, not an accident):
  * It reports whether the SYSTEM CAN READ the resume. It never returns the ATS score or its weights and never says how to
    raise a score: coaching a candidate against the exact rubric that grades them invites gaming (Goodhart's law) and would
    leak the scoring logic.
  * The only job-specific hint is a plain list of skills the job description names that the resume does not mention, with the
    reminder to add them ONLY if the candidate genuinely has them. It never suggests inventing experience.
  * Nothing is inferred about the person: no emotion, no personality, no demographic attribute. It looks at document structure.
  * The report never contains the resume text, so it can be shown or logged without copying personal data.
  * It does not decide anything about the candidate and is not an input to any hiring decision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

from parsers.experience_parser import compute_total_experience, parse_experience, reference_date
from parsers.resume_extractor import KNOWN_SECTIONS, normalize_section_headings
from parsers.section_extractor import RESUME_ALIASES, extract_jd_sections, extract_resume_sections
from parsers.skill_extractor import extract_skills
from utils.logger import get_logger

logger = get_logger(__name__)

MIN_WORDS = 80
MAX_WORDS = 1500
_HEADING_WORD = re.compile(r"^[A-Z][A-Za-z&/\-]*$")


@dataclass(frozen=True)
class ReadinessIssue:
    code: str
    severity: str            # blocker | warning | tip
    message: str
    suggestion: str


@dataclass
class ReadinessReport:
    sections_found: Dict[str, bool]
    unrecognized_headings: List[str]
    experience_entries: int
    experience_years: float
    skills_found: List[str]
    skills_in_job_not_in_resume: List[str]
    word_count: int
    issues: List[ReadinessIssue] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        """True when nothing stops the system reading the resume (warnings and tips do not)."""
        return not any(i.severity == "blocker" for i in self.issues)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ready": self.ready, "sections_found": dict(self.sections_found), "unrecognized_headings": list(self.unrecognized_headings),
            "experience_entries": self.experience_entries, "experience_years": self.experience_years, "skills_found": list(self.skills_found),
            "skills_in_job_not_in_resume": list(self.skills_in_job_not_in_resume), "word_count": self.word_count,
            "issues": [{"code": i.code, "severity": i.severity, "message": i.message, "suggestion": i.suggestion} for i in self.issues],
        }


def _known_heading_keys() -> set:
    keys = {s.lower() for s in KNOWN_SECTIONS}
    for aliases in RESUME_ALIASES.values():
        keys.update(aliases)
    return keys


def _looks_like_heading(line: str) -> bool:
    """A short line that is ALL CAPS or ends with a colon. (Title-case lines are too often plain content such as a hobby
    or a project name, so they are not flagged: missing a heading is better than inventing one.)"""
    raw = line.strip()
    s = raw.rstrip(":").strip()
    if not s or len(s) > 30 or any(c in s for c in ",.@0123456789•*-("):
        return False
    words = s.split()
    return 1 <= len(words) <= 4 and (s.isupper() or (raw.endswith(":") and all(_HEADING_WORD.match(w) for w in words)))


def check_resume_readiness(resume_text: str, job_description: Optional[str] = None, as_of: Optional[date] = None) -> ReadinessReport:
    """Report whether the system can read this resume. `as_of` pins what "Present" means (default: today)."""
    if not isinstance(resume_text, str):
        raise TypeError(f"resume_text must be text, got {type(resume_text).__name__}")
    if job_description is not None and not isinstance(job_description, str):
        raise TypeError(f"job_description must be text, got {type(job_description).__name__}")

    text = normalize_section_headings(resume_text)
    lines = [ln.strip() for ln in text.split("\n")]
    words = len(resume_text.split())

    sections = {name: any(ln.lower().startswith(name.lower() + ":") for ln in lines) for name in KNOWN_SECTIONS}
    known = _known_heading_keys()
    first = next((i for i, ln in enumerate(lines) if ln), None)
    unrecognized = [ln.rstrip(":").strip() for i, ln in enumerate(lines)
                    if i != first and _looks_like_heading(ln) and ln.rstrip(":").strip().lower() not in known]
    unrecognized = list(dict.fromkeys(unrecognized))

    with reference_date(as_of):
        summary = compute_total_experience(parse_experience(text)) if resume_text.strip() else None
    entries = len(summary.entries) if summary else 0
    years = summary.total_years if summary else 0.0

    skills = sorted({s.name for s in extract_skills(extract_resume_sections(text)["skills"])}) if sections["Skills"] else []
    all_resume_skills = {s.name.lower() for s in extract_skills(text)} if resume_text.strip() else set()
    gap: List[str] = []
    if job_description and job_description.strip():
        wanted = [s.name for s in extract_skills(extract_jd_sections(job_description)["skills"])]
        gap = sorted({w for w in wanted if w.lower() not in all_resume_skills})

    issues: List[ReadinessIssue] = []

    def add(code: str, sev: str, msg: str, tip: str) -> None:
        issues.append(ReadinessIssue(code, sev, msg, tip))

    if not resume_text.strip():
        add("NO_TEXT", "blocker", "The file has no readable text (it may be blank, or a scanned image).", "Upload a DOCX or a PDF that you can select text from.")
    else:
        if not sections["Skills"]:
            add("NO_SKILLS_SECTION", "blocker", "We could not find a Skills section, so your skills may not be read.", "Add a heading called 'Skills' and list your skills under it.")
        if not sections["Experience"]:
            add("NO_EXPERIENCE_SECTION", "warning", "We could not find an Experience section.", "If you have worked, add a heading called 'Experience'. Students can skip this.")
        elif entries == 0 and not (summary and summary.warnings):
            add("NO_DATED_ROLES", "warning", "We found an Experience section but could not read any dated roles.", "Write each role as: Role, Company (Jan 2022 - Present).")
        for w in (summary.warnings if summary else []):
            add("DATE_PROBLEM", "warning", w[0].upper() + w[1:] + ".", "Check the dates of that role.")
        if unrecognized:
            add("UNRECOGNIZED_HEADINGS", "tip", f"These headings are not read by the system: {', '.join(unrecognized)}.",
                "If they hold information that matters (for example skills or work history), also put it under Skills or Experience.")
        if words < MIN_WORDS:
            add("VERY_SHORT", "warning", f"The resume has only {words} words; the system may not find enough to read.", "Add detail about your skills and work.")
        elif words > MAX_WORDS:
            add("VERY_LONG", "tip", f"The resume has {words} words.", "Two pages is usually enough.")
        if gap:
            add("JOB_SKILLS_NOT_MENTIONED", "tip", f"The job description names skills your resume does not mention: {', '.join(gap)}.",
                "Add them only if you genuinely have them.")
    return ReadinessReport(sections, unrecognized, entries, years, skills, gap, words, issues)
