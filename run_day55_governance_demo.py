"""
Day 55 demo -- Security & AI Governance. Regenerates, from scratch, every
number quoted in docs/day55_security_and_ai_governance.md:

  1. LIFECYCLE   one candidate through consent -> score log -> decision log ->
                 human finalization, using the REAL Day 51/52 objects.
  2. ACCESS      a 14-scenario access matrix with the rule that decided each.
  3. AUDIT       five attacks on the log (edit, delete, truncate, consistent
                 rewrite, rewrite against an HMAC key) and which defence caught each.
  4. RETENTION   eight records evaluated at three dates.
  5. WITHDRAWAL  consent withdrawal -> immediate deletions.
  6. STORAGE     the plan validated, then three deliberately weakened plans.
  7. STATUS      the Day 43 readiness table restated.

Writes logs/day55_governance_run.log and data/results/day55_governance_report.json.

HONESTY NOTES: nothing here touches a real database, key service or identity
system; every clock is a fixed timestamp so the output is deterministic; the
retention periods and permission matrix are reasoned defaults for review, not
legal or security sign-off.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
from datetime import datetime, timedelta, timezone

logging.disable(logging.CRITICAL)   # keep demo output readable; module logs are covered by tests

from parsers.access_control import Action as A, Actor, Resource, ResourceType as RT, Role
from parsers.audit_trail import AuditEventType, AuditLog
from parsers.cross_round_aggregation_engine import RoundResult, compute_cross_round_score
from parsers.data_governance import ConsentRegistry, DataCategory as C, Purpose, RetentionPolicy, StoredRecord, pseudonymise
from parsers.final_recommendation_engine import HumanReview, decide, finalize_with_human
from parsers.governance_framework import GovernanceService
from parsers.hr_interview_question_bank import ExperienceLevel, RoleType
from parsers.secure_storage_plan import build_default_plan, plan_summary, validate_plan

LOG_PATH = "logs/day55_governance_run.log"
REPORT_PATH = "data/results/day55_governance_report.json"
os.makedirs("logs", exist_ok=True)
os.makedirs("data/results", exist_ok=True)
_lines = []
report = {}


def say(s=""):
    print(s)
    _lines.append(s)


def head(s):
    say(); say("=" * 78); say(s); say("=" * 78)


D0 = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)
KEY = b"demo-only-pseudonym-key-do-not-use"

# ------------------------------------------------------------------ 1 lifecycle
head("1. LIFECYCLE  consent -> score log -> decision log -> human finalization")
consent = ConsentRegistry("1.0")
audit = AuditLog(hmac_key=b"demo-only-audit-hmac-key-32-bytes!")
gov = GovernanceService(audit, consent, RetentionPolicy())
ref = pseudonymise("candidate-1001", KEY)
say(f"candidate_ref (keyed pseudonym of 'candidate-1001'): {ref}")
consent.grant(ref, Purpose.AI_SCREENING, "1.0", D0)
consent.grant(ref, Purpose.AI_INTERVIEW_RECORDING, "1.0", D0)
rounds = [RoundResult(n, s) for n, s in [("ats", 58), ("screening", 54), ("hr_interview", 52), ("technical_interview", 47), ("machine_test", 44)]]
score = compute_cross_round_score(rounds, RoleType.TECHNICAL, ExperienceLevel.EXPERIENCED, "candidate-1001")
decision = decide(score)
audit.log_hiring_fit(score, "v0.1.0", ref, timestamp=D0 + timedelta(days=1))
audit.log_decision(decision, "v0.1.0", ref, timestamp=D0 + timedelta(days=1))
final = finalize_with_human(decision, HumanReview("recruiter-17", decision.outcome, ""))
audit.log_finalized(final, ref, timestamp=D0 + timedelta(days=2))
say(f"hiring fit {score.hiring_fit_percentage:.1f}  engine outcome: {decision.outcome.value}  final: {final.final_outcome.value}  decided_by: {final.decided_by}")
for ln in audit.explain_candidate(ref):
    say("  " + ln)
assert audit.verify().valid
payload_has_no_content = all("transcript" not in json.dumps(e.payload) for e in audit.entries)
say(f"audit entries: {len(audit)}  chain valid: True  payloads free of transcript text: {payload_has_no_content}")
from types import SimpleNamespace
auto_rejection = SimpleNamespace(candidate_id=ref, engine_outcome="hold", final_outcome="rejected", decided_by="policy:auto", overridden=False, note="")
try:
    audit.log_finalized(auto_rejection)
    auto_reject_refused = False
except ValueError:
    auto_reject_refused = True
say(f"automated REJECTION refused by the audit log: {auto_reject_refused}")
assert auto_reject_refused
report["lifecycle"] = {"entries": len(audit), "outcome": final.final_outcome.value, "auto_reject_refused": auto_reject_refused}

# ------------------------------------------------------------------ 2 access
head("2. ACCESS  deny-by-default, with the rule that decided each request")
rec = Actor("recruiter-17", Role.RECRUITER, "co1")
other = Actor("recruiter-99", Role.RECRUITER, "co2")
me = Actor("c", Role.CANDIDATE, candidate_ref=ref)
adm, aud, svc = Actor("admin", Role.PLATFORM_ADMIN), Actor("aud", Role.AUDITOR), Actor("ats", Role.SERVICE)
R = lambda t, u=False, **k: Resource(t, **{"candidate_ref": ref, "company_id": "co1", **k}, unlocked=u)
scenarios = [
    ("recruiter reads report preview", rec, A.READ, R(RT.REPORT_PREVIEW)),
    ("recruiter reads FULL report (not paid)", rec, A.READ, R(RT.REPORT_FULL)),
    ("recruiter reads FULL report (paid)", rec, A.READ, R(RT.REPORT_FULL, True)),
    ("recruiter of another company reads score", other, A.READ, R(RT.SCORE)),
    ("candidate reads own transcript", me, A.READ, R(RT.TRANSCRIPT)),
    ("candidate reads someone else's transcript", me, A.READ, R(RT.TRANSCRIPT, candidate_ref="cref_other")),
    ("candidate reads recording", me, A.READ, R(RT.RECORDING)),
    ("platform admin reads transcript", adm, A.READ, R(RT.TRANSCRIPT, True)),
    ("auditor reads audit log", aud, A.READ, R(RT.AUDIT_LOG)),
    ("platform admin deletes audit log", adm, A.DELETE, R(RT.AUDIT_LOG)),
    ("AI service appends to audit log", svc, A.WRITE, R(RT.AUDIT_LOG)),
    ("AI service confirms a rejection", svc, A.CONFIRM_REJECTION, R(RT.DECISION)),
    ("recruiter confirms a rejection", rec, A.CONFIRM_REJECTION, R(RT.DECISION)),
    ("recruiter exports paid report", rec, A.EXPORT, R(RT.REPORT_FULL, True)),
]
rows = []
for label, actor, act, res in scenarios:
    d = gov.access.decide(actor, act, res)
    rows.append({"scenario": label, "allowed": d.allowed, "rule": d.rule_id, "obligations": list(d.obligations)})
    say(f"  {'ALLOW' if d.allowed else 'DENY ':5} {label:46} {d.rule_id}")
report["access"] = rows
allowed = sum(r["allowed"] for r in rows)
say(f"{allowed} allowed, {len(rows) - allowed} denied of {len(rows)}")

# ------------------------------------------------------------------ 3 audit attacks
head("3. AUDIT  five attacks on the log and which defence caught each")


def fresh(key=None):
    lg = AuditLog(key)
    for i in range(6):
        lg.log_score(ref, "ats", {"ats": 50.0 + i}, "v1", "ats_engine", timestamp=D0 + timedelta(hours=i))
    return lg


attacks = []
lg = fresh(); anchor = (lg.head_hash, len(lg))
lg._entries[2] = dataclasses.replace(lg._entries[2], payload={"round": "ats", "scores": {"ats": 99.0}})
r = lg.verify(); attacks.append(("edit a past score", "chain", not r.valid, f"first bad seq {r.first_bad_seq}"))
lg = fresh(); del lg._entries[3]
r = lg.verify(); attacks.append(("delete a middle entry", "chain", not r.valid, f"first bad seq {r.first_bad_seq}"))
lg = fresh(); anchor = (lg.head_hash, len(lg)); del lg._entries[-2:]
chain_alone = lg.verify().valid; r = lg.verify(*anchor)
attacks.append(("truncate the last 2 entries", "external anchor (chain alone says valid=%s)" % chain_alone, not r.valid, r.reason))
lg = fresh(); anchor = lg.head_hash
forged = AuditLog()
for e in lg.entries:
    p = dict(e.payload)
    if e.seq == 1: p["scores"] = {"ats": 1.0}
    forged.append(AuditEventType(e.event_type), e.actor, e.action, p, e.candidate_ref, datetime.fromisoformat(e.timestamp))
r = forged.verify(expected_head=anchor)
attacks.append(("consistent rewrite, no key", "external anchor (chain alone says valid=%s)" % forged.verify().valid, not r.valid, r.reason))
k = b"k" * 32; lg = fresh(k)
forged = AuditLog()
for e in lg.entries:
    forged.append(AuditEventType(e.event_type), e.actor, e.action, e.payload, e.candidate_ref, datetime.fromisoformat(e.timestamp))
r = AuditLog.verify_entries(forged.entries, hmac_key=k)
attacks.append(("consistent rewrite vs HMAC log", "secret HMAC key", not r.valid, r.reason))
for name, defence, caught, note in attacks:
    say(f"  {'CAUGHT' if caught else 'MISSED'}  {name:34} by {defence}")
assert all(a[2] for a in attacks)
report["audit_attacks"] = [{"attack": a[0], "defence": a[1], "caught": a[2]} for a in attacks]
say("Limit: the chain alone does NOT catch truncation or a keyless full rewrite; those need an external anchor or an HMAC key.")

# ------------------------------------------------------------------ 4 retention
head("4. RETENTION  eight records, three dates (policy %s)" % RetentionPolicy().version)
pol = RetentionPolicy()
recs = [StoredRecord("rec-video", C.RECORDING, ref, D0), StoredRecord("transcript", C.TRANSCRIPT, ref, D0),
        StoredRecord("resume", C.RESUME, ref, D0), StoredRecord("report", C.REPORT, ref, D0),
        StoredRecord("scores", C.SCORES, ref, D0), StoredRecord("consent", C.CONSENT_RECORD, ref, D0),
        StoredRecord("pending-case", C.TRANSCRIPT, "cref_x", None), StoredRecord("disputed", C.TRANSCRIPT, "cref_y", D0, legal_hold=True)]
ret = {}
for days in (45, 120, 400):
    rep = pol.due_actions(recs, D0 + timedelta(days=days))
    ret[days] = {"due": [f"{a.record_id}:{a.action.value}" for a in rep.due], "held": rep.skipped_legal_hold, "awaiting": rep.awaiting_trigger, "not_yet_due": rep.not_yet_due}
    say(f"  day {days:3}: due={ret[days]['due']}  held={rep.skipped_legal_hold}  awaiting_trigger={rep.awaiting_trigger}  not_yet_due={rep.not_yet_due}")
report["retention"] = {"policy_problems": pol.validate(), "by_day": {str(k): v for k, v in ret.items()}}
say(f"policy coherence problems: {pol.validate() or 'none'}")

# ------------------------------------------------------------------ 5 withdrawal
head("5. WITHDRAWAL  consent withdrawn -> immediate deletions + refused access")
r1 = gov.authorize(rec, A.READ, R(RT.RECORDING, True), D0 + timedelta(days=3))
say(f"before withdrawal: recruiter reads recording -> {'ALLOW' if r1.allowed else 'DENY ' + r1.rule_id}")
acts = gov.withdraw_consent(ref, Purpose.AI_INTERVIEW_RECORDING, D0 + timedelta(days=4), recs[:3])
say(f"withdrawn: immediate deletions = {[a.record_id for a in acts]}  (resume untouched, retention clock not needed)")
r2 = gov.authorize(rec, A.READ, R(RT.RECORDING, True), D0 + timedelta(days=5))
say(f"after withdrawal : recruiter reads recording -> {'ALLOW' if r2.allowed else 'DENY ' + r2.rule_id}  fallback={r2.fallback}")
assert r1.allowed and not r2.allowed
report["withdrawal"] = {"deletions": [a.record_id for a in acts], "after": r2.rule_id, "fallback": r2.fallback}
assert audit.verify().valid
say(f"audit log now has {len(audit)} entries, still valid: True")

# ------------------------------------------------------------------ 6 storage
head("6. STORAGE PLAN  validated, then weakened three ways")
plan = build_default_plan()
s = plan_summary(validate_plan(plan))
say(f"default plan: {s['passed']}/{s['checks']} checks pass, {s['open_items']} open items (deployment decisions / not built)")
variants = {
    "keys co-located with data": dataclasses.replace(plan, stores=tuple(dataclasses.replace(x, key_service="co_located_with_data") if x.store_id == "transcript_store" else x for x in plan.stores)),
    "raw transcripts exposed to analytics": dataclasses.replace(plan, stores=tuple(dataclasses.replace(x, analytics_reads_scrubbed_only=False) if x.store_id == "transcript_store" else x for x in plan.stores)),
    "audit store mutable": dataclasses.replace(plan, stores=tuple(dataclasses.replace(x, append_only=False) if x.store_id == "audit_store" else x for x in plan.stores)),
}
report["storage"] = {"default": s, "variants": {}}
for name, v in variants.items():
    bad = [f.check for f in validate_plan(v) if not f.passed and f.check != "Open item"]
    say(f"  weakened ({name}): fails -> {bad}")
    assert bad
    report["storage"]["variants"][name] = bad
say("Open items (not decided, not built):")
for item in plan.open_items:
    say("  - " + item)

# ------------------------------------------------------------------ 7 status
head("7. STATUS  Day 43 readiness table, restated")
rows = GovernanceService.compliance_status()
for r in rows:
    say(f"  {r['area']:38} Day43: {r['day43']:13} Now: {r['now']}")
report["status"] = rows

with open(LOG_PATH, "w", encoding="utf-8") as fh:
    fh.write("\n".join(_lines) + "\n")
with open(REPORT_PATH, "w", encoding="utf-8") as fh:
    json.dump(report, fh, indent=2, default=str)
say(f"\nwrote {LOG_PATH} and {REPORT_PATH}")
