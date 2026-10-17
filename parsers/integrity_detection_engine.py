"""
Malpractice & Integrity Detection Design (Day 49)

WHAT THIS DAY BUILDS, AND WHAT IT DELIBERATELY DOES NOT:
the brief lists four malpractice signals -- tab-switching frequency,
loss of screen focus, external voice detection, repeated looking away.
They are not the same kind of signal:

    Brief's signal            Status            Why
    ------------------------  ----------------  -----------------------------------
    Tab switching frequency   IMPLEMENTED       Browser visibility events (a client
                                                reports "tab hidden / visible").
    Loss of screen focus      IMPLEMENTED       Browser window blur / focus events.
    External voice detection  NOT IMPLEMENTED   Needs audio analysis. No audio
                                                pipeline exists in this project, and
                                                it would also capture bystanders'
                                                voices (a third-party privacy issue).
    Repeated looking away     NOT IMPLEMENTED   Needs camera / computer vision --
                                                the same line Day 48 already
                                                refused to cross, for the same
                                                reasons (biometric data, no consent
                                                infrastructure, no fairness review).

Building detectors with those last two names that process no audio or
image data would fabricate a capability, so they are listed as "not
implemented" in EVERY report (same discipline as Day 48's four camera
signals), with the reason attached. Secondary-device / mobile-phone
usage, which the PRD (Phases 19 and 42) also mentions, is likewise not
observable from browser events and is listed the same way.

DESIGN RULES THE ENGINE ENFORCES:
  1. Output is an integrity RISK TAG plus the reasons behind it -- never
     a "cheating" verdict. MEDIUM/HIGH mean "a human should review",
     nothing more.
  2. `automated_action` is always "none" and `scoring_impact` is always
     "none". The engine never rejects, terminates, or re-scores anyone.
  3. Day 48 behavioral signals (latency spikes) can only CORROBORATE a
     browser-event finding. A slow or hesitant answer with no browser
     event never raises risk by itself -- slowness is not malpractice.
  4. Very short focus losses (< 1.5 s) are ignored but still counted and
     reported, because OS notifications and pop-ups steal focus too.
  5. Every threshold is reasoned, not calibrated -- no labelled
     malpractice data exists in this project. Same caveat as every
     scoring day since Day 34.

INPUT CONTRACT:
  events   -- BrowserEvent(event_type, timestamp_seconds_since_session_start)
  windows  -- optional QuestionWindow list, or timed records from Day 48
              (TimedResponseRecord) from which windows are rebuilt
  session_end -- optional seconds-since-start at which the session ended
OUTPUT CONTRACT:
  IntegrityReport (see class) -- signals, flags, risk tag, alerts,
  explicit not-implemented list, caveats; .to_dict() / .to_summary_text().

Real-time alerts are provided by IntegrityMonitor, which consumes events
one at a time and returns an IntegrityAlert immediately when a
threshold is crossed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence

from parsers.behavioral_signal_engine import TimedResponseRecord, assess_distraction_spikes

# ---------------------------------------------------------------------------
# Tunable thresholds -- reasoned, NOT calibrated against labelled data
# ---------------------------------------------------------------------------

MIN_AWAY_SECONDS = 1.5            # shorter focus losses are treated as OS pop-ups/notifications
LONG_ABSENCE_SECONDS = 30.0       # a single absence this long is notable on its own
MEDIUM_ABSENCE_SECONDS = 10.0
BURST_WINDOW_SECONDS = 60.0       # N away-events inside this window is a "burst"
BURST_MIN_COUNT = 3
LOOKUP_ONSET_SECONDS = 5.0        # left within this long of a question appearing...
LOOKUP_RETURN_BEFORE_SUBMIT_SECONDS = 10.0   # ...and came back this close to answering
LOOKUP_MIN_AWAY_SECONDS = 3.0
LOOKUP_MIN_QUESTIONS = 2          # one occurrence is coincidence; two is a pattern
AWAY_FRACTION_MEDIUM = 0.05       # share of session spent away
AWAY_FRACTION_HIGH = 0.15

ALERT_NOTICE_AT = 1               # Nth counted away-event -> candidate-visible notice
ALERT_WARNING_AT = 2              # -> candidate-visible warning (through FLAG_AT - 1)
ALERT_FLAG_AT = 4                 # -> internal review flag (not shown to the candidate)

RISK_LOW_MIN = 1
RISK_MEDIUM_MIN = 3
RISK_HIGH_MIN = 6

NOTICE_MESSAGE = (
    "We noticed this interview window lost focus. "
    "Please keep this window in the foreground for the rest of the interview."
)
WARNING_MESSAGE = (
    "Reminder: leaving the interview window may be recorded and reviewed by the hiring team. "
    "Please stay on this window until the interview is finished."
)


# ---------------------------------------------------------------------------
# Events and derived intervals
# ---------------------------------------------------------------------------

class BrowserEventType(str, Enum):
    """Client-reported browser events (no camera, no microphone, no biometrics)."""
    TAB_HIDDEN = "tab_hidden"        # document visibilitychange -> hidden
    TAB_VISIBLE = "tab_visible"      # document visibilitychange -> visible
    WINDOW_BLUR = "window_blur"      # window lost focus (e.g. alt-tab to another app)
    WINDOW_FOCUS = "window_focus"    # window regained focus


class AwayCause(str, Enum):
    TAB_SWITCH = "tab_switch"        # the tab was actually hidden
    WINDOW_BLUR = "window_blur"      # focus lost, tab still visible (e.g. second monitor)


@dataclass
class BrowserEvent:
    """One client-reported event; timestamp is seconds since session start."""
    event_type: BrowserEventType
    timestamp: float

    def __post_init__(self) -> None:
        if self.timestamp < 0:
            raise ValueError("Event timestamp must be >= 0 (seconds since session start).")


@dataclass
class QuestionWindow:
    """The span of session time during which one question was on screen."""
    question_id: str
    start: float
    end: float


@dataclass
class AwayInterval:
    start: float
    end: float
    cause: AwayCause
    unclosed: bool = False                 # still away when the session ended / was polled
    question_id: Optional[str] = None

    @property
    def duration(self) -> float:
        return round(max(0.0, self.end - self.start), 3)


def windows_from_records(records: Sequence[TimedResponseRecord]) -> List[QuestionWindow]:
    """Rebuild question windows from Day 48 timed records.

    Day 48's tracker presents each question the instant the previous one is
    submitted, so cumulative latency IS the question timeline -- no change
    to the tracker or the session classes is needed."""
    windows: List[QuestionWindow] = []
    clock = 0.0
    for rec in records:
        windows.append(QuestionWindow(rec.question_id, round(clock, 3), round(clock + rec.latency_seconds, 3)))
        clock += rec.latency_seconds
    return windows


def _question_at(t: float, windows: Sequence[QuestionWindow]) -> Optional[str]:
    for idx, w in enumerate(windows):
        last = idx == len(windows) - 1
        if w.start <= t < w.end or (last and t == w.end):
            return w.question_id
    return None


def build_away_intervals(
    events: Sequence[BrowserEvent],
    session_end: Optional[float] = None,
    windows: Optional[Sequence[QuestionWindow]] = None,
) -> List[AwayInterval]:
    """Pair raw events into away-intervals.

    A browser fires both a hidden AND a blur event when the tab changes, so
    the two are tracked as independent states and merged: the candidate is
    "away" while EITHER is active, and the interval closes only when BOTH
    have cleared. Duplicate or orphan 'visible'/'focus' events are harmless."""
    ordered = sorted(events, key=lambda e: e.timestamp)
    if session_end is not None:
        ordered = [e for e in ordered if e.timestamp <= session_end]

    hidden = blurred = False
    start: Optional[float] = None
    saw_hidden = False
    intervals: List[AwayInterval] = []

    for ev in ordered:
        was_away = hidden or blurred
        if ev.event_type is BrowserEventType.TAB_HIDDEN:
            hidden = True
        elif ev.event_type is BrowserEventType.TAB_VISIBLE:
            hidden = False
        elif ev.event_type is BrowserEventType.WINDOW_BLUR:
            blurred = True
        elif ev.event_type is BrowserEventType.WINDOW_FOCUS:
            blurred = False
        now_away = hidden or blurred

        if not was_away and now_away:
            start, saw_hidden = ev.timestamp, hidden
        elif was_away and now_away:
            saw_hidden = saw_hidden or hidden
        elif was_away and not now_away and start is not None:
            cause = AwayCause.TAB_SWITCH if saw_hidden else AwayCause.WINDOW_BLUR
            intervals.append(AwayInterval(start, ev.timestamp, cause))
            start, saw_hidden = None, False

    if (hidden or blurred) and start is not None:
        end = session_end if session_end is not None else ordered[-1].timestamp
        cause = AwayCause.TAB_SWITCH if saw_hidden else AwayCause.WINDOW_BLUR
        intervals.append(AwayInterval(start, max(end, start), cause, unclosed=True))

    if windows:
        for iv in intervals:
            iv.question_id = _question_at(iv.start, windows)
    return intervals


# ---------------------------------------------------------------------------
# Signals (the brief's "malpractice signals", the two that are observable)
# ---------------------------------------------------------------------------

@dataclass
class IntegritySignals:
    away_event_count: int                 # counted intervals (>= MIN_AWAY_SECONDS)
    tab_switch_count: int                 # ...of which the tab was actually hidden
    window_blur_count: int                # ...of which focus was lost with the tab visible
    ignored_blips: int                    # sub-threshold focus losses, reported for transparency
    total_away_seconds: float
    longest_away_seconds: float
    session_duration_seconds: Optional[float]
    away_fraction: Optional[float]        # None when the session length is unknown
    away_events_per_question: Dict[str, int]


def compute_signals(
    intervals: Sequence[AwayInterval], session_duration: Optional[float] = None
) -> IntegritySignals:
    counted = [i for i in intervals if i.duration >= MIN_AWAY_SECONDS]
    blips = len(intervals) - len(counted)
    total = round(sum(i.duration for i in counted), 3)
    longest = max((i.duration for i in counted), default=0.0)
    fraction = round(total / session_duration, 3) if session_duration and session_duration > 0 else None

    per_q: Dict[str, int] = {}
    for i in counted:
        if i.question_id:
            per_q[i.question_id] = per_q.get(i.question_id, 0) + 1

    return IntegritySignals(
        away_event_count=len(counted),
        tab_switch_count=sum(1 for i in counted if i.cause is AwayCause.TAB_SWITCH),
        window_blur_count=sum(1 for i in counted if i.cause is AwayCause.WINDOW_BLUR),
        ignored_blips=blips,
        total_away_seconds=total,
        longest_away_seconds=round(longest, 3),
        session_duration_seconds=session_duration,
        away_fraction=fraction,
        away_events_per_question=per_q,
    )


# ---------------------------------------------------------------------------
# Detection logic: threshold flags, pattern recognition, corroboration
# ---------------------------------------------------------------------------

@dataclass
class IntegrityFlag:
    code: str
    category: str          # "threshold" | "pattern" | "corroboration"
    points: int            # contribution to the risk tag
    explanation: str
    evidence: Dict

    def to_dict(self) -> Dict:
        return {"code": self.code, "category": self.category, "points": self.points,
                "explanation": self.explanation, "evidence": self.evidence}


def evaluate_threshold_flags(signals: IntegritySignals) -> List[IntegrityFlag]:
    """Threshold-based flags: simple, explainable cut-offs on the counted signals."""
    flags: List[IntegrityFlag] = []

    c = signals.away_event_count
    if c >= 2:
        pts = 3 if c >= 6 else 2 if c >= 4 else 1
        flags.append(IntegrityFlag(
            "FREQUENT_FOCUS_LOSS", "threshold", pts,
            f"The interview window lost focus {c} times "
            f"({signals.tab_switch_count} tab switch(es), {signals.window_blur_count} window-focus loss(es)).",
            {"away_event_count": c, "tab_switch_count": signals.tab_switch_count,
             "window_blur_count": signals.window_blur_count},
        ))

    if signals.away_fraction is not None and signals.away_fraction >= AWAY_FRACTION_MEDIUM:
        pts = 2 if signals.away_fraction >= AWAY_FRACTION_HIGH else 1
        flags.append(IntegrityFlag(
            "SIGNIFICANT_AWAY_TIME", "threshold", pts,
            f"The candidate was away from the interview window for {signals.away_fraction:.0%} of the session.",
            {"total_away_seconds": signals.total_away_seconds, "away_fraction": signals.away_fraction},
        ))

    if signals.longest_away_seconds >= MEDIUM_ABSENCE_SECONDS:
        pts = 2 if signals.longest_away_seconds >= LONG_ABSENCE_SECONDS else 1
        flags.append(IntegrityFlag(
            "LONG_SINGLE_ABSENCE", "threshold", pts,
            f"One absence from the interview window lasted {signals.longest_away_seconds:.0f}s.",
            {"longest_away_seconds": signals.longest_away_seconds},
        ))
    return flags


def detect_burst_pattern(intervals: Sequence[AwayInterval]) -> Optional[IntegrityFlag]:
    """Pattern: several away-events packed into a short window."""
    starts = sorted(i.start for i in intervals if i.duration >= MIN_AWAY_SECONDS)
    for a in range(len(starts)):
        in_window = [s for s in starts[a:] if s - starts[a] <= BURST_WINDOW_SECONDS]
        if len(in_window) >= BURST_MIN_COUNT:
            return IntegrityFlag(
                "BURST_SWITCHING", "pattern", 2,
                f"{len(in_window)} focus losses occurred within {BURST_WINDOW_SECONDS:.0f} seconds.",
                {"burst_start_times": [round(s, 1) for s in in_window]},
            )
    return None


def detect_lookup_pattern(
    intervals: Sequence[AwayInterval], windows: Sequence[QuestionWindow]
) -> Optional[IntegrityFlag]:
    """Pattern: leave right after a question appears, return right before answering.

    That leave-early / return-late shape across two or more different
    questions is what looking something up between 'question shown' and
    'answer given' looks like. One occurrence is not enough -- everyone
    sometimes checks a message once."""
    matched: List[str] = []
    for w in windows:
        for i in intervals:
            if i.duration < LOOKUP_MIN_AWAY_SECONDS:
                continue
            left_early = 0.0 <= i.start - w.start <= LOOKUP_ONSET_SECONDS
            returned_late = (w.end - LOOKUP_RETURN_BEFORE_SUBMIT_SECONDS) <= i.end <= (w.end + 0.5)
            if left_early and returned_late:
                matched.append(w.question_id)
                break
    if len(matched) >= LOOKUP_MIN_QUESTIONS:
        return IntegrityFlag(
            "QUESTION_LOOKUP_PATTERN", "pattern", 3,
            f"On {len(matched)} questions the candidate left the window right after the question "
            "appeared and returned just before answering.",
            {"question_ids": matched},
        )
    return None


def corroborate_with_behavior(
    intervals: Sequence[AwayInterval], records: Sequence[TimedResponseRecord]
) -> Optional[IntegrityFlag]:
    """Integration with Day 48: a latency spike on a question where a focus
    loss ALSO occurred. Spikes alone never reach this function's output --
    it only ever strengthens an existing browser-event finding."""
    spikes = set(assess_distraction_spikes(list(records)).spike_question_ids)
    away_q = {i.question_id for i in intervals if i.duration >= MIN_AWAY_SECONDS and i.question_id}
    both = sorted(spikes & away_q)
    if not both:
        return None
    return IntegrityFlag(
        "LATENCY_CORROBORATION", "corroboration", min(len(both), 2),
        f"Unusually long response time coincided with a focus loss on {len(both)} question(s).",
        {"question_ids": both},
    )


# ---------------------------------------------------------------------------
# Risk tagging
# ---------------------------------------------------------------------------

class IntegrityRiskTag(str, Enum):
    CLEAR = "clear"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


RISK_MEANING = {
    IntegrityRiskTag.CLEAR: "No integrity indicators observed in the signals this system can see (not proof none exist).",
    IntegrityRiskTag.LOW: "Minor indicators, consistent with ordinary distraction. No action suggested.",
    IntegrityRiskTag.MEDIUM: "Review recommended: a recruiter should look at the evidence before relying on this interview.",
    IntegrityRiskTag.HIGH: "Human review required before any decision relies on this interview.",
}


def compute_risk_tag(flags: Sequence[IntegrityFlag]) -> tuple:
    """Sum flag points into a tag. Returns (tag, points)."""
    points = sum(f.points for f in flags)
    if points >= RISK_HIGH_MIN:
        tag = IntegrityRiskTag.HIGH
    elif points >= RISK_MEDIUM_MIN:
        tag = IntegrityRiskTag.MEDIUM
    elif points >= RISK_LOW_MIN:
        tag = IntegrityRiskTag.LOW
    else:
        tag = IntegrityRiskTag.CLEAR
    return tag, points


# ---------------------------------------------------------------------------
# Real-time warnings
# ---------------------------------------------------------------------------

class AlertLevel(str, Enum):
    NOTICE = "notice"      # candidate-visible, gentle
    WARNING = "warning"    # candidate-visible, firmer
    FLAG = "flag"          # internal only -- never shown to the candidate


@dataclass
class IntegrityAlert:
    level: AlertLevel
    trigger: str                          # "away_event_count" | "long_absence"
    timestamp: float
    candidate_message: Optional[str]      # None for internal-only alerts
    internal_note: str
    away_event_count: int

    def to_dict(self) -> Dict:
        return {"level": self.level.value, "trigger": self.trigger, "timestamp": self.timestamp,
                "candidate_message": self.candidate_message, "internal_note": self.internal_note,
                "away_event_count": self.away_event_count}


class IntegrityMonitor:
    """Stateful, real-time front end: feed it events as they arrive and it
    returns an alert the moment a threshold is crossed.

    Escalation ladder (counted away-events, i.e. >= MIN_AWAY_SECONDS):
        1st            -> NOTICE   (candidate sees a gentle reminder)
        2nd .. 3rd     -> WARNING  (candidate sees a firmer reminder)
        4th            -> FLAG     (internal review flag; the candidate is not
                                    accused mid-interview)
    The interview is never terminated or paused by the monitor."""

    def __init__(self, windows: Optional[Sequence[QuestionWindow]] = None) -> None:
        self.windows: List[QuestionWindow] = list(windows or [])
        self.events: List[BrowserEvent] = []
        self.alerts: List[IntegrityAlert] = []
        self._processed_count = 0
        self._long_absence_alerted_at: set = set()

    def record_event(self, event: BrowserEvent) -> Optional[IntegrityAlert]:
        """Ingest one event; return an alert if this event completed a counted away-interval that crosses a threshold."""
        self.events.append(event)
        closed = [
            i for i in build_away_intervals(self.events)
            if not i.unclosed and i.duration >= MIN_AWAY_SECONDS
        ]
        n = len(closed)
        if n <= self._processed_count:
            return None
        self._processed_count = n

        if n >= ALERT_FLAG_AT:
            if any(a.level is AlertLevel.FLAG for a in self.alerts):
                return None
            alert = IntegrityAlert(
                AlertLevel.FLAG, "away_event_count", event.timestamp, None,
                f"Integrity review flag: {n} focus losses so far. Tagged for human review; no automated action taken.",
                n,
            )
        elif n >= ALERT_WARNING_AT:
            alert = IntegrityAlert(
                AlertLevel.WARNING, "away_event_count", event.timestamp, WARNING_MESSAGE,
                f"Warning shown to candidate after focus loss #{n}.", n,
            )
        else:
            alert = IntegrityAlert(
                AlertLevel.NOTICE, "away_event_count", event.timestamp, NOTICE_MESSAGE,
                f"Notice shown to candidate after focus loss #{n}.", n,
            )
        self.alerts.append(alert)
        return alert

    def poll(self, now: float) -> Optional[IntegrityAlert]:
        """Call periodically: raises a one-time warning if the candidate is STILL away past LONG_ABSENCE_SECONDS."""
        for iv in build_away_intervals(self.events, session_end=now):
            if iv.unclosed and iv.duration >= LONG_ABSENCE_SECONDS and iv.start not in self._long_absence_alerted_at:
                self._long_absence_alerted_at.add(iv.start)
                alert = IntegrityAlert(
                    AlertLevel.WARNING, "long_absence", now, WARNING_MESSAGE,
                    f"Candidate has been away from the interview window for {iv.duration:.0f}s and has not returned.",
                    self._processed_count,
                )
                self.alerts.append(alert)
                return alert
        return None

    def finalize(
        self, session_end: Optional[float] = None, records: Optional[Sequence[TimedResponseRecord]] = None
    ) -> "IntegrityReport":
        """Close out the session and build the final report (alerts included)."""
        return build_integrity_report(
            self.events, session_end=session_end, windows=self.windows or None,
            records=records, alerts=list(self.alerts),
        )


# ---------------------------------------------------------------------------
# Final, explainable report
# ---------------------------------------------------------------------------

NOT_IMPLEMENTED: Dict[str, str] = {
    "external_voice_detection": "Requires audio analysis; no audio pipeline exists, and it would also capture bystanders' voices.",
    "repeated_looking_away": "Requires camera / computer vision; same biometric, consent and fairness blockers as Day 48's camera signals.",
    "secondary_device_or_mobile_usage": "Not observable from browser events; a second device is invisible to this system.",
}

CAVEATS: List[str] = [
    "Focus loss is not proof of cheating: notifications, OS dialogs, assistive technology, second monitors, "
    "and browser or network problems can all cause it.",
    "Browser events can be blocked or spoofed, and a second device is invisible here: a CLEAR tag is not an integrity guarantee.",
    "Thresholds are reasoned, not calibrated -- no labelled malpractice data exists in this project.",
    "Candidates must be told monitoring is active before the interview starts; consent capture does not exist yet (Day 43 finding).",
    "This tag must be reviewed by a person and must not be used as an automatic rejection or score adjustment.",
]


@dataclass
class IntegrityReport:
    signals: IntegritySignals
    flags: List[IntegrityFlag]
    risk_tag: IntegrityRiskTag
    risk_points: int
    alerts: List[IntegrityAlert] = field(default_factory=list)
    not_implemented: Dict[str, str] = field(default_factory=lambda: dict(NOT_IMPLEMENTED))
    caveats: List[str] = field(default_factory=lambda: list(CAVEATS))
    automated_action: str = "none"      # never anything else -- see module docstring rule 2
    scoring_impact: str = "none"

    @property
    def human_review_required(self) -> bool:
        return self.risk_tag in (IntegrityRiskTag.MEDIUM, IntegrityRiskTag.HIGH)

    def to_dict(self) -> Dict:
        s = self.signals
        return {
            "risk_tag": self.risk_tag.value,
            "risk_points": self.risk_points,
            "risk_meaning": RISK_MEANING[self.risk_tag],
            "human_review_required": self.human_review_required,
            "automated_action": self.automated_action,
            "scoring_impact": self.scoring_impact,
            "signals": {
                "away_event_count": s.away_event_count, "tab_switch_count": s.tab_switch_count,
                "window_blur_count": s.window_blur_count, "ignored_blips": s.ignored_blips,
                "total_away_seconds": s.total_away_seconds, "longest_away_seconds": s.longest_away_seconds,
                "session_duration_seconds": s.session_duration_seconds, "away_fraction": s.away_fraction,
                "away_events_per_question": s.away_events_per_question,
            },
            "flags": [f.to_dict() for f in self.flags],
            "alerts": [a.to_dict() for a in self.alerts],
            "not_implemented": self.not_implemented,
            "caveats": self.caveats,
        }

    def to_summary_text(self) -> str:
        s = self.signals
        lines = [
            "Interview Integrity Report (browser events only -- no camera, no audio)",
            "=" * 66,
            f"Risk tag: {self.risk_tag.value.upper()} ({self.risk_points} point(s))",
            f"  {RISK_MEANING[self.risk_tag]}",
            f"Focus losses counted: {s.away_event_count} "
            f"({s.tab_switch_count} tab switch, {s.window_blur_count} window blur; "
            f"{s.ignored_blips} sub-{MIN_AWAY_SECONDS}s blip(s) ignored)",
            f"Time away: {s.total_away_seconds}s, longest single absence {s.longest_away_seconds}s",
            "Flags:",
        ]
        lines += [f"  - [{f.category}] {f.code} (+{f.points}): {f.explanation}" for f in self.flags] or ["  - none"]
        lines += ["Automated action: none. Score impact: none. Human review required: "
                  f"{'YES' if self.human_review_required else 'no'}.", "",
                  "Not implemented (cannot be observed by this system):"]
        lines += [f"  - {k}: {v}" for k, v in self.not_implemented.items()]
        return "\n".join(lines)


def build_integrity_report(
    events: Sequence[BrowserEvent],
    session_end: Optional[float] = None,
    windows: Optional[Sequence[QuestionWindow]] = None,
    records: Optional[Sequence[TimedResponseRecord]] = None,
    alerts: Optional[Sequence[IntegrityAlert]] = None,
) -> IntegrityReport:
    """Run the full detection pipeline over a session's browser events.

    `records` (Day 48's TimedSessionTracker.records) is optional: when
    given it supplies the question windows and enables corroboration."""
    if windows is None and records:
        windows = windows_from_records(records)
    windows = list(windows or [])

    effective_end = session_end if session_end is not None else (windows[-1].end if windows else None)
    intervals = build_away_intervals(events, session_end=effective_end, windows=windows)
    signals = compute_signals(intervals, session_duration=effective_end)

    flags = evaluate_threshold_flags(signals)
    for pattern in (detect_burst_pattern(intervals), detect_lookup_pattern(intervals, windows)):
        if pattern:
            flags.append(pattern)
    if records and signals.away_event_count > 0:
        corr = corroborate_with_behavior(intervals, records)
        if corr:
            flags.append(corr)

    tag, points = compute_risk_tag(flags)
    return IntegrityReport(signals=signals, flags=flags, risk_tag=tag, risk_points=points, alerts=list(alerts or []))
