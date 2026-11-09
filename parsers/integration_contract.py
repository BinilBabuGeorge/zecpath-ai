"""
Integration Contract (Day 59)

WHAT THIS DAY BUILDS. The brief is a PLANNING day: "define how all AI modules integrate with backend services and external
systems". This module is the plan in a form a machine can check, so the plan cannot quietly drift away from the code:

  1. OPERATIONS    the catalogue of AI APIs (resume parsing, ATS scoring, screening, interview, decision, plus the job resource),
                   each with its sync/async mode, the code that implements it, its scope, and every data store it touches.
  2. ERROR_RULES   every error code the code can emit -> HTTP status, whether a retry is allowed, and how many.
  3. Retry         exponential backoff with full jitter, a retry loop that follows ERROR_RULES, and idempotency-key handling.
  4. Job states    the Day 16 state machine, unchanged.
  5. Schemas       JSON Schema for every request and response, BUILT FROM THE CODE'S OWN ENUMS and limits, so an enum value added
                   to the code appears in the schema; plus the OpenAPI 3.1 document generated from them (one source of truth).
  6. Gateway check `validate_request()` runs a request through its schema and answers in the same error codes the services use.
  7. Access check  `check_data_access()` runs every store touch through the real Day 55 `AccessController`.

WHAT IT DOES NOT DO. It serves nothing: there is no gateway, queue, database or auth server in this project. The retry loop and
the idempotency store are small reference implementations that make the policy testable; a real deployment would use its queue
and cache for the same rules. Numbers marked PROPOSED (timeouts, limits, token lifetimes) are starting points to tune, not
measurements. The measured numbers come from `run_day59_integration_demo.py`.
"""

from __future__ import annotations

import copy
import hashlib
import json
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from parsers.access_control import AccessController, Action, Actor, Resource, ResourceType, Role
from parsers.secure_storage_plan import build_default_plan
from utils.base_service import API_VERSION, MAX_ITEMS, MAX_TEXT_CHARS
from utils.config import MODEL_VERSION
from utils.logger import get_logger

logger = get_logger(__name__)

CONTRACT_VERSION = "1.0"
API_PREFIX = "/v1/ai"
MAX_ANSWER_CHARS = 20_000            # the interview service's own per-answer limit
GATEWAY_SERVICE_NAME = "ai_gateway"
CANDIDATE_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"   # pseudonymous ref: no spaces, no '@', so a name or an email cannot pass


# ======================================================================================================================
# 1. The API catalogue
# ======================================================================================================================
class Mode(str, Enum):
    SYNC = "sync"
    ASYNC = "async"


class ImplStatus(str, Enum):
    SERVICE = "service"          # a service class behind run() exists and is tested
    PLANNED = "planned"          # contract defined; the HTTP/queue layer around it is not built


@dataclass(frozen=True)
class DataTouch:
    """One read or write the backend makes around an AI call. `resource` is the Day 55 ResourceType (None = not modelled)."""
    resource: Optional[ResourceType]
    action: Action
    store: str
    note: str = ""

    @property
    def label(self) -> str:
        return self.resource.value if self.resource else self.store


@dataclass(frozen=True)
class Operation:
    op_id: str
    method: str
    path: str
    mode: Mode
    summary: str
    implementation: str                    # dotted path of the class that does the work ("" = job store, not an AI class)
    request_schema: Optional[str]
    response_schema: str                   # schema of the 200 body, or of the job result for async operations
    scope: Optional[str]                   # OAuth-style scope the caller's service token must carry
    idempotency: str                       # "required" | "optional" | "n/a"
    timeout_s: float                       # PROPOSED: gateway timeout (sync) or per-attempt worker timeout (async)
    touches: Tuple[DataTouch, ...] = ()
    extra_errors: Tuple[int, ...] = ()
    max_body_bytes: int = 1_048_576        # PROPOSED request-size cap enforced by the gateway

    @property
    def success_status(self) -> int:
        return 202 if self.mode == Mode.ASYNC else 200

    @property
    def path_with_prefix(self) -> str:
        return API_PREFIX + self.path


R, W = Action.READ, Action.WRITE
RT = ResourceType
_AUDIT = DataTouch(RT.AUDIT_LOG, W, "audit_store", "one entry per call: ids, scores, versions, never text")

