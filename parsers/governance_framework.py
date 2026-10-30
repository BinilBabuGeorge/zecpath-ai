"""
Governance Framework Facade (Day 55)

Ties the four Day 55 parts together so a caller makes ONE call and gets every
control applied in the right order:

    authorize()  : access rule (access_control) -> consent (data_governance)
                   -> retention/legal-hold -> audit entry (audit_trail).
                   EVERY request is logged, denials included: a denied
                   attempt is exactly what an auditor wants to see.
    record_*()   : score / decision logs.
    withdraw_consent(): registry + audit + immediate retention actions.
    compliance_status(): the Day 43 readiness table, restated honestly.

The facade holds no state of its own beyond the objects it is given, and it
does not do I/O. Wiring it into the real intake, API gateway and storage layer
is the follow-up this project cannot complete without those layers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from parsers.access_control import (CONTENT_TYPES, AccessController, AccessDecision, Action, Actor, Resource, ResourceType, Role)
from parsers.audit_trail import AuditEventType, AuditLog
from parsers.data_governance import (ConsentRegistry, DataCategory, DueAction, Purpose, RetentionPolicy, StoredRecord, actions_for_withdrawal)
from utils.logger import get_logger

logger = get_logger(__name__)

_TYPE_TO_PURPOSE = {ResourceType.RECORDING: Purpose.AI_INTERVIEW_RECORDING, ResourceType.TRANSCRIPT: Purpose.AI_INTERVIEW_RECORDING}
_TYPE_TO_CATEGORY = {ResourceType.RESUME: DataCategory.RESUME, ResourceType.TRANSCRIPT: DataCategory.TRANSCRIPT,
                     ResourceType.RECORDING: DataCategory.RECORDING, ResourceType.REPORT_FULL: DataCategory.REPORT}


@dataclass(frozen=True)
class AuthorizationResult:
    allowed: bool
    rule_id: str
    reason: str
    obligations: tuple = ()
    fallback: Optional[str] = None


class GovernanceService:
    def __init__(self, audit: AuditLog, consent: ConsentRegistry, retention: RetentionPolicy,
                 access: Optional[AccessController] = None) -> None:
        self.audit, self.consent, self.retention = audit, consent, retention
        self.access = access or AccessController()

    # ------------------------------------------------------------ authorize
    def authorize(self, actor: Actor, action: Action, resource: Resource, now: datetime,
                  record: Optional[StoredRecord] = None) -> AuthorizationResult:
        d: AccessDecision = self.access.decide(actor, action, resource)
        res = AuthorizationResult(d.allowed, d.rule_id, d.reason, d.obligations)
        if d.allowed and resource.resource_type in CONTENT_TYPES and actor.role != Role.CANDIDATE:
            res = self._content_checks(res, resource, now, record)
        self.audit.append(
            AuditEventType.ACCESS, f"{'human' if actor.role != Role.SERVICE else 'service'}:{actor.actor_id}",
            "access_allowed" if res.allowed else "access_denied",
            {"role": actor.role.value, "action": action.value, "resource": resource.resource_type.value,
             "rule": res.rule_id, "allowed": res.allowed}, resource.candidate_ref, now)
        return res

    def _content_checks(self, res: AuthorizationResult, resource: Resource, now: datetime,
                        record: Optional[StoredRecord]) -> AuthorizationResult:
        purpose = _TYPE_TO_PURPOSE.get(resource.resource_type)
        if purpose and resource.candidate_ref:
            c = self.consent.check(resource.candidate_ref, purpose, now)
            if not c.allowed:
                return AuthorizationResult(False, "CONSENT_required", c.reason, (), c.fallback)
        cat = _TYPE_TO_CATEGORY.get(resource.resource_type)
        if record is not None and cat is not None:
            if record.legal_hold:
                return res
            rep = self.retention.due_actions([record], now)
            if rep.due:
                return AuthorizationResult(False, "RETENTION_expired", f"retention period ended on {rep.due[0].expired_on:%Y-%m-%d}; record is due for {rep.due[0].action.value}")
        return res

    # ------------------------------------------------------------------ logs
    def record_score(self, *a: Any, **k: Any):
        return self.audit.log_score(*a, **k)

    def record_decision(self, *a: Any, **k: Any):
        return self.audit.log_decision(*a, **k)

    def record_final(self, *a: Any, **k: Any):
        return self.audit.log_finalized(*a, **k)

    # ------------------------------------------------------------ withdrawal
    def withdraw_consent(self, candidate_ref: str, purpose: Purpose, now: datetime,
                         records: List[StoredRecord]) -> List[DueAction]:
        self.consent.withdraw(candidate_ref, purpose, now)
        actions = actions_for_withdrawal(candidate_ref, purpose, records)
        self.audit.append(AuditEventType.CONSENT, f"human:{candidate_ref}", "consent_withdrawn",
                          {"purpose": purpose.value, "deletions_triggered": len(actions)}, candidate_ref, now)
        return actions

    # --------------------------------------------------------------- status
    @staticmethod
    def compliance_status() -> List[Dict[str, str]]:
        """Day 43 'NOT READY' rows, restated after Day 55. Status words are deliberately conservative."""
        return [
            {"area": "Audit trail (score + decision logs)", "day43": "not present", "now": "Built (in-memory, hash-chained); persistent store not chosen"},
            {"area": "Data retention", "day43": "Not ready", "now": "Policy + due-action logic built and tested; no deletion job, no storage to run it on"},
            {"area": "Consent-based data usage", "day43": "Not ready", "now": "Registry + gate built and tested; no intake UI/API captures it yet"},
            {"area": "Secure storage", "day43": "not present", "now": "Plan + validator only; nothing encrypts or stores data"},
            {"area": "Access control", "day43": "not present", "now": "Role + context rules built and tested; authentication and gateway wiring not built"},
            {"area": "Production compliance overall", "day43": "Not ready", "now": "Still NOT production-ready: logic exists, enforcement points do not"},
        ]
