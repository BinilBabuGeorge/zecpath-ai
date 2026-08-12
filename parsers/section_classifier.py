"""
Resume Section Classifier (Day 8)

Tags every non-empty line of a resume with the section it belongs to:
Skills, Work Experience, Education, Certifications, Projects, or Other
(identity block / summary / anything that isn't one of the five target
sections).

Two detection strategies are combined:
1. Rule-based heading detection: recognizes known section headings and
   their common synonyms (e.g. "What I Know" -> Skills), and assigns
   every line under a heading to that section until the next heading.
2. Content-based fallback (a small state machine, not a full NLP model,
   hence "NLP-lite"): used only for lines that aren't under any
   recognized heading -- e.g. a resume with no headings at all, or
   content before the first heading. It looks at line *shape* (date
   ranges, comma-separated lists, degree keywords, certificate keywords)
   to infer which section a line most likely belongs to.

Public API:
    classify_resume(text: str) -> List[LabeledLine]
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

# ---------------------------------------------------------------------------
# Rule-based heading synonyms
# ---------------------------------------------------------------------------

HEADING_SYNONYMS = {
    "Skills": ["skills", "what i know", "technical skills", "key skills", "core skills"],
    "Work Experience": ["experience", "work experience", "my journey", "employment history",
                          "professional experience", "career history"],
    "Education": ["education", "academic background", "academics"],
    "Certifications": ["certifications", "licenses & badges", "licenses", "certificates",
                         "certification"],
    "Projects": ["projects", "key projects", "personal projects"],
}

# Flatten to a single lookup: normalized heading text -> canonical section
_HEADING_LOOKUP = {
    syn: section for section, syns in HEADING_SYNONYMS.items() for syn in syns
}

TARGET_SECTIONS = ["Skills", "Work Experience", "Education", "Certifications", "Projects"]

# ---------------------------------------------------------------------------
# Content-shape patterns used by the fallback classifier
# ---------------------------------------------------------------------------

IDENTITY_FIELD_RE = re.compile(r"^(Name|Designation|Location|Email|Phone)\s*:", re.I)

DATE_RANGE_RE = re.compile(
    r"\((?:[A-Z][a-z]{2}\s+\d{4}|\d{4})\s*[-\u2013]\s*(?:[A-Z][a-z]{2}\s+\d{4}|Present|\d{4})\)",
)

DEGREE_KEYWORDS_RE = re.compile(
    r"\b(B\.?Tech|M\.?Tech|B\.?Sc|M\.?Sc|B\.?A\.?|M\.?A\.?|B\.?Com|B\.?E\.?|M\.?B\.?A|"
    r"B\.?Des|Bachelor|Master|University|College|Institute)\b", re.I
)

CERT_KEYWORDS_RE = re.compile(r"\b(Certified|Certificate|Certification|License)\b", re.I)

PROJECT_TITLE_RE = re.compile(r"^-?\s*[A-Z][\w\s]{2,40}:\s+\S")  # "Project Name: description"


def _looks_like_skills_line(line: str) -> bool:
    """Heuristic: a flat comma-separated list of short items, no sentence punctuation."""
    if line.count(",") < 2:
        return False
    if re.search(r"[.!?]$", line.strip()):
        return False
    tokens = [t.strip() for t in line.split(",")]
    avg_len = sum(len(t) for t in tokens) / len(tokens)
    return avg_len <= 20


@dataclass
class LabeledLine:
    line: str
    section: str
    method: str  # "heading" | "fallback"


# ---------------------------------------------------------------------------
# Pass 1: heading detection
# ---------------------------------------------------------------------------

def _match_heading(line: str) -> Optional[str]:
    normalized = line.strip().rstrip(":").strip().lower()
    return _HEADING_LOOKUP.get(normalized)


def _segment_by_headings(lines: List[str]) -> List[Optional[str]]:
    """Return a section label (or None) for each line, based purely on
    which heading block it falls under. Heading lines themselves are
    labeled None (they aren't content, just markers)."""
    labels: List[Optional[str]] = [None] * len(lines)
    current_section: Optional[str] = None

    for i, line in enumerate(lines):
        heading = _match_heading(line)
        if heading:
            current_section = heading
            continue  # the heading line itself carries no content label
        labels[i] = current_section

    return labels


# ---------------------------------------------------------------------------
# Pass 2: content-based fallback (state machine)
# ---------------------------------------------------------------------------

def _fallback_classify(lines: List[str]) -> List[str]:
    """Classify lines with no heading coverage using line-shape heuristics.
    Maintains a running 'current section' state so description lines that
    follow a role/company line inherit that role's section."""
    labels: List[str] = []
    state = "Other"

    for line in lines:
        stripped = line.strip()

        if IDENTITY_FIELD_RE.match(stripped):
            labels.append("Other")
            continue

        if DEGREE_KEYWORDS_RE.search(stripped):
            state = "Education"
            labels.append(state)
            continue

        if CERT_KEYWORDS_RE.search(stripped):
            state = "Certifications"
            labels.append(state)
            continue

        if DATE_RANGE_RE.search(stripped):
            state = "Work Experience"
            labels.append(state)
            continue

        if _looks_like_skills_line(stripped):
            labels.append("Skills")
            # skills is usually a single line; don't change ongoing state
            continue

        if PROJECT_TITLE_RE.match(stripped) and state != "Work Experience":
            state = "Projects"
            labels.append(state)
            continue

        # Continuation line (e.g. a bullet description under a role/project)
        if state in {"Work Experience", "Projects"}:
            labels.append(state)
            continue

        labels.append("Other")

    return labels


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def classify_resume(text: str) -> List[LabeledLine]:
    """Classify every non-empty line of a resume into one of the target
    sections (or 'Other'), using heading detection first and falling back
    to content-based classification for anything not under a heading."""
    raw_lines = [ln for ln in text.replace("\r\n", "\n").split("\n") if ln.strip()]

    heading_labels = _segment_by_headings(raw_lines)

    # Lines not covered by any heading go through the fallback classifier,
    # processed in original order so state (current role/project) carries over.
    fallback_indices = [i for i, lbl in enumerate(heading_labels) if lbl is None]
    fallback_lines = [raw_lines[i] for i in fallback_indices]
    fallback_labels = _fallback_classify(fallback_lines)

    results: List[LabeledLine] = []
    fallback_ptr = 0
    for i, line in enumerate(raw_lines):
        if _match_heading(line):
            continue  # skip heading marker lines in the output
        if heading_labels[i] is not None:
            results.append(LabeledLine(line=line.strip(), section=heading_labels[i], method="heading"))
        else:
            results.append(LabeledLine(line=line.strip(), section=fallback_labels[fallback_ptr], method="fallback"))
            fallback_ptr += 1

    return results


if __name__ == "__main__":
    import sys
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        text = f.read()
    for labeled in classify_resume(text):
        print(f"[{labeled.section:15s}] ({labeled.method:8s}) {labeled.line}")
