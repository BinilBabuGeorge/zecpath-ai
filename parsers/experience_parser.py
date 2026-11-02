"""
Experience Parser (originally Day 10)

Parses the Experience section of a resume into structured entries
(company, title, dates), and computes total experience correctly,
handling overlapping roles and detecting gaps.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from typing import Iterator, List, Optional, Tuple

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Day 57: a date may be "Mon YYYY" OR a bare "YYYY" (the old pattern silently dropped "2019 - 2022", so such a job
# counted as 0 years); the separator may be a hyphen, en dash, em dash or "to"; "Present" has common synonyms.
_DATE = r"(?:[A-Za-z]{3,9}\.?\s*)?\d{4}"
_PRESENT = r"Present|Current|Ongoing|Now|Till\s*date|Till\s*now"
ENTRY_PATTERN = re.compile(
    r"^-?\s*(?P<title>[^,]+),\s*(?P<company>[^(]+?)\s*"
    rf"\((?P<start>{_DATE})\s*(?:[-\u2013\u2014]|\bto\b)\s*(?P<end>{_PRESENT}|{_DATE})\)\s*$",
    re.IGNORECASE,
)
_PRESENT_RE = re.compile(rf"^(?:{_PRESENT})$", re.IGNORECASE)

# Day 57: a person is not credited with a career longer than this (a typo like "1900" must not become 126 years).
MAX_PLAUSIBLE_CAREER_YEARS = 60

# Day 57: the reference date for "Present". Defaults to the real today; set it to make results reproducible
# (the experience result for a resume that says "Present" otherwise changes with the calendar -- Day 56 finding F4).
_REFERENCE_DATE: Optional[date] = None


def today() -> date:
    """The date that "Present" means. The real today unless `reference_date()` is in force."""
    return _REFERENCE_DATE or date.today()


@contextmanager
def reference_date(as_of: Optional[date]) -> Iterator[None]:
    """Pin what "Present" means, for the duration of the block. Not thread-safe by design (a module-level setting)."""
    global _REFERENCE_DATE
    previous, _REFERENCE_DATE = _REFERENCE_DATE, as_of
    try:
        yield
    finally:
        _REFERENCE_DATE = previous

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
            return today().replace(day=1)
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
    warnings: List[str] = field(default_factory=list)       # Day 57: entries that were left out, and why


def _month_diff(d1: date, d2: date) -> int:
    return (d2.year - d1.year) * 12 + (d2.month - d1.month)


def _parse_month_year(text: str) -> Tuple[int, int]:
    text = text.strip().rstrip(".")
    parts = text.split()
    if len(parts) == 1 and parts[0].isdigit() and len(parts[0]) == 4:
        return int(parts[0]), 0                    # bare year: month 0 = "unknown", resolved by the caller
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
            end_raw = match.group("end")
            is_current = bool(_PRESENT_RE.match(end_raw.strip()))
            try:
                start_year, start_month = _parse_month_year(match.group("start"))
                end_year, end_month = (None, None) if is_current else _parse_month_year(end_raw)
            except ValueError:
                # Day 57: a date slot that looks like a date but is not one ("Foo 2020") must not abort the whole
                # resume; the line is simply not treated as a job entry.
                if current_entry is not None:
                    current_entry.description = (current_entry.description + " " + line).strip()
                continue
            # Day 57: bare years. Convention: a start year means mid-year (July) and an end year means mid-year
            # (June), so "2019 - 2022" is 3.0 years; a job inside ONE bare year is credited 6 months (Jul-Dec).
            if start_month == 0 or end_month == 0:
                if start_month == 0 and end_month == 0 and start_year == end_year:
                    start_month, end_month = 7, 12
                else:
                    start_month = 7 if start_month == 0 else start_month
                    end_month = 6 if end_month == 0 else end_month

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

    # Day 57: leave out entries that cannot be trusted, and SAY so, instead of producing negative or absurd totals.
    now = today().replace(day=1)
    horizon = date(max(now.year - MAX_PLAUSIBLE_CAREER_YEARS, 1), 1, 1)
    usable: List[ExperienceEntry] = []
    warnings: List[str] = []
    for e in entries:
        label = f"{e.title} at {e.company}"
        if e.start_date > now:
            warnings.append(f"left out '{label}': it starts in the future ({e.start_date:%b %Y})")
        elif not e.is_current and e.end_date < e.start_date:
            warnings.append(f"left out '{label}': the end date is before the start date")
        elif e.start_date < horizon:
            warnings.append(f"left out '{label}': started {e.start_date.year}, more than {MAX_PLAUSIBLE_CAREER_YEARS} years ago")
        else:
            usable.append(e)
    if not usable:
        return ExperienceSummary(entries=[], total_months=0, total_years=0.0, warnings=warnings)
    entries = usable

    sorted_entries = sorted(entries, key=lambda e: e.start_date)

    overlaps: List[Tuple[ExperienceEntry, ExperienceEntry]] = []
    for i in range(len(sorted_entries) - 1):
        a, b = sorted_entries[i], sorted_entries[i + 1]
        if b.start_date <= a.end_date:
            overlaps.append((a, b))

    merged: List[List[date]] = []
    for entry in sorted_entries:
        start, end = entry.start_date, min(entry.end_date, now)       # a job cannot run past today
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
        total_years=round(total_months / 12, 1), gaps=gaps, overlaps=overlaps, warnings=warnings,
    )
