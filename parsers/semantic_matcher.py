"""
Semantic Matching Engine (originally Day 12)

Uses TF-IDF vector embeddings + cosine similarity (not a trained neural
embedding model -- documented honestly in the Day 12 report), with
skill-synonym preprocessing to bridge lexical gaps.
"""

from __future__ import annotations

import re
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List

from parsers.skill_dictionary import SKILL_DICTIONARY

_SYNONYM_LOOKUP: Dict[str, str] = {}
for canonical, info in SKILL_DICTIONARY.items():
    _SYNONYM_LOOKUP[canonical.lower()] = canonical
    for syn in info["synonyms"]:
        _SYNONYM_LOOKUP[syn.lower()] = canonical
_SORTED_SYNONYMS = sorted(_SYNONYM_LOOKUP.keys(), key=len, reverse=True)
_COMBINED_SYNONYM_PATTERN = re.compile(
    r"(?<!\w)(" + "|".join(re.escape(s) for s in _SORTED_SYNONYMS) + r")(?!\w)"
)


def normalize_for_embedding(text: str) -> str:
    # PERFORMANCE (Day 18): this used to run one re.sub() pass PER SYNONYM
    # (143 separate full-text scans, O(N_synonyms * len(text))). Profiling
    # showed this was the single largest hotspot in scoring -- 37% of total
    # wall time across a batch scoring run (1.57s of 4.25s cumulative),
    # almost all inside re.sub/re.escape. Replaced with one precompiled
    # alternation pattern -- a single O(len(text)) pass. Alternatives stay
    # ordered longest-first (_SORTED_SYNONYMS is already sorted that way)
    # so multi-word/longer phrases are still preferred over short
    # substrings, matching the original sequential-replace semantics.
    # See docs/day18_performance_report.md for the before/after benchmark.
    lowered = text.lower()
    return _COMBINED_SYNONYM_PATTERN.sub(_replace_synonym_match, lowered)


def _replace_synonym_match(match: "re.Match") -> str:
    canonical = _SYNONYM_LOOKUP[match.group(0)]
    return canonical.replace(".", "").replace(" ", "_")


# PERFORMANCE (Day 54): scoring one job description against many resumes embedded the SAME job text
# again for every resume, and each comparison paid sklearn's cosine_similarity input validation on
# vectors that are already unit length. Profiling the 64-pair sample batch showed ~75% of ATS scoring
# time in this class. Two changes, both verified to give bit-identical rounded scores on every pair
# (tests/test_day54_semantic_matcher_equivalence.py compares against sklearn's own cosine):
#   1. embed() memoises by text in a bounded LRU cache (the vectorizer is fitted once, so a vector is a
#      pure function of its text);
#   2. similarity() takes the dot product directly. TfidfVectorizer's default norm='l2' makes every
#      vector unit length, so cosine similarity IS the dot product.
EMBED_CACHE_SIZE = 1024


class SemanticMatcher:
    def __init__(self, corpus: List[str], normalize: bool = True, cache_size: int = EMBED_CACHE_SIZE):
        # MEMORY (Day 60): scikit-learn (with NumPy and SciPy) is about 120 MB of resident memory and a second of import time. It used to be
        # imported when this module was, and this module is reached by every service that touches an ATS zone (decision, interview,
        # screening), none of which builds a matcher. Importing it here, on first use, means only workers that really score resumes pay for it.
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.normalize = normalize
        prepared = [normalize_for_embedding(t) if normalize else t for t in corpus]
        self.vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        self.vectorizer.fit(prepared)
        self._cache_size = max(0, int(cache_size))
        self._cache: "OrderedDict[str, object]" = OrderedDict()
        self._lock = threading.Lock()
        self.cache_hits = 0
        self.cache_misses = 0

    def embed(self, text: str):
        if self._cache_size:
            with self._lock:
                cached = self._cache.get(text)
                if cached is not None:
                    self._cache.move_to_end(text)
                    self.cache_hits += 1
                    return cached
        prepared = normalize_for_embedding(text) if self.normalize else text
        vector = self.vectorizer.transform([prepared])
        if self._cache_size:
            with self._lock:
                self.cache_misses += 1
                self._cache[text] = vector
                if len(self._cache) > self._cache_size:
                    self._cache.popitem(last=False)
        return vector

    def embed_many(self, texts: List[str]) -> list:
        """Vectors for several texts, in order, equal to calling embed() on each.

        PERFORMANCE (Day 60): profiling found that most of the time in embed() was not the arithmetic but scikit-learn's fixed
        per-call cost (input validation, sparse-matrix construction): scoring one resume made six separate transform() calls. The
        rows of a TF-IDF transform are independent of one another, so ONE call for every text that is not already cached gives
        each text the same vector it would have got alone (tests/test_day60_performance.py compares them array by array).
        """
        vectors: list = [None] * len(texts)
        missing: Dict[str, List[int]] = {}
        for i, text in enumerate(texts):
            cached = None
            if self._cache_size:
                with self._lock:
                    cached = self._cache.get(text)
                    if cached is not None:
                        self._cache.move_to_end(text)
                        self.cache_hits += 1
            if cached is not None:
                vectors[i] = cached
            else:
                missing.setdefault(text, []).append(i)
        if missing:
            unique = list(missing)
            prepared = [normalize_for_embedding(t) if self.normalize else t for t in unique]
            matrix = self.vectorizer.transform(prepared)
            for row, text in enumerate(unique):
                vector = matrix[row]
                for i in missing[text]:
                    vectors[i] = vector
                if self._cache_size:
                    with self._lock:
                        self.cache_misses += 1
                        self._cache[text] = vector
                        if len(self._cache) > self._cache_size:
                            self._cache.popitem(last=False)
        return vectors

    def similarity(self, text_a: str, text_b: str) -> float:
        vec_a = self.embed(text_a)
        vec_b = self.embed(text_b)
        score = vec_a.multiply(vec_b).sum()      # unit-length vectors: cosine similarity == dot product
        return round(float(score), 4)


COMPONENT_WEIGHTS = {"skills": 0.45, "experience": 0.35, "overall": 0.20}


@dataclass
class MatchResult:
    overall_score: float
    component_scores: Dict[str, float] = field(default_factory=dict)
    classification: str = ""


def classify_score(score: float, thresholds: Dict[str, float]) -> str:
    if score >= thresholds["strong"]:
        return "Strong Match"
    if score >= thresholds["moderate"]:
        return "Moderate Match"
    return "Weak Match"


def compare_resume_to_jd(
    resume_sections: Dict[str, str],
    jd_sections: Dict[str, str],
    matcher: SemanticMatcher,
    thresholds: Dict[str, float],
) -> MatchResult:
    component_scores = {}
    names = list(COMPONENT_WEIGHTS)
    if hasattr(matcher, "embed_many"):
        # PERFORMANCE (Day 60): all six section texts embedded in one call (see SemanticMatcher.embed_many); same arithmetic as similarity().
        vectors = matcher.embed_many([resume_sections.get(c, "") for c in names] + [jd_sections.get(c, "") for c in names])
        for i, component in enumerate(names):
            component_scores[component] = round(float(vectors[i].multiply(vectors[i + len(names)]).sum()), 4)
    else:
        for component in names:
            component_scores[component] = matcher.similarity(resume_sections.get(component, ""), jd_sections.get(component, ""))

    overall = round(sum(component_scores[c] * w for c, w in COMPONENT_WEIGHTS.items()), 4)
    classification = classify_score(overall, thresholds)

    return MatchResult(overall_score=overall, component_scores=component_scores, classification=classification)
