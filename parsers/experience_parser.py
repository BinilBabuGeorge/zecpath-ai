"""
Experience Parser (originally Day 10)

Parses the Experience section of a resume into structured entries
(company, title, dates), and computes total experience correctly,
handling overlapping roles and detecting gaps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Tuple

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

ENTRY_PATTERN = re.compile(
    r"^-?\s*(?P<title>[^,]+),\s*(?P<company>[^(]+?)\s*"
    r"\((?P<start>[A-Za-z]{3,9}\.?\s*\d{4})\s*[-\u2013]\s*(?P<end>Present|[A-Za-z]{3,9}\.?\s*\d{4})\)\s*$",
    re.IGNORECASE,
)

OTHER_SECTION_HEADINGS = {"skills", "education", "certifications", "projects"}
EXPERIENCE_HEADINGS = {"experience", "work experience", "professional experience"}


@dataclass
class ExperienceEntry:
    title: str
    company: str
    start_year: int
    start_month: int
    end_year: Optional[int]
    end_month: Optional[int]
    is_current: bool
    description: str = ""

    @property
    def start_date(self) -> date:
        return date(self.start_year, self.start_month, 1)

    @property
    def end_date(self) -> date:
        if self.is_current:
            return date.today().replace(day=1)
        return date(self.end_year, self.end_month, 1)

    @property
    def duration_months(self) -> int:
        return _month_diff(self.start_date, self.end_date) + 1


@dataclass
class ExperienceSummary:
    entries: List[ExperienceEntry]
    total_months: int
    total_years: float
    gaps: List[Tuple[date, date]] = field(default_factory=list)
    overlaps: List[Tuple[ExperienceEntry, ExperienceEntry]] = field(default_factory=list)


def _month_diff(d1: date, d2: date) -> int:
    return (d2.year - d1.year) * 12 + (d2.month - d1.month)


def _parse_month_year(text: str) -> Tuple[int, int]:
    text = text.strip().rstrip(".")
    parts = text.split()
    if len(parts) == 2:
        month_str, year_str = parts
        month = MONTHS.get(month_str[:3].lower())
        if month is None:
            raise ValueError(f"Unrecognized month: {month_str}")
        return int(year_str), month
    raise ValueError(f"Cannot parse date: {text}")


def parse_experience(text: str) -> List[ExperienceEntry]:
    lines = [ln.rstrip() for ln in text.split("\n")]
    entries: List[ExperienceEntry] = []
    current_entry: Optional[ExperienceEntry] = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        heading_key = line.rstrip(":").lower()

        if heading_key in OTHER_SECTION_HEADINGS:
            current_entry = None
            continue

        if heading_key in EXPERIENCE_HEADINGS:
            continue

        match = ENTRY_PATTERN.match(line)
        if match:
            start_year, start_month = _parse_month_year(match.group("start"))
            end_raw = match.group("end")
            is_current = end_raw.strip().lower() == "present"
            end_year, end_month = (None, None) if is_current else _parse_month_year(end_raw)

            current_entry = ExperienceEntry(
                title=match.group("title").strip(), company=match.group("company").strip(),
                start_year=start_year, start_month=start_month,
                end_year=end_year, end_month=end_month, is_current=is_current,
            )
            entries.append(current_entry)
            continue

        if current_entry is not None:
            current_entry.description = (current_entry.description + " " + line).strip()

    return entries


def compute_total_experience(entries: List[ExperienceEntry]) -> ExperienceSummary:
    if not entries:
        return ExperienceSummary(entries=[], total_months=0, total_years=0.0)

    sorted_entries = sorted(entries, key=lambda e: e.start_date)

    overlaps: List[Tuple[ExperienceEntry, ExperienceEntry]] = []
    for i in range(len(sorted_entries) - 1):
        a, b = sorted_entries[i], sorted_entries[i + 1]
        if b.start_date <= a.end_date:
            overlaps.append((a, b))

    merged: List[List[date]] = []
    for entry in sorted_entries:
        start, end = entry.start_date, entry.end_date
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    total_months = sum(_month_diff(s, e) + 1 for s, e in merged)

    gaps: List[Tuple[date, date]] = []
    for i in range(len(merged) - 1):
        gap_start = merged[i][1]
        gap_end = merged[i + 1][0]
        if _month_diff(gap_start, gap_end) > 1:
            gaps.append((gap_start, gap_end))

    return ExperienceSummary(
        entries=sorted_entries, total_months=total_months,
        total_years=round(total_months / 12, 1), gaps=gaps, overlaps=overlaps,
    )
