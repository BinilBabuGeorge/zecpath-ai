"""
Answer Intent & Understanding Engine (Day 25)

SCOPE, STATED HONESTLY UP FRONT: "intent classification" here is a
deterministic, keyword-and-pattern-based classifier -- NOT a trained
NLU/ML model. This project has no labeled intent-classification training
data and no model-training infrastructure, so claiming a real classifier
would be exactly the kind of fabricated capability this project has
consistently avoided (Day 16: "PDF/DOCX not implemented", Day 23/24:
"nothing performs real speech-to-text"). What IS real: a genuinely
useful, independently-tested rule-based classifier that works well on
the direct, keyword-bearing answers a screening call actually produces,
plus honestly-flagged limits on paraphrased or oblique answers a real
NLU model would catch and this one won't.

Pipeline position -- this sits AFTER, not instead of, Day 23/24:

    audio -> STTProvider.transcribe() (Day 24)
          -> clean_transcript()       (Day 24)
          -> understand_answer()      (Day 25, THIS module)
          -> StructuredAnswer         (Day 25 semantic object)

Day 23's normalize_answer() coerces a SINGLE question's answer to its
declared expected_answer_type (number/duration/yes_no/free_text). Day 25
solves a different, complementary problem: figuring out what a
free-form answer is actually ABOUT (intent), pulling out whichever of
several entity types (skills / experience / availability / salary) it
happens to mention -- useful because a real candidate's answer to "tell
me about yourself" routinely mentions two or three of these at once,
not just the one the question nominally targets -- and flagging answers
that don't engage with the question at all (off-topic), don't say
anything concrete (vague), or say nothing (missing).

Entity extraction reuses existing, already-tested modules rather than
re-implementing them:
  - Skills:      parsers.skill_extractor.extract_skills() (Day 4)
  - Numbers/duration: parsers.transcript_schema.normalize_answer()
    (Day 23), called with expected_answer_type="number"/"duration" as
    its own public entry point -- not by reaching into its private
    helpers.
Salary-expectation parsing (lakhs/LPA/thousand-per-month) is new here;
nothing upstream handles Indian salary phrasing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from parsers.skill_extractor import extract_skills
from parsers.transcript_schema import normalize_answer, NormalizationStatus


# ---------------------------------------------------------------------------
# Category / intent taxonomy -- aligned with Day 22's question categories
# ---------------------------------------------------------------------------

class AnswerIntent(str, Enum):
    INTRODUCTION = "introduction"
    EDUCATION = "education"
    EXPERIENCE = "experience"
    SKILLS = "skills"
    LOCATION = "location"
    SALARY = "salary"
    AVAILABILITY = "availability"    # maps to Day 22's "notice_period" category
    UNKNOWN = "unknown"              # no category's vocabulary matched -- honest "don't know", not a guess


class AnswerQuality(str, Enum):
    OK = "ok"
    VAGUE = "vague"          # hedging, non-committal, or too short to be a real answer
    OFF_TOPIC = "off_topic"  # positively matches a DIFFERENT category than the one asked
    MISSING = "missing"      # no speech at all (Day 24 SILENT) or empty text


# Keyword lexicons used ONLY for intent scoring (which topic is this
# answer about), not for entity extraction itself -- extraction below
# reuses real, already-tested modules where one exists (skills,
# numbers, duration) and adds new logic only where nothing existed
# (salary phrasing). Word-boundary matched throughout -- the same
# substring-matching bug class already found and fixed in Day 23
# ("no" inside "not") is guarded against here from the start rather
# than discovered later.
_CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "introduction": ["myself", "about me", "my name is", "i am a", "i'm a", "background"],
    "education": ["degree", "b\\.?tech", "bachelor", "master", "college", "university",
                  "diploma", "cgpa", "percentage", "graduate", "graduated"],
    "experience": ["experience", "worked", "working", "previous company", "current company",
                   "current role", "my role", "responsibilities", "years in"],
    "location": ["live in", "based in", "currently in", "relocate", "relocating", "my location", "my city"],
    "salary": ["salary", "ctc", "lakh", "lakhs", "lac", "lacs", "lpa", "package",
               "compensation", "expected pay", "hike"],
    "availability": ["notice period", "immediate", "immediately", "can join", "availability",
                     "days notice", "weeks notice", "months notice", "serving notice"],
}
# "skills" deliberately has no keyword list -- it is scored from a real
# extract_skills() call instead (see _score_categories), which is a
# strictly better signal than a hand-picked keyword list for a category
# whose whole vocabulary is "any known tech/soft skill term."

_CATEGORY_TO_INTENT = {
    "introduction": AnswerIntent.INTRODUCTION,
    "education": AnswerIntent.EDUCATION,
    "experience": AnswerIntent.EXPERIENCE,
    "location": AnswerIntent.LOCATION,
    "salary": AnswerIntent.SALARY,
    "availability": AnswerIntent.AVAILABILITY,
    "skills": AnswerIntent.SKILLS,
}

_HEDGE_PHRASES = [
    "i don't know", "i dont know", "not sure", "not certain", "maybe",
    "i guess", "depends", "hard to say", "can't say", "cant say",
    "not really sure", "i'm not sure", "i am not sure",
]


@dataclass
class IntentClassification:
    intent: AnswerIntent
    confidence: float                 # heuristic 0.0-1.0, NOT a calibrated probability -- see docstring
    category_scores: Dict[str, float] # every category's raw keyword/entity hit score, for auditability
    note: Optional[str] = None


@dataclass
class ExtractedEntities:
    skills: List[str] = field(default_factory=list)
    experience_years: Optional[float] = None
    availability: Optional[Dict] = None          # {amount, unit, immediate} -- Day 23's duration shape, reused as-is
    salary_expectation: Optional[Dict] = None    # {amount, unit, raw} -- see extract_salary_expectation()


@dataclass
class StructuredAnswer:
    """The semantic-object deliverable: one free-form answer, fully
    understood -- what it's about, how good an answer it is, and
    whatever concrete entities could honestly be pulled out of it."""
    raw_text: str
    question_category: str            # the category the question WAS asking about (from Day 22)
    intent: IntentClassification
    quality: AnswerQuality
    entities: ExtractedEntities
    notes: List[str] = field(default_factory=list)
    turn_id: Optional[str] = None     # links back to Day 23's TranscriptTurn.turn_id, when available

    def to_dict(self) -> Dict:
        return {
            "turn_id": self.turn_id,
            "question_category": self.question_category,
            "raw_text": self.raw_text,
            "quality": self.quality.value,
            "notes": self.notes,
            "intent": {
                "predicted": self.intent.intent.value,
                "confidence": self.intent.confidence,
                "category_scores": self.intent.category_scores,
                "note": self.intent.note,
            },
            "entities": {
                "skills": self.entities.skills,
                "experience_years": self.entities.experience_years,
                "availability": self.entities.availability,
                "salary_expectation": self.entities.salary_expectation,
            },
        }


# ---------------------------------------------------------------------------
# 1. Intent classification
# ---------------------------------------------------------------------------

def _score_categories(text: str) -> Dict[str, float]:
    lowered = text.lower()
    scores: Dict[str, float] = {}

    for category, phrases in _CATEGORY_KEYWORDS.items():
        hits = 0
        for phrase in phrases:
            if re.search(rf"\b{phrase}\b", lowered):
                hits += 1
        scores[category] = float(hits)

    # Skills scored from the real extractor, not a keyword guess. Each
    # distinct skill found is stronger evidence than a keyword hit
    # (e.g. finding "React" and "Node.js" is unambiguous skills-talk),
    # so it's weighted at 1.5x a plain keyword hit.
    found_skills = extract_skills(text)
    scores["skills"] = round(len(found_skills) * 1.5, 2)

    return scores


def classify_intent(text: str) -> IntentClassification:
    """Rule-based only -- see module docstring for why. Picks the
    highest-scoring category; ties broken by a fixed priority order
    (skills/experience treated as more information-bearing than a
    passing mention of introduction phrasing) rather than silently by
    dict order, which would be an accident, not a decision.
    """
    text = (text or "").strip()
    if not text:
        return IntentClassification(intent=AnswerIntent.UNKNOWN, confidence=0.0, category_scores={}, note="Empty text")

    scores = _score_categories(text)
    top_score = max(scores.values()) if scores else 0.0

    if top_score == 0.0:
        return IntentClassification(
            intent=AnswerIntent.UNKNOWN, confidence=0.0, category_scores=scores,
            note="No category's vocabulary matched -- an honest 'don't know', not a guess. "
                 "A real NLU model would likely classify paraphrased or oblique answers this "
                 "rule-based version misses.",
        )

    _TIE_PRIORITY = ["skills", "experience", "salary", "availability", "education", "location", "introduction"]
    tied = [cat for cat, s in scores.items() if s == top_score]
    winner = next((cat for cat in _TIE_PRIORITY if cat in tied), tied[0])

    total = sum(scores.values())
    # Heuristic scaling, not a calibrated probability: how dominant the
    # winning category's score is relative to everything else that
    # matched at all. Explicitly documented as a heuristic in the
    # dataclass field comment above -- do not treat this as "the model
    # is N% sure."
    confidence = round(top_score / total, 2) if total > 0 else 0.0

    return IntentClassification(
        intent=_CATEGORY_TO_INTENT[winner], confidence=confidence, category_scores=scores,
    )


# ---------------------------------------------------------------------------
# 2. Entity extraction -- reuses real modules; adds only what's missing
# ---------------------------------------------------------------------------

def extract_experience_years(text: str) -> Optional[float]:
    """Reuses Day 23's public normalize_answer() entry point (typed
    "number") rather than duplicating its word-number parsing logic.
    Only called on text that classify_intent already scored as
    experience-relevant by the caller (understand_answer) -- a bare
    number extracted from an off-topic sentence would be meaningless.
    """
    result = normalize_answer(text, expected_answer_type="number", asr_confidence=1.0)
    if result.status == NormalizationStatus.OK:
        return result.value
    return None


def extract_availability(text: str) -> Optional[Dict]:
    """Reuses Day 23's duration extraction via its public entry point."""
    result = normalize_answer(text, expected_answer_type="duration", asr_confidence=1.0)
    if result.status == NormalizationStatus.OK:
        return result.value
    return None


