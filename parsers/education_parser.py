"""
Education & Certification Parser (originally Day 11)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from parsers.education_dictionary import DEGREE_DICTIONARY, DEGREE_LEVEL_RANK, CERT_CATEGORY_KEYWORDS


def _normalize_key(text: str) -> str:
    return text.strip().replace(".", "").lower()


_DEGREE_LOOKUP = {}
for canonical, info in DEGREE_DICTIONARY.items():
    _DEGREE_LOOKUP[_normalize_key(canonical)] = canonical
    for syn in info["synonyms"]:
        _DEGREE_LOOKUP[_normalize_key(syn)] = canonical

EDUCATION_PATTERN_WITH_FIELD = re.compile(
    r"^-?\s*(?P<degree>[^,]+?)\s+in\s+(?P<field>[^,]+),\s*(?P<institution>[^,]+),\s*(?P<year>\d{4})\s*$",
    re.IGNORECASE,
)
EDUCATION_PATTERN_NO_FIELD = re.compile(
    r"^-?\s*(?P<degree>[^,]+),\s*(?P<institution>[^,]+),\s*(?P<year>\d{4})\s*$",
    re.IGNORECASE,
)
CERTIFICATION_PATTERN = re.compile(
    r"^-?\s*(?P<name>[^(]+?)(?:,\s*(?P<issuer>[^(]+?))?\s*\((?P<year>\d{4})\)\s*$",
)


@dataclass
class EducationEntry:
    raw_degree: str
    degree: str
    level: Optional[str]
    field_of_study: Optional[str]
    institution: str
    year: int


@dataclass
class CertificationEntry:
    name: str
    issuer: Optional[str]
    year: Optional[int]
    category: str


def normalize_degree(raw_degree: str) -> tuple:
    key = _normalize_key(raw_degree)
    canonical = _DEGREE_LOOKUP.get(key)
    if canonical:
        return canonical, DEGREE_DICTIONARY[canonical]["level"]
    return raw_degree.strip(), None


def categorize_certification(name: str) -> str:
    lowered = name.lower()
    for category, keywords in CERT_CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in lowered:
                return category
    return "Other"


def parse_education(text: str) -> List[EducationEntry]:
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
            raw_degree=raw_degree, degree=canonical, level=level,
            field_of_study=field, institution=match.group("institution").strip(),
            year=int(match.group("year")),
        ))

    return entries


def parse_certifications(text: str) -> List[CertificationEntry]:
    entries = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        # STABILITY (Day 18): CERTIFICATION_PATTERN requires a literal "("
        # (the year parenthesis) to match at all -- so a line with none can
        # never match. Before this check, a long line with many commas and
        # no "(" (e.g. malformed/noisy resume text with no certifications
        # section) hit catastrophic backtracking in the regex engine, since
        # the pattern has two adjacent lazy groups searching for a required
        # "(" that doesn't exist. Measured directly: one such line took
        # 3.17 SECONDS in a single re.match() call (see
        # docs/day18_performance_report.md). This pre-check is a pure
        # early-exit -- it changes zero matching behavior (verified against
        # a 64-pair golden-master regression) since CERTIFICATION_PATTERN
        # could never have matched these lines anyway.
        if "(" not in line:
            continue

        match = CERTIFICATION_PATTERN.match(line)
        if not match:
            continue

        name = match.group("name").strip()
        issuer = match.group("issuer").strip() if match.group("issuer") else None
        year = int(match.group("year")) if match.group("year") else None

        entries.append(CertificationEntry(
            name=name, issuer=issuer, year=year, category=categorize_certification(name),
        ))

    return entries
