"""
Secure Storage Plan for Transcripts and Reports (Day 55)

WHAT THIS DAY BUILDS (part 4 of 4): the brief says "PLAN secure storage", and
that is what this is -- a machine-checkable PLAN, not an implementation.
Nothing here encrypts, stores or deletes a byte. The project has no database,
object store or key service yet (`utils/config.py` holds placeholder URLs
only), and inventing one would be fiction. What a plan can do honestly is state
the requirements precisely enough that (a) a reviewer can challenge them and
(b) `validate_plan()` can check a plan -- this one, or a changed one -- against
the invariants that matter, so the design cannot quietly drift.

THE DESIGN IN FIVE PRINCIPLES (each is a checked invariant):
  1. ENCRYPT EVERYTHING PERSONAL: encryption at rest (envelope encryption,
     AES-256-GCM) and TLS 1.2+ in transit, for every store holding personal data.
  2. KEYS LIVE APART FROM DATA: keys in a managed key service, scoped per
     tenant, rotated on a schedule; never stored beside the ciphertext.
  3. IDENTITY SEPARATED FROM CONTENT: transcripts and reports are keyed by the
     pseudonymous candidate_ref; the ref -> identity table is a different store
     with tighter access. Analytics only ever read SCRUBBED transcripts (Day 43
     demographic scrubber), never raw ones.
  4. DELETION MUST ACTUALLY DELETE: delete the object AND destroy its key
     (crypto-shredding), and backups must expire soon enough that a deleted
     record does not survive in a backup past the stated window.
  5. EVIDENCE IS WRITE-ONCE: the audit store is append-only/WORM and holds no
     personal content.

Algorithm names (AES-256-GCM, TLS 1.2+) are well-established defaults; the
specific products (KMS, bucket type, region) are left as `TBD_DEPLOYMENT`
because they are deployment decisions, and the validator reports them as open
items rather than pretending they are settled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from parsers.data_governance import DataCategory, RetentionPolicy
from utils.logger import get_logger

logger = get_logger(__name__)

TBD = "TBD_DEPLOYMENT"


@dataclass(frozen=True)
class StoreSpec:
    store_id: str
    categories: Tuple[DataCategory, ...]
    holds_personal_data: bool
    encryption_at_rest: Optional[str]          # e.g. "AES-256-GCM envelope"
    in_transit: Optional[str]                  # e.g. "TLS1.2+"
    key_service: str                           # where keys live ("managed KMS" / "co-located" is a violation)
    key_scope: str                             # "per_tenant" | "per_record" | "global"
    key_rotation_days: Optional[int]
    keyed_by: str                              # "candidate_ref" | "candidate_identity" | "event_seq"
    contains_identity: bool
    append_only: bool
    backup_expiry_days: Optional[int]          # how long a backup copy can outlive a delete
    deletion_method: str                       # "crypto_shred+delete" | "none"
    readers: Tuple[str, ...]                   # roles, see access_control
    analytics_reads_scrubbed_only: bool = True
    notes: str = ""


@dataclass(frozen=True)
class StoragePlan:
    version: str
    stores: Tuple[StoreSpec, ...]
    open_items: Tuple[str, ...]


@dataclass
class Finding:
    check: str
    passed: bool
    detail: str


MAX_BACKUP_EXPIRY_DAYS = 35
MAX_KEY_ROTATION_DAYS = 365


def build_default_plan() -> StoragePlan:
    common = dict(encryption_at_rest="AES-256-GCM envelope encryption", in_transit="TLS1.2+",
                  key_service="managed_kms_separate_from_data", key_scope="per_tenant", key_rotation_days=365,
                  backup_expiry_days=30, deletion_method="crypto_shred+delete")
    return StoragePlan(
        version="1.0",
        stores=(
            StoreSpec("transcript_store", (DataCategory.TRANSCRIPT,), True, keyed_by="candidate_ref", contains_identity=False,
                      append_only=False, readers=("recruiter", "candidate", "service"), analytics_reads_scrubbed_only=True,
                      notes="Raw transcripts; analytics reads only the scrubbed derivative (Day 43).", **common),
            StoreSpec("report_store", (DataCategory.REPORT, DataCategory.SCORES), True, keyed_by="candidate_ref", contains_identity=False,
                      append_only=False, readers=("recruiter", "company_admin", "candidate", "service"),
                      notes="Day 53 reports + score history; full report gated by paid unlock.", **common),
            StoreSpec("recording_store", (DataCategory.RECORDING,), True, keyed_by="candidate_ref", contains_identity=False,
                      append_only=False, readers=("recruiter", "service"), notes="Shortest retention; highest sensitivity.", **common),
            StoreSpec("resume_store", (DataCategory.RESUME,), True, keyed_by="candidate_ref", contains_identity=False,
                      append_only=False, readers=("recruiter", "candidate", "service"), **common),
            StoreSpec("identity_map", (DataCategory.CONSENT_RECORD,), True, keyed_by="candidate_identity", contains_identity=True,
                      append_only=False, readers=("service",), notes="ref -> person link and consent records; separate, tighter access.",
                      **{**common, "key_scope": "per_tenant"}),
            StoreSpec("audit_store", (DataCategory.AUDIT_LOG,), False, encryption_at_rest="AES-256-GCM envelope encryption",
                      in_transit="TLS1.2+", key_service="managed_kms_separate_from_data", key_scope="global", key_rotation_days=365,
                      keyed_by="event_seq", contains_identity=False, append_only=True, backup_expiry_days=None,
                      deletion_method="none", readers=("auditor", "platform_admin", "service"),
                      notes="WORM / append-only; anchor head hash outside this store (see audit_trail)."),
        ),
        open_items=(
            f"{TBD}: object store and database product, region/residency",
            f"{TBD}: key management service and key-ceremony owner",
            f"{TBD}: who holds the audit head-hash anchor",
            "Decision needed: per-tenant vs per-record keys (per-record makes crypto-shredding precise but costs more)",
            "Not built: any code that encrypts, stores, backs up or deletes data",
        ),
    )


def validate_plan(plan: StoragePlan, policy: Optional[RetentionPolicy] = None) -> List[Finding]:
    """Check a plan against the five principles and the retention policy. Returns every finding (passes included)."""
    policy = policy or RetentionPolicy()
    out: List[Finding] = []

    def add(check: str, ok: bool, detail: str) -> None:
        out.append(Finding(check, ok, detail))

    personal = [s for s in plan.stores if s.holds_personal_data]
    bad = [s.store_id for s in personal if not s.encryption_at_rest or not s.in_transit]
    add("P1 encryption at rest and in transit", not bad, "all personal-data stores encrypted" if not bad else f"missing encryption: {bad}")

    bad = [s.store_id for s in plan.stores if "co_located" in s.key_service or s.key_service in ("", "same_store")]
    add("P2 keys separate from data", not bad, "keys held in a separate managed service" if not bad else f"keys co-located: {bad}")
    bad = [s.store_id for s in personal if s.key_scope == "global"]
    add("P2 personal data not under one global key", not bad, "per-tenant or finer" if not bad else f"global key: {bad}")
    bad = [s.store_id for s in plan.stores if s.key_rotation_days is None or s.key_rotation_days > MAX_KEY_ROTATION_DAYS]
    add("P2 key rotation defined", not bad, f"rotation <= {MAX_KEY_ROTATION_DAYS}d everywhere" if not bad else f"rotation missing/too long: {bad}")

    bad = [s.store_id for s in plan.stores if s.contains_identity and s.keyed_by != "candidate_identity"]
    ident = [s.store_id for s in plan.stores if s.contains_identity]
    add("P3 identity isolated in one store", not bad and len(ident) == 1, f"identity only in {ident}" if len(ident) == 1 and not bad else f"identity in {ident or 'no store'}")
    bad = [s.store_id for s in plan.stores if s.categories and set(s.categories) & {DataCategory.TRANSCRIPT, DataCategory.REPORT} and s.keyed_by != "candidate_ref"]
    add("P3 transcripts/reports keyed by pseudonymous ref", not bad, "keyed by candidate_ref" if not bad else f"keyed by identity: {bad}")
    bad = [s.store_id for s in plan.stores if DataCategory.TRANSCRIPT in s.categories and not s.analytics_reads_scrubbed_only]
    add("P3 analytics reads scrubbed transcripts only", not bad, "scrubbed-only" if not bad else f"raw transcripts exposed to analytics: {bad}")

    bad = [s.store_id for s in personal if s.deletion_method != "crypto_shred+delete"]
    add("P4 deletion = delete + key destruction", not bad, "crypto_shred+delete" if not bad else f"weak deletion: {bad}")
    bad = [s.store_id for s in personal if s.backup_expiry_days is None or s.backup_expiry_days > MAX_BACKUP_EXPIRY_DAYS]
    add("P4 backups expire soon after deletion", not bad, f"<= {MAX_BACKUP_EXPIRY_DAYS}d" if not bad else f"backup window missing/too long: {bad}")

    audit = [s for s in plan.stores if DataCategory.AUDIT_LOG in s.categories]
    add("P5 audit store is append-only and personal-data-free", bool(audit) and all(s.append_only and not s.holds_personal_data for s in audit),
        "append-only, no personal data" if audit and all(s.append_only and not s.holds_personal_data for s in audit) else "audit store missing or mutable")

    covered = {c for s in plan.stores for c in s.categories}
    missing = [c.value for c in DataCategory if c not in covered]
    add("Coverage: every retention category has a store", not missing, "all categories placed" if not missing else f"no store for: {missing}")
    problems = policy.validate()
    add("Retention policy is coherent", not problems, "ok" if not problems else "; ".join(problems))

    for item in plan.open_items:
        add("Open item", False, item)
    return out


def plan_summary(findings: List[Finding]) -> Dict[str, int]:
    checks = [f for f in findings if f.check != "Open item"]
    return {"checks": len(checks), "passed": sum(f.passed for f in checks),
            "failed": sum(not f.passed for f in checks), "open_items": len(findings) - len(checks)}