# New here: Day 23/24 have no salary-specific unit handling. "eleven
# lakhs" and "45k a month" mean very different things and must NOT be
# collapsed to the same bare number -- same reasoning Day 23 applied to
# keeping duration as {amount, unit} instead of a bare number.
_LAKH_PATTERN = re.compile(r"(\d+\.?\d*|\bone\b|\btwo\b|\bthree\b|\bfour\b|\bfive\b|\bsix\b|\bseven\b|\beight\b|\bnine\b|\bten\b|\beleven\b|\btwelve\b)\s*(?:lakhs?|lacs?|lpa)\b", re.IGNORECASE)
_THOUSAND_PATTERN = re.compile(r"(\d+\.?\d*)\s*k\b(?!\w)", re.IGNORECASE)
_WORD_NUMS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
              "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}


def extract_salary_expectation(text: str) -> Optional[Dict]:
    """Returns {amount, unit, raw} or None. unit is one of
    "lakhs_per_annum" or "thousand_per_month" -- deliberately NOT
    collapsed to a single rupee figure, since that would require
    guessing an annual/monthly convention the candidate never stated.
    A bare unit-less number (e.g. "around eight hundred thousand") is
    NOT parsed here -- flagged as a documented gap below, not silently
    misread, consistent with this project's established stance
    (Day 23's number/duration extractors do the same: fall through to
    "not found" rather than guess).
    """
    match = _LAKH_PATTERN.search(text)
    if match:
        raw_amount = match.group(1).lower()
        amount = _WORD_NUMS.get(raw_amount, None)
        if amount is None:
            amount = float(raw_amount)
        return {"amount": amount, "unit": "lakhs_per_annum", "raw": match.group(0)}

    match = _THOUSAND_PATTERN.search(text)
    if match:
        return {"amount": float(match.group(1)), "unit": "thousand_per_month", "raw": match.group(0)}

    return None


