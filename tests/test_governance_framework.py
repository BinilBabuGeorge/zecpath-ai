from datetime import datetime, timedelta, timezone

from parsers import cross_round_aggregation_engine as day51
from parsers.access_control import Action as A, Actor, Resource, ResourceType as RT, Role
from parsers.audit_trail import AuditEventType, AuditLog
from parsers.cross_round_aggregation_engine import RoundResult, compute_cross_round_score
from parsers.data_governance import ConsentRegistry, DataCategory as C, Purpose, RetentionPolicy, StoredRecord
from parsers.final_recommendation_engine import DecisionOutcome, HumanReview, decide, finalize_with_human
from parsers.governance_framework import GovernanceService
from parsers.hr_interview_question_bank import ExperienceLevel, RoleType

D0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
REC = Actor("r1", Role.RECRUITER, "co1")


def svc():
    reg = ConsentRegistry()
    return GovernanceService(AuditLog(), reg, RetentionPolicy()), reg


def rsrc(rt, unlocked=True):
    return Resource(rt, "cref_a", "co1", unlocked)


def test_every_request_is_audited_including_denials():
    g, reg = svc()
    g.authorize(REC, A.READ, rsrc(RT.REPORT_PREVIEW), D0)
    g.authorize(REC, A.READ, Resource(RT.SCORE, "cref_a", "co2"), D0)
    e = g.audit.entries
    assert [x.action for x in e] == ["access_allowed", "access_denied"] and e[1].payload["rule"] == "R1_tenant_isolation"
    assert g.audit.verify().valid


def test_recording_access_needs_consent_even_when_paid_unlock_is_true():
    g, reg = svc()
    r = g.authorize(REC, A.READ, rsrc(RT.RECORDING), D0)
    assert not r.allowed and r.rule_id == "CONSENT_required" and r.fallback == "human_process"
    reg.grant("cref_a", Purpose.AI_INTERVIEW_RECORDING, "1.0", D0)
    assert g.authorize(REC, A.READ, rsrc(RT.RECORDING), D0 + timedelta(days=1)).allowed


def test_expired_data_is_not_served_but_legal_hold_keeps_it_available():
    g, reg = svc()
    reg.grant("cref_a", Purpose.AI_INTERVIEW_RECORDING, "1.0", D0)
    rec = StoredRecord("t1", C.TRANSCRIPT, "cref_a", D0)
    later = D0 + timedelta(days=120)
    r = g.authorize(REC, A.READ, rsrc(RT.TRANSCRIPT), later, rec)
    assert not r.allowed and r.rule_id == "RETENTION_expired"
    rec.legal_hold = True
    assert g.authorize(REC, A.READ, rsrc(RT.TRANSCRIPT), later, rec).allowed


def test_withdrawal_updates_consent_audits_and_returns_deletions():
    g, reg = svc()
    reg.grant("cref_a", Purpose.AI_INTERVIEW_RECORDING, "1.0", D0)
    recs = [StoredRecord("rec1", C.RECORDING, "cref_a", None)]
    acts = g.withdraw_consent("cref_a", Purpose.AI_INTERVIEW_RECORDING, D0 + timedelta(days=2), recs)
    assert [a.record_id for a in acts] == ["rec1"]
    assert not reg.check("cref_a", Purpose.AI_INTERVIEW_RECORDING).allowed
    assert g.audit.entries_of_type(AuditEventType.CONSENT)[0].payload["deletions_triggered"] == 1


def test_compliance_status_does_not_overclaim():
    rows = GovernanceService.compliance_status()
    assert "NOT production-ready" in rows[-1]["now"]
    assert all("compliant" not in r["now"].lower().replace("not production", "") for r in rows)


def test_end_to_end_with_real_day51_and_day52_objects():
    g, _ = svc()
    rounds = [RoundResult(n, s) for n, s in [("ats", 55), ("screening", 52), ("hr_interview", 50), ("technical_interview", 48), ("machine_test", 45)]]
    score = compute_cross_round_score(rounds, RoleType.TECHNICAL, ExperienceLevel.EXPERIENCED, "cand-1")
    decision = decide(score)
    g.audit.log_hiring_fit(score, "v1", "cref_a")
    g.record_decision(decision, "v1", "cref_a")
    assert decision.outcome in DecisionOutcome
    final = finalize_with_human(decision, HumanReview("r1", decision.outcome, ""))
    g.record_final(final, "cref_a")
    kinds = [e.event_type for e in g.audit.entries]
    assert kinds == ["score", "decision", "final_decision"] and g.audit.verify().valid
    assert "hiring_fit" in g.audit.entries[0].payload["scores"]
    assert g.audit.entries[2].actor == "human:r1"