OPERATIONS: Tuple[Operation, ...] = (
    Operation("parse_resume", "POST", "/resumes/parse", Mode.ASYNC,
              "Read a resume file and return its text, sections, skills, experience, education and certifications",
              "ats_engine.resume_parsing_service.ResumeParsingService", "ParseResumeRequest", "ParseResumeResult",
              "ai:resume:parse", "required", 60.0,
              (DataTouch(RT.RESUME, R, "resume_store", "the uploaded file, by file_ref"),
               DataTouch(RT.RESUME, W, "resume_store", "parsed fields stored next to the file"), _AUDIT),
              extra_errors=(404, 415), max_body_bytes=16_384),
    Operation("score_ats", "POST", "/ats/score", Mode.SYNC,
              "Score one resume against one job description (Day 57 ATSService)",
              "ats_engine.service.ATSService", "ATSScoreRequest", "ATSScoreResult", "ai:ats:score", "optional", 2.0,
              (DataTouch(RT.RESUME, R, "resume_store", "parsed text"),
               DataTouch(None, R, "job_store", "the job description (a company document, not personal data)"),
               DataTouch(RT.SCORE, W, "report_store"), _AUDIT)),
    Operation("score_ats_batch", "POST", "/ats/score-batch", Mode.ASYNC,
              "Score many resumes against one job description, one result each",
              "ats_engine.batch_service.ATSBatchService", "ATSBatchScoreRequest", "ATSBatchScoreResult", "ai:ats:score",
              "required", 120.0,
              (DataTouch(RT.RESUME, R, "resume_store", "parsed text of every applicant"),
               DataTouch(None, R, "job_store", "the job description"), DataTouch(RT.SCORE, W, "report_store"), _AUDIT),
              max_body_bytes=10_485_760),
    Operation("score_screening", "POST", "/screening/score", Mode.SYNC,
              "Score a screening-call conversation that has already happened (Day 57 ScreeningService)",
              "screening_ai.service.ScreeningService", "ScreeningScoreRequest", "ScreeningScoreResult", "ai:screening:score",
              "optional", 2.0,
              (DataTouch(RT.TRANSCRIPT, R, "transcript_store", "the turns, as speech-to-text produced them"),
               DataTouch(RT.SCORE, W, "report_store"), _AUDIT), max_body_bytes=2_097_152),
    Operation("score_interview", "POST", "/interviews/score", Mode.SYNC,
              "Score the answers of an HR or technical interview in real time (Day 57 InterviewIntelligenceService)",
              "interview_ai.service.InterviewIntelligenceService", "InterviewScoreRequest", "InterviewScoreResult",
              "ai:interview:score", "optional", 2.0,
              (DataTouch(RT.TRANSCRIPT, R, "transcript_store", "the candidate's answers"),
               DataTouch(RT.SCORE, W, "report_store"), _AUDIT), max_body_bytes=2_097_152),
    Operation("recommend_decision", "POST", "/decisions/recommend", Mode.SYNC,
              "Combine the round scores into a hiring-fit score and a RECOMMENDATION a person acts on (Day 57 DecisionScoringService)",
              "scoring.service.DecisionScoringService", "DecisionRequest", "DecisionResult", "ai:decision:recommend",
              "optional", 2.0,
              (DataTouch(RT.SCORE, R, "report_store", "the round scores"), DataTouch(RT.DECISION, W, "report_store"), _AUDIT),
              max_body_bytes=16_384),
    Operation("get_job", "GET", "/jobs/{job_id}", Mode.SYNC, "Read the status, and when finished the result, of an asynchronous job",
              "", None, "JobStatus", "ai:jobs:read", "n/a", 2.0, (), extra_errors=(404,)),
    Operation("cancel_job", "POST", "/jobs/{job_id}/cancel", Mode.SYNC, "Cancel a queued or running job",
              "", None, "JobStatus", "ai:jobs:cancel", "n/a", 2.0, (), extra_errors=(404, 409)),
    Operation("health", "GET", "/health", Mode.SYNC, "Liveness and versions; no personal data, no authentication",
              "", None, "HealthResponse", None, "n/a", 1.0, ()),
)
OPERATION_BY_ID: Dict[str, Operation] = {o.op_id: o for o in OPERATIONS}
STATUS_OF: Dict[str, ImplStatus] = {o.op_id: (ImplStatus.SERVICE if o.implementation else ImplStatus.PLANNED) for o in OPERATIONS}
STATUS_OF.update({"get_job": ImplStatus.PLANNED, "cancel_job": ImplStatus.PLANNED, "health": ImplStatus.PLANNED})


# ======================================================================================================================
# 2. Error policy
# ======================================================================================================================
@dataclass(frozen=True)
class ErrorRule:
    code: str
    http_status: int
    source: str                  # service | resume_upload | gateway
    max_retries: int             # 0 = never retry; the caller must change the request
    client_action: str


def _e(code: str, status: int, source: str, retries: int, action: str) -> Tuple[str, ErrorRule]:
    return code, ErrorRule(code, status, source, retries, action)


ERROR_RULES: Dict[str, ErrorRule] = dict([
    # -- emitted by BaseAIService.run() / the services (Day 57) ---------------------------------------------------------
    _e("invalid_payload", 400, "service", 0, "Send a JSON object as the body."),
    _e("invalid_input", 422, "service", 0, "Fix the field named in error.field; retrying the same request fails the same way."),
    _e("missing_field", 422, "service", 0, "Add the field named in error.field."),
    _e("invalid_score", 422, "service", 0, "Send a number from 0 to 100."),
    _e("too_large", 413, "service", 0, "Send less text or fewer items; the limit is in the message."),
    _e("unsupported_value", 422, "service", 0, "Use one of the values listed in the message."),
    _e("internal_error", 500, "service", 1, "Retry once; the scoring is deterministic, so a second failure is a bug, not bad luck. Report the request_id."),
    # -- emitted by the resume upload path (Day 57 ResumeUploadError) ---------------------------------------------------
    _e("unsupported_type", 415, "resume_upload", 0, "Ask the candidate for a PDF or DOCX."),
    _e("file_not_found", 404, "resume_upload", 2, "The file may not have replicated yet: retry twice, then treat as missing."),
    _e("empty_file", 422, "resume_upload", 0, "Ask the candidate to upload a file that has content."),
    _e("corrupt_file", 422, "resume_upload", 0, "Ask the candidate to re-save the file or export it again."),
    # -- emitted by the gateway and job layer (Day 59 plan; not built) --------------------------------------------------
    _e("unauthenticated", 401, "gateway", 0, "Get a fresh service token; do not retry with the same one."),
    _e("forbidden", 403, "gateway", 0, "The token lacks the scope for this operation."),
    _e("not_found", 404, "gateway", 0, "The job does not exist or belongs to another tenant."),
    _e("conflict", 409, "gateway", 0, "The job already finished, so it cannot be cancelled."),
    _e("idempotency_conflict", 409, "gateway", 0, "The Idempotency-Key was already used with a different body; use a new key."),
    _e("rate_limited", 429, "gateway", 5, "Wait for Retry-After, then retry with backoff."),
    _e("service_unavailable", 503, "gateway", 5, "Retry with backoff."),
    _e("timeout", 504, "gateway", 3, "Retry with backoff; safe because scoring is deterministic and job creation carries an Idempotency-Key."),
])
ERROR_CODES: Tuple[str, ...] = tuple(ERROR_RULES)


