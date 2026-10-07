"""
Transcript Demographic Disclosure Scrubber (Day 43)

WHAT THIS DAY ADDS: Day 15 already masks demographic/PII fields on
resumes -- but only LABELED fields ("Gender:", "Religion:", "Age:"),
which matches how Indian resumes in this project's sample set present
that data. Screening-call and HR-interview answers have no such
structure -- they're free-form speech, and a candidate can volunteer
a protected attribute unprompted ("I'm a single mother returning to
work", "as a 45-year-old switching careers", "being Muslim, I'd need
Friday prayer time") while answering an ordinary question. Nothing in
this project currently scrubs that before it's stored or scored. This
closes that gap for the two rounds Day 15 doesn't reach.

SCOPE, STATED HONESTLY: this is keyword/phrase pattern matching, the
same approach every classifier in this project uses -- NOT natural-
language understanding. It will miss indirect disclosures (an
employment-gap story that implies a reason without naming it) and can
over-match in ambiguous cases (a candidate discussing a PAST PROJECT
"for a Catholic charity" isn't disclosing their own religion). Each
match is reported with category and matched phrase so a human
reviewer can check it, not auto-trusted. This is a defensible
reduction in exposure, not a guarantee of zero demographic signal.

REUSE: mirrors Day 15's mask_pii() SHAPE exactly (return masked text +
list of detected categories, never the actual value) for a consistent
interface, but the matching itself can't reuse Day 15's label-anchored
regexes (`^Field:\\s*(.+)$`) since there are no field labels in a
transcript -- free text needs first-person self-disclosure phrasing
instead. The category set itself (gender, age, religion, marital
status, nationality, disability) is the same list Day 15 already
established as the project's protected-attribute vocabulary, reused
directly rather than re-derived.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

REDACTED = "[REDACTED]"

# Each category: a list of regex patterns matching FIRST-PERSON
# self-disclosure phrasing specifically -- deliberately narrow rather
# than matching any mention of the topic, so a candidate describing
# someone else, a past employer's policy, or a project domain isn't
# false-flagged as disclosing their own attribute.
_DEMOGRAPHIC_DISCLOSURE_PATTERNS: Dict[str, List[str]] = {
    "Age": [
        r"\bi('m| am)\s+(a\s+)?\d{1,2}[\s-]?(years?[\s-]?old|yo)\b",
        r"\bat\s+(my\s+)?age\s+of\s+\d{1,2}\b",
        r"\bas\s+a\s+\d{1,2}[\s-]year[\s-]old\b",
    ],
    "Gender identity": [
        r"\bi('m| am)\s+(a\s+)?(transgender|trans|non-binary|nonbinary)\b",
        r"\bi\s+identify\s+as\s+(a\s+|an\s+)?\w+",
    ],
    "Religion": [
        r"\bi('m| am)\s+(a\s+)?(muslim|hindu|christian|sikh|buddhist|jain|jewish|catholic)\b",
        r"\bbeing\s+(a\s+)?(muslim|hindu|christian|sikh|buddhist|jain|jewish|catholic)\b",
        r"\bmy\s+religion\s+is\b",
    ],
    "Marital/family status": [
        r"\bi('m| am)\s+a\s+(single\s+)?(mother|father|parent|mom|dad)\b",
        r"\bi('m| am)\s+(married|divorced|widowed|a\s+widow|a\s+widower)\b",
        r"\bmy\s+(husband|wife|spouse)\b",
        r"\bi\s+have\s+(a\s+|two\s+|three\s+|\d\s+)?(kids|children|a\s+child)\b",
    ],
    "Nationality/origin": [
        r"\bi('m| am)\s+(a\s+|an\s+)?(indian|pakistani|bangladeshi|american|british|nepali|sri\s*lankan)\s+(national|citizen|origin)\b",
        r"\bmy\s+nationality\s+is\b",
    ],
    "Disability": [
        r"\bi\s+have\s+a\s+disability\b",
        r"\bi('m| am)\s+(visually|hearing)\s+impaired\b",
        r"\bi\s+use\s+a\s+wheelchair\b",
    ],
}

_COMPILED_PATTERNS: Dict[str, List[re.Pattern]] = {
    category: [re.compile(p, re.IGNORECASE) for p in patterns]
    for category, patterns in _DEMOGRAPHIC_DISCLOSURE_PATTERNS.items()
}


@dataclass
class DemographicDisclosureReport:
    categories_detected: List[str] = field(default_factory=list)
    matched_phrases: List[Tuple[str, str]] = field(default_factory=list)  # (category, matched text)


def detect_demographic_disclosures(text: str) -> DemographicDisclosureReport:
    """Reports what was found WITHOUT altering the text -- use this
    when you need to flag an answer for human review without
    necessarily rewriting the stored transcript."""
    categories: List[str] = []
    matches: List[Tuple[str, str]] = []

    for category, patterns in _COMPILED_PATTERNS.items():
        for pattern in patterns:
            m = pattern.search(text)
            if m:
                categories.append(category)
                matches.append((category, m.group(0)))
                break  # one hit per category is enough to flag it

    return DemographicDisclosureReport(categories_detected=categories, matched_phrases=matches)


def mask_demographic_disclosures(text: str) -> Tuple[str, List[str]]:
    """Same shape as Day 15's mask_pii(): returns (masked_text,
    categories_detected), never the actual disclosed value, so a
    report built from this is safe to log or store."""
    masked_text = text
    detected: List[str] = []

    for category, patterns in _COMPILED_PATTERNS.items():
        for pattern in patterns:
            if pattern.search(masked_text):
                detected.append(category)
                masked_text = pattern.sub(REDACTED, masked_text)
                break

    return masked_text, detected
