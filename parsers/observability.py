"""
Observability (Day 61): structured logs, metrics, and an observer that wraps a service call

WHAT THIS DAY BUILDS. The brief is a design day ("enable tracking, debugging and performance monitoring of AI systems"). This module is the
part of the design that can be run and tested, so the plan does not rest on promises:

  1. StructuredLogger   emits ONE JSON line per event, in a fixed envelope, for three kinds of event: `api_request`, `model_output` and `error`.
                        It is built around what must NOT be logged. Every event field is on an allowlist; a forbidden key (the Day 55 list:
                        text, answers, name, email ...), an unlisted key, or a long string is refused and counted, never written.
  2. MetricsRegistry    counters, gauges and histograms with a hard limit on label combinations (a label that takes a new value per candidate would
                        blow up a metrics store), and Prometheus text output.
  3. ServiceObserver    calls any Day 57 service's run(payload), times it, and emits the events and metrics for that call. It never changes the
                        response and never lets a logging problem break a request.

THE RULE THAT SHAPES EVERYTHING: logs are an uncontrolled copy. They are shipped, indexed, searched by engineers and kept for weeks, so they
must never hold what the audit log is forbidden to hold (resume text, answers, transcripts, names, contact details). Model outputs are
logged as NUMBERS AND CODES chosen from a per-operation allowlist, never by "log the whole response". What a service returns that is not on
the list (the cleaned resume text, a reason sentence) never leaves the process.

WHAT IT IS NOT. There is no log shipper, metrics server, alert manager or dashboard tool in this project: the sink is any callable (the demo
writes a file). Retention periods, sampling rates and thresholds are PROPOSED. The overhead figure comes from the demo on one machine.
"""

from __future__ import annotations

import json
import math
import threading
import time
import uuid
from bisect import bisect_left
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from parsers.audit_trail import FORBIDDEN_PAYLOAD_KEYS, MAX_STRING_VALUE_LEN
from parsers.final_recommendation_engine import DecisionOutcome, HoldKind
from parsers.integration_contract import ERROR_RULES, OPERATION_BY_ID
from scoring.service import ZONES as ZONES_FOR_LABELS
from utils.base_service import API_VERSION

LOG_SCHEMA_VERSION = "1.0"
EVENT_KINDS = ("api_request", "model_output", "error")
LEVELS = {"api_request": "INFO", "model_output": "INFO", "error": "ERROR"}

# Envelope: present on every event. Values are short codes, numbers or pseudonymous references; never content.
ENVELOPE_FIELDS = frozenset({"schema_version", "ts", "event", "level", "request_id", "op_id", "service", "model_version", "api_version", "tenant_ref",
                             "candidate_ref", "tier"})
# Fields allowed per event kind (in addition to the envelope).
EVENT_FIELDS: Dict[str, frozenset] = {
    "api_request": frozenset({"status", "http_status", "error_code", "error_class", "duration_ms", "input_chars", "warnings", "mode", "retry_attempt"}),
    "model_output": frozenset({"outputs"}),
    "error": frozenset({"error_code", "error_class", "http_status", "field", "retryable", "exception_type", "duration_ms"}),
}

# What may leave the process from each operation's response. Everything else in the response stays out of the logs.
# Each value is a source field: copied as is when a number, a boolean, or a short code; lists are logged as their LENGTH.
MODEL_OUTPUT_ALLOWLIST: Dict[str, Tuple[str, ...]] = {
    "parse_resume": ("file_type", "has_text", "line_count", "detected_sections", "skills", "education", "certifications", "warnings"),
    "score_ats": ("scoring_mode", "ats_score", "zone", "role_category", "warnings"),
    "score_ats_batch": ("scoring_basis", "total", "succeeded", "failed", "warnings"),
    "score_screening": ("call_status", "screening_score", "categories_answered", "categories_missing", "turns_used", "warnings"),
    "score_interview": ("interview_type", "interview_status", "tier", "hr_score", "technical_score", "communication_score", "relevance_score", "confidence_score",
                        "answers_scored", "answers_ignored", "non_substantive_answers", "warnings"),
    "recommend_decision": ("hiring_fit_score", "decision", "hold_kind", "confidence", "provisional", "missing_rounds", "human_review_required",
                           "human_confirmation_required", "automation_eligible", "automated_action", "human_review_reasons", "warnings"),
}
# Numbers inside the nested structures that are safe to log as plain numbers (experience years, not skills' names).
NESTED_NUMBERS = {"parse_resume": {"experience": ("total_years", "total_months")}}