def classify(code: str) -> ErrorRule:
    """The rule for a code. An unmapped code is treated as an internal error: a code nobody planned for is never retried freely."""
    return ERROR_RULES.get(code, ERROR_RULES["internal_error"])


@dataclass
class GatewayError:
    http_status: int
    body: Dict[str, Any]
    headers: Dict[str, str] = field(default_factory=dict)


def to_gateway_error(envelope: Mapping[str, Any], request_id: str, retry_after_seconds: Optional[float] = None) -> GatewayError:
    """Turn a service's error envelope into the response the gateway sends: HTTP status, request id, retry advice."""
    if envelope.get("status") != "error" or not isinstance(envelope.get("error"), Mapping):
        raise ValueError("to_gateway_error needs an error envelope")
    err = envelope["error"]
    code = err.get("code")
    known = code in ERROR_RULES
    rule = classify(code)
    body = dict(envelope)
    body["error"] = {"code": code if known else "internal_error",
                     "message": err.get("message") if known else "An internal error occurred; the request was not processed.",
                     "field": err.get("field") if known else None}
    body["request_id"] = request_id
    body["retryable"] = rule.max_retries > 0
    wait = retry_after_seconds if rule.http_status in (429, 503) else None
    body["retry_after_seconds"] = wait
    headers = {"X-Request-Id": request_id}
    if wait is not None:
        headers["Retry-After"] = str(int(max(1, round(wait))))
    return GatewayError(rule.http_status, body, headers)


# ======================================================================================================================
# 3. Retry and idempotency
# ======================================================================================================================
@dataclass(frozen=True)
class RetryPolicy:
    """PROPOSED defaults: 0.5 s doubling to a 30 s cap, full jitter, at most 4 retries, 20 s of waiting in total."""
    base_delay_s: float = 0.5
    max_delay_s: float = 30.0
    max_retries: int = 4
    total_wait_budget_s: float = 20.0


def backoff_delay(retry_number: int, policy: RetryPolicy = RetryPolicy(), rng: Callable[[], float] = random.random) -> float:
    """Full jitter: a random wait between 0 and min(cap, base * 2^(n-1)). `retry_number` starts at 1. Jitter stops many clients
    that failed together from all coming back together."""
    if retry_number < 1:
        raise ValueError("retry_number starts at 1")
    ceiling = min(policy.max_delay_s, policy.base_delay_s * (2 ** (retry_number - 1)))
    return rng() * ceiling


class TransportError(Exception):
    """The call never produced an envelope: connection refused, gateway timeout. `code` is one of ERROR_RULES."""

    def __init__(self, code: str, retry_after_seconds: Optional[float] = None) -> None:
        super().__init__(code)
        self.code = code
        self.retry_after_seconds = retry_after_seconds


@dataclass
class RetryOutcome:
    envelope: Dict[str, Any]
    attempts: int
    delays: List[float]
    gave_up: Optional[str] = None        # None = finished; otherwise why we stopped


def call_with_retry(fn: Callable[[int], Dict[str, Any]], policy: RetryPolicy = RetryPolicy(),
                    sleep: Callable[[float], None] = time.sleep, rng: Callable[[], float] = random.random) -> RetryOutcome:
    """Call `fn(attempt)` until it succeeds, fails for a reason a retry cannot fix, or the retry budget runs out.

    `fn` returns an envelope or raises TransportError. A retry happens only when ERROR_RULES allows retries for that code, fewer
    than `min(rule.max_retries, policy.max_retries)` have been used, and the wait would fit in `total_wait_budget_s`.
    A server's Retry-After is honoured as a minimum wait.
    """
    delays: List[float] = []
    attempt = 0
    while True:
        attempt += 1
        retry_after: Optional[float] = None
        try:
            envelope = fn(attempt)
        except TransportError as exc:
            envelope = {"status": "error", "error": {"code": exc.code, "message": "transport failure", "field": None}}
            retry_after = exc.retry_after_seconds
        if envelope.get("status") != "error":
            return RetryOutcome(envelope, attempt, delays)
        rule = classify(envelope["error"].get("code"))
        used = attempt - 1
        limit = min(rule.max_retries, policy.max_retries)
        if limit == 0:
            return RetryOutcome(envelope, attempt, delays, "not_retryable")
        if used >= limit:
            return RetryOutcome(envelope, attempt, delays, "retries_exhausted")
        wait = backoff_delay(used + 1, policy, rng)
        if retry_after is not None:
            wait = max(wait, retry_after)
        if sum(delays) + wait > policy.total_wait_budget_s:
            return RetryOutcome(envelope, attempt, delays, "wait_budget_exhausted")
        delays.append(wait)
        sleep(wait)


