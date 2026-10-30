import dataclasses
from datetime import datetime, timezone
from types import SimpleNamespace as NS

import pytest

from parsers.audit_trail import (GENESIS_HASH, AuditEventType, AuditIntegrityError, AuditLog, AuditPayloadError)

T0 = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)


def make_log(key=None):
    log = AuditLog(key)
    log.log_score("cref_a", "ats", {"ats": 72.5}, "v1", "ats_engine", timestamp=T0)
    log.log_score("cref_a", "hr", {"hr": 66.0, "communication": 70}, "v1", "hr_scoring", timestamp=T0)
    log.append(AuditEventType.ACCESS, "human:r1", "access_allowed", {"rule": "ALLOW"}, "cref_b", T0)
    return log


def test_empty_log_verifies_and_head_is_genesis():
    log = AuditLog()
    assert log.verify().valid and log.head_hash == GENESIS_HASH and len(log) == 0


def test_chain_links_each_entry_to_the_previous_one():
    log = make_log()
    e = log.entries
    assert e[0].prev_hash == GENESIS_HASH
    assert e[1].prev_hash == e[0].entry_hash and e[2].prev_hash == e[1].entry_hash
    assert [x.seq for x in e] == [0, 1, 2]
    assert log.verify().valid


def test_changing_a_payload_value_is_detected_at_that_entry():
    log = make_log()
    log._entries[1] = dataclasses.replace(log._entries[1], payload={"round": "hr", "scores": {"hr": 99.0}})
    r = log.verify()
    assert not r.valid and r.first_bad_seq == 1 and "hash" in r.reason


def test_deleting_an_entry_is_detected():
    log = make_log()
    del log._entries[1]
    r = log.verify()
    assert not r.valid and r.first_bad_seq == 2


def test_reordering_is_detected():
    log = make_log()
    log._entries[0], log._entries[1] = log._entries[1], log._entries[0]
    assert not log.verify().valid


def test_truncating_the_tail_is_only_caught_with_an_external_anchor():
    log = make_log()
    anchor_head, anchor_len = log.head_hash, len(log)
    del log._entries[-1]
    assert log.verify().valid                      # chain alone cannot see a dropped tail
    r = log.verify(expected_head=anchor_head, expected_length=anchor_len)
    assert not r.valid and "truncation" in r.reason


def test_full_rewrite_without_key_passes_chain_but_fails_anchor():
    log = make_log()
    anchor = log.head_hash
    forged = AuditLog()
    for e in log.entries:
        p = dict(e.payload)
        if e.seq == 0:
            p["scores"] = {"ats": 10.0}
        forged.append(AuditEventType(e.event_type), e.actor, e.action, p, e.candidate_ref, datetime.fromisoformat(e.timestamp))
    assert forged.verify().valid                   # a consistent forgery
    assert not forged.verify(expected_head=anchor).valid


def test_hmac_key_defeats_the_rewrite():
    log = make_log(key=b"k" * 32)
    forged = AuditLog()                            # attacker has no key
    for e in log.entries:
        forged.append(AuditEventType(e.event_type), e.actor, e.action, e.payload, e.candidate_ref, datetime.fromisoformat(e.timestamp))
    assert not AuditLog.verify_entries(forged.entries, hmac_key=b"k" * 32).valid
    assert AuditLog.verify_entries(log.entries, hmac_key=b"k" * 32).valid


def test_jsonl_roundtrip_and_tampered_load_refused():
    log = make_log()
    text = log.export_jsonl()
    again = AuditLog.from_jsonl(text)
    assert again.head_hash == log.head_hash and len(again) == 3
    with pytest.raises(AuditIntegrityError):
        AuditLog.from_jsonl(text.replace("72.5", "92.5"))


@pytest.mark.parametrize("key", ["transcript", "answer_text", "email", "Gender", "religion", "name"])
def test_forbidden_keys_rejected(key):
    with pytest.raises(AuditPayloadError):
        AuditLog().append(AuditEventType.SCORE, "service:x", "a", {key: "x"})


def test_forbidden_key_rejected_when_nested():
    with pytest.raises(AuditPayloadError):
        AuditLog().append(AuditEventType.SCORE, "service:x", "a", {"meta": {"deep": [{"email": "a@b.c"}]}})


def test_long_free_text_under_an_innocent_key_is_rejected():
    with pytest.raises(AuditPayloadError):
        AuditLog().append(AuditEventType.SCORE, "service:x", "a", {"note": "word " * 100})


def test_scores_must_be_numeric():
    with pytest.raises(AuditPayloadError):
        AuditLog().log_score("c", "ats", {"ats": "high"}, "v1", "m")
    with pytest.raises(AuditPayloadError):
        AuditLog().log_score("c", "ats", {"ats": True}, "v1", "m")


def test_actor_required():
    with pytest.raises(ValueError):
        AuditLog().append(AuditEventType.ACCESS, "", "x")


def test_queries_and_explanation():
    log = make_log()
    assert len(log.entries_for("cref_a")) == 2 and len(log.entries_for("cref_b")) == 1
    assert len(log.entries_of_type(AuditEventType.SCORE)) == 2
    lines = log.explain_candidate("cref_a")
    assert len(lines) == 2 and lines[0].startswith("#0")


def test_naive_timestamp_is_treated_as_utc():
    e = AuditLog().append(AuditEventType.ACCESS, "human:r", "x", {}, None, datetime(2026, 1, 1, 12, 0))
    assert e.timestamp.endswith("+00:00")


def test_rejection_must_be_decided_by_a_human():
    final = NS(candidate_id="c", engine_outcome="rejected", final_outcome="rejected", decided_by="policy:auto", overridden=False, note="")
    with pytest.raises(ValueError):
        AuditLog().log_finalized(final)


def test_human_rejection_is_logged_without_the_note_text():
    final = NS(candidate_id="c", engine_outcome="hold", final_outcome="rejected", decided_by="human:r9", overridden=True, note="Lacks required certification for the role")
    e = AuditLog().log_finalized(final, timestamp=T0)
    assert e.actor == "human:r9" and e.payload["overridden"] is True
    assert e.payload["note_present"] is True and "note" not in e.payload
