"""
Audit Trail System (Day 55)

WHAT THIS DAY BUILDS (part 1 of 4): the audit trail the brief asks for --
SCORE LOGS and DECISION LOGS -- as an append-only, hash-chained record.
Day 43 found that nothing in the codebase could later answer "which score
did this candidate get, from which model version, and who confirmed the
outcome?". This module is that record.

Input contract : scores / decisions / access events as plain values, or the
                 Day 51 `CrossRoundCandidateScore`, Day 52 `CandidateDecision`
                 and `FinalizedDecision` objects (read by attribute; this
                 module does not import them, so it has no heavy dependencies).
Output contract: `AuditEntry` rows chained by SHA-256, `VerificationResult`
                 from `AuditLog.verify()`, JSONL export / re-load.

WHAT A LOG ENTRY MAY CONTAIN -- AND WHY IT IS ENFORCED IN CODE:
the audit log has the LONGEST retention in the system (it is the evidence),
so it must never become a second copy of the personal data it audits.
Payloads therefore carry scores, outcomes, versions, rule ids and a
PSEUDONYMOUS `candidate_ref` -- never transcript text, answers, resume text,
names, contact details or demographic attributes. `AuditPayloadError` is
raised for forbidden keys and for long free-text values (a transcript pasted
under an innocent key still fails the length cap). Erasure then works by
destroying the candidate_ref -> identity mapping, not by editing the log
(editing would break the chain, which is its point).

TAMPER-EVIDENT, NOT TAMPER-PROOF -- STATED HONESTLY: each entry hashes its
own content plus the previous entry's hash, so changing, deleting, inserting
or reordering any past entry makes `verify()` fail at that point. Two limits:
  1. Someone with write access to the whole store can rewrite every later
     hash. Defences: (a) an optional secret `hmac_key` (the rewriter would
     need it) and (b) `head_hash` / `length` stored somewhere the log's
     writers cannot reach (an external anchor). Neither is provided by this
     module alone; the demo shows both the attack and the defence.
  2. This is an in-memory structure with JSONL export. No database, WORM
     bucket or key service has been chosen (see the storage plan).

A REJECTION IS NEVER AUTOMATIC -- ENFORCED HERE TOO: `log_finalized` raises
if a REJECTED final outcome was not decided by a named human, mirroring Day
52's rule, so the audit trail can never record an automated rejection as if
it were legitimate.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)

AUDIT_SCHEMA_VERSION = "1.0"
GENESIS_HASH = "0" * 64
MAX_STRING_VALUE_LEN = 200

# Keys that may never appear (at any depth) in an audit payload.
FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "transcript", "transcript_text", "answer", "answers", "answer_text", "response",
        "response_text", "raw_text", "resume_text", "text", "audio", "video", "recording",
        "name", "full_name", "first_name", "last_name", "email", "phone", "address",
        "dob", "date_of_birth", "age", "gender", "religion", "caste", "ethnicity", "race",
        "nationality", "marital_status", "disability", "photo",
    }
)


class AuditEventType(str, Enum):
    SCORE = "score"
    DECISION = "decision"
    FINAL_DECISION = "final_decision"
    ACCESS = "access"
    CONSENT = "consent"
    RETENTION = "retention"
    POLICY_CHANGE = "policy_change"


class AuditPayloadError(ValueError):
    """The payload would put personal content (or something unbounded) into the log."""


class AuditIntegrityError(ValueError):
    """A log could not be loaded because it failed verification."""


def _enum_value(x: Any) -> Any:
    return getattr(x, "value", x)


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _check_payload(value: Any, path: str = "payload") -> None:
    """Reject forbidden keys and long free text anywhere inside the payload."""
    if isinstance(value, dict):
        for k, v in value.items():
            if str(k).lower() in FORBIDDEN_PAYLOAD_KEYS:
                raise AuditPayloadError(f"forbidden key '{k}' at {path}: audit logs hold scores and references, not content")
            _check_payload(v, f"{path}.{k}")
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            _check_payload(v, f"{path}[{i}]")
    elif isinstance(value, str) and len(value) > MAX_STRING_VALUE_LEN:
        raise AuditPayloadError(f"string value at {path} is {len(value)} chars (> {MAX_STRING_VALUE_LEN}): looks like free text")


def _iso(ts: Optional[datetime]) -> str:
    ts = ts or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class AuditEntry:
    """One immutable, chained audit row."""
    seq: int
    timestamp: str
    event_type: str
    actor: str                      # "service:<name>" | "human:<id>" | "system:<job>"
    candidate_ref: Optional[str]    # pseudonymous reference, never a name or e-mail
    action: str                     # short verb phrase, e.g. "score_recorded"
    payload: Dict[str, Any]
    prev_hash: str
    entry_hash: str
    schema_version: str = AUDIT_SCHEMA_VERSION

    def body(self) -> Dict[str, Any]:
        d = {
            "seq": self.seq, "timestamp": self.timestamp, "event_type": self.event_type,
            "actor": self.actor, "candidate_ref": self.candidate_ref, "action": self.action,
            "payload": self.payload, "prev_hash": self.prev_hash, "schema_version": self.schema_version,
        }
        return d

    def to_dict(self) -> Dict[str, Any]:
        d = self.body()
        d["entry_hash"] = self.entry_hash
        return d


@dataclass
class VerificationResult:
    valid: bool
    entries_checked: int
    first_bad_seq: Optional[int] = None
    reason: str = "ok"
    head_hash: str = GENESIS_HASH


class AuditLog:
    """Append-only, hash-chained audit log (in memory; JSONL export / import)."""

    def __init__(self, hmac_key: Optional[bytes] = None) -> None:
        self._entries: List[AuditEntry] = []
        self._key = hmac_key

    # ------------------------------------------------------------------ core
    def _digest(self, body: Dict[str, Any]) -> str:
        data = _canonical(body).encode("utf-8")
        if self._key:
            return hmac.new(self._key, data, hashlib.sha256).hexdigest()
        return hashlib.sha256(data).hexdigest()

    @property
    def head_hash(self) -> str:
        return self._entries[-1].entry_hash if self._entries else GENESIS_HASH

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def entries(self) -> List[AuditEntry]:
        return list(self._entries)

    def append(
        self,
        event_type: AuditEventType,
        actor: str,
        action: str,
        payload: Optional[Dict[str, Any]] = None,
        candidate_ref: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> AuditEntry:
        """Append one entry; raises AuditPayloadError rather than log personal content."""
        if not actor or not isinstance(actor, str):
            raise ValueError("actor is required (e.g. 'service:ats', 'human:r-17')")
        payload = dict(payload or {})
        _check_payload(payload)
        draft = AuditEntry(
            seq=len(self._entries), timestamp=_iso(timestamp), event_type=_enum_value(event_type),
            actor=actor, candidate_ref=candidate_ref, action=action, payload=payload,
            prev_hash=self.head_hash, entry_hash="",
        )
        entry = AuditEntry(**{**draft.__dict__, "entry_hash": self._digest(draft.body())})
        self._entries.append(entry)
        logger.info("audit %s seq=%d actor=%s", entry.event_type, entry.seq, actor)
        return entry

    # -------------------------------------------------------- typed loggers
    def log_score(
        self, candidate_ref: str, round_name: str, scores: Dict[str, float], model_version: str,
        source_module: str, actor: str = "service:scoring", config_version: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> AuditEntry:
        """SCORE LOG: which numbers were produced, by which module and model version."""
        for k, v in scores.items():
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                raise AuditPayloadError(f"score '{k}' must be numeric, got {type(v).__name__}")
        return self.append(
            AuditEventType.SCORE, actor, "score_recorded",
            {"round": round_name, "scores": dict(scores), "model_version": model_version,
             "source_module": source_module, "config_version": config_version},
            candidate_ref, timestamp,
        )

    def log_hiring_fit(self, score: Any, model_version: str, candidate_ref: Optional[str] = None,
                       actor: str = "service:scoring", timestamp: Optional[datetime] = None) -> AuditEntry:
        """SCORE LOG from a Day 51 CrossRoundCandidateScore (read by attribute)."""
        contribs = {getattr(c, "round_name", getattr(c, "round", f"r{i}")): getattr(c, "score", None)
                    for i, c in enumerate(getattr(score, "contributions", []) or [])}
        scores = {k: v for k, v in contribs.items() if isinstance(v, (int, float))}
        fit = getattr(score, "hiring_fit_percentage", None)
        if isinstance(fit, (int, float)):
            scores["hiring_fit"] = fit
        return self.append(
            AuditEventType.SCORE, actor, "hiring_fit_recorded",
            {"scores": scores, "weight_profile": getattr(score, "weight_profile_id", None),
             "coverage": getattr(score, "coverage", None), "missing_rounds": list(getattr(score, "missing_rounds", []) or []),
             "provisional": bool(getattr(score, "provisional", False)), "model_version": model_version,
             "source_module": "cross_round_aggregation_engine"},
            candidate_ref or getattr(score, "candidate_id", None), timestamp,
        )

    def log_decision(self, decision: Any, model_version: str, candidate_ref: Optional[str] = None,
                     actor: str = "service:final_recommendation", timestamp: Optional[datetime] = None) -> AuditEntry:
        """DECISION LOG for a Day 52 CandidateDecision: the engine's recommendation and the rule trace."""
        conf = getattr(decision, "confidence", None)
        fired = [getattr(r, "rule_id", "?") for r in (getattr(decision, "rule_trace", []) or []) if getattr(r, "fired", False)]
        return self.append(
            AuditEventType.DECISION, actor, "recommendation_recorded",
            {"outcome": _enum_value(getattr(decision, "outcome", None)),
             "score_band": _enum_value(getattr(decision, "score_band", None)),
             "hiring_fit": getattr(decision, "hiring_fit_percentage", None),
             "confidence": getattr(conf, "score", None), "rules_fired": fired,
             "reason_count": len(getattr(decision, "reasons", []) or []),
             "automation_eligible": bool(getattr(decision, "automation_eligible", False)),
             "automated_action": getattr(decision, "automated_action", "none"),
             "model_version": model_version},
            candidate_ref or getattr(decision, "candidate_id", None), timestamp,
        )

    def log_finalized(self, final: Any, candidate_ref: Optional[str] = None,
                      timestamp: Optional[datetime] = None) -> AuditEntry:
        """DECISION LOG for a Day 52 FinalizedDecision. An automated REJECTION is refused."""
        decided_by = str(getattr(final, "decided_by", ""))
        outcome = str(_enum_value(getattr(final, "final_outcome", "")))
        if outcome.lower() == "rejected" and not decided_by.startswith("human:"):
            raise ValueError("a REJECTED outcome must be decided by a named human ('human:<id>'); refusing to log it as valid")
        note = str(getattr(final, "note", "") or "")
        return self.append(
            AuditEventType.FINAL_DECISION, decided_by or "unknown", "decision_finalized",
            {"engine_outcome": _enum_value(getattr(final, "engine_outcome", None)), "final_outcome": outcome,
             "overridden": bool(getattr(final, "overridden", False)), "note_present": bool(note.strip()),
             "note_length": len(note)},
            candidate_ref or getattr(final, "candidate_id", None), timestamp,
        )

    # ---------------------------------------------------------------- query
    def entries_for(self, candidate_ref: str) -> List[AuditEntry]:
        return [e for e in self._entries if e.candidate_ref == candidate_ref]

    def entries_of_type(self, event_type: AuditEventType) -> List[AuditEntry]:
        v = _enum_value(event_type)
        return [e for e in self._entries if e.event_type == v]

    def explain_candidate(self, candidate_ref: str) -> List[str]:
        """One line per event, oldest first: what a reviewer or an affected person would be shown."""
        return [f"#{e.seq} {e.timestamp} {e.event_type}/{e.action} by {e.actor}" for e in self.entries_for(candidate_ref)]

    # --------------------------------------------------------------- verify
    @staticmethod
    def verify_entries(entries: Iterable[AuditEntry], hmac_key: Optional[bytes] = None,
                       expected_head: Optional[str] = None, expected_length: Optional[int] = None) -> VerificationResult:
        probe = AuditLog(hmac_key)
        prev = GENESIS_HASH
        n = 0
        for i, e in enumerate(entries):
            n += 1
            if e.seq != i:
                return VerificationResult(False, n, e.seq, f"sequence gap or reorder at position {i} (seq={e.seq})", prev)
            if e.prev_hash != prev:
                return VerificationResult(False, n, e.seq, "prev_hash does not match the preceding entry", prev)
            if probe._digest(e.body()) != e.entry_hash:
                return VerificationResult(False, n, e.seq, "entry content does not match its hash", prev)
            prev = e.entry_hash
        if expected_length is not None and n != expected_length:
            return VerificationResult(False, n, n, f"log has {n} entries but the external anchor says {expected_length} (truncation?)", prev)
        if expected_head is not None and prev != expected_head:
            return VerificationResult(False, n, n - 1 if n else None, "head hash differs from the external anchor (rewrite?)", prev)
        return VerificationResult(True, n, None, "ok", prev)

    def verify(self, expected_head: Optional[str] = None, expected_length: Optional[int] = None) -> VerificationResult:
        return self.verify_entries(self._entries, self._key, expected_head, expected_length)

    # ------------------------------------------------------------ export/load
    def export_jsonl(self) -> str:
        return "\n".join(_canonical(e.to_dict()) for e in self._entries)

    @classmethod
    def from_jsonl(cls, text: str, hmac_key: Optional[bytes] = None) -> "AuditLog":
        """Load and VERIFY; a log that fails verification is not silently accepted."""
        log = cls(hmac_key)
        for line in [ln for ln in text.splitlines() if ln.strip()]:
            d = json.loads(line)
            log._entries.append(AuditEntry(
                seq=d["seq"], timestamp=d["timestamp"], event_type=d["event_type"], actor=d["actor"],
                candidate_ref=d.get("candidate_ref"), action=d["action"], payload=d["payload"],
                prev_hash=d["prev_hash"], entry_hash=d["entry_hash"], schema_version=d.get("schema_version", AUDIT_SCHEMA_VERSION),
            ))
        res = log.verify()
        if not res.valid:
            raise AuditIntegrityError(f"audit log failed verification at seq {res.first_bad_seq}: {res.reason}")
        return log
