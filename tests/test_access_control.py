import itertools

import pytest

from parsers.access_control import (PERMISSIONS, AccessController, Action as A, Actor, Resource, ResourceType as RT, Role)

AC = AccessController()
REC = Actor("r1", Role.RECRUITER, "co1")
OWN = dict(candidate_ref="cref_a", company_id="co1")


def res(rt, unlocked=False, **kw):
    return Resource(rt, **{**OWN, **kw}, unlocked=unlocked)


def test_recruiter_reads_preview_but_not_full_report_until_unlocked():
    assert AC.decide(REC, A.READ, res(RT.REPORT_PREVIEW)).allowed
    d = AC.decide(REC, A.READ, res(RT.REPORT_FULL))
    assert not d.allowed and d.rule_id == "R3_paid_unlock_required"
    assert AC.decide(REC, A.READ, res(RT.REPORT_FULL, unlocked=True)).allowed


def test_tenant_isolation():
    d = AC.decide(REC, A.READ, res(RT.SCORE, company_id="co2"))
    assert not d.allowed and d.rule_id == "R1_tenant_isolation"
    assert not AC.decide(Actor("r2", Role.RECRUITER, None), A.READ, res(RT.SCORE)).allowed


def test_candidate_sees_only_own_data():
    me = Actor("cref_a", Role.CANDIDATE, candidate_ref="cref_a")
    assert AC.decide(me, A.READ, res(RT.TRANSCRIPT)).allowed
    d = AC.decide(me, A.READ, res(RT.TRANSCRIPT, candidate_ref="cref_b"))
    assert not d.allowed and d.rule_id == "R2_own_data_only"


def test_candidate_cannot_touch_recordings_reports_or_edit_scores():
    me = Actor("cref_a", Role.CANDIDATE, candidate_ref="cref_a")
    for rt, a in [(RT.RECORDING, A.READ), (RT.REPORT_FULL, A.READ), (RT.SCORE, A.WRITE), (RT.AUDIT_LOG, A.READ)]:
        assert not AC.decide(me, a, res(rt)).allowed


def test_oversight_roles_never_see_content():
    for role in (Role.PLATFORM_ADMIN, Role.AUDITOR):
        for rt in (RT.TRANSCRIPT, RT.RECORDING, RT.RESUME, RT.REPORT_FULL):
            assert not AC.decide(Actor("x", role), A.READ, res(rt, unlocked=True)).allowed
    assert AC.decide(Actor("a", Role.AUDITOR), A.READ, res(RT.AUDIT_LOG)).allowed


@pytest.mark.parametrize("role,action", list(itertools.product(Role, [A.WRITE, A.DELETE])))
def test_audit_log_is_append_only_for_everyone_but_the_system(role, action):
    d = AC.decide(Actor("x", role, "co1", "cref_a"), action, res(RT.AUDIT_LOG))
    if role == Role.SERVICE and action == A.WRITE:
        assert d.allowed
    else:
        assert not d.allowed


def test_only_human_company_roles_can_confirm_a_rejection():
    for role in Role:
        d = AC.decide(Actor("x", role, "co1", "cref_a"), A.CONFIRM_REJECTION, res(RT.DECISION))
        assert d.allowed == (role in (Role.RECRUITER, Role.COMPANY_ADMIN)), role


def test_service_role_can_never_hold_confirm_rejection_even_with_a_custom_matrix():
    custom = {**PERMISSIONS, Role.SERVICE: {**PERMISSIONS[Role.SERVICE], RT.DECISION: frozenset({A.CONFIRM_REJECTION, A.WRITE})}}
    d = AccessController(custom).decide(Actor("svc", Role.SERVICE), A.CONFIRM_REJECTION, Resource(RT.DECISION))
    assert not d.allowed and d.rule_id == "R6_rejection_is_human"


def test_deny_by_default_for_unlisted_pairs():
    assert not AC.decide(REC, A.DELETE, res(RT.RESUME)).allowed
    assert not AC.decide(REC, A.WRITE, res(RT.POLICY_CONFIG)).allowed


def test_export_carries_a_watermark_obligation_and_all_allows_log_access():
    d = AC.decide(REC, A.EXPORT, res(RT.REPORT_FULL, unlocked=True))
    assert "watermark_export" in d.obligations and "log_access" in d.obligations
    assert "verify_consent_and_retention" in d.obligations


def test_company_admin_can_change_policy_config_but_recruiter_cannot():
    adm = Actor("a", Role.COMPANY_ADMIN, "co1")
    assert AC.decide(adm, A.WRITE, res(RT.POLICY_CONFIG)).allowed
    assert not AC.decide(REC, A.WRITE, res(RT.POLICY_CONFIG)).allowed


def test_every_denial_names_a_rule_and_reason():
    for role, rt, a in itertools.product(Role, RT, A):
        d = AC.decide(Actor("x", role, "co1", "cref_a"), a, res(rt))
        assert d.rule_id and d.reason
        if d.allowed:
            assert "log_access" in d.obligations


def test_r4_is_defence_in_depth_when_a_matrix_grants_oversight_roles_content():
    custom = {**PERMISSIONS, Role.PLATFORM_ADMIN: {**PERMISSIONS[Role.PLATFORM_ADMIN], RT.TRANSCRIPT: frozenset({A.READ})}}
    d = AccessController(custom).decide(Actor("adm", Role.PLATFORM_ADMIN), A.READ, res(RT.TRANSCRIPT))
    assert not d.allowed and d.rule_id == "R4_no_content_for_oversight_roles"
