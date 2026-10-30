import dataclasses

from parsers.data_governance import DataCategory as C
from parsers.secure_storage_plan import build_default_plan, plan_summary, validate_plan


def failed(plan):
    return {f.check for f in validate_plan(plan) if not f.passed and f.check != "Open item"}


def tweak(plan, store_id, **kw):
    return dataclasses.replace(plan, stores=tuple(dataclasses.replace(s, **kw) if s.store_id == store_id else s for s in plan.stores))


def test_default_plan_passes_every_check_and_lists_open_items():
    f = validate_plan(build_default_plan())
    s = plan_summary(f)
    assert s["failed"] == 0 and s["passed"] == s["checks"] >= 12
    assert s["open_items"] >= 4 and any("Not built" in x.detail for x in f)


def test_unencrypted_transcript_store_fails():
    assert "P1 encryption at rest and in transit" in failed(tweak(build_default_plan(), "transcript_store", encryption_at_rest=None))


def test_colocated_keys_fail():
    assert "P2 keys separate from data" in failed(tweak(build_default_plan(), "report_store", key_service="co_located_with_data"))


def test_global_key_on_personal_data_fails():
    assert "P2 personal data not under one global key" in failed(tweak(build_default_plan(), "recording_store", key_scope="global"))


def test_missing_rotation_fails():
    assert "P2 key rotation defined" in failed(tweak(build_default_plan(), "resume_store", key_rotation_days=None))


def test_identity_in_a_content_store_fails():
    p = tweak(build_default_plan(), "transcript_store", contains_identity=True)
    assert "P3 identity isolated in one store" in failed(p)


def test_transcript_keyed_by_identity_fails():
    assert "P3 transcripts/reports keyed by pseudonymous ref" in failed(tweak(build_default_plan(), "transcript_store", keyed_by="candidate_identity"))


def test_raw_transcripts_exposed_to_analytics_fail():
    assert "P3 analytics reads scrubbed transcripts only" in failed(tweak(build_default_plan(), "transcript_store", analytics_reads_scrubbed_only=False))


def test_weak_deletion_and_long_backups_fail():
    p = tweak(tweak(build_default_plan(), "report_store", deletion_method="none"), "resume_store", backup_expiry_days=400)
    f = failed(p)
    assert "P4 deletion = delete + key destruction" in f and "P4 backups expire soon after deletion" in f


def test_mutable_or_personal_audit_store_fails():
    assert "P5 audit store is append-only and personal-data-free" in failed(tweak(build_default_plan(), "audit_store", append_only=False))
    assert "P5 audit store is append-only and personal-data-free" in failed(tweak(build_default_plan(), "audit_store", holds_personal_data=True))


def test_unplaced_category_fails():
    plan = build_default_plan()
    plan = dataclasses.replace(plan, stores=tuple(s for s in plan.stores if C.RECORDING not in s.categories))
    assert "Coverage: every retention category has a store" in failed(plan)
