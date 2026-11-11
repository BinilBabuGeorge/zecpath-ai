"""
Skill Extraction Engine (originally Day 9)

Extracts technical, business, and creative skills from raw resume/JD text
via dictionary-based entity recognition (exact/synonym match, skill stack
expansion, fuzzy spelling match), with per-skill confidence scoring.
"""

from __future__ import annotations

import re
import difflib
import hashlib
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional

from parsers.skill_dictionary import SKILL_DICTIONARY, SKILL_STACKS
from utils.perf import BoundedLRU

_SYNONYM_LOOKUP: Dict[str, str] = {}


def _normalize_key(text: str) -> str:
    return text.strip().lower()


for canonical, info in SKILL_DICTIONARY.items():
    _SYNONYM_LOOKUP[_normalize_key(canonical)] = canonical
    for synonym in info["synonyms"]:
        _SYNONYM_LOOKUP[_normalize_key(synonym)] = canonical
_SORTED_SYNONYMS = sorted(_SYNONYM_LOOKUP.keys(), key=len, reverse=True)
# PERFORMANCE (Day 18): _find_exact_matches used to run one re.finditer()
# pass PER SYNONYM (one full-text scan per entry in _SORTED_SYNONYMS, using
# a `consumed` bytearray to hand-roll overlap prevention). Profiling showed
# this was the top hotspot after the Day 18 semantic_matcher fix -- 0.9s
# cumulative across a 940-call batch. A single precompiled alternation
# pattern gets the same longest-match-wins, non-overlapping behavior for
# free from finditer() (a single pattern's matches never overlap by
# construction), in one O(len(text)) pass instead of N. Alternatives stay
# ordered longest-first so multi-word/longer synonyms are still preferred
# over short substrings. See docs/day18_performance_report.md.
_COMBINED_EXACT_PATTERN = re.compile(
    r"(?<!\w)(" + "|".join(re.escape(s) for s in _SORTED_SYNONYMS) + r")(?!\w)"
)

_STACK_LOOKUP = {name.lower(): skills for name, skills in SKILL_STACKS.items()}
# PERFORMANCE (Day 60): the stack pattern was rebuilt (re.escape + string join + re cache lookup) for every stack on every call.
# Compiling each once gives the identical match (same pattern text) without the repeated work.
_STACK_PATTERNS = {name: re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)") for name in _STACK_LOOKUP}

FUZZY_MATCH_THRESHOLD = 0.82

# PERFORMANCE (Day 18, verified in this session): _find_fuzzy_matches used to
# rebuild list(_SYNONYM_LOOKUP.keys()) -- ~150+ entries -- on every single
# call, just to hand it to difflib.get_close_matches(). _SYNONYM_LOOKUP is a
# module-level constant that never changes after import, so the list only
# needs to be built once. Profiling showed _find_fuzzy_matches as the
# second-largest hotspot after the redundant-extract_skills fix (see
# docs/day18_performance_report.md); this alone doesn't reduce the O(n*m)
# difflib comparison cost per fragment, but removes a real per-call
# list-construction cost sitting in front of it.
_ALL_KNOWN_TERMS = list(_SYNONYM_LOOKUP.keys())

# PERFORMANCE (Day 60), two changes to the fuzzy fallback, which Day 60 profiling found was 15% of ATS scoring, 42% of DOCX parsing
# and 37% of screening scoring (difflib.get_close_matches, once per unfamiliar fragment):
#   1. LENGTH WINDOW. difflib only keeps a term if real_quick_ratio() >= cutoff, and real_quick_ratio is 2*min(la,lb)/(la+lb), which
#      depends only on the two LENGTHS. A term whose length makes that ratio fall below the cutoff can never be returned, so it is
#      never offered to difflib. The test uses the same expression difflib does, so the result is identical by construction
#      (checked on 20,000 generated fragments in tests/test_day60_performance.py).
#   2. MEMO. The answer for a fragment depends only on the fragment (the dictionary is a constant), and the same fragments recur
#      across resumes ("node js", "reactjs", "communication"). Stored in a bounded LRU (see utils/perf.py).
_MAX_TERM_LEN_INDEXED = 64


def _terms_for_length(length: int) -> List[str]:
    return [t for t in _ALL_KNOWN_TERMS if 2.0 * min(length, len(t)) / (length + len(t)) >= FUZZY_MATCH_THRESHOLD]