def canonical_request_hash(op_id: str, body: Any) -> str:
    """Stable fingerprint of an operation and its body: same meaning -> same hash, whatever the key order or spacing."""
    text = json.dumps({"op": op_id, "body": body}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class IdempotencyStore:
    """Reference implementation of Idempotency-Key handling (a real one lives in a shared cache with a TTL; 24 h PROPOSED).

    begin() -> "new" (go ahead) | "replay" (return the stored response) | "in_progress" | "conflict" (same key, different body).
    """

    def __init__(self) -> None:
        self._entries: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def begin(self, tenant: str, key: str, op_id: str, body: Any) -> Tuple[str, Optional[Dict[str, Any]]]:
        if not key or len(key) > 128:
            raise ValueError("Idempotency-Key must be 1-128 characters")
        fingerprint = canonical_request_hash(op_id, body)
        entry = self._entries.get((tenant, key))
        if entry is None:
            self._entries[(tenant, key)] = {"fingerprint": fingerprint, "response": None}
            return "new", None
        if entry["fingerprint"] != fingerprint:
            return "conflict", None
        if entry["response"] is None:
            return "in_progress", None
        return "replay", copy.deepcopy(entry["response"])

    def complete(self, tenant: str, key: str, response: Dict[str, Any]) -> None:
        self._entries[(tenant, key)]["response"] = copy.deepcopy(response)


# ======================================================================================================================
# 4. Job state machine (Day 16, unchanged)
# ======================================================================================================================
JOB_STATES = ("queued", "running", "completed", "failed", "cancelled")
JOB_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "queued": ("running", "cancelled"),
    "running": ("completed", "failed", "cancelled"),
    "completed": (), "failed": (), "cancelled": (),
}
MAX_JOB_ATTEMPTS = 3         # PROPOSED: attempts happen INSIDE `running`; the state machine gains no new state


def can_transition(current: str, new: str) -> bool:
    return new in JOB_TRANSITIONS.get(current, ())


# ======================================================================================================================
# 5. Schemas, built from the code
# ======================================================================================================================
def _ref(name: str) -> Dict[str, str]:
    return {"$ref": f"#/$defs/{name}"}


def _obj(props: Dict[str, Any], required: Sequence[str] = (), strict: bool = True, **extra: Any) -> Dict[str, Any]:
    d: Dict[str, Any] = {"type": "object", "properties": props}
    if required:
        d["required"] = list(required)
    d["additionalProperties"] = not strict         # requests are strict; responses stay open so new fields do not break clients
    d.update(extra)
    return d


