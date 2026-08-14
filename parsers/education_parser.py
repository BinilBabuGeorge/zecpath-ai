"""
Education & Certification Parser (Day 11)

Extracts structured academic entries from resume text:
  - Education: degree, field of study, institution, graduation year
  - Certifications: name, issuer (if present), year, relevance category

Public API:
    parse_education(text) -> List[EducationEntry]
    parse_certifications(text) -> List[CertificationEntry]
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from parsers.education_dictionary import DEGREE_DICTIONARY, DEGREE_LEVEL_RANK, CERT_CATEGORY_KEYWORDS

# normalized synonym -> canonical degree name.
# All periods are stripped (not just trailing ones) when building keys, so
# "B.E.", "B.E", and "BE" all normalize to the same lookup key -- matching
# exactly how normalize_degree() below prepares its input for lookup.
def _normalize_key(text: str) -> str:
    return text.strip().replace(".", "").lower()


_DEGREE_LOOKUP = {}
for canonical, info in DEGREE_DICTIONARY.items():
    _DEGREE_LOOKUP[_normalize_key(canonical)] = canonical
    for syn in info["synonyms"]:
        _DEGREE_LOOKUP[_normalize_key(syn)] = canonical


# "B.Tech in Computer Science, VIT Vellore, 2021"  (field of study present)
EDUCATION_PATTERN_WITH_FIELD = re.compile(
    r"^-?\s*(?P<degree>[^,]+?)\s+in\s+(?P<field>[^,]+),\s*(?P<institution>[^,]+),\s*(?P<year>\d{4})\s*$",
    re.IGNORECASE,
)
# "B.Com, Osmania University, 2019"  (no field of study)
EDUCATION_PATTERN_NO_FIELD = re.compile(
    r"^-?\s*(?P<degree>[^,]+),\s*(?P<institution>[^,]+),\s*(?P<year>\d{4})\s*$",
    re.IGNORECASE,
)

# "MongoDB Certified Developer Associate (2023)"
# "AWS Solutions Architect - Associate, Amazon Web Services (2023)"  (issuer present)
CERTIFICATION_PATTERN = re.compile(
    r"^-?\s*(?P<name>[^(]+?)(?:,\s*(?P<issuer>[^(]+?))?\s*\((?P<year>\d{4})\)\s*$",
)


@dataclass
class EducationEntry:
    raw_degree: str
    degree: str          # canonical, or raw_degree unchanged if not in dictionary
    level: Optional[str]  # Diploma / Bachelor's / Master's / Doctorate / None if unknown
    field_of_study: Optional[str]
    institution: str
    year: int


@dataclass
class CertificationEntry:
    name: str
    issuer: Optional[str]
    year: Optional[int]
    category: str  # from CERT_CATEGORY_KEYWORDS, or "Other"


def normalize_degree(raw_degree: str) -> tuple:
    """Return (canonical_name, level) for a raw degree string, matching
    against known synonyms regardless of period placement (e.g. 'B.E.',
    'B.E', and 'BE' all resolve the same way). Falls back to
    (raw_degree, None) if unrecognized."""
    key = _normalize_key(raw_degree)
    canonical = _DEGREE_LOOKUP.get(key)
    if canonical:
        return canonical, DEGREE_DICTIONARY[canonical]["level"]
    return raw_degree.strip(), None


def categorize_certification(name: str) -> str:
    """Assign a relevance category to a certification based on keyword match."""
    lowered = name.lower()
    for category, keywords in CERT_CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in lowered:
                return category
    return "Other"


def parse_education(text: str) -> List[EducationEntry]:
    """Parse every education entry found in the given text."""
    entries = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        match = EDUCATION_PATTERN_WITH_FIELD.match(line)
        field = None
        if match:
            field = match.group("field").strip()
        else:
            match = EDUCATION_PATTERN_NO_FIELD.match(line)

        if not match:
            continue

        raw_degree = match.group("degree").strip()
        canonical, level = normalize_degree(raw_degree)

        entries.append(EducationEntry(
            raw_degree=raw_degree,
            degree=canonical,
            level=level,
            field_of_study=field,
            institution=match.group("institution").strip(),
            year=int(match.group("year")),
        ))

    return entries


def parse_certifications(text: str) -> List[CertificationEntry]:
    """Parse every certification entry found in the given text."""
    entries = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        match = CERTIFICATION_PATTERN.match(line)
        if not match:
            continue

        name = match.group("name").strip()
        issuer = match.group("issuer").strip() if match.group("issuer") else None
        year = int(match.group("year")) if match.group("year") else None

        entries.append(CertificationEntry(
            name=name,
            issuer=issuer,
            year=year,
            category=categorize_certification(name),
        ))

    return entries


if __name__ == "__main__":
    import sys
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        text = f.read()

    print("=== Education ===")
    for e in parse_education(text):
        print(f"{e.degree} ({e.level}) in {e.field_of_study} @ {e.institution}, {e.year}  [raw: '{e.raw_degree}']")

    print("\n=== Certifications ===")
    for c in parse_certifications(text):
        print(f"{c.name}  issuer={c.issuer}  year={c.year}  category={c.category}")
