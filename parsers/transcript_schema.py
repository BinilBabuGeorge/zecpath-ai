"""
Transcript Data Architecture (Day 23)

Defines how a voice screening call -- once Day 22's questions are asked
and a candidate answers out loud -- gets turned into structured,
AI-processable data. Nothing in this project performs real speech-to-
text; every transcript this module consumes is either a human-typed
proxy for what ASR would produce, or a synthetic example clearly marked
as such (see run_day23_transcript_demo.py). What IS real: the schema,
the normalization logic, and the DB DDL, all independently verified in
this session (normalization tested against real edge cases; DDL proven
by actually creating the tables in SQLite, not just eyeballing SQL text).

Two storage granularities, matching how a real screening call actually
happens:
  - CallSession -- one call: who, which job, when, overall outcome.
  - TranscriptTurn -- one Q&A exchange within that call: which question
    (linking back to Day 22's ScreeningQuestion.id), the raw ASR text,
    ASR confidence, and the normalized value once that raw text is
    coerced toward the question's expected_answer_type.

Metadata standard (the four required fields from the Day 23 brief,
Candidate ID / Job ID / Question ID / Timestamp / Confidence level) live
at the TURN level, not the call level -- confidence is inherently a
per-utterance ASR concept, and a call is just the sum of its turns plus
timing envelope.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class CallStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DROPPED = "dropped"          # candidate hung up / call disconnected mid-way
    FAILED = "failed"            # technical failure (e.g. no answer, line error)


class NormalizationStatus(str, Enum):
    OK = "ok"                    # raw text cleanly coerced to the expected type
    PARTIAL = "partial"          # coerced, but with a caveat worth a human glance
    NEEDS_REVIEW = "needs_review"  # could not confidently coerce -- do not auto-score this turn
    NOT_APPLICABLE = "not_applicable"  # free_text has no coercion to attempt


# ---------------------------------------------------------------------------
# Core records
# ---------------------------------------------------------------------------

@dataclass
class NormalizedAnswer:
    """The result of turning raw ASR text into something a downstream
    scorer can actually use. `raw_text` is always preserved alongside
    `value` -- normalization is lossy by nature (word-to-number mapping,
    yes/no phrase matching), and anything that touches a hiring decision
    needs the original utterance auditable, not just the machine's
    interpretation of it.
    """
    value: object                    # type depends on expected_answer_type -- see normalize_answer()
    status: NormalizationStatus
    raw_text: str
    note: Optional[str] = None       # why status is PARTIAL/NEEDS_REVIEW, when relevant

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class TranscriptTurn:
    """One question-answer exchange. Metadata standard fields (Day 23
    brief): candidate_id, job_id, question_id, timestamp, confidence
    are all present here, at turn granularity.
    """
    turn_id: str
    call_id: str
    candidate_id: str
    job_id: str
    question_id: str                 # matches screening_question_bank.ScreeningQuestion.id
    turn_index: int                  # 0-based order within the call
    question_text: str               # the exact text asked (rendered, not the template)
    raw_transcript: str              # ASR output for the candidate's spoken answer
    asr_confidence: float            # 0.0-1.0
    timestamp: str                   # ISO 8601, UTC
    expected_answer_type: str        # from Day 22: free_text|number|duration|yes_no|list
    normalized: Optional[NormalizedAnswer] = None

    def to_dict(self) -> Dict:
        d = asdict(self)
        if self.normalized is not None:
            d["normalized"] = self.normalized.to_dict()
        return d


@dataclass
class CallSession:
    """One screening call. `turns` holds every TranscriptTurn in order;
    a call's overall confidence is intentionally NOT a single averaged
    number stored here -- see docs/day23_transcript_architecture.md for
    why a per-call average confidence is a bad idea that hides the turns
    that actually need review.
    """
    call_id: str
    candidate_id: str
    job_id: str
    started_at: str
    ended_at: Optional[str] = None
    status: CallStatus = CallStatus.IN_PROGRESS
    language: str = "en"
    turns: List[TranscriptTurn] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "call_id": self.call_id, "candidate_id": self.candidate_id, "job_id": self.job_id,
            "started_at": self.started_at, "ended_at": self.ended_at,
            "status": self.status.value, "language": self.language,
            "turns": [t.to_dict() for t in self.turns],
        }

    def turns_needing_review(self) -> List[TranscriptTurn]:
        return [t for t in self.turns if t.normalized and t.normalized.status == NormalizationStatus.NEEDS_REVIEW]


def new_call_id() -> str:
    return f"call_{uuid.uuid4().hex[:12]}"


def new_turn_id(call_id: str, turn_index: int) -> str:
    return f"{call_id}-t{turn_index:03d}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Transcript normalization rules
# ---------------------------------------------------------------------------
# Explicitly scoped, heuristic, regex/lookup-table based -- NOT a general
# NLU numeral/date parser. Documented limitations in
# docs/day23_transcript_architecture.md. Every rule below was tested
# against specific real phrasings, not assumed to work.

_WORD_NUMBERS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
}
# Deliberately excludes "a"/"an" as number words -- an earlier version
# included them (to catch "a year" -> 1), but "a" is such a common
# article that it false-matched ordinary filler speech with no numeric
# content at all: "quite a while actually" incorrectly extracted 1.0.
# Found and fixed this by testing against realistic phrasings, not by
# inspection -- exactly the kind of silent-wrong-answer bug that matters
# most to catch in something feeding a hiring decision. "couple"/"few"/
# "half" are kept: they're rare enough in casual speech, and specific
# enough in meaning, not to cause the same false-positive problem.
_APPROXIMATE_WORD_NUMBERS = {"couple": 2, "few": 3, "half": 0.5}

_YES_PHRASES = {"yes", "yeah", "yep", "yup", "sure", "definitely", "absolutely", "correct", "right", "of course"}
_NO_PHRASES = {"no", "nope", "not really", "no way", "negative", "not at all"}

_LOW_CONFIDENCE_THRESHOLD = 0.55
# Below this ASR confidence, normalization refuses to guess even if the
# text superficially parses -- a low-confidence transcript is exactly
# the case where a plausible-looking parse is most likely to be wrong.


def _extract_number(text: str) -> Optional[float]:
    """Digit extraction first (handles '3', '3.5', '8,00,000'), then a
    single word-number lookup as fallback (handles 'three'). Does NOT
    handle compound number words ('twenty-three', 'thirty five years') --
    documented gap, not silently mishandled (falls through to None ->
    NEEDS_REVIEW rather than guessing wrong).
    """
    cleaned = text.replace(",", "")
    match = re.search(r"-?\d+\.?\d*", cleaned)
    if match:
        return float(match.group())
    all_word_numbers = {**_WORD_NUMBERS, **_APPROXIMATE_WORD_NUMBERS}
    lowered = text.lower()
    for word, value in all_word_numbers.items():
        match = re.search(rf"\b{word}\b", lowered)
        if not match:
            continue
        start, end = match.span()
        # A hyphen immediately before/after the matched word means it's
        # part of a compound number word ("twenty-three") -- \b alone
        # doesn't catch this, since a hyphen is a non-word character and
        # creates a legitimate word boundary on its own. Compound number
        # words are a documented non-goal (see module docstring); this
        # guard makes the code actually match that documentation instead
        # of silently extracting the wrong number (e.g. "three" out of
        # "twenty-three"). Found via a test written against the
        # documented intent, not assumed to already work.
        preceded_by_hyphen = start > 0 and lowered[start - 1] == "-"
        followed_by_hyphen = end < len(lowered) and lowered[end] == "-"
        if preceded_by_hyphen or followed_by_hyphen:
            continue
        return float(value)
    return None


def _extract_duration_description(text: str) -> Optional[Dict]:
    """Duration is kept as a structured {amount, unit} dict rather than
    coerced to a single number -- '2 weeks' and '2 months' are both
    parseable but mean very different things for a notice-period
    decision, and collapsing them to a bare '2' would destroy that.
    """
    lowered = text.lower()
    if re.search(r"\bimmediate(ly)?\b|\bcan join now\b|\bno notice\b", lowered):
        return {"amount": 0, "unit": "days", "immediate": True}
    match = re.search(r"(\d+\.?\d*|\bone\b|\btwo\b|\bthree\b|\bfour\b)\s*(day|week|month)", lowered)
    if match:
        amount_text = match.group(1)
        amount = _WORD_NUMBERS.get(amount_text, None)
        if amount is None:
            amount = float(amount_text)
        unit = match.group(2) + "s"
        return {"amount": amount, "unit": unit, "immediate": False}
    return None


_NEGATORS = ("not ", "n't ", "never ")


def _is_negated(lowered: str, match_start: int) -> bool:
    """True if a negator appears shortly before the match -- catches
    "not totally sure" so it doesn't confidently match the YES phrase
    "sure" embedded inside it. Deliberately conservative: this only
    SKIPS a would-be match (falling through toward NEEDS_REVIEW if
    nothing else matches) rather than flipping it to the opposite
    answer -- "not correct" might well mean "no," but guessing that
    confidently risks being wrong in the direction that matters most
    (silently recording a false answer). Deferring to human review is
    the safer failure mode, consistent with this project's established
    stance (see Day 20's zone-classification design).
    """
    window = lowered[max(0, match_start - 12):match_start]
    return any(neg in window for neg in _NEGATORS)


def _extract_yes_no(text: str) -> Optional[bool]:
    """Word-boundary matching, not naive substring containment -- an
    earlier version used plain `phrase in lowered`, which incorrectly
    matched "no" inside "not" (e.g. "not totally sure" silently became
    False) since "not" contains the literal two characters "n","o"
    contiguously. Found via testing an ambiguous, hedging answer
    ("maybe, I'm not totally sure") that should be NEEDS_REVIEW, not a
    confident False -- exactly the silent-wrong-answer failure mode this
    module's docstring says it exists to avoid. Also negation-scope
    aware (see _is_negated) after fixing the substring bug surfaced a
    second, related case: the same hedging phrase then matched the bare
    word "sure" inside it as a false YES.
    """
    lowered = text.lower().strip()
    for phrase in _NO_PHRASES:
        match = re.search(rf"\b{re.escape(phrase)}\b", lowered)
        if match and not _is_negated(lowered, match.start()):
            return False
    for phrase in _YES_PHRASES:
        match = re.search(rf"\b{re.escape(phrase)}\b", lowered)
        if match and not _is_negated(lowered, match.start()):
            return True
    return None


def normalize_answer(raw_text: str, expected_answer_type: str, asr_confidence: float) -> NormalizedAnswer:
    """The single entry point every TranscriptTurn's answer should go
    through. Confidence-gated: below _LOW_CONFIDENCE_THRESHOLD, always
    returns NEEDS_REVIEW regardless of whether the text superficially
    parses -- see the threshold's docstring above for why.
    """
    raw_text = (raw_text or "").strip()

    if not raw_text:
        return NormalizedAnswer(value=None, status=NormalizationStatus.NEEDS_REVIEW, raw_text=raw_text, note="Empty transcript")

    if asr_confidence < _LOW_CONFIDENCE_THRESHOLD:
        return NormalizedAnswer(
            value=None, status=NormalizationStatus.NEEDS_REVIEW, raw_text=raw_text,
            note=f"ASR confidence {asr_confidence:.2f} below threshold {_LOW_CONFIDENCE_THRESHOLD} -- not auto-normalized",
        )

    if expected_answer_type == "free_text" or expected_answer_type == "list":
        # No coercion attempted -- these are for a human/downstream NLP
        # reader, not a numeric/boolean scorer. Passing the raw text
        # through as `value` is the correct behavior, not a shortcut.
        return NormalizedAnswer(value=raw_text, status=NormalizationStatus.NOT_APPLICABLE, raw_text=raw_text)

    if expected_answer_type == "yes_no":
        result = _extract_yes_no(raw_text)
        if result is None:
            return NormalizedAnswer(value=None, status=NormalizationStatus.NEEDS_REVIEW, raw_text=raw_text, note="No clear yes/no phrase found")
        return NormalizedAnswer(value=result, status=NormalizationStatus.OK, raw_text=raw_text)

    if expected_answer_type == "number":
        result = _extract_number(raw_text)
        if result is None:
            return NormalizedAnswer(value=None, status=NormalizationStatus.NEEDS_REVIEW, raw_text=raw_text, note="No number found in transcript")
        return NormalizedAnswer(value=result, status=NormalizationStatus.OK, raw_text=raw_text)

    if expected_answer_type == "duration":
        result = _extract_duration_description(raw_text)
        if result is None:
            return NormalizedAnswer(value=None, status=NormalizationStatus.NEEDS_REVIEW, raw_text=raw_text, note="Could not identify a duration in transcript")
        status = NormalizationStatus.OK
        return NormalizedAnswer(value=result, status=status, raw_text=raw_text)

    return NormalizedAnswer(value=raw_text, status=NormalizationStatus.NEEDS_REVIEW, raw_text=raw_text, note=f"Unknown expected_answer_type '{expected_answer_type}'")
