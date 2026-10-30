from datetime import datetime, timedelta, timezone

import pytest

from parsers.data_governance import (ConsentError, ConsentRegistry, DataCategory as C, Purpose, RetentionAction, RetentionPolicy,
                                     RetentionRule, StoredRecord, Trigger, actions_for_withdrawal, pseudonymise)

D0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
KEY = b"0123456789abcdef0123"


def rec(rid, cat, trigger=D0, hold=False, ref="cref_a"):
    return StoredRecord(rid, cat, ref, trigger, hold)


# ---------------- pseudonyms
def test_pseudonym_is_stable_keyed_and_opaque():
    a = pseudonymise("cand-1", KEY)
    assert a == pseudonymise("cand-1", KEY) and a.startswith("cref_") and "cand-1" not in a
    assert a != pseudonymise("cand-2", KEY) and a != pseudonymise("cand-1", b"another-key-0123456")


def test_pseudonym_rejects_empty_id_and_short_key():
    with pytest.raises(ValueError):
        pseudonymise("", KEY)
    with pytest.raises(ValueError):
        pseudonymise("c", b"short")


# ---------------- retention
def test_default_policy_is_coherent():
    assert RetentionPolicy().validate() == []


def test_audit_log_must_outlive_personal_data():
    rules = tuple(RetentionRule(r.category, r.trigger, 30 if r.category == C.AUDIT_LOG else r.days, r.action, r.rationale)
                  for r in RetentionPolicy().rules.values())
    probs = RetentionPolicy(rules).validate()
    assert any("audit log" in p for p in probs)


def test_missing_category_and_bad_days_are_reported():
    p = RetentionPolicy((RetentionRule(C.RESUME, Trigger.FINAL_DECISION, 0, RetentionAction.DELETE, "x"),))
    probs = p.validate()
    assert any("transcript" in x for x in probs) and any("positive" in x for x in probs)


def test_not_due_before_expiry_and_due_exactly_at_expiry():
    p = RetentionPolicy()
    r = rec("t1", C.TRANSCRIPT)
    assert not p.due_actions([r], D0 + timedelta(days=89)).due
    due = p.due_actions([r], D0 + timedelta(days=90)).due
    assert len(due) == 1 and due[0].action == RetentionAction.DELETE


def test_recording_expires_before_transcript_before_resume():
    p = RetentionPolicy()
    now = D0 + timedelta(days=100)
    got = {a.category for a in p.due_actions([rec("a", C.RECORDING), rec("b", C.TRANSCRIPT), rec("c", C.RESUME)], now).due}
    assert got == {C.RECORDING, C.TRANSCRIPT}


def test_scores_are_anonymised_not_deleted():
    due = RetentionPolicy().due_actions([rec("s", C.SCORES)], D0 + timedelta(days=400)).due
    assert due[0].action == RetentionAction.ANONYMISE


def test_clock_not_started_is_reported_not_guessed():
    rep = RetentionPolicy().due_actions([rec("t", C.TRANSCRIPT, trigger=None)], D0 + timedelta(days=9999))
    assert rep.awaiting_trigger == ["t"] and not rep.due


def test_legal_hold_blocks_deletion_and_is_reported():
    rep = RetentionPolicy().due_actions([rec("t", C.TRANSCRIPT, hold=True)], D0 + timedelta(days=500))
    assert rep.skipped_legal_hold == ["t"] and not rep.due


def test_naive_datetimes_are_treated_as_utc():
    r = StoredRecord("t", C.RECORDING, "c", datetime(2026, 1, 1))
    assert RetentionPolicy().due_actions([r], datetime(2026, 3, 1)).due


# ---------------- consent
def test_default_deny_with_human_fallback_for_ai_purposes():
    reg = ConsentRegistry()
    d = reg.check("c", Purpose.AI_INTERVIEW_RECORDING)
    assert not d.allowed and d.fallback == "human_process"
    assert reg.check("c", Purpose.MODEL_IMPROVEMENT).fallback is None


def test_grant_then_check_and_purposes_are_not_bundled():
    reg = ConsentRegistry()
    reg.grant("c", Purpose.AI_SCREENING, "1.0", D0)
    assert reg.check("c", Purpose.AI_SCREENING).allowed
    assert not reg.check("c", Purpose.AI_INTERVIEW_RECORDING).allowed
    assert not reg.check("c", Purpose.VOICE_CLONING).allowed


def test_withdrawal_wins_and_history_is_kept():
    reg = ConsentRegistry()
    reg.grant("c", Purpose.VOICE_CLONING, "1.0", D0)
    reg.withdraw("c", Purpose.VOICE_CLONING, D0 + timedelta(days=1))
    assert not reg.check("c", Purpose.VOICE_CLONING).allowed
    assert [h.granted for h in reg.history("c", Purpose.VOICE_CLONING)] == [True, False]


def test_check_as_of_a_past_time_sees_the_past_state():
    reg = ConsentRegistry()
    reg.grant("c", Purpose.AI_SCREENING, "1.0", D0)
    reg.withdraw("c", Purpose.AI_SCREENING, D0 + timedelta(days=10))
    assert reg.check("c", Purpose.AI_SCREENING, D0 + timedelta(days=5)).allowed
    assert not reg.check("c", Purpose.AI_SCREENING, D0 - timedelta(days=1)).allowed


def test_regrant_after_withdrawal_restores_consent():
    reg = ConsentRegistry()
    reg.grant("c", Purpose.AI_SCREENING, "1.0", D0)
    reg.withdraw("c", Purpose.AI_SCREENING, D0 + timedelta(days=1))
    reg.grant("c", Purpose.AI_SCREENING, "1.0", D0 + timedelta(days=2))
    assert reg.check("c", Purpose.AI_SCREENING).allowed


def test_new_notice_version_makes_old_consent_stale():
    reg = ConsentRegistry("1.0")
    reg.grant("c", Purpose.AI_SCREENING, "1.0", D0)
    reg.required_notice_version = "2.0"
    d = reg.check("c", Purpose.AI_SCREENING)
    assert not d.allowed and "re-consent" in d.reason


def test_implied_consent_methods_are_rejected():
    with pytest.raises(ValueError):
        ConsentRegistry().grant("c", Purpose.AI_SCREENING, "1.0", D0, method="pre_ticked_box")


def test_out_of_order_events_are_rejected():
    reg = ConsentRegistry()
    reg.grant("c", Purpose.AI_SCREENING, "1.0", D0)
    with pytest.raises(ValueError):
        reg.withdraw("c", Purpose.AI_SCREENING, D0 - timedelta(days=1))


def test_require_raises_consent_error():
    with pytest.raises(ConsentError):
        ConsentRegistry().require("c", Purpose.AI_SCREENING)


def test_withdrawal_triggers_immediate_deletion_of_dependent_data_only():
    recs = [rec("rec1", C.RECORDING), rec("tr1", C.TRANSCRIPT), rec("cv1", C.RESUME), rec("other", C.RECORDING, ref="cref_z"),
            rec("held", C.RECORDING, hold=True)]
    acts = actions_for_withdrawal("cref_a", Purpose.AI_INTERVIEW_RECORDING, recs)
    assert {a.record_id for a in acts} == {"rec1", "tr1"}
    assert all(a.action == RetentionAction.DELETE for a in acts)
