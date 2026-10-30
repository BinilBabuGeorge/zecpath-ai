"""
Data Governance: Retention Policy + Consent-Based Data Usage (Day 55)

WHAT THIS DAY BUILDS (part 2 of 4). Day 43's compliance report marked two
areas "NOT READY" with no code at all: DATA RETENTION and CONSENT. This module
closes the *logic* half of both. It does not delete anything and it does not
show a consent screen -- there is no storage layer or intake UI in this
project to attach to (see the storage plan). What exists now is a tested,
configurable decision engine that those layers can call.

RETENTION. A `RetentionPolicy` maps each data category to: when its clock
starts (the trigger), how long it may be kept, and what happens at expiry
(DELETE or ANONYMISE). `due_actions()` is a PURE function: give it a list of
`StoredRecord`s and a clock, get back the actions that are due. Rules:
  * Clock not started (no final decision yet) -> no action, reported as
    "awaiting trigger" -- never guessed.
  * Legal hold -> skipped and reported, never silently dropped.
  * Withdrawn consent -> immediate action, regardless of the clock.
  * The audit log must outlive every personal-data category (validated),
    because it is the evidence of what was done to that data.
The periods below are DEFAULTS CHOSEN FOR THIS PROJECT, not legal advice. A
real deployment needs counsel to set them per jurisdiction (GDPR-style storage
limitation, Indian DPDP Act, local labour law). That is why they are config.

CONSENT. Default-deny. One record per (candidate, purpose); purposes are never
bundled (screening consent does not imply recording or voice-cloning consent).
Latest record wins; history is kept, never overwritten. Consent is tied to the
notice version the candidate saw: if the notice text changes materially,
`required_notice_version` makes older consents stale. Two honest caveats built
into behaviour: (1) in hiring, consent can fail the "freely given" test because
the candidate may fear a refusal costs them the job -- so a refusal for the AI
interview returns `fallback="human_process"`, and the caller MUST offer it;
(2) consent is one lawful basis among several, not the only one.

PSEUDONYMISATION. `pseudonymise()` derives a stable candidate_ref with keyed
HMAC-SHA256. Logs and analytics use the ref; the ref -> identity table lives
in a separate, access-controlled store. Destroying that mapping (or the key)
unlinks the logs from the person without editing the audit chain.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple

from utils.logger import get_logger

logger = get_logger(__name__)


# ----------------------------------------------------------------- pseudonyms
def pseudonymise(candidate_id: str, key: bytes, length: int = 20) -> str:
    """Stable keyed pseudonym ('cref_...'). Without the key it cannot be recomputed from an id."""
    if not candidate_id:
        raise ValueError("candidate_id is required")
    if not key or len(key) < 16:
        raise ValueError("pseudonymisation key must be at least 16 bytes")
    return "cref_" + hmac.new(key, candidate_id.encode("utf-8"), hashlib.sha256).hexdigest()[:length]


def _utc(ts: datetime) -> datetime:
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)


# ------------------------------------------------------------------ retention
class DataCategory(str, Enum):
    RESUME = "resume"
    TRANSCRIPT = "transcript"
    RECORDING = "recording"
    SCORES = "scores"
    REPORT = "report"
    AUDIT_LOG = "audit_log"
    CONSENT_RECORD = "consent_record"


class Trigger(str, Enum):
    COLLECTION = "collection"
    FINAL_DECISION = "final_decision"
    NONE = "none"                      # no expiry clock (kept under its own rule)


class RetentionAction(str, Enum):
    DELETE = "delete"
    ANONYMISE = "anonymise"
    REVIEW = "review"


@dataclass(frozen=True)
class RetentionRule:
    category: DataCategory
    trigger: Trigger
    days: Optional[int]
    action: RetentionAction
    rationale: str


DEFAULT_RULES: Tuple[RetentionRule, ...] = (
    RetentionRule(DataCategory.RECORDING, Trigger.FINAL_DECISION, 30, RetentionAction.DELETE,
                  "Most sensitive (face, voice); only needed for dispute/review window."),
    RetentionRule(DataCategory.TRANSCRIPT, Trigger.FINAL_DECISION, 90, RetentionAction.DELETE,
                  "Needed to explain a decision if challenged; free text can hold special-category data."),
    RetentionRule(DataCategory.RESUME, Trigger.FINAL_DECISION, 180, RetentionAction.DELETE,
                  "Short window after the hiring process; longer only with talent-pool consent."),
    RetentionRule(DataCategory.REPORT, Trigger.FINAL_DECISION, 180, RetentionAction.DELETE,
                  "Contains derived judgements about a person; keep no longer than the inputs."),
    RetentionRule(DataCategory.SCORES, Trigger.FINAL_DECISION, 365, RetentionAction.ANONYMISE,
                  "Aggregate statistics for fairness monitoring survive once unlinked from the person."),
    RetentionRule(DataCategory.CONSENT_RECORD, Trigger.FINAL_DECISION, 730, RetentionAction.DELETE,
                  "Proof that consent existed must outlive the data it covered."),
    RetentionRule(DataCategory.AUDIT_LOG, Trigger.COLLECTION, 1095, RetentionAction.REVIEW,
                  "Evidence log: holds only scores/refs; must outlive every personal-data category."),
)

# Which consent purpose each category depends on (withdrawal -> immediate action).
PURPOSE_CATEGORIES: Dict[str, Tuple[DataCategory, ...]] = {
    "ai_interview_recording": (DataCategory.RECORDING, DataCategory.TRANSCRIPT),
    "voice_cloning": (DataCategory.RECORDING,),
    "talent_pool": (DataCategory.RESUME,),
}


@dataclass
class StoredRecord:
    record_id: str
    category: DataCategory
    candidate_ref: str
    trigger_date: Optional[datetime] = None     # None = trigger event has not happened yet
    legal_hold: bool = False


@dataclass(frozen=True)
class DueAction:
    record_id: str
    category: DataCategory
    action: RetentionAction
    reason: str
    expired_on: Optional[datetime] = None


@dataclass
class RetentionReport:
    due: List[DueAction] = field(default_factory=list)
    skipped_legal_hold: List[str] = field(default_factory=list)
    awaiting_trigger: List[str] = field(default_factory=list)
    not_yet_due: int = 0


class RetentionPolicy:
    def __init__(self, rules: Optional[Tuple[RetentionRule, ...]] = None, version: str = "1.0-default") -> None:
        self.version = version
        self.rules: Dict[DataCategory, RetentionRule] = {r.category: r for r in (rules or DEFAULT_RULES)}

    def validate(self) -> List[str]:
        """Problems with the policy itself (empty list = coherent)."""
        problems: List[str] = []
        for cat in DataCategory:
            if cat not in self.rules:
                problems.append(f"no retention rule for {cat.value}")
        for r in self.rules.values():
            if r.trigger != Trigger.NONE and (r.days is None or r.days <= 0):
                problems.append(f"{r.category.value}: days must be a positive integer")
        audit = self.rules.get(DataCategory.AUDIT_LOG)
        if audit and audit.days:
            longest = max((r.days or 0) for c, r in self.rules.items() if c != DataCategory.AUDIT_LOG)
            if audit.days < longest:
                problems.append(f"audit log retention ({audit.days}d) is shorter than the longest personal-data rule ({longest}d)")
        return problems

    def due_actions(self, records: List[StoredRecord], now: datetime) -> RetentionReport:
        now = _utc(now)
        rep = RetentionReport()
        for rec in records:
            rule = self.rules.get(rec.category)
            if rule is None or rule.trigger == Trigger.NONE:
                rep.not_yet_due += 1
                continue
            if rec.legal_hold:
                rep.skipped_legal_hold.append(rec.record_id)
                continue
            if rec.trigger_date is None:
                rep.awaiting_trigger.append(rec.record_id)
                continue
            expiry = _utc(rec.trigger_date) + timedelta(days=rule.days or 0)
            if now >= expiry:
                rep.due.append(DueAction(rec.record_id, rec.category, rule.action,
                                         f"{rule.days}d after {rule.trigger.value} elapsed", expiry))
            else:
                rep.not_yet_due += 1
        return rep


# -------------------------------------------------------------------- consent
class Purpose(str, Enum):
    AI_SCREENING = "ai_screening"
    AI_INTERVIEW_RECORDING = "ai_interview_recording"
    VOICE_CLONING = "voice_cloning"
    TALENT_POOL = "talent_pool"
    MODEL_IMPROVEMENT = "model_improvement"


class ConsentError(PermissionError):
    pass


@dataclass(frozen=True)
class ConsentRecord:
    candidate_ref: str
    purpose: Purpose
    granted: bool
    notice_version: str
    at: datetime
    method: str = "explicit_opt_in"


@dataclass(frozen=True)
class ConsentDecision:
    allowed: bool
    reason: str
    fallback: Optional[str] = None      # "human_process" when AI-processing consent is absent


# Purposes whose refusal must leave the candidate a non-AI route.
_FALLBACK_PURPOSES = {Purpose.AI_SCREENING, Purpose.AI_INTERVIEW_RECORDING}


class ConsentRegistry:
    def __init__(self, required_notice_version: str = "1.0") -> None:
        self.required_notice_version = required_notice_version
        self._history: Dict[Tuple[str, Purpose], List[ConsentRecord]] = {}

    def _add(self, rec: ConsentRecord) -> ConsentRecord:
        h = self._history.setdefault((rec.candidate_ref, rec.purpose), [])
        if h and _utc(rec.at) < _utc(h[-1].at):
            raise ValueError("consent events must be recorded in time order")
        h.append(rec)
        return rec

    def grant(self, candidate_ref: str, purpose: Purpose, notice_version: str, at: datetime,
              method: str = "explicit_opt_in") -> ConsentRecord:
        if method not in {"explicit_opt_in", "signed_form"}:
            raise ValueError("consent must be an explicit act; pre-ticked or implied methods are not accepted")
        return self._add(ConsentRecord(candidate_ref, purpose, True, notice_version, _utc(at), method))

    def withdraw(self, candidate_ref: str, purpose: Purpose, at: datetime) -> ConsentRecord:
        prior = self._history.get((candidate_ref, purpose))
        notice = prior[-1].notice_version if prior else self.required_notice_version
        return self._add(ConsentRecord(candidate_ref, purpose, False, notice, _utc(at), "withdrawal"))

    def history(self, candidate_ref: str, purpose: Purpose) -> List[ConsentRecord]:
        return list(self._history.get((candidate_ref, purpose), []))

    def check(self, candidate_ref: str, purpose: Purpose, at: Optional[datetime] = None) -> ConsentDecision:
        fb = "human_process" if purpose in _FALLBACK_PURPOSES else None
        h = self._history.get((candidate_ref, purpose))
        if not h:
            return ConsentDecision(False, "no consent on record (default deny)", fb)
        ts = _utc(at) if at else None
        relevant = [r for r in h if ts is None or _utc(r.at) <= ts]
        if not relevant:
            return ConsentDecision(False, "no consent on record at that time", fb)
        last = relevant[-1]
        if not last.granted:
            return ConsentDecision(False, "consent withdrawn", fb)
        if last.notice_version != self.required_notice_version:
            return ConsentDecision(False, f"consent given under notice {last.notice_version}; {self.required_notice_version} requires re-consent", fb)
        return ConsentDecision(True, "valid consent on record")

    def require(self, candidate_ref: str, purpose: Purpose, at: Optional[datetime] = None) -> None:
        d = self.check(candidate_ref, purpose, at)
        if not d.allowed:
            raise ConsentError(f"{purpose.value}: {d.reason}")


def actions_for_withdrawal(candidate_ref: str, purpose: Purpose, records: List[StoredRecord]) -> List[DueAction]:
    """Immediate DELETE actions for data that depended on the withdrawn purpose. Withdrawal beats the retention clock
    (but not a legal hold, which is reported by the caller)."""
    cats = PURPOSE_CATEGORIES.get(purpose.value, ())
    return [DueAction(r.record_id, r.category, RetentionAction.DELETE, f"consent for {purpose.value} withdrawn")
            for r in records if r.candidate_ref == candidate_ref and r.category in cats and not r.legal_hold]
