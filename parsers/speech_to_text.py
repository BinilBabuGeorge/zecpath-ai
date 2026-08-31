"""
Speech-to-Text Integration & Cleaning (Day 24)

SCOPE, STATED HONESTLY UP FRONT: this sandbox has no network access and
no real audio files exist anywhere in this project. There is no real
speech-to-text integration here, and there cannot honestly be one under
these constraints -- claiming otherwise would be exactly the kind of
fabricated capability this project has consistently avoided (see Day 16's
"PDF/DOCX not implemented," Day 23's "nothing performs real speech-to-
text"). What IS real and independently useful:

1. `STTProvider` -- a real, usable interface contract any actual STT
   vendor (Google STT, AWS Transcribe, Whisper, etc.) could implement
   to plug into this pipeline, so a future day (or someone with API
   access) has a concrete integration point rather than a blank page.
2. `MockSTTProvider` -- clearly labeled as a mock, not a real service.
   Deterministically injects realistic ASR-style noise (filler words,
   accent-driven mishearings, dropped punctuation, occasional silence)
   into known ground-truth text, seeded for reproducibility. This is
   what makes the accuracy testing below possible without real audio.
3. `clean_transcript()` -- the REAL, fully-working deliverable. Takes
   noisy raw text (from a real STT service or the mock) and produces
   clean, structured text ready for Day 23's `normalize_answer()`.

Pipeline position: audio -> STTProvider.transcribe() -> raw noisy text
-> clean_transcript() (this module) -> TranscriptTurn.raw_transcript
-> Day 23's normalize_answer() -> typed value.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Protocol


# ---------------------------------------------------------------------------
# 1. STT provider interface -- a real contract, no real implementation
# ---------------------------------------------------------------------------

@dataclass
class RawSTTResult:
    """What any STT provider hands back, real or mock."""
    text: str
    confidence: float  # 0.0-1.0, feeds directly into Day 23's asr_confidence
    is_silent: bool = False  # true silence detected (distinct from a low-confidence mumble)
    language: str = "en"


class STTProvider(Protocol):
    """Any real STT integration (Google STT, AWS Transcribe, Whisper,
    etc.) should implement this. Deliberately minimal -- audio_ref is a
    path/URL/bytes handle, not specified further here, since the actual
    audio storage/transport layer doesn't exist yet in this project
    (would be a Day 22-Phase-11-adjacent concern, per the PRD's AI Video
    Interview Infrastructure phase) and shouldn't be guessed at here.
    """
    def transcribe(self, audio_ref: str, language: str = "en") -> RawSTTResult:
        ...


# ---------------------------------------------------------------------------
# 2. Mock provider -- clearly a simulation, not a real integration
# ---------------------------------------------------------------------------

# Real, documented phenomenon (not invented for this demo): generic,
# Western-English-trained ASR models systematically mishear certain
# Indian-English pronunciations and India-specific vocabulary. These
# substitution pairs are illustrative examples of well-known ASR
# failure classes, used here only to generate realistic-shaped test
# noise -- not measured against any real ASR engine's actual error
# distribution, which this project has no way to obtain.
_ACCENT_SUBSTITUTIONS = {
    "indian_en": {
        "lakhs": "lakes", "lakh": "lack", "years": "yours",
        "notice": "no this", "immediately": "and mediately",
    },
    "clear": {},  # no substitutions -- a clean, high-confidence baseline
}

_FILLER_INSERTIONS = ["um", "uh", "like", "you know", "I mean", "so"]


class MockSTTProvider:
    """A deterministic, seeded noise-injection harness -- NOT a real STT
    service. Exists solely to make the "test multiple accents and noise
    conditions" task honestly testable without real audio: given a known
    ground-truth sentence, produces a plausibly-noisy transcript plus a
    confidence score that degrades with the requested noise_level, so
    clean_transcript()'s recovery quality can be measured against a
    known-correct answer (see run_day24_stt_accuracy_report.py).
    """

    def __init__(self, seed: int = 42):
        self._rng = random.Random(seed)

    def simulate(self, ground_truth: str, accent: str = "clear", noise_level: float = 0.0) -> RawSTTResult:
        """noise_level in [0.0, 1.0]: probability-scaling knob for filler
        insertion, casing/punctuation degradation, and (at high levels)
        silence. Deterministic for a given seed + inputs."""
        text = ground_truth

        subs = _ACCENT_SUBSTITUTIONS.get(accent, {})
        for wrong_sounding, mis_heard in subs.items():
            text = re.sub(rf"\b{re.escape(wrong_sounding)}\b", mis_heard, text, flags=re.IGNORECASE)

        words = text.split()
        if noise_level > 0:
            noisy_words = []
            for w in words:
                noisy_words.append(w)
                if self._rng.random() < noise_level * 0.15:
                    noisy_words.append(self._rng.choice(_FILLER_INSERTIONS))
            words = noisy_words
        text = " ".join(words)

        if noise_level > 0.3:
            text = text.lower()
            text = re.sub(r"[.,!?]", "", text)

        confidence = max(0.15, 1.0 - noise_level * 0.75 - (0.1 if subs else 0.0))
        is_silent = noise_level >= 0.95 and self._rng.random() < 0.3
        if is_silent:
            text = ""
            confidence = 0.0

        return RawSTTResult(text=text, confidence=round(confidence, 2), is_silent=is_silent)


# ---------------------------------------------------------------------------
# 3. clean_transcript() -- the real, working deliverable
# ---------------------------------------------------------------------------

class CleanStatus(str, Enum):
    OK = "ok"
    SILENT = "silent"                  # no speech detected at all
    PARTIAL_ANSWER = "partial_answer"  # speech cut off / trails off mid-thought
    SELF_CORRECTED = "self_corrected"  # candidate restarted/corrected themselves


@dataclass
class CleanedTranscript:
    text: str
    status: CleanStatus
    notes: List[str] = field(default_factory=list)
    had_filler_words: bool = False
    had_self_correction: bool = False


# Only unambiguous discourse fillers -- "like", "actually", "sort of",
# "kind of" are deliberately EXCLUDED even though they're common fillers,
# because they're also real content words ("I'd like to...", "it was
# actually broken") and stripping them risks silently deleting meaning.
# Consistent with this project's established preference (Day 23) for an
# honest gap over a confident wrong guess.
_FILLER_WORDS = {"um", "uh", "umm", "uhh", "erm", "hmm", "uh-huh"}
_FILLER_PHRASES = ["you know", "i mean"]

_CORRECTION_MARKERS = [
    r"\bno wait\b", r"\bsorry,? i mean\b", r"\bactually no\b",
    r"\blet me restart\b", r"\bscratch that\b", r"—", r"--",
]

_TRAILING_CUTOFF_WORDS = {"and", "but", "so", "the", "a", "an", "with", "because", "or"}


def _strip_filler_words(text: str) -> tuple:
    original = text
    for phrase in _FILLER_PHRASES:
        text = re.sub(rf"\b{re.escape(phrase)}\b,?", "", text, flags=re.IGNORECASE)
    words = text.split()
    kept = [w for w in words if w.strip(",.").lower() not in _FILLER_WORDS]
    cleaned = " ".join(kept)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned, cleaned != original.strip()


def _detect_self_correction(text: str) -> tuple:
    """If a correction marker is found, keep only the text AFTER the
    LAST marker (the candidate's final, corrected statement) -- not the
    abandoned first attempt. Returns (text_after_correction, found)."""
    last_end = None
    for pattern in _CORRECTION_MARKERS:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            if last_end is None or m.end() > last_end:
                last_end = m.end()
    if last_end is None:
        return text, False
    remainder = text[last_end:].strip(" ,.-—")
    return (remainder if remainder else text), True


def _fix_punctuation_and_case(text: str) -> str:
    text = text.strip()
    if not text:
        return text
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+([,.!?])", r"\1", text)  # no space before punctuation
    # Capitalize the first letter and after every sentence-ending punctuation.
    def _cap(match):
        return match.group(1) + match.group(2).upper()
    text = re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)
    # Standalone "i" -> "I"
    text = re.sub(r"\bi\b", "I", text)
    if text and text[-1] not in ".!?":
        text += "."
    return text


def _looks_like_partial_answer(text: str) -> bool:
    if not text:
        return False
    last_word = re.sub(r"[.,!?]$", "", text.split()[-1]).lower()
    return last_word in _TRAILING_CUTOFF_WORDS


def clean_transcript(raw: RawSTTResult) -> CleanedTranscript:
    """The real, working core of Day 24. Takes a RawSTTResult (from a
    real provider or MockSTTProvider) and produces clean, structured
    text plus a status flag for the three "Handle:" cases in the brief:
    interrupted speech, partial answers, silence detection.
    """
    if raw.is_silent or not raw.text.strip():
        return CleanedTranscript(
            text="", status=CleanStatus.SILENT,
            notes=["No speech detected -- distinct from a low-confidence transcription; "
                   "consider re-prompting the candidate rather than treating this as an answer."],
        )

    text = raw.text
    text, had_correction = _detect_self_correction(text)
    text, had_fillers = _strip_filler_words(text)
    text = _fix_punctuation_and_case(text)

    notes = []
    status = CleanStatus.OK
    if had_correction:
        status = CleanStatus.SELF_CORRECTED
        notes.append("Candidate appeared to restart or correct themselves -- kept the final statement only.")
    if _looks_like_partial_answer(text):
        status = CleanStatus.PARTIAL_ANSWER
        notes.append(f"Answer trails off on a connecting word ('{text.split()[-1].strip('.')}') -- likely cut off.")

    return CleanedTranscript(
        text=text, status=status, notes=notes,
        had_filler_words=had_fillers, had_self_correction=had_correction,
    )