_TERMS_BY_FRAGMENT_LENGTH: Dict[int, List[str]] = {n: _terms_for_length(n) for n in range(1, _MAX_TERM_LEN_INDEXED + 1)}
_FUZZY_CACHE = BoundedLRU("skill_fuzzy", max_items=8192, max_bytes=2_000_000, sizeof=lambda v: 120 if v is None else 120 + len(v))
_SKILLS_CACHE = BoundedLRU("skill_extract_text", max_items=1024, max_bytes=8_000_000, sizeof=lambda v: 400 + sum(250 + 60 * len(s.mentions) for s in v))


def _closest_known_term(frag_lower: str) -> Optional[str]:
    """The single dictionary term difflib.get_close_matches(frag, terms, n=1, cutoff=FUZZY_MATCH_THRESHOLD) would return, or None."""
    def compute() -> Optional[str]:
        terms = _TERMS_BY_FRAGMENT_LENGTH.get(len(frag_lower), _ALL_KNOWN_TERMS)
        close = difflib.get_close_matches(frag_lower, terms, n=1, cutoff=FUZZY_MATCH_THRESHOLD)
        return close[0] if close else None
    return _FUZZY_CACHE.get_or_compute(frag_lower, compute)


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

    for m in _COMBINED_EXACT_PATTERN.finditer(lowered):
        matched_text = m.group()
        canonical = _SYNONYM_LOOKUP[matched_text]
        found.setdefault(canonical, []).append(matched_text)

    return found


def _find_stack_matches(text: str) -> Dict[str, List[str]]:
    found: Dict[str, List[str]] = {}
    lowered = text.lower()

    for stack_name, implied_skills in _STACK_LOOKUP.items():
        if _STACK_PATTERNS[stack_name].search(lowered):
            for skill in implied_skills:
                found.setdefault(skill, []).append(f"(via '{stack_name.upper()}' stack)")

    return found


_TOKEN_SPLIT = re.compile(r"[,\n;|]|(?:\s{2,})")

# STABILITY (Day 18): every real resume in this project's sample dataset
# produces 15-31 candidate fragments (checked directly, not guessed). Fuzzy
# matching is O(fragments x dictionary_terms) via difflib -- a resume that
# is mostly noise (garbled PDF extraction, thousands of tiny junk tokens)
# can produce thousands of fragments and turn one score_candidate() call
# into multiple seconds of work. Measured directly: 3000 short garbage
# fragments took 3.2s for a single resume (see docs/day18_performance_report.md).
# Capped well above any legitimate resume's fragment count -- 10x the
# largest real sample -- so this only engages on genuinely pathological input.
_MAX_FUZZY_FRAGMENTS = 300


def _candidate_fragments(text: str) -> List[str]:
    fragments = []
    for part in _TOKEN_SPLIT.split(text):
        part = part.strip(" -\u2022\t")
        if 2 <= len(part) <= 30:
            fragments.append(part)
            if len(fragments) >= _MAX_FUZZY_FRAGMENTS:
                break
    return fragments


def _find_fuzzy_matches(text: str, already_found: set) -> Dict[str, List[str]]:
    found: Dict[str, List[str]] = {}

    for fragment in _candidate_fragments(text):
        frag_lower = fragment.lower()
        if frag_lower in _SYNONYM_LOOKUP:
            continue

        close_term = _closest_known_term(frag_lower)
        if close_term is None:
            continue

        canonical = _SYNONYM_LOOKUP[close_term]
        if canonical in already_found:
            continue

        ratio = difflib.SequenceMatcher(None, frag_lower, close_term).ratio()
        found.setdefault(canonical, []).append(f"{fragment} (~{ratio:.2f} match to '{close_term}')")

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
    """Skills found in `text`. PERFORMANCE (Day 60): the result is a pure function of the text, and the same text is extracted many
    times (a job description's skills section once per candidate; a resume once when parsed and again when scored). Results are
    memoised by a hash of the text (the text itself is not kept alive) in a bounded LRU, and every caller gets its OWN copy, so
    changing a returned skill can never change what the next caller sees."""
    key = hashlib.blake2b(text.encode("utf-8", "surrogatepass"), digest_size=16).digest()
    cached = _SKILLS_CACHE.get_or_compute(key, lambda: _extract_skills_uncached(text))
    return [replace(skill, mentions=list(skill.mentions)) for skill in cached]


def _extract_skills_uncached(text: str) -> List[ExtractedSkill]:
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
