"""
Skill Extraction Engine (originally Day 9)

Extracts technical, business, and creative skills from raw resume/JD text
via dictionary-based entity recognition (exact/synonym match, skill stack
expansion, fuzzy spelling match), with per-skill confidence scoring.
"""

from __future__ import annotations

import re
import difflib
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from parsers.skill_dictionary import SKILL_DICTIONARY, SKILL_STACKS

_SYNONYM_LOOKUP: Dict[str, str] = {}


def _normalize_key(text: str) -> str:
    return text.strip().lower()


for canonical, info in SKILL_DICTIONARY.items():
    _SYNONYM_LOOKUP[_normalize_key(canonical)] = canonical
    for synonym in info["synonyms"]:
        _SYNONYM_LOOKUP[_normalize_key(synonym)] = canonical
_SORTED_SYNONYMS = sorted(_SYNONYM_LOOKUP.keys(), key=len, reverse=True)

_STACK_LOOKUP = {name.lower(): skills for name, skills in SKILL_STACKS.items()}

FUZZY_MATCH_THRESHOLD = 0.82


@dataclass
class ExtractedSkill:
    name: str
    group: str
    category: str
    confidence: float
    method: str
    mentions: List[str] = field(default_factory=list)


def _find_exact_matches(text: str) -> Dict[str, List[str]]:
    found: Dict[str, List[str]] = {}
    lowered = text.lower()
    consumed = bytearray(len(lowered))

    for synonym in _SORTED_SYNONYMS:
        pattern = r"(?<!\w)" + re.escape(synonym) + r"(?!\w)"
        for m in re.finditer(pattern, lowered):
            start, end = m.span()
            if any(consumed[start:end]):
                continue
            consumed[start:end] = bytes([1]) * (end - start)
            canonical = _SYNONYM_LOOKUP[synonym]
            found.setdefault(canonical, []).append(m.group())

    return found


def _find_stack_matches(text: str) -> Dict[str, List[str]]:
    found: Dict[str, List[str]] = {}
    lowered = text.lower()

    for stack_name, implied_skills in _STACK_LOOKUP.items():
        pattern = r"(?<!\w)" + re.escape(stack_name) + r"(?!\w)"
        if re.search(pattern, lowered):
            for skill in implied_skills:
                found.setdefault(skill, []).append(f"(via '{stack_name.upper()}' stack)")

    return found


_TOKEN_SPLIT = re.compile(r"[,\n;|]|(?:\s{2,})")


def _candidate_fragments(text: str) -> List[str]:
    fragments = []
    for part in _TOKEN_SPLIT.split(text):
        part = part.strip(" -\u2022\t")
        if 2 <= len(part) <= 30:
            fragments.append(part)
    return fragments


def _find_fuzzy_matches(text: str, already_found: set) -> Dict[str, List[str]]:
    found: Dict[str, List[str]] = {}
    all_known_terms = list(_SYNONYM_LOOKUP.keys())

    for fragment in _candidate_fragments(text):
        frag_lower = fragment.lower()
        if frag_lower in _SYNONYM_LOOKUP:
            continue

        close = difflib.get_close_matches(frag_lower, all_known_terms, n=1, cutoff=FUZZY_MATCH_THRESHOLD)
        if not close:
            continue

        canonical = _SYNONYM_LOOKUP[close[0]]
        if canonical in already_found:
            continue

        ratio = difflib.SequenceMatcher(None, frag_lower, close[0]).ratio()
        found.setdefault(canonical, []).append(f"{fragment} (~{ratio:.2f} match to '{close[0]}')")

    return found


def _score_confidence(method: str, mention_count: int, fuzzy_ratio: Optional[float] = None) -> float:
    if method == "exact":
        base = 1.0
    elif method == "stack_expansion":
        base = 0.90
    elif method == "fuzzy":
        base = 0.55 + (fuzzy_ratio or FUZZY_MATCH_THRESHOLD) * 0.35
    else:
        base = 0.5

    boost = min(0.02 * (mention_count - 1), 0.05)
    return round(min(base + boost, 1.0), 2)


def extract_skills(text: str) -> List[ExtractedSkill]:
    exact = _find_exact_matches(text)
    stacks = _find_stack_matches(text)
    exact_and_stack_names = set(exact) | set(stacks)
    fuzzy = _find_fuzzy_matches(text, already_found=exact_and_stack_names)

    results: List[ExtractedSkill] = []
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
            name=canonical, group=info["group"], category=info["category"],
            confidence=confidence, method=method, mentions=mentions,
        ))

    results.sort(key=lambda s: (-s.confidence, s.name))
    return results
