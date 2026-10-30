"""
Access Control Logic (Day 55)

WHAT THIS DAY BUILDS (part 3 of 4): who may do what to which data. Deny by
default; every decision carries the rule that produced it so a refusal can be
explained and audited.

MODEL: role-based permissions (what a role may ever do) PLUS contextual rules
(whether this particular request is allowed). A request is allowed only if the
role matrix permits it AND no contextual rule vetoes it.

Contextual rules, in the order they are evaluated:
  R1 tenant isolation  -- a company user can only touch their own company's data
                          (the PRD requires multi-tenant architecture).
  R2 own-data only     -- a candidate can only touch their own records.
  R3 paid unlock       -- recruiter access to the FULL report / recording /
                          transcript requires the resource to be unlocked
                          (PRD phases 23/48/73/100: preview free, full paid).
                          Payment buys access to the company's own candidates'
                          data; it never overrides consent or retention, which
                          the facade (governance_framework) checks as well.
  R4 no content for admins/auditors -- platform admins and auditors see
                          metadata and the audit log, not transcripts or
                          recordings (least privilege).
  R5 audit log is append-only -- NO role, including admins, may WRITE or
                          DELETE it; only the system 'service' role appends.
  R6 rejection is human -- CONFIRM_REJECTION is limited to human company
                          roles; the AI `service` role can never hold it
                          (mirrors Day 52: a rejection is never automatic).

OBLIGATIONS: an allow can carry duties the caller must honour (log the access,
watermark an export). They are returned, not silently applied.

NOT BUILT: authentication (proving who the actor is), session handling, API
gateway wiring. This module assumes the `Actor` it is given is already
authenticated. The permission matrix is a reasoned starting point to review
with the product owner, not a signed-off security policy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, FrozenSet, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


class Role(str, Enum):
    CANDIDATE = "candidate"
    RECRUITER = "recruiter"
    COMPANY_ADMIN = "company_admin"
    PLATFORM_ADMIN = "platform_admin"
    AUDITOR = "auditor"
    SERVICE = "service"            # the AI services themselves


class Action(str, Enum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    EXPORT = "export"
    OVERRIDE_DECISION = "override_decision"
    CONFIRM_REJECTION = "confirm_rejection"


class ResourceType(str, Enum):
    RESUME = "resume"
    TRANSCRIPT = "transcript"
    RECORDING = "recording"
    SCORE = "score"
    REPORT_PREVIEW = "report_preview"
    REPORT_FULL = "report_full"
    DECISION = "decision"
    AUDIT_LOG = "audit_log"
    CONSENT_RECORD = "consent_record"
    POLICY_CONFIG = "policy_config"


CONTENT_TYPES = frozenset({ResourceType.RESUME, ResourceType.TRANSCRIPT, ResourceType.RECORDING, ResourceType.REPORT_FULL})
PAID_TYPES = frozenset({ResourceType.REPORT_FULL, ResourceType.RECORDING, ResourceType.TRANSCRIPT})

R, W, D, E = Action.READ, Action.WRITE, Action.DELETE, Action.EXPORT
OV, CR = Action.OVERRIDE_DECISION, Action.CONFIRM_REJECTION
RT = ResourceType


def _m(**kw: FrozenSet[Action]) -> Dict[ResourceType, FrozenSet[Action]]:
    return {ResourceType(k): v for k, v in kw.items()}


PERMISSIONS: Dict[Role, Dict[ResourceType, FrozenSet[Action]]] = {
    Role.CANDIDATE: _m(resume=frozenset({R, W, D}), transcript=frozenset({R}), score=frozenset({R}),
                       decision=frozenset({R}), consent_record=frozenset({R, W}), report_preview=frozenset({R})),
    Role.RECRUITER: _m(resume=frozenset({R}), transcript=frozenset({R}), recording=frozenset({R}), score=frozenset({R}),
                       report_preview=frozenset({R}), report_full=frozenset({R, E}), decision=frozenset({R, OV, CR})),
    Role.COMPANY_ADMIN: _m(resume=frozenset({R}), score=frozenset({R}), report_preview=frozenset({R}),
                           report_full=frozenset({R, E}), decision=frozenset({R, OV, CR}), policy_config=frozenset({R, W})),
    Role.PLATFORM_ADMIN: _m(score=frozenset({R}), report_preview=frozenset({R}), decision=frozenset({R}),
                            audit_log=frozenset({R}), policy_config=frozenset({R, W}), consent_record=frozenset({R})),
    Role.AUDITOR: _m(score=frozenset({R}), decision=frozenset({R}), audit_log=frozenset({R}),
                     consent_record=frozenset({R}), policy_config=frozenset({R})),
    Role.SERVICE: _m(resume=frozenset({R}), transcript=frozenset({R, W}), recording=frozenset({R, W}), score=frozenset({R, W}),
                     report_preview=frozenset({W}), report_full=frozenset({W}), decision=frozenset({W}), audit_log=frozenset({W})),
}


@dataclass(frozen=True)
class Actor:
    actor_id: str
    role: Role
    company_id: Optional[str] = None
    candidate_ref: Optional[str] = None         # for role == CANDIDATE: their own ref


@dataclass(frozen=True)
class Resource:
    resource_type: ResourceType
    candidate_ref: Optional[str] = None
    company_id: Optional[str] = None
    unlocked: bool = False                      # paid-access flag for PAID_TYPES


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    rule_id: str
    reason: str
    obligations: tuple = ()


def _deny(rule: str, reason: str) -> AccessDecision:
    return AccessDecision(False, rule, reason)


class AccessController:
    """Stateless evaluator. Construct with a custom matrix to review alternatives."""

    def __init__(self, permissions: Optional[Dict[Role, Dict[ResourceType, FrozenSet[Action]]]] = None) -> None:
        self.permissions = permissions or PERMISSIONS

    def decide(self, actor: Actor, action: Action, resource: Resource) -> AccessDecision:
        rt = resource.resource_type
        # R5: nobody but the system appends to the audit log; nobody edits or deletes it.
        if rt == ResourceType.AUDIT_LOG and action in (W, D):
            if not (actor.role == Role.SERVICE and action == W):
                return _deny("R5_audit_append_only", "the audit log is append-only and written only by the system")
        # R6: a rejection is a human act.
        if action == CR and actor.role not in (Role.RECRUITER, Role.COMPANY_ADMIN):
            return _deny("R6_rejection_is_human", "only a human company reviewer can confirm a rejection")
        # Role matrix.
        allowed_actions = self.permissions.get(actor.role, {}).get(rt, frozenset())
        if action not in allowed_actions:
            return _deny("RBAC_matrix", f"role {actor.role.value} may not {action.value} {rt.value}")
        # R4: admins/auditors never see personal content.
        if actor.role in (Role.PLATFORM_ADMIN, Role.AUDITOR) and rt in CONTENT_TYPES:
            return _deny("R4_no_content_for_oversight_roles", "oversight roles see metadata, not personal content")
        # R1: tenant isolation.
        if actor.role in (Role.RECRUITER, Role.COMPANY_ADMIN):
            if not actor.company_id or actor.company_id != resource.company_id:
                return _deny("R1_tenant_isolation", "resource belongs to a different company")
        # R2: candidates see only their own data.
        if actor.role == Role.CANDIDATE:
            if not actor.candidate_ref or actor.candidate_ref != resource.candidate_ref:
                return _deny("R2_own_data_only", "candidates may only access their own records")
        # R3: paid unlock.
        if actor.role in (Role.RECRUITER, Role.COMPANY_ADMIN) and rt in PAID_TYPES and not resource.unlocked:
            return _deny("R3_paid_unlock_required", "full content requires the paid unlock; the preview is available")
        obligations: List[str] = ["log_access"]
        if action == E:
            obligations.append("watermark_export")
        if rt in CONTENT_TYPES and actor.role != Role.CANDIDATE:
            obligations.append("verify_consent_and_retention")
        return AccessDecision(True, "ALLOW", f"{actor.role.value} may {action.value} {rt.value}", tuple(obligations))