# ---------------------------------------------------------------------------
# 3. Quality gating -- vague / off-topic / missing
# ---------------------------------------------------------------------------

def _is_vague(text: str, category_scores: Optional[Dict[str, float]] = None) -> bool:
    lowered = text.lower().strip()
    if any(re.search(rf"\b{re.escape(phrase)}\b", lowered) for phrase in _HEDGE_PHRASES):
        return True
    # A very short answer (1-2 words) that isn't a clean yes/no is
    # ONLY too thin to be a real answer if it also carries no
    # recognizable concrete content. Originally this flagged EVERY
    # short answer as vague regardless of content -- a real bug found
    # during Day 30 testing: "5 years", "Ten lakhs", "B.Tech CSE",
    # "Immediately", and "Thirty days" are all complete, confident,
    # perfectly answerable screening responses that were being
    # rejected purely for their length. See Day 30's docs for the
    # false-rejection evidence this fix is based on.
    words = lowered.split()
    if 0 < len(words) <= 2 and lowered not in {"yes", "no", "yeah", "nope"}:
        if not _looks_like_concrete_short_answer(lowered, category_scores):
            return True
    return False


# Broader than Day 23/25's strict number-extraction word list --
# purely for "does this look like a confident, concrete short answer"
# purposes, not for extracting a precise value. A wider net here is
# safe: the worst case is a short non-answer slipping through as OK,
# which downstream (Day 26 completeness scoring) still catches if
# nothing extractable comes of it.
_NUMBER_WORDS_BROAD = {
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
    "eighteen", "nineteen", "twenty", "thirty", "forty", "fifty", "sixty",
    "seventy", "eighty", "ninety", "hundred",
}
_CONFIDENT_SHORT_ANSWER_WORDS = {"immediately", "immediate", "asap"}