STR: Dict[str, Any] = {"type": "string"}
NSTR: Dict[str, Any] = {"type": ["string", "null"]}
BOOL: Dict[str, Any] = {"type": "boolean"}
NUM: Dict[str, Any] = {"type": "number"}
NNUM: Dict[str, Any] = {"type": ["number", "null"]}
INT: Dict[str, Any] = {"type": "integer", "minimum": 0}
NINT: Dict[str, Any] = {"type": ["integer", "null"]}
SCORE: Dict[str, Any] = {"type": "number", "minimum": 0, "maximum": 100}
STRS: Dict[str, Any] = {"type": "array", "items": STR}
ISO_DATE: Dict[str, Any] = {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"}
ISO_TS: Dict[str, Any] = {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"}


def _text(max_chars: int = MAX_TEXT_CHARS, non_blank: bool = False) -> Dict[str, Any]:
    d: Dict[str, Any] = {"type": "string", "maxLength": max_chars}
    if non_blank:
        d["pattern"] = r"\S"
    return d


def _envelope(service_name: str) -> Dict[str, Any]:
    return {"service": {"const": service_name}, "model_version": STR, "api_version": {"const": API_VERSION}, "status": {"const": "success"}}


def _result(service_name: str, props: Dict[str, Any], required: Sequence[str]) -> Dict[str, Any]:
    base = _envelope(service_name)
    return _obj({**base, **props}, ["service", "model_version", "api_version", "status", *required], strict=False)


def build_schemas() -> Dict[str, Any]:
    """The `$defs` for every request and response. Enum values and limits are read from the code, not typed in a second time."""
    from parsers.cross_round_aggregation_engine import ats_zone_of  # noqa: F401  (documents where the zone values come from)
    from parsers.final_recommendation_engine import DecisionOutcome, HoldKind
    from parsers.hr_interview_question_bank import ExperienceLevel, RoleType
    from parsers.technical_interview_question_bank import DifficultyTier, TechnicalDomain
    from scoring.service import ROUND_KEYS, ZONES

    role_types = [r.value for r in RoleType]
    levels = [e.value for e in ExperienceLevel]
    domains = [d.value for d in TechnicalDomain]
    outcomes = [o.value for o in DecisionOutcome]
    hold_kinds = [h.value for h in HoldKind]
    tiers = [t.value for t in DifficultyTier]
    score_keys = list(ROUND_KEYS.values())
    candidate_id = {"type": "string", "pattern": CANDIDATE_ID_PATTERN,
                    "description": "The PSEUDONYMOUS candidate reference (Day 55 `cref_...`), never a name or an email."}

    d: Dict[str, Any] = {}
    # -- shared -----------------------------------------------------------------------------------------------------------
    d["ErrorCode"] = {"type": "string", "enum": list(ERROR_CODES)}
    d["ErrorBody"] = _obj({"code": _ref("ErrorCode"), "message": STR, "field": NSTR}, ["code", "message"], strict=False)
    d["ErrorResponse"] = _obj({
        "service": STR, "model_version": STR, "api_version": STR, "status": {"const": "error"}, "error": _ref("ErrorBody"),
        "request_id": STR, "retryable": BOOL, "retry_after_seconds": NNUM,
    }, ["api_version", "status", "error", "request_id", "retryable"], strict=False)
    d["ServiceErrorEnvelope"] = _obj({
        "service": STR, "model_version": STR, "api_version": STR, "status": {"const": "error"}, "error": _ref("ErrorBody"),
    }, ["api_version", "status", "error"], strict=False)
    d["Warnings"] = STRS
    # -- resume parsing ---------------------------------------------------------------------------------------------------
    d["ParseResumeRequest"] = _obj({
        "candidate_id": candidate_id,
        "file_ref": {"type": "string", "minLength": 1, "maxLength": 512, "description": "A key inside the resume store."},
        "file_type": {"enum": ["pdf", "docx"]},
        "as_of_date": {**ISO_DATE, "description": "What 'Present' means for a current job. Pin it for repeatable results."},
    }, ["candidate_id", "file_ref", "file_type"])
    d["ParseResumeResult"] = _result("resume_parsing_service", {
        "candidate_id": STR, "file_type": {"enum": ["pdf", "docx"]}, "as_of_date": ISO_DATE, "has_text": BOOL, "line_count": INT,
        "detected_sections": STRS,
        "cleaned_text": {"type": "string", "description": "CONTAINS PERSONAL DATA (it is the resume). Never log it."},
        "skills": {"type": "array", "items": _obj({
            "name": STR, "group": STR, "category": STR, "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "method": STR, "mentions": STRS}, ["name", "confidence"], strict=False)},
        "experience": _obj({
            "total_years": {"type": "number", "minimum": 0}, "total_months": INT,
            "entries": {"type": "array", "items": _obj({
                "title": STR, "company": STR, "start_year": INT, "start_month": {"type": "integer", "minimum": 1, "maximum": 12},
                "end_year": NINT, "end_month": NINT, "is_current": BOOL, "description": STR},
                ["title", "company", "start_year", "start_month", "is_current"], strict=False)},
            "gaps": {"type": "array", "items": _obj({"start": ISO_DATE, "end": ISO_DATE}, ["start", "end"], strict=False)},
            "overlap_count": INT}, ["total_years", "total_months", "entries"], strict=False),
        "education": {"type": "array", "items": _obj({
            "raw_degree": STR, "degree": STR, "level": NSTR, "field_of_study": NSTR, "institution": STR, "year": INT},
            ["degree", "institution", "year"], strict=False)},
        "certifications": {"type": "array", "items": _obj({"name": STR, "issuer": NSTR, "year": NINT, "category": STR}, ["name"], strict=False)},
        "warnings": _ref("Warnings"),
    }, ["candidate_id", "file_type", "as_of_date", "has_text", "cleaned_text", "skills", "experience", "education",
        "certifications", "warnings"])
    # -- ATS --------------------------------------------------------------------------------------------------------------
    d["ATSScoreRequest"] = _obj({
        "resume_text": _text(),
        "job_description": _text(non_blank=True),
        "job_requirements": {"type": "array", "items": STR, "maxItems": MAX_ITEMS, "deprecated": True,
                             "description": "DEPRECATED keyword-coverage mode: the result is NOT an ATS score."},
    }, [], anyOf=[{"required": ["job_description"]}, {"required": ["job_requirements"]}])
    zone = {"enum": list(ZONES)}
    d["ATSScoreEngineResult"] = _result("ats_ai_service", {
        "scoring_mode": {"const": "ats_engine"}, "ats_score": SCORE, "zone": zone, "role_category": STR,
        "components": {"type": "array", "items": _obj({"name": STR, "score": NNUM, "available": BOOL}, ["name", "available"], strict=False)},
        "warnings": _ref("Warnings")}, ["scoring_mode", "ats_score", "zone", "components", "warnings"])
    d["ATSScoreKeywordResult"] = _result("ats_ai_service", {
        "scoring_mode": {"const": "keyword_coverage"}, "ats_score": SCORE, "matched_keywords": STRS, "warnings": _ref("Warnings")},
        ["scoring_mode", "ats_score", "matched_keywords", "warnings"])
    d["ATSScoreResult"] = {"oneOf": [_ref("ATSScoreEngineResult"), _ref("ATSScoreKeywordResult")]}
    d["ATSBatchScoreRequest"] = _obj({
        "job_description": _text(non_blank=True),
        "candidates": {"type": "array", "minItems": 1, "maxItems": MAX_ITEMS, "items": _obj(
            {"candidate_id": candidate_id, "resume_text": _text()}, ["candidate_id", "resume_text"])},
    }, ["job_description", "candidates"])
    d["ATSBatchScoreResult"] = _result("ats_batch_service", {
        "scoring_basis": {"const": "per_pair"}, "total": INT, "succeeded": INT, "failed": INT,
        "results": {"type": "array", "items": _obj({"candidate_id": STR, "outcome": {"oneOf": [_ref("ATSScoreResult"), _ref("ServiceErrorEnvelope")]}},
                                                   ["candidate_id", "outcome"], strict=False)},
        "warnings": _ref("Warnings")}, ["scoring_basis", "total", "succeeded", "failed", "results"])
    # -- screening --------------------------------------------------------------------------------------------------------
    d["ScreeningScoreRequest"] = _obj({
        "candidate_id": candidate_id, "job_role": {"type": "string", "maxLength": 200},
        "turns": {"type": "array", "maxItems": MAX_ITEMS, "items": _obj({
            "text": _text(MAX_ANSWER_CHARS), "confidence": {"type": "number", "minimum": 0, "maximum": 1}, "is_silent": BOOL}, ["text"])},
    })
    d["ScreeningScoreResult"] = _result("screening_ai_service", {
        "candidate_id": NSTR, "call_status": {"enum": ["not_started", "completed", "incomplete", "ended_early"]},
        "screening_score": NNUM, "categories_answered": STRS, "categories_missing": STRS, "turns_used": INT,
        "warnings": _ref("Warnings")}, ["call_status", "screening_score", "categories_answered", "categories_missing", "turns_used"])
    # -- interviews -------------------------------------------------------------------------------------------------------
    d["InterviewScoreRequest"] = _obj({
        "interview_type": {"enum": ["hr", "technical"]},
        "answers": {"type": "array", "maxItems": MAX_ITEMS, "items": _text(MAX_ANSWER_CHARS)},
        "role_type": {"enum": role_types}, "experience_level": {"enum": levels},
        "domain": {"enum": domains}, "experience_years": {"type": "number", "minimum": 0, "maximum": 60},
    }, [], allOf=[{"if": {"properties": {"interview_type": {"const": "technical"}}, "required": ["interview_type"]},
                   "then": {"required": ["experience_years"]}}])
    d["HRInterviewResult"] = _result("interview_intelligence_service", {
        "interview_type": {"const": "hr"}, "interview_status": {"enum": ["not_started", "scored"]}, "hr_score": NNUM,
        "communication_score": NNUM, "technical_score": NNUM, "relevance_score": NNUM, "confidence_score": NNUM,
        "answers_scored": INT, "answers_ignored": INT, "non_substantive_answers": INT, "warnings": _ref("Warnings")},
        ["interview_type", "interview_status", "hr_score", "answers_scored", "answers_ignored"])
    d["TechnicalInterviewResult"] = _result("interview_intelligence_service", {
        "interview_type": {"const": "technical"}, "tier": {"enum": tiers}, "interview_status": {"enum": ["not_started", "scored"]},
        "technical_score": NNUM, "communication_score": NNUM, "answers_scored": INT, "answers_ignored": INT,
        "warnings": _ref("Warnings")}, ["interview_type", "tier", "interview_status", "technical_score", "answers_scored", "answers_ignored"])
    d["InterviewScoreResult"] = {"oneOf": [_ref("HRInterviewResult"), _ref("TechnicalInterviewResult")]}
    # -- decision ---------------------------------------------------------------------------------------------------------
    score_props = {k: SCORE for k in score_keys}
    d["DecisionRequest"] = _obj({
        "candidate_id": candidate_id, "role_type": {"enum": role_types}, "experience_level": {"enum": levels},
        "ats_zone": {"enum": list(ZONES)}, **score_props,
        "communication_score": {**SCORE, "deprecated": True, "description": "Legacy alias of hr_interview_score."},
        "behavior_score": {**SCORE, "deprecated": True, "description": "Ignored: there is no behaviour round."},
    }, [], anyOf=[{"required": [k]} for k in [*score_keys, "communication_score"]])
    d["DecisionResult"] = _result("decision_scoring_service", {
        "candidate_id": NSTR, "hiring_fit_score": SCORE, "decision": {"enum": outcomes},
        "hold_kind": {"enum": [*hold_kinds, None]}, "confidence": NNUM, "provisional": BOOL, "missing_rounds": STRS,
        "human_review_required": BOOL, "human_review_reasons": STRS, "human_confirmation_required": BOOL,
        "automation_eligible": BOOL, "automated_action": STR, "reasons": STRS, "warnings": _ref("Warnings")},
        ["hiring_fit_score", "decision", "human_confirmation_required", "automated_action", "reasons"])
    # -- jobs and health --------------------------------------------------------------------------------------------------
    job_id = {"type": "string", "pattern": r"^job_[A-Za-z0-9]{8,40}$"}
    d["JobAccepted"] = _obj({"job_id": job_id, "operation": {"enum": [o.op_id for o in OPERATIONS if o.mode == Mode.ASYNC]},
                             "status": {"const": "queued"}, "created_at": ISO_TS, "retry_after_seconds": NNUM},
                            ["job_id", "operation", "status", "created_at"], strict=False)
    d["JobStatus"] = _obj({
        "job_id": job_id, "operation": {"enum": [o.op_id for o in OPERATIONS if o.mode == Mode.ASYNC]}, "status": {"enum": list(JOB_STATES)},
        "attempts": INT, "max_attempts": {"type": "integer", "minimum": 1}, "created_at": ISO_TS,
        "started_at": {"anyOf": [ISO_TS, {"type": "null"}]}, "completed_at": {"anyOf": [ISO_TS, {"type": "null"}]},
        "result": {"anyOf": [_ref("ParseResumeResult"), _ref("ATSBatchScoreResult"), {"type": "null"}]},
        "error": {"anyOf": [_ref("ErrorBody"), {"type": "null"}]},
    }, ["job_id", "operation", "status", "attempts", "max_attempts", "created_at", "result", "error"], strict=False, allOf=[
        {"if": {"properties": {"status": {"const": "completed"}}, "required": ["status"]},
         "then": {"properties": {"result": {"not": {"type": "null"}}, "error": {"type": "null"}}}},
        {"if": {"properties": {"status": {"const": "failed"}}, "required": ["status"]},
         "then": {"properties": {"error": {"not": {"type": "null"}}, "result": {"type": "null"}}}},
        {"if": {"properties": {"status": {"enum": ["queued", "running", "cancelled"]}}, "required": ["status"]},
         "then": {"properties": {"result": {"type": "null"}}}},
    ])
    d["HealthResponse"] = _obj({"status": {"enum": ["ok", "degraded"]}, "api_version": STR, "model_version": STR,
                                "services": {"type": "object", "additionalProperties": {"enum": ["ok", "down"]}}},
                               ["status", "api_version"], strict=False)
    return d


def schema_document() -> Dict[str, Any]:
    """The standalone JSON Schema file (`schemas/integration_api_schemas.json`)."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://zecpath.ai/schemas/integration_api_schemas.json",
        "title": "Zecpath AI integration API schemas",
        "description": "Request and response schemas for the AI APIs (Day 59). GENERATED by parsers/integration_contract.py from the "
                       "code's own enums and limits: do not edit by hand; run run_day59_integration_demo.py to regenerate.",
        "contract_version": CONTRACT_VERSION,
        "$defs": build_schemas(),
    }


def _rewrite_refs(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: (v.replace("#/$defs/", "#/components/schemas/") if k == "$ref" and isinstance(v, str) else _rewrite_refs(v))
                for k, v in node.items()}
    if isinstance(node, list):
        return [_rewrite_refs(v) for v in node]
    return node


def build_openapi() -> Dict[str, Any]:
    """OpenAPI 3.1 (whose schemas ARE JSON Schema 2020-12) generated from OPERATIONS and the schemas above."""
    schemas = _rewrite_refs(build_schemas())
    common = {"400": "Not a JSON object", "401": "Missing or invalid service token", "403": "Token lacks the scope", "413": "Too large",
              "422": "Invalid field", "429": "Rate limited", "500": "Internal error", "503": "Unavailable", "504": "Timeout"}
    responses = {code: {"description": text, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}}}
                 for code, text in {**common, "404": "Not found", "409": "Conflict", "415": "Unsupported file type"}.items()}
    paths: Dict[str, Any] = {}
    for op in OPERATIONS:
        params: List[Dict[str, Any]] = [{"name": "X-Request-Id", "in": "header", "required": False, "schema": {"type": "string", "maxLength": 128}}]
        if "{job_id}" in op.path:
            params.append({"name": "job_id", "in": "path", "required": True, "schema": _rewrite_refs(build_schemas()["JobStatus"]["properties"]["job_id"])})
        if op.idempotency != "n/a":
            params.append({"name": "Idempotency-Key", "in": "header", "required": op.idempotency == "required",
                           "schema": {"type": "string", "minLength": 1, "maxLength": 128}})
        body_schema = op.response_schema if op.mode == Mode.SYNC else "JobAccepted"
        item: Dict[str, Any] = {
            "operationId": op.op_id, "summary": op.summary, "parameters": params,
            "x-mode": op.mode.value, "x-implementation": op.implementation or None, "x-status": STATUS_OF[op.op_id].value,
            "x-timeout-seconds": op.timeout_s, "x-max-body-bytes": op.max_body_bytes,
            "x-async-result-schema": op.response_schema if op.mode == Mode.ASYNC else None,
            "responses": {str(op.success_status): {"description": "OK" if op.mode == Mode.SYNC else "Accepted; poll GET /jobs/{job_id}",
                                                   "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{body_schema}"}}}}},
        }
        item = {k: v for k, v in item.items() if v is not None}
        codes = ["400", "422", "413", "429", "500", "503", "504"] if op.scope else []
        if op.scope:
            codes += ["401", "403"]
            item["security"] = [{"serviceToken": [op.scope]}]
        else:
            item["security"] = []
        codes += [str(c) for c in op.extra_errors]
        for c in sorted(set(codes)):
            item["responses"][c] = {"$ref": f"#/components/responses/E{c}"}
        if op.request_schema:
            item["requestBody"] = {"required": True, "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{op.request_schema}"}}}}
        paths.setdefault(op.path, {})[op.method.lower()] = item
    return {
        "openapi": "3.1.0",
        "info": {"title": "Zecpath AI Integration API", "version": CONTRACT_VERSION,
                 "description": "GENERATED from parsers/integration_contract.py (Day 59). A PLAN, not a deployed service: the gateway, queue "
                                "and job store do not exist yet. Timeouts, limits and token lifetimes are PROPOSED."},
        "servers": [{"url": "https://ai.zecpath.example.com" + API_PREFIX, "description": "Placeholder, not deployed"}],
        "paths": paths,
        "components": {
            "securitySchemes": {"serviceToken": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT",
                                                 "description": "Short-lived service token (client credentials over mTLS); scopes per operation."}},
            "schemas": schemas,
            "responses": {f"E{k}": v for k, v in responses.items()},
        },
    }


# ======================================================================================================================
# 6. Gateway request validation
# ======================================================================================================================
def _validator_for(schema_name: str):
    import jsonschema
    return jsonschema.Draft202012Validator({"$ref": f"#/$defs/{schema_name}", "$defs": build_schemas()},
                                           format_checker=jsonschema.FormatChecker())


_VALIDATORS: Dict[str, Any] = {}


def _path_to_field(path: Sequence[Any]) -> Optional[str]:
    out = ""
    for p in path:
        out += f"[{p}]" if isinstance(p, int) else (f".{p}" if out else str(p))
    return out or None


def _schema_error_code(err: Any) -> str:
    """Map a JSON-Schema failure to the SAME code the service would give for that fault."""
    v = err.validator
    last = str(err.absolute_path[-1]) if err.absolute_path else ""
    if not err.absolute_path and v == "type":
        return "invalid_payload"
    if v in ("required", "anyOf"):
        return "missing_field"
    if v in ("enum", "const"):
        return "unsupported_value"
    if v in ("maxLength", "maxItems"):
        return "too_large"
    if v in ("type", "minimum", "maximum") and last.endswith("score"):
        return "invalid_score"
    return "invalid_input"


def _first_error(errors: List[Any]) -> Any:
    return sorted(errors, key=lambda e: (len(list(e.absolute_path)), [str(p) for p in e.absolute_path], e.validator))[0]


def validate_request(op_id: str, body: Any) -> Optional[Dict[str, Any]]:
    """Check a request body against its schema. None = acceptable; otherwise an ERROR ENVELOPE in the services' own vocabulary."""
    op = OPERATION_BY_ID[op_id]
    if not op.request_schema:
        return None
    validator = _VALIDATORS.setdefault(op.request_schema, _validator_for(op.request_schema))
    errors = list(validator.iter_errors(body))
    if not errors:
        return None
    err = _first_error(errors)
    code = _schema_error_code(err)
    field_name = _path_to_field(list(err.absolute_path))
    if err.validator == "required":
        missing = err.message.split("'")[1] if "'" in err.message else None
        field_name = _path_to_field([*err.absolute_path, missing]) if missing else field_name
    elif err.validator == "anyOf":
        first_required = (err.validator_value[0].get("required") or [None])[0]
        field_name = _path_to_field([*err.absolute_path, first_required]) if first_required else field_name
    return {"service": GATEWAY_SERVICE_NAME, "model_version": MODEL_VERSION, "api_version": API_VERSION, "status": "error",
            "error": {"code": code, "message": err.message[:300], "field": field_name}}


def validate_response(schema_name: str, body: Any) -> List[str]:
    """Problems found when checking a response body against its schema ([] = valid)."""
    validator = _VALIDATORS.setdefault(schema_name, _validator_for(schema_name))
    return [f"{_path_to_field(list(e.absolute_path)) or '<root>'}: {e.message[:160]}" for e in validator.iter_errors(body)]


def declared_keys(schema_name: str) -> frozenset:
    """Top-level property names a response schema declares (all branches of a oneOf), for the 'no undeclared key' check."""
    schema = build_schemas()[schema_name]
    branches = [schema] if "properties" in schema else [build_schemas()[b["$ref"].split("/")[-1]] for b in schema.get("oneOf", [])]
    return frozenset(k for b in branches for k in b.get("properties", {}))


def worst_case_bytes(schema_name: str) -> int:
    """Largest request the schema allows, in UTF-8 bytes (4 per character): shows what the item limits add up to."""
    defs = build_schemas()

    def size(node: Dict[str, Any]) -> int:
        if "$ref" in node:
            return size(defs[node["$ref"].split("/")[-1]])
        t = node.get("type")
        if t == "string" or (isinstance(t, list) and "string" in t):
            return node.get("maxLength", 64) * 4
        if t == "array":
            return node.get("maxItems", MAX_ITEMS) * size(node.get("items", {}))
        if t == "object":
            return sum(size(v) for v in node.get("properties", {}).values())
        return 16

    return size(defs[schema_name])


# ======================================================================================================================
# 7. Data-access check against the real Day 55 matrix
# ======================================================================================================================
@dataclass(frozen=True)
class AccessCheck:
    op_id: str
    touch: DataTouch
    allowed: Optional[bool]          # None = the resource is not modelled in Day 55
    rule_id: str

    @property
    def key(self) -> Tuple[str, str, str]:
        return (self.op_id, self.touch.label, self.touch.action.value)


# Each is a REAL finding from running the plan through the Day 55 code. The test pins this set exactly, so fixing one (or finding a new one)
# forces the plan and the document to be updated.
KNOWN_GAPS: Dict[Tuple[str, str, str], str] = {
    ("parse_resume", "resume", "write"): "G1: the Day 55 role matrix lets the service READ a resume but not WRITE one, and has no resource type for parsed fields (skills, experience, education).",
    ("score_ats", "job_store", "read"): "G2: job descriptions are not a Day 55 resource type, and the storage plan has no job store.",
    ("score_ats_batch", "job_store", "read"): "G2: job descriptions are not a Day 55 resource type, and the storage plan has no job store.",
}
UNMODELLED_STORES = frozenset({"job_store"})


def check_data_access(operations: Sequence[Operation] = OPERATIONS, controller: Optional[AccessController] = None) -> List[AccessCheck]:
    """Run every data touch through the real AccessController as the backend's service role."""
    controller = controller or AccessController()
    actor = Actor("ai-backend-worker", Role.SERVICE)
    checks: List[AccessCheck] = []
    for op in operations:
        for t in op.touches:
            if t.resource is None:
                checks.append(AccessCheck(op.op_id, t, None, "NOT_MODELLED"))
                continue
            decision = controller.decide(actor, t.action, Resource(t.resource, candidate_ref="cref_example", company_id="co_example"))
            checks.append(AccessCheck(op.op_id, t, decision.allowed, decision.rule_id))
    return checks


def known_store_ids() -> frozenset:
    return frozenset(s.store_id for s in build_default_plan().stores) | UNMODELLED_STORES


# ======================================================================================================================
# 8. Security plan values that code can check (PROPOSED unless noted)
# ======================================================================================================================
SERVICE_TOKEN_LIFETIME_S = 300
USER_TOKEN_LIFETIME_S = 900
IDEMPOTENCY_TTL_S = 86_400
WEBHOOK_SIGNATURE = "HMAC-SHA256 over '<timestamp>.<body>' with a per-tenant secret; reject if the timestamp is more than 5 minutes old"
