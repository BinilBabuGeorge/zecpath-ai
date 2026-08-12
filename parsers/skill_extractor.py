"""
Skill Extraction Engine (Day 9)

Extracts technical, business, and creative skills from raw resume text --
not just from clean comma-separated skill lists, but from anywhere in the
text (Experience bullets, Project descriptions, prose sentences).

This is dictionary-based entity recognition ("gazetteer" style NLP): every
match is against the master skill dictionary (skill_dictionary.py), not a
trained ML/NER model. That distinction is documented honestly in the
accuracy discussion, same as Day 8's classifier.

Three extraction strategies, each with a different confidence level:
  1. Exact / synonym match  -- word-boundary match against dictionary   (high confidence)
  2. Skill stack expansion  -- "MERN" implies 4 underlying skills       (medium-high confidence)
  3. Fuzzy spelling match   -- catches variants not in the dictionary   (lower confidence, scaled)

Public API:
    extract_skills(text: str) -> List[ExtractedSkill]
"""

from __future__ import annotations

import re
import difflib
from dataclasses import dataclass, field
from typing import List, Dict, Optional

from parsers.skill_dictionary import SKILL_DICTIONARY, SKILL_STACKS

# ---------------------------------------------------------------------------
# Build lookup tables from the master dictionary
# ---------------------------------------------------------------------------

# normalized synonym text -> canonical skill name
# Every canonical name is automatically included as a synonym of itself
# (lowercased), so e.g. "Python" matches exactly rather than only fuzzy-
# matching against a synonym like "python3".
_SYNONYM_LOOKUP: Dict[str, str] = {}
for canonical, info in SKILL_DICTIONARY.items():
    _SYNONYM_LOOKUP[canonical.lower()] = canonical
    for synonym in info["synonyms"]:
        _SYNONYM_LOOKUP[synonym.lower()] = canonical

# Sort synonyms longest-first so multi-word synonyms (e.g. "power bi") match
# before shorter overlapping ones would.
_SORTED_SYNONYMS = sorted(_SYNONYM_LOOKUP.keys(), key=len, reverse=True)

_STACK_LOOKUP = {name.lower(): skills for name, skills in SKILL_STACKS.items()}

FUZZY_MATCH_THRESHOLD = 0.82  # minimum similarity ratio to accept a fuzzy match


@dataclass
class ExtractedSkill:
    name: str
    group: str
    category: str
    confidence: float
    method: str  # "exact" | "stack_expansion" | "fuzzy"
    mentions: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Stage 1: exact / synonym matching (word-boundary, case-insensitive)
# ---------------------------------------------------------------------------

def _find_exact_matches(text: str) -> Dict[str, List[str]]:
    """Return {canonical_name: [matched substrings]} for every dictionary
    synonym found in text via word-boundary regex matching.

    Matches longest synonyms first and marks their character spans as
    consumed, so a shorter synonym that happens to be a substring of an
    already-matched longer one (e.g. 'SQL' inside 'Postgre SQL') is not
    also counted as a separate, incorrect match.
    """
    found: Dict[str, List[str]] = {}
    lowered = text.lower()
    consumed = bytearray(len(lowered))  # 0 = free, 1 = already matched

    for synonym in _SORTED_SYNONYMS:
        # Word-boundary on both sides. Using plain \w (not the wider
        # [\w.+#/-] class) so a trailing sentence period/comma after a
        # skill (e.g. "...deployed on AWS.") doesn't block the match --
        # only an adjacent *word* character (as in "reactive" containing
        # "react") should block it. Compound synonyms like "node.js" or
        # "c++" still match correctly since the whole escaped synonym is
        # matched as one contiguous literal; only the outer edges are
        # boundary-checked.
        pattern = r"(?<!\w)" + re.escape(synonym) + r"(?!\w)"
        for m in re.finditer(pattern, lowered):
            start, end = m.span()
            if any(consumed[start:end]):
                continue  # overlaps a longer synonym already matched here
            consumed[start:end] = bytes([1]) * (end - start)
            canonical = _SYNONYM_LOOKUP[synonym]
            found.setdefault(canonical, []).append(m.group())

    return found


# ---------------------------------------------------------------------------
# Stage 2: skill stack expansion
# ---------------------------------------------------------------------------

