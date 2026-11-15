"""
Decision audit (Day 61)

THE QUESTION AN AUDITOR ASKS: "Why was this candidate recommended for rejection or held, and can you show it?" The Day 55 audit log (a hash-chained,
append-only record that refuses personal content) already records scores and outcomes. Day 61 checked whether it records ENOUGH, by running two
decisions that differ only in the ATS zone through the Day 55 typed loggers (`log_hiring_fit`, `log_decision`). They gave different outcomes (selected
against hold-for-review with `selection_blocked`) but IDENTICAL score entries: the zone, which caused the difference, is not recorded anywhere, and the
decision entry says only that rule R4 fired. So from the log alone nobody can say WHY. (tests/test_observability.py reproduces this.)

This module adds what is missing, using only the existing log (`AuditLog.append`), so the chain, the forbidden-key guard and the human-rejection rule
all still apply:

  * record()               one entry with the INPUTS to the decision (round scores, ATS zone, role, level, versions, the request id) and one with the
                           RESULT (outcome, hold kind, confidence, review flags, a digest of the reasons). The request id ties both to the API log line.
  * record_human_review()  the person's confirmation, override or deferral. A REJECTION is never final without a named human (`human:<id>`).
  * replay()               re-runs the decision service on the logged inputs and compares with the logged result: the strongest check that the log
                           explains the decision. It works because scoring is deterministic (Day 57).
  * completeness()         decisions that were made but never audited; rejections still waiting for a human.
  * explain()              a plain timeline for one candidate reference.

WHAT IS NEVER LOGGED: resume text, answers, transcripts, names, contact details, or the reason SENTENCES (only their count and a digest, which proves they
were not altered but reveals nothing). The candidate is a pseudonymous reference. Erasure works by deleting the reference-to-person mapping, not by editing the log.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from parsers.audit_trail import AuditEntry, AuditEventType, AuditLog, AuditPayloadError

DECISION_INPUT_KEYS = ("role_type", "experience_level", "ats_zone", "ats_score", "screening_score", "hr_interview_score", "technical_score",
                       "machine_test_score", "communication_score")
RESULT_FIELDS = ("decision", "hold_kind", "hiring_fit_score", "confidence", "provisional", "human_review_required", "human_confirmation_required",
                 "automation_eligible", "automated_action")
HUMAN_ACTIONS = ("confirmed", "overridden", "deferred")
FINAL_OUTCOMES = ("selected", "hold_review", "rejected")


def reasons_digest(reasons: Sequence[str]) -> str:
    return hashlib.sha256("\n".join(reasons).encode("utf-8")).hexdigest()[:16]


@dataclass
class ReplayResult:
    request_id: str
    replayable: bool
    match: bool = False
    differences: List[str] = field(default_factory=list)
    version_mismatch: bool = False
    note: str = ""


class DecisionAuditRecorder:
    def __init__(self, log: AuditLog, actor: str = "service:scoring") -> None:
        self.log = log
        self.actor = actor

    # ------------------------------------------------------------------------------------------------------------------
    def record(self, request: Mapping[str, Any], response: Mapping[str, Any], request_id: str, candidate_ref: str) -> Tuple[AuditEntry, AuditEntry]:
        """Write the inputs entry and the result entry for one DecisionScoringService call."""
        if response.get("status") != "success":
            raise ValueError("only a successful decision is recorded; an error response made no decision")
        if response.get("decision") == "rejected" and (response.get("automated_action") != "none" or not response.get("human_confirmation_required")):
            raise AuditPayloadError("a rejection must require human confirmation and carry no automated action; refusing to record it as valid")
        inputs = {k: request[k] for k in DECISION_INPUT_KEYS if k in request and request[k] is not None}
        versions = {"api_version": response.get("api_version"), "model_version": response.get("model_version")}
        a = self.log.append(AuditEventType.SCORE, self.actor, "decision_inputs_recorded",
                            {"request_id": request_id, "inputs": inputs, **versions, "source_module": "scoring.service.DecisionScoringService"}, candidate_ref)
        result = {k: response.get(k) for k in RESULT_FIELDS}
        reasons = list(response.get("reasons") or [])
        b = self.log.append(AuditEventType.DECISION, self.actor, "recommendation_recorded",
                            {"request_id": request_id, **result, "missing_rounds": list(response.get("missing_rounds") or []),
                             "human_review_reasons_count": len(response.get("human_review_reasons") or []), "reasons_count": len(reasons),
                             "reasons_digest": reasons_digest(reasons), **versions}, candidate_ref)
        return a, b

    def record_human_review(self, candidate_ref: str, request_id: str, reviewer: str, action: str, final_outcome: str, note_present: bool = False) -> AuditEntry:
        if not reviewer.startswith("human:") or len(reviewer) <= len("human:"):
            raise ValueError("a human review must name the person ('human:<id>')")
        if action not in HUMAN_ACTIONS:
            raise ValueError(f"action must be one of {HUMAN_ACTIONS}")
        if final_outcome not in FINAL_OUTCOMES:
            raise ValueError(f"final_outcome must be one of {FINAL_OUTCOMES}")
        recommended = self._decision_entry(request_id)
        if recommended is None:
            raise ValueError(f"no recorded recommendation for request {request_id!r}")
        return self.log.append(AuditEventType.FINAL_DECISION, reviewer, f"decision_{action}",
                               {"request_id": request_id, "engine_outcome": recommended.payload.get("decision"), "final_outcome": final_outcome,
                                "overridden": final_outcome != recommended.payload.get("decision"), "note_present": bool(note_present)}, candidate_ref)

    # ------------------------------------------------------------------------------------------------------------------
    def _entries_for_request(self, request_id: str) -> List[AuditEntry]:
        return [e for e in self.log.entries if e.payload.get("request_id") == request_id]

    def _decision_entry(self, request_id: str) -> Optional[AuditEntry]:
        return next((e for e in self._entries_for_request(request_id) if e.action == "recommendation_recorded"), None)

    def replay(self, request_id: str, service: Optional[Any] = None) -> ReplayResult:
        """Re-run the decision on the logged inputs and compare with the logged result."""
        entries = self._entries_for_request(request_id)
        inp = next((e for e in entries if e.action == "decision_inputs_recorded"), None)
        dec = next((e for e in entries if e.action == "recommendation_recorded"), None)
        if inp is None or dec is None:
            return ReplayResult(request_id, False, note="the log has no inputs entry and a result entry for this request id")
        if service is None:
            from scoring.service import DecisionScoringService
            service = DecisionScoringService()
        again = service.run({**inp.payload["inputs"], "candidate_id": inp.candidate_ref})
        if again.get("status") != "success":
            return ReplayResult(request_id, True, False, [f"replay returned an error: {again.get('error', {}).get('code')}"])
        diffs = [f"{k}: logged {dec.payload.get(k)!r}, replayed {again.get(k)!r}" for k in RESULT_FIELDS if dec.payload.get(k) != again.get(k)]
        if dec.payload.get("reasons_digest") != reasons_digest(list(again.get("reasons") or [])):
            diffs.append("reasons: digest differs")
        version_mismatch = (dec.payload.get("model_version"), dec.payload.get("api_version")) != (again.get("model_version"), again.get("api_version"))
        return ReplayResult(request_id, True, not diffs, diffs, version_mismatch,
                            "versions differ from the ones that made the decision; a difference may be a model change, not tampering" if version_mismatch else "")

    def completeness(self, decision_request_ids: Iterable[str]) -> List[str]:
        """Request ids of decisions (from the model_output logs) that have no recommendation entry in the audit log."""
        have = {e.payload.get("request_id") for e in self.log.entries if e.action == "recommendation_recorded"}
        return sorted(set(decision_request_ids) - have)

    def rejections_pending(self) -> List[str]:
        """Request ids where the engine recommended rejection and no human has yet recorded a decision."""
        decided = {e.payload.get("request_id") for e in self.log.entries if e.event_type == AuditEventType.FINAL_DECISION.value}
        return [e.payload["request_id"] for e in self.log.entries
                if e.action == "recommendation_recorded" and e.payload.get("decision") == "rejected" and e.payload["request_id"] not in decided]

    def explain(self, candidate_ref: str) -> List[str]:
        lines: List[str] = []
        for e in self.log.entries_for(candidate_ref):
            p = e.payload
            if e.action == "decision_inputs_recorded":
                lines.append(f"#{e.seq} inputs recorded for {p['request_id']}: {p['inputs']}")
            elif e.action == "recommendation_recorded":
                lines.append(f"#{e.seq} recommendation {p.get('decision')} ({p.get('hold_kind')}), fit {p.get('hiring_fit_score')}, confidence {p.get('confidence')}, "
                             f"human review required: {p.get('human_review_required')}")
            elif e.event_type == AuditEventType.FINAL_DECISION.value:
                lines.append(f"#{e.seq} {e.actor} {e.action.replace('decision_', '')}: engine said {p.get('engine_outcome')}, final {p.get('final_outcome')}, overridden {p.get('overridden')}")
        return lines