class LogPolicyError(ValueError):
    """An event would put personal content, an unlisted field or an unbounded string into a log."""


def _is_short_code(value: Any) -> bool:
    return isinstance(value, str) and len(value) <= 64 and "\n" not in value


def check_event(event: Mapping[str, Any]) -> None:
    """Refuse anything that is not an allowlisted field holding a number, boolean, null, short code or (for outputs) a flat mapping of those."""
    kind = event.get("event")
    if kind not in EVENT_KINDS:
        raise LogPolicyError(f"unknown event kind {kind!r}")
    allowed = ENVELOPE_FIELDS | EVENT_FIELDS[kind]
    for key, value in event.items():
        if str(key).lower() in FORBIDDEN_PAYLOAD_KEYS:
            raise LogPolicyError(f"forbidden key {key!r}: logs hold codes and numbers, not content")
        if key not in allowed:
            raise LogPolicyError(f"field {key!r} is not allowed in a {kind} event")
        _check_value(value, key)


def _check_value(value: Any, path: str, depth: int = 0) -> None:
    if value is None or isinstance(value, (bool, int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise LogPolicyError(f"non-finite number at {path}")
        return
    if isinstance(value, str):
        if len(value) > min(MAX_STRING_VALUE_LEN, 64):
            raise LogPolicyError(f"string at {path} is {len(value)} characters: looks like free text")
        return
    if isinstance(value, Mapping) and depth < 2:
        for k, v in value.items():
            if str(k).lower() in FORBIDDEN_PAYLOAD_KEYS:
                raise LogPolicyError(f"forbidden key {k!r} at {path}")
            _check_value(v, f"{path}.{k}", depth + 1)
        return
    raise LogPolicyError(f"value at {path} has type {type(value).__name__}, which is not allowed in a log event")


# ======================================================================================================================
# Structured logger
# ======================================================================================================================
class StructuredLogger:
    """JSON-lines logger. `sink` receives one string per event. `sample` maps an event kind to the fraction kept (errors are never sampled)."""

    def __init__(self, sink: Callable[[str], None], sample: Optional[Mapping[str, float]] = None, clock: Callable[[], datetime] = None,
                 on_drop: Optional[Callable[[str], None]] = None) -> None:
        self._sink = sink
        self._sample = dict(sample or {})
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._on_drop = on_drop or (lambda reason: None)
        self._acc: Dict[str, float] = {}
        self._lock = threading.Lock()
        self.dropped: Dict[str, int] = {}
        self.written = 0

    def _drop(self, reason: str) -> None:
        with self._lock:
            self.dropped[reason] = self.dropped.get(reason, 0) + 1
        self._on_drop(reason)

    def emit(self, kind: str, **fields: Any) -> Optional[Dict[str, Any]]:
        """Write one event, or drop it (and count why). Never raises: a logging problem must not break the request that caused it."""
        try:
            fraction = 1.0 if kind == "error" else self._sample.get(kind, 1.0)
            if fraction < 1.0:                                              # deterministic 1-in-N sampling: keep when the running total crosses 1
                with self._lock:
                    self._acc[kind] = self._acc.get(kind, 0.0) + max(0.0, fraction)
                    keep = self._acc[kind] >= 1.0
                    if keep:
                        self._acc[kind] -= 1.0
                if not keep:
                    return None
            event = {"schema_version": LOG_SCHEMA_VERSION, "ts": self._clock().astimezone(timezone.utc).isoformat(timespec="milliseconds"),
                     "event": kind, "level": LEVELS.get(kind, "INFO"), **{k: v for k, v in fields.items() if v is not None or k in ("error_code",)}}
            check_event(event)
            line = json.dumps(event, sort_keys=True, separators=(",", ":"))
            self._sink(line)
            with self._lock:
                self.written += 1
            return event
        except LogPolicyError:
            self._drop("policy_violation")
        except Exception:                                                   # noqa: BLE001  (a sink failure must not reach the caller either)
            self._drop("sink_error")
        return None


# ======================================================================================================================
# Metrics
# ======================================================================================================================
LATENCY_BUCKETS_S = (0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
SCORE_BUCKETS = tuple(float(x) for x in range(10, 101, 10))
MAX_LABEL_SETS = 200
OVERFLOW = "__overflow__"


class MetricsRegistry:
    """Counters, gauges and histograms. Every metric declares its label NAMES up front; a metric may hold at most MAX_LABEL_SETS distinct label
    combinations, after which new ones are folded into one overflow series and counted, so a mistake cannot create millions of series."""

    def __init__(self, max_label_sets: int = MAX_LABEL_SETS) -> None:
        self._defs: Dict[str, Dict[str, Any]] = {}
        self._values: Dict[str, Dict[Tuple[str, ...], Any]] = {}
        self._max = max_label_sets
        self._lock = threading.Lock()
        self.overflowed: Dict[str, int] = {}

    def define(self, name: str, kind: str, labels: Sequence[str] = (), help: str = "", buckets: Optional[Sequence[float]] = None) -> None:
        if kind not in ("counter", "gauge", "histogram"):
            raise ValueError(f"unknown metric kind {kind!r}")
        if kind == "histogram" and not buckets:
            raise ValueError("a histogram needs buckets")
        with self._lock:
            self._defs[name] = {"kind": kind, "labels": tuple(labels), "help": help, "buckets": tuple(sorted(buckets)) if buckets else None}
            self._values.setdefault(name, {})

    def _key(self, name: str, labels: Mapping[str, Any]) -> Tuple[str, ...]:
        d = self._defs[name]
        if set(labels) != set(d["labels"]):
            raise ValueError(f"{name} takes labels {list(d['labels'])}, got {sorted(labels)}")
        key = tuple(str(labels[l]) for l in d["labels"])
        series = self._values[name]
        if key not in series and len(series) >= self._max:
            self.overflowed[name] = self.overflowed.get(name, 0) + 1
            key = tuple(OVERFLOW for _ in d["labels"])
        return key

    def inc(self, name: str, amount: float = 1.0, **labels: Any) -> None:
        if amount < 0:
            raise ValueError("a counter cannot decrease")
        with self._lock:
            key = self._key(name, labels)
            self._values[name][key] = self._values[name].get(key, 0.0) + amount

    def set(self, name: str, value: float, **labels: Any) -> None:
        with self._lock:
            self._values[name][self._key(name, labels)] = float(value)

    def observe(self, name: str, value: float, **labels: Any) -> None:
        with self._lock:
            d = self._defs[name]
            key = self._key(name, labels)
            h = self._values[name].setdefault(key, {"counts": [0] * (len(d["buckets"]) + 1), "sum": 0.0, "count": 0})
            h["counts"][bisect_left(d["buckets"], value)] += 1
            h["sum"] += value
            h["count"] += 1

    def get(self, name: str, **labels: Any) -> Any:
        with self._lock:
            return self._values[name].get(self._key(name, labels))

    def quantile(self, name: str, q: float, **labels: Any) -> Optional[float]:
        """Estimate a quantile from histogram buckets (linear inside the bucket the rank falls in). Accurate to the bucket width."""
        h = self.get(name, **labels)
        if not h or not h["count"]:
            return None
        buckets = self._defs[name]["buckets"]
        rank = q * h["count"]
        seen = 0
        for i, c in enumerate(h["counts"]):
            if seen + c >= rank and c:
                lower = 0.0 if i == 0 else buckets[i - 1]
                upper = buckets[i] if i < len(buckets) else buckets[-1]
                return lower + (upper - lower) * ((rank - seen) / c)
            seen += c
        return buckets[-1]

    def render_prometheus(self) -> str:
        """Prometheus text exposition format (what a scraper would read from a /metrics endpoint)."""
        lines: List[str] = []
        with self._lock:
            for name, d in sorted(self._defs.items()):
                lines.append(f"# HELP {name} {d['help']}")
                lines.append(f"# TYPE {name} {d['kind']}")
                for key, val in sorted(self._values[name].items()):
                    label = ",".join(f'{l}="{v}"' for l, v in zip(d["labels"], key))
                    base = f"{name}{{{label}}}" if label else name
                    if d["kind"] == "histogram":
                        cum = 0
                        for b, c in zip(d["buckets"], val["counts"]):
                            cum += c
                            lines.append(f'{name}_bucket{{{label + "," if label else ""}le="{b}"}} {cum}')
                        lines.append(f'{name}_bucket{{{label + "," if label else ""}le="+Inf"}} {val["count"]}')
                        lines.append(f"{name}_sum{{{label}}} {val['sum']:.6f}" if label else f"{name}_sum {val['sum']:.6f}")
                        lines.append(f"{name}_count{{{label}}} {val['count']}" if label else f"{name}_count {val['count']}")
                    else:
                        lines.append(f"{base} {val:g}")
        return "\n".join(lines) + "\n"


def standard_metrics() -> MetricsRegistry:
    """The metrics the observer fills. Names, labels and meaning are also listed in observability_plan.METRICS (a test keeps the two in step)."""
    m = MetricsRegistry()
    m.define("ai_requests_total", "counter", ("op", "status", "error_class"), "AI API requests by operation, outcome and error class (none, client, server)")
    m.define("ai_errors_total", "counter", ("op", "code"), "AI API errors by operation and error code")
    m.define("ai_request_duration_seconds", "histogram", ("op",), "Compute time of one AI call, in seconds", LATENCY_BUCKETS_S)
    m.define("ai_score_value", "histogram", ("op", "score"), "Distribution of produced scores (0-100), for drift monitoring", SCORE_BUCKETS)
    m.define("ai_zone_total", "counter", ("zone",), "ATS scoring results by zone")
    m.define("ai_decision_total", "counter", ("decision", "hold_kind"), "Hiring recommendations by outcome")
    m.define("ai_human_review_required_total", "counter", ("op",), "Results that ask for a person to review")
    m.define("ai_screening_calls_total", "counter", ("call_status",), "Screening conversations by how they ended")
    m.define("ai_interviews_total", "counter", ("interview_type", "interview_status"), "Interview scoring requests by type and status")
    m.define("ai_resume_parses_total", "counter", ("file_type", "outcome"), "Resume parses by file type and outcome (parsed, no_text, error code)")
    m.define("ai_invariant_violations_total", "counter", ("invariant",), "Rules that must never be broken (for example an automated rejection)")
    m.define("ai_log_dropped_total", "counter", ("reason",), "Log events refused or lost, by reason")
    return m


# ======================================================================================================================
# Observer
# ======================================================================================================================
def _known(value: Any, allowed: Iterable[str], other: str = "other") -> str:
    return str(value) if str(value) in set(allowed) else other


def new_request_id() -> str:
    return "req-" + uuid.uuid4().hex[:16]


class ServiceObserver:
    """Wraps service.run(payload). Usage: `observer.call("score_ats", payload, candidate_ref="cref_...")` returns the service's envelope unchanged."""

    def __init__(self, services: Mapping[str, Any], logger: StructuredLogger, metrics: Optional[MetricsRegistry] = None,
                 clock: Callable[[], float] = time.perf_counter, request_ids: Callable[[], str] = new_request_id, tier: Optional[str] = None) -> None:
        self.services = dict(services)
        self.logger = logger
        self.metrics = metrics or standard_metrics()
        self._clock = clock
        self._request_ids = request_ids
        self.tier = tier
        # a metrics-visible count of dropped log events, so a leak attempt is an alertable number and not a silent line
        previous = logger._on_drop
        logger._on_drop = lambda reason: (self._count_drop(reason), previous(reason))

    def _count_drop(self, reason: str) -> None:
        try:
            self.metrics.inc("ai_log_dropped_total", reason=_known(reason, ("policy_violation", "sink_error")))
        except Exception:                                                   # noqa: BLE001
            pass

    # ------------------------------------------------------------------------------------------------------------------
    def call(self, op_id: str, payload: Any, candidate_ref: Optional[str] = None, tenant_ref: Optional[str] = None,
             request_id: Optional[str] = None) -> Dict[str, Any]:
        if op_id not in self.services:
            raise KeyError(f"no service registered for operation {op_id!r}")
        request_id = request_id or self._request_ids()
        start = self._clock()
        envelope = self.services[op_id].run(payload)
        duration = self._clock() - start
        try:
            self._record(op_id, payload, envelope, duration, request_id, candidate_ref, tenant_ref)
        except Exception:                                                   # noqa: BLE001  (observability must never break the request)
            self._count_drop("sink_error")
        return envelope

    def _record(self, op_id: str, payload: Any, env: Mapping[str, Any], duration: float, request_id: str, candidate_ref: Optional[str],
                tenant_ref: Optional[str]) -> None:
        ok = env.get("status") == "success"
        err = env.get("error") or {}
        code = err.get("code")
        rule = ERROR_RULES.get(code) if code else None
        error_class = "none" if ok else ("server" if rule and rule.http_status >= 500 else "client")
        envelope_fields = dict(request_id=request_id, op_id=op_id, service=env.get("service"), model_version=env.get("model_version"),
                               api_version=env.get("api_version", API_VERSION), tenant_ref=tenant_ref, candidate_ref=candidate_ref,
                               tier=self.tier or (OPERATION_BY_ID[op_id].mode.value if op_id in OPERATION_BY_ID else None))
        op_label = _known(op_id, OPERATION_BY_ID)
        m = self.metrics
        m.inc("ai_requests_total", op=op_label, status="success" if ok else "error", error_class=error_class)
        m.observe("ai_request_duration_seconds", duration, op=op_label)
        input_chars = _input_size(payload)
        self.logger.emit("api_request", **envelope_fields, status="success" if ok else "error", http_status=200 if ok else (rule.http_status if rule else 500),
                         error_code=code, error_class=error_class, duration_ms=round(duration * 1000, 3), input_chars=input_chars,
                         warnings=len(env.get("warnings") or []) if ok else None, mode=OPERATION_BY_ID[op_id].mode.value if op_id in OPERATION_BY_ID else None)
        if not ok:
            m.inc("ai_errors_total", op=op_label, code=_known(code, ERROR_RULES))
            self.logger.emit("error", **envelope_fields, error_code=code, error_class=error_class, http_status=rule.http_status if rule else 500,
                             field=(err.get("field") if _is_short_code(err.get("field")) else None), retryable=bool(rule and rule.max_retries), duration_ms=round(duration * 1000, 3))
            if op_id == "parse_resume":
                m.inc("ai_resume_parses_total", file_type=_known((payload or {}).get("file_type") if isinstance(payload, Mapping) else None, ("pdf", "docx")),
                      outcome=_known(code, ERROR_RULES))
            return
        outputs = extract_outputs(op_id, env)
        self.logger.emit("model_output", **envelope_fields, outputs=outputs)
        self._record_outputs(op_label, op_id, env)

    def _record_outputs(self, op_label: str, op_id: str, env: Mapping[str, Any]) -> None:
        m = self.metrics
        if op_id == "score_ats":
            if env.get("scoring_mode") == "ats_engine":
                m.observe("ai_score_value", float(env["ats_score"]), op=op_label, score="ats_score")
                m.inc("ai_zone_total", zone=_known(env.get("zone"), ZONES_FOR_LABELS))
        elif op_id == "score_ats_batch":
            for item in env.get("results", []):
                out = item.get("outcome", {})
                if out.get("status") == "success" and out.get("scoring_mode") == "ats_engine":
                    m.observe("ai_score_value", float(out["ats_score"]), op="score_ats", score="ats_score")
                    m.inc("ai_zone_total", zone=_known(out.get("zone"), ZONES_FOR_LABELS))
        elif op_id == "score_screening":
            m.inc("ai_screening_calls_total", call_status=_known(env.get("call_status"), ("not_started", "completed", "incomplete", "ended_early")))
            if env.get("screening_score") is not None:
                m.observe("ai_score_value", float(env["screening_score"]), op=op_label, score="screening_score")
        elif op_id == "score_interview":
            m.inc("ai_interviews_total", interview_type=_known(env.get("interview_type"), ("hr", "technical")),
                  interview_status=_known(env.get("interview_status"), ("not_started", "scored")))
            for key in ("hr_score", "technical_score"):
                if env.get(key) is not None:
                    m.observe("ai_score_value", float(env[key]), op=op_label, score=key)
        elif op_id == "recommend_decision":
            m.inc("ai_decision_total", decision=_known(env.get("decision"), [o.value for o in DecisionOutcome]),
                  hold_kind=_known(env.get("hold_kind") or "none", ["none", *[h.value for h in HoldKind]]))
            if env.get("human_review_required"):
                m.inc("ai_human_review_required_total", op=op_label)
            m.observe("ai_score_value", float(env["hiring_fit_score"]), op=op_label, score="hiring_fit_score")
            if env.get("decision") == "rejected" and (not env.get("human_confirmation_required") or env.get("automated_action") != "none"):
                m.inc("ai_invariant_violations_total", invariant="automated_rejection")
        elif op_id == "parse_resume":
            m.inc("ai_resume_parses_total", file_type=_known(env.get("file_type"), ("pdf", "docx")), outcome="parsed" if env.get("has_text") else "no_text")


def _input_size(payload: Any) -> Optional[int]:
    """Total characters of text fields in the request: a SIZE, never the text itself."""
    if not isinstance(payload, Mapping):
        return None
    total = 0
    for v in payload.values():
        if isinstance(v, str):
            total += len(v)
        elif isinstance(v, (list, tuple)):
            for item in v:
                if isinstance(item, str):
                    total += len(item)
                elif isinstance(item, Mapping):
                    total += sum(len(x) for x in item.values() if isinstance(x, str))
    return total


def extract_outputs(op_id: str, env: Mapping[str, Any]) -> Dict[str, Any]:
    """Only the allowlisted response fields, as numbers and codes. A list becomes its length; text never passes."""
    out: Dict[str, Any] = {}
    for key in MODEL_OUTPUT_ALLOWLIST.get(op_id, ()):
        if key not in env:
            continue
        v = env[key]
        if isinstance(v, (list, tuple)):
            out[f"{key}_count"] = len(v)
        elif v is None or isinstance(v, (bool, int, float)) or _is_short_code(v):
            out[key] = v
    for key, fields in NESTED_NUMBERS.get(op_id, {}).items():
        nested = env.get(key) or {}
        for f in fields:
            if isinstance(nested.get(f), (int, float)):
                out[f"{key}_{f}"] = nested[f]
    return out


# ======================================================================================================================
# JSON Schema of the log events, generated from the constants above (so the schema cannot drift from the guard)
# ======================================================================================================================
def _output_property_names() -> Dict[str, Dict[str, Any]]:
    """Every key a `model_output.outputs` object may hold, with a loose type; lists appear as `<name>_count`."""
    props: Dict[str, Dict[str, Any]] = {}
    for fields in MODEL_OUTPUT_ALLOWLIST.values():
        for f in fields:
            props.setdefault(f if f not in _LIST_FIELDS else f + "_count", {"type": ["number", "boolean", "string", "null"], "maxLength": 64})
    for nested in NESTED_NUMBERS.values():
        for key, fields in nested.items():
            for f in fields:
                props[f"{key}_{f}"] = {"type": "number"}
    return props


_LIST_FIELDS = frozenset({"detected_sections", "skills", "education", "certifications", "warnings", "categories_answered", "categories_missing", "missing_rounds",
                          "human_review_reasons"})


def log_schema_document() -> Dict[str, Any]:
    code = {"type": "string", "maxLength": 64}
    envelope = {
        "schema_version": {"const": LOG_SCHEMA_VERSION}, "ts": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"}, "event": {"enum": list(EVENT_KINDS)},
        "level": {"enum": ["INFO", "ERROR"]}, "request_id": code, "op_id": {"enum": sorted(OPERATION_BY_ID)}, "service": {"type": "string", "maxLength": 64},
        "model_version": code, "api_version": code, "tenant_ref": code, "candidate_ref": code, "tier": {"enum": ["sync", "async"]},
    }
    kinds = {
        "api_request": {"status": {"enum": ["success", "error"]}, "http_status": {"type": "integer"}, "error_code": {"type": ["string", "null"], "maxLength": 64},
                        "error_class": {"enum": ["none", "client", "server"]}, "duration_ms": {"type": "number", "minimum": 0}, "input_chars": {"type": ["integer", "null"], "minimum": 0},
                        "warnings": {"type": "integer", "minimum": 0}, "mode": {"enum": ["sync", "async"]}, "retry_attempt": {"type": "integer", "minimum": 0}},
        "model_output": {"outputs": {"type": "object", "properties": _output_property_names(), "additionalProperties": False}},
        "error": {"error_code": code, "error_class": {"enum": ["client", "server"]}, "http_status": {"type": "integer"}, "field": code, "retryable": {"type": "boolean"},
                  "exception_type": code, "duration_ms": {"type": "number", "minimum": 0}},
    }
    defs = {}
    for kind, extra in kinds.items():
        required = ["schema_version", "ts", "event", "level", "request_id", "op_id"] + {"api_request": ["status", "duration_ms"], "model_output": ["outputs"], "error": ["error_code"]}[kind]
        defs[f"{kind}_event"] = {"type": "object", "properties": {**envelope, **extra, "event": {"const": kind}}, "required": required, "additionalProperties": False}
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "https://zecpath.ai/schemas/observability_log_schemas.json",
            "title": "Zecpath AI log events", "description": "GENERATED by parsers/observability.py: every field a log event may hold. A field not listed here is refused by the logger.",
            "forbidden_keys": sorted(FORBIDDEN_PAYLOAD_KEYS), "max_string_length": 64, "$defs": defs, "oneOf": [{"$ref": f"#/$defs/{k}"} for k in defs]}
