"""
Semantic Matching Engine (Day 12)

IMPORTANT, upfront: this uses TF-IDF vector embeddings + cosine similarity,
NOT a trained neural embedding model (e.g. sentence-transformers, BERT).
This sandbox has no general internet access -- it cannot reach
huggingface.co or any model hosting service to download pretrained model
weights, only a handful of package registries (pypi, npm, etc). TF-IDF is
a legitimate, real embedding technique (each document becomes a vector in
a high-dimensional space, and cosine similarity between vectors measures
closeness) -- it's just a classical statistical technique, not a deep
learning one. That distinction matters and is documented honestly
throughout this report.

To partially bridge the gap between "exact word overlap" (what plain
TF-IDF sees) and genuine semantic equivalence, text is preprocessed
through Day 9's skill dictionary first: "ReactJS" and "React.js" are
both rewritten to the same canonical token before vectorizing, so a
resume and JD that describe the same skill differently still produce
similar vectors. This is demonstrated quantitatively in section 3 of the
Day 12 report (with vs. without normalization).

Public API:
    SemanticMatcher(corpus: List[str])          -- fit on a text corpus
    matcher.similarity(text_a, text_b) -> float  -- 0.0-1.0
    compare_resume_to_jd(resume_sections, jd_sections, matcher) -> MatchResult
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from parsers.skill_dictionary import SKILL_DICTIONARY

# normalized synonym -> canonical skill name (same pattern as Day 9)
_SYNONYM_LOOKUP: Dict[str, str] = {}
for canonical, info in SKILL_DICTIONARY.items():
    _SYNONYM_LOOKUP[canonical.lower()] = canonical
    for syn in info["synonyms"]:
        _SYNONYM_LOOKUP[syn.lower()] = canonical
_SORTED_SYNONYMS = sorted(_SYNONYM_LOOKUP.keys(), key=len, reverse=True)


def normalize_for_embedding(text: str) -> str:
    """Rewrite every recognized skill synonym in the text to its canonical
    form (joined with underscores so it stays one token for TF-IDF, e.g.
    'react.js' and 'reactjs' both become 'React_js'), before vectorizing.
    This is what lets TF-IDF catch cases plain word-overlap would miss."""
    lowered = text.lower()
    for synonym in _SORTED_SYNONYMS:
        pattern = r"(?<!\w)" + re.escape(synonym) + r"(?!\w)"
        canonical_token = _SYNONYM_LOOKUP[synonym].replace(".", "").replace(" ", "_")
        lowered = re.sub(pattern, canonical_token, lowered)
    return lowered


class SemanticMatcher:
    """Fits a shared TF-IDF vocabulary on a corpus, then measures cosine
    similarity between any two texts in that vector space."""

    def __init__(self, corpus: List[str], normalize: bool = True):
        self.normalize = normalize
        prepared = [normalize_for_embedding(t) if normalize else t for t in corpus]
        self.vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        self.vectorizer.fit(prepared)

    def embed(self, text: str):
        prepared = normalize_for_embedding(text) if self.normalize else text
        return self.vectorizer.transform([prepared])

    def similarity(self, text_a: str, text_b: str) -> float:
        vec_a = self.embed(text_a)
        vec_b = self.embed(text_b)
        score = cosine_similarity(vec_a, vec_b)[0][0]
        return round(float(score), 4)


# ---------------------------------------------------------------------------
# Resume <-> JD component comparison
# ---------------------------------------------------------------------------

COMPONENT_WEIGHTS = {"skills": 0.45, "experience": 0.35, "overall": 0.20}


@dataclass
class MatchResult:
    overall_score: float  # 0-1
    component_scores: Dict[str, float] = field(default_factory=dict)
    classification: str = ""  # "Strong Match" | "Moderate Match" | "Weak Match"


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
    """Compare a resume to a JD component-by-component (skills, experience,
    overall text), then combine into a weighted overall score."""
    component_scores = {}
    for component, weight in COMPONENT_WEIGHTS.items():
        resume_text = resume_sections.get(component, "")
        jd_text = jd_sections.get(component, "")
        component_scores[component] = matcher.similarity(resume_text, jd_text)

    overall = round(sum(component_scores[c] * w for c, w in COMPONENT_WEIGHTS.items()), 4)
    classification = classify_score(overall, thresholds)

    return MatchResult(overall_score=overall, component_scores=component_scores, classification=classification)