def _find_stack_matches(text: str) -> Dict[str, List[str]]:
    """Return {canonical_name: [stack mention]} for skills implied by a
    named stack (e.g. 'MERN' -> MongoDB, Express.js, React.js, Node.js)."""
    found: Dict[str, List[str]] = {}
    lowered = text.lower()

    for stack_name, implied_skills in _STACK_LOOKUP.items():
        pattern = r"(?<!\w)" + re.escape(stack_name) + r"(?!\w)"
        if re.search(pattern, lowered):
            for skill in implied_skills:
                found.setdefault(skill, []).append(f"(via '{stack_name.upper()}' stack)")

    return found


# ---------------------------------------------------------------------------
# Stage 3: fuzzy matching for spelling variants not in the dictionary
# ---------------------------------------------------------------------------

_TOKEN_SPLIT = re.compile(r"[,\n;|]|(?:\s{2,})")


def _candidate_fragments(text: str) -> List[str]:
    """Break text into short candidate fragments (comma/line separated)
    worth fuzzy-matching -- avoids fuzzy-matching entire sentences."""
    fragments = []
    for part in _TOKEN_SPLIT.split(text):
        part = part.strip(" -\u2022\t")
        if 2 <= len(part) <= 30:
            fragments.append(part)
    return fragments


def _find_fuzzy_matches(text: str, already_found: set) -> Dict[str, List[str]]:
    """Catch spelling variants of dictionary skills that exact matching
    missed, using string similarity. Only considers short fragments to
    avoid false positives on long sentences."""
    found: Dict[str, List[str]] = {}
    all_known_terms = list(_SYNONYM_LOOKUP.keys())

    for fragment in _candidate_fragments(text):
        frag_lower = fragment.lower()
        if frag_lower in _SYNONYM_LOOKUP:
            continue  # already an exact match, skip

        close = difflib.get_close_matches(frag_lower, all_known_terms, n=1, cutoff=FUZZY_MATCH_THRESHOLD)
        if not close:
            continue

        canonical = _SYNONYM_LOOKUP[close[0]]
        if canonical in already_found:
            continue

        ratio = difflib.SequenceMatcher(None, frag_lower, close[0]).ratio()
        found.setdefault(canonical, []).append(f"{fragment} (~{ratio:.2f} match to '{close[0]}')")

    return found


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------

def _score_confidence(method: str, mention_count: int, fuzzy_ratio: Optional[float] = None) -> float:
    if method == "exact":
        base = 1.0
    elif method == "stack_expansion":
        base = 0.90
    elif method == "fuzzy":
        base = 0.55 + (fuzzy_ratio or FUZZY_MATCH_THRESHOLD) * 0.35  # scales ~0.75-0.90
    else:
        base = 0.5

    # Multiple independent mentions of the same skill slightly increase confidence
    boost = min(0.02 * (mention_count - 1), 0.05)
    return round(min(base + boost, 1.0), 2)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def extract_skills(text: str) -> List[ExtractedSkill]:
    """Extract, deduplicate, and confidence-score every skill mentioned
    anywhere in the given text."""
    exact = _find_exact_matches(text)
    stacks = _find_stack_matches(text)
    exact_and_stack_names = set(exact) | set(stacks)
    fuzzy = _find_fuzzy_matches(text, already_found=exact_and_stack_names)

    results: List[ExtractedSkill] = []

    # Exact matches take priority; if a skill was also stack-implied, merge mentions.
    all_canonical_names = set(exact) | set(stacks) | set(fuzzy)
    for canonical in all_canonical_names:
        info = SKILL_DICTIONARY[canonical]
        mentions = exact.get(canonical, []) + stacks.get(canonical, []) + fuzzy.get(canonical, [])

        if canonical in exact:
            method = "exact"
        elif canonical in stacks:
            method = "stack_expansion"
        else:
            method = "fuzzy"

        fuzzy_ratio = None
        if method == "fuzzy" and mentions:
            ratio_match = re.search(r"~([\d.]+) match", mentions[0])
            if ratio_match:
                fuzzy_ratio = float(ratio_match.group(1))

        confidence = _score_confidence(method, len(mentions), fuzzy_ratio)

        results.append(ExtractedSkill(
            name=canonical,
            group=info["group"],
            category=info["category"],
            confidence=confidence,
            method=method,
            mentions=mentions,
        ))

    results.sort(key=lambda s: (-s.confidence, s.name))
    return results


if __name__ == "__main__":
    import sys
    import json
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        text = f.read()
    skills = extract_skills(text)
    for s in skills:
        print(f"{s.confidence:.2f}  [{s.method:<15}] {s.name:<20} ({s.group}/{s.category})  <- {s.mentions[0] if s.mentions else ''}")
