"""
Behavioral AI Research & Design (Day 48)

WHAT THIS DAY IS, AND WHY IT ISN'T WHAT THE BRIEF LITERALLY LISTS:
the brief's "research behavior signals" bullets -- eye movement, gaze
stability, head movement, facial engagement -- describe CAMERA-BASED
biometric analysis. This project has no video pipeline anywhere: no
camera input, no frame processing, no face/landmark detection library
(verified directly -- a project-wide search for cv2/opencv/mediapipe/
dlib/face_recognition/webcam/video returns zero hits). Building
functions named `detect_gaze_stability()` or `detect_nervous_gestures()`
that don't actually process any image data would not be a limited or
approximate version of that capability -- it would be fabricating a
capability that does not exist, exactly the kind of thing every prior
day in this project has gone out of its way NOT to do. That line is
not crossed here either.

THE BRIEF'S OWN LAST TASK IS THE WAY THROUGH THIS: "design a
NON-INVASIVE behavioral scoring approach." Camera-based gaze/facial
analysis is the invasive option -- it requires biometric data
collection, and this project's own Day 43 audit already found ZERO
consent-capture infrastructure exists anywhere, for even plain text.
Video/facial data is a materially higher-stakes category than text
(most privacy frameworks, and emerging AI-specific regulation in
several jurisdictions, treat biometric categorization and emotion
inference in employment contexts as high-risk or restricted) -- adding
it on top of an already-flagged consent gap, with no fairness review
for a signal type well-documented to carry demographic bias risk in
other systems, would be compounding a known problem rather than fixing
it. (General awareness of the regulatory landscape, not legal advice
-- a real deployment should get real legal review before touching
biometric data at all.)

THE ACTUAL DESIGN DECISION THIS DAY MAKES: treat "non-invasive" as the
binding constraint, not a nice-to-have, and build genuinely observable
behavioral signals that come from INTERACTION TIMING and TEXT -- data
this project already collects or can collect without adding any new
sensor, camera, or biometric capture:

    Brief's signal          ->  What this day actually measures
    ------------------------------------------------------------------
    Eye movement/gaze        ->  NOT IMPLEMENTED (needs camera; see above)
    Head movement             ->  NOT IMPLEMENTED (needs camera; see above)
    Facial engagement          ->  NOT IMPLEMENTED (needs camera; see above)
    Focus level                ->  Response-latency CONSISTENCY across a session
    Distraction frequency       ->  Anomalous latency SPIKES relative to the
                                     candidate's own median pace
    Nervous gestures             ->  NOT IMPLEMENTED AS ASKED (a physical/visual
                                     signal). The closest available proxy --
                                     verbal hesitation (filler words, reused
                                     directly from Day 27) -- is a genuinely
                                     different signal (speech disfluency, not
                                     gesture) and is labeled as such, not
                                     substituted in silently.

REUSE: `detect_hesitation()` is imported directly from Day 27's
`confidence_sentiment_engine`, unchanged -- the same generic,
screening-independent filler-word detector Day 36 already reused for
a different purpose. Timing itself is new: no session in this project
currently records when a question was presented or when a response
arrived, so this day adds that via the same additive, opt-in WRAPPER
pattern Day 45 established (`submit_scrubbed_response()`) rather than
modifying `InterviewSession` or `TechnicalInterviewSession` directly --
works with either session type via light duck-typing, and leaves both
untouched for every existing caller.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol

from parsers.confidence_sentiment_engine import detect_hesitation, HesitationResult

# A latency this many times the candidate's own median counts as a
# "spike" -- reasoned, not data-calibrated (no labeled data exists for
# this signal, the same caveat every scoring day since 34 has stated).
_SPIKE_MULTIPLIER = 2.0
_MIN_RECORDS_FOR_SPIKE_DETECTION = 3   # fewer than this, "spike" isn't a meaningful concept yet


class _TimableSession(Protocol):
    """Structural typing only -- InterviewSession and
    TechnicalInterviewSession both satisfy this without either being
    imported or modified."""
    is_complete: bool

    @property
    def current_question(self): ...
    def submit_response(self, text: str) -> None: ...


def _extract_question_id(question_state) -> str:
    # InterviewQuestionState (Day 33) has question_id directly;
    # TechnicalQuestionState (Day 46) nests it under .question.
    if hasattr(question_state, "question_id"):
        return question_state.question_id
    return question_state.question.question_id


@dataclass
class TimedResponseRecord:
    question_id: str
    response_text: str
    latency_seconds: float


@dataclass
class TimedSessionTracker:
    """Wraps any question-presenting session (Day 33's
    InterviewSession or Day 46's TechnicalInterviewSession) to record
    presentation-to-submission latency per question. Opt-in: a caller
    using the session's own submit_response() directly is completely
    unaffected, same guarantee Day 45 gives for its wrapper."""
    session: _TimableSession
    records: List[TimedResponseRecord] = field(default_factory=list)
    _question_presented_at: Optional[float] = None
    _current_question_id: Optional[str] = None

    def __post_init__(self) -> None:
        self._mark_current_question_presented()

    def _mark_current_question_presented(self) -> None:
        q = self.session.current_question
        if q is not None:
            self._current_question_id = _extract_question_id(q)
            self._question_presented_at = time.monotonic()
        else:
            self._current_question_id = None
            self._question_presented_at = None

    def submit_timed_response(self, text: str) -> TimedResponseRecord:
        if self.session.is_complete or self._question_presented_at is None:
            raise ValueError("Session already complete -- no current question to time a response for.")

        latency = round(time.monotonic() - self._question_presented_at, 3)
        question_id = self._current_question_id

        self.session.submit_response(text)

        record = TimedResponseRecord(question_id=question_id, response_text=text, latency_seconds=latency)
        self.records.append(record)

        self._mark_current_question_presented()
        return record


# ---------------------------------------------------------------------------
# Signals computable from timing alone -- "focus level" and
# "distraction frequency", honestly reinterpreted as described above
# ---------------------------------------------------------------------------

@dataclass
class FocusConsistencyResult:
    latencies: List[float]
    mean_latency: float
    stdev_latency: float
    coefficient_of_variation: Optional[float]   # stdev / mean -- lower means steadier pacing
    focus_level_score: float   # 0-100, higher = steadier pacing across the session


def assess_focus_consistency(records: List[TimedResponseRecord]) -> FocusConsistencyResult:
    latencies = [r.latency_seconds for r in records]
    if len(latencies) < 2:
        mean = latencies[0] if latencies else 0.0
        return FocusConsistencyResult(latencies=latencies, mean_latency=mean, stdev_latency=0.0, coefficient_of_variation=None, focus_level_score=100.0)

    mean = statistics.mean(latencies)
    stdev = statistics.stdev(latencies)
    cv = round(stdev / mean, 3) if mean > 0 else None

    # Lower variation -> higher focus-level score. cv of 0 -> 100;
    # cv of 1.0 (stdev equal to the mean) or higher -> 0. Linear
    # between, same reasoned-not-calibrated discipline as every prior
    # scoring day.
    score = max(0.0, min(100.0, (1.0 - (cv or 0.0)) * 100.0))

    return FocusConsistencyResult(latencies=latencies, mean_latency=round(mean, 3), stdev_latency=round(stdev, 3), coefficient_of_variation=cv, focus_level_score=round(score, 1))


@dataclass
class DistractionSpikeResult:
    spike_question_ids: List[str]
    spike_count: int
    median_latency: float
    distraction_frequency_score: float   # 0-100, LOWER = more spikes (worse)


def assess_distraction_spikes(records: List[TimedResponseRecord]) -> DistractionSpikeResult:
    if len(records) < _MIN_RECORDS_FOR_SPIKE_DETECTION:
        median = statistics.median([r.latency_seconds for r in records]) if records else 0.0
        return DistractionSpikeResult(spike_question_ids=[], spike_count=0, median_latency=round(median, 3), distraction_frequency_score=100.0)

    latencies = [r.latency_seconds for r in records]
    median = statistics.median(latencies)
    threshold = median * _SPIKE_MULTIPLIER

    spikes = [r.question_id for r in records if median > 0 and r.latency_seconds > threshold]
    spike_rate = len(spikes) / len(records)
    score = round(max(0.0, 100.0 - spike_rate * 100.0), 1)

    return DistractionSpikeResult(spike_question_ids=spikes, spike_count=len(spikes), median_latency=round(median, 3), distraction_frequency_score=score)


# ---------------------------------------------------------------------------
# Verbal hesitation -- reused from Day 27, explicitly NOT a substitute
# for the brief's "nervous gestures" (a physical/visual signal)
# ---------------------------------------------------------------------------

@dataclass
class VerbalHesitationSummary:
    per_question: Dict[str, HesitationResult]
    average_hesitation_rate_per_100_words: float


def assess_verbal_hesitation(records: List[TimedResponseRecord]) -> VerbalHesitationSummary:
    per_question = {r.question_id: detect_hesitation(r.response_text) for r in records}
    rates = [h.hesitation_rate_per_100_words for h in per_question.values()]
    avg = round(sum(rates) / len(rates), 2) if rates else 0.0
    return VerbalHesitationSummary(per_question=per_question, average_hesitation_rate_per_100_words=avg)


# ---------------------------------------------------------------------------
# Combined, explainable behavioral insight report
# ---------------------------------------------------------------------------

@dataclass
class BehavioralInsightReport:
    focus: FocusConsistencyResult
    distraction: DistractionSpikeResult
    verbal_hesitation: VerbalHesitationSummary
    not_implemented: List[str] = field(default_factory=lambda: [
        "eye_movement_gaze_stability", "head_movement", "facial_engagement", "nervous_gestures_physical",
    ])

    def to_dict(self) -> Dict:
        return {
            "focus_level": {
                "score": self.focus.focus_level_score, "mean_latency_seconds": self.focus.mean_latency,
                "coefficient_of_variation": self.focus.coefficient_of_variation,
            },
            "distraction_frequency": {
                "score": self.distraction.distraction_frequency_score, "spike_count": self.distraction.spike_count,
                "spike_question_ids": self.distraction.spike_question_ids, "median_latency_seconds": self.distraction.median_latency,
            },
            "verbal_hesitation": {
                "average_rate_per_100_words": self.verbal_hesitation.average_hesitation_rate_per_100_words,
                "note": "Speech disfluency signal, reused from Day 27 -- NOT a substitute for physical nervous gestures, which this project cannot observe without a camera.",
            },
            "not_implemented": self.not_implemented,
        }

    def to_summary_text(self) -> str:
        lines = [
            "Behavioral Interaction Signal Report (non-invasive, timing + text only)",
            "=" * 60,
            f"Focus level (pacing consistency): {self.focus.focus_level_score}/100",
            f"Distraction frequency (latency spikes): {self.distraction.distraction_frequency_score}/100 "
            f"({self.distraction.spike_count} spike(s): {', '.join(self.distraction.spike_question_ids) or 'none'})",
            f"Verbal hesitation rate: {self.verbal_hesitation.average_hesitation_rate_per_100_words} per 100 words "
            "(speech disfluency, not a gesture signal)",
            "",
            "Not implemented (would require camera/computer-vision input this project does not have):",
        ]
        lines += [f"  - {item}" for item in self.not_implemented]
        return "\n".join(lines)


def build_behavioral_insight_report(tracker: TimedSessionTracker) -> BehavioralInsightReport:
    return BehavioralInsightReport(
        focus=assess_focus_consistency(tracker.records),
        distraction=assess_distraction_spikes(tracker.records),
        verbal_hesitation=assess_verbal_hesitation(tracker.records),
    )