def _looks_like_concrete_short_answer(lowered_text: str, category_scores: Optional[Dict[str, float]]) -> bool:
    if any(ch.isdigit() for ch in lowered_text):
        return True
    words = re.findall(r"[a-z']+", lowered_text)
    if any(w in _NUMBER_WORDS_BROAD for w in words):
        return True
    if any(w in _CONFIDENT_SHORT_ANSWER_WORDS for w in words):
        return True
    if category_scores and any(s > 0 for s in category_scores.values()):
        return True
    return False


def _assess_quality(text: str, expected_category: str, intent: IntentClassification, is_silent: bool) -> AnswerQuality:
    if is_silent or not text.strip():
        return AnswerQuality.MISSING
    if _is_vague(text, intent.category_scores):
        return AnswerQuality.VAGUE

    expected_score = intent.category_scores.get(expected_category, 0.0)
    if expected_score == 0.0:
        # Only call this OFF_TOPIC when there's POSITIVE evidence the
        # answer is about something else -- absence of the expected
        # category's vocabulary alone is not proof of an off-topic
        # answer (it could just be phrased in a way this rule-based
        # classifier doesn't recognize). This mirrors Day 20's
        # documented stance: an honest "can't tell" beats a confident
        # wrong guess.
        other_hits = {cat: s for cat, s in intent.category_scores.items() if cat != expected_category and s > 0}
        if other_hits:
            return AnswerQuality.OFF_TOPIC
    return AnswerQuality.OK


# ---------------------------------------------------------------------------
# 4. Single entry point -- the "answer understanding engine" deliverable
# ---------------------------------------------------------------------------

def understand_answer(
    text: str,
    expected_category: str,
    turn_id: Optional[str] = None,
    is_silent: bool = False,
) -> StructuredAnswer:
    """Runs the full Day 25 pipeline on one cleaned answer (post Day 24
    clean_transcript()) and returns a fully structured semantic object.

    expected_category should be one of Day 22's CATEGORY_METADATA keys
    (introduction/education/experience/skills/location/salary/notice_period).
    "notice_period" is accepted as an alias for "availability" so this
    module lines up with Day 22's naming without renaming Day 22's
    established category.
    """
    if expected_category == "notice_period":
        expected_category = "availability"

    intent = classify_intent(text)
    quality = _assess_quality(text, expected_category, intent, is_silent)

    entities = ExtractedEntities()
    notes: List[str] = []

    if quality in (AnswerQuality.OK,):
        # Entities are extracted from whichever categories the answer
        # actually scored on -- not just the expected one -- since a
        # single free-form answer routinely touches more than one
        # (e.g. an introduction that also states years of experience).
        scored_categories = {cat for cat, s in intent.category_scores.items() if s > 0}

        if "skills" in scored_categories:
            entities.skills = [s.name for s in extract_skills(text)]
        if "experience" in scored_categories:
            entities.experience_years = extract_experience_years(text)
            if entities.experience_years is None:
                notes.append("Experience-relevant answer, but no clear numeric years found.")
        if "availability" in scored_categories:
            entities.availability = extract_availability(text)
            if entities.availability is None:
                notes.append("Availability-relevant answer, but no clear duration found.")
        if "salary" in scored_categories:
            entities.salary_expectation = extract_salary_expectation(text)
            if entities.salary_expectation is None:
                notes.append("Salary-relevant answer, but amount/unit could not be confidently parsed "
                             "(e.g. no lakh/LPA/k unit stated) -- documented gap, not a guess.")
    elif quality == AnswerQuality.OFF_TOPIC:
        matched_other = [cat for cat, s in intent.category_scores.items() if cat != expected_category and s > 0]
        notes.append(f"Expected a '{expected_category}' answer, but the response matches '{matched_other[0]}' vocabulary instead.")
    elif quality == AnswerQuality.VAGUE:
        notes.append("Answer is a hedge/non-answer or too short to extract anything concrete from.")
    elif quality == AnswerQuality.MISSING:
        notes.append("No speech content to understand -- see Day 24's clean_transcript() SILENT status.")

    return StructuredAnswer(
        raw_text=text, question_category=expected_category, intent=intent,
        quality=quality, entities=entities, notes=notes, turn_id=turn_id,
    )
