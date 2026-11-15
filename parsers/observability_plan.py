"""
Observability plan as code (Day 61)

Day 61 asks for a plan: key metrics, alerting rules, a dashboard structure. This module holds each of those as DATA that code can check and run,
so the plan cannot drift away from what is emitted or silently contradict itself:

  1. METRICS / SLOS      what is measured, grouped as the brief asks (response time, accuracy, failure rates), with the SLO each service level is held to.
  2. psi()               a drift measure for score distributions (Population Stability Index), because ground-truth accuracy arrives late or never.
  3. ALERT_RULES         every alert with its condition, window, severity, owner and runbook; an AlertManager evaluates them against a stream of log events.
  4. DASHBOARDS          panel definitions and `build_dashboard_data()`, which computes the panel values from real events, with small-group suppression.
  5. generate_stream()   synthetic traffic made by resampling REAL service events, plus incident injectors, so every rule can be tested for both
                         "fires when it should" and "stays quiet when it should".

HONEST LIMITS. Thresholds, windows and SLOs are PROPOSED. The traffic simulator resamples real events (real durations, real outputs) but the arrival
pattern, the error background and every incident are invented, so a result such as "detected in 4 minutes" describes the RULE on that invented incident,
not a production guarantee. Nothing here is connected to a metrics server or a pager.
"""

from __future__ import annotations

import bisect
import math
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from parsers.integration_contract import ERROR_RULES, OPERATION_BY_ID

# ======================================================================================================================
# 1. Metrics and SLOs
# ======================================================================================================================


@dataclass(frozen=True)
class MetricDef:
    name: str
    kind: str                      # counter | gauge | histogram
    labels: Tuple[str, ...]
    category: str                  # response_time | accuracy | failure | quality | volume | audit | saturation
    description: str
    source: str                    # service | gateway | queue | backend | evaluation | audit
    status: str                    # prototype (emitted by parsers/observability.py) | planned


M = MetricDef
METRICS: Tuple[MetricDef, ...] = (
    # -- emitted today by the observer -----------------------------------------------------------------------------------
    M("ai_requests_total", "counter", ("op", "status", "error_class"), "volume", "AI API requests by operation, outcome and error class", "service", "prototype"),
    M("ai_errors_total", "counter", ("op", "code"), "failure", "AI API errors by operation and error code", "service", "prototype"),
    M("ai_request_duration_seconds", "histogram", ("op",), "response_time", "Compute time of one AI call", "service", "prototype"),
    M("ai_score_value", "histogram", ("op", "score"), "accuracy", "Distribution of produced scores (drift input)", "service", "prototype"),
    M("ai_zone_total", "counter", ("zone",), "accuracy", "ATS results by zone (drift input)", "service", "prototype"),
    M("ai_decision_total", "counter", ("decision", "hold_kind"), "quality", "Hiring recommendations by outcome", "service", "prototype"),
    M("ai_human_review_required_total", "counter", ("op",), "quality", "Results asking a person to review", "service", "prototype"),
    M("ai_screening_calls_total", "counter", ("call_status",), "quality", "Screening conversations by how they ended", "service", "prototype"),
    M("ai_interviews_total", "counter", ("interview_type", "interview_status"), "quality", "Interview scoring requests by type and status", "service", "prototype"),
    M("ai_resume_parses_total", "counter", ("file_type", "outcome"), "failure", "Resume parses by file type and outcome", "service", "prototype"),
    M("ai_invariant_violations_total", "counter", ("invariant",), "audit", "Rules that must never be broken", "service", "prototype"),
    M("ai_log_dropped_total", "counter", ("reason",), "failure", "Log events refused or lost, by reason", "service", "prototype"),
    # -- planned: need infrastructure that does not exist yet (Day 59 gateway and queue, Day 60 autoscaler) or data nobody collects yet -------------
    M("ai_gateway_request_duration_seconds", "histogram", ("op",), "response_time", "End-to-end latency seen at the gateway, including queueing and network", "gateway", "planned"),
    M("ai_job_queue_wait_seconds", "histogram", ("op",), "response_time", "Time from job submission to the start of work", "queue", "planned"),
    M("ai_job_queue_oldest_age_seconds", "gauge", ("op",), "saturation", "Age of the oldest waiting job (autoscaling and alert signal)", "queue", "planned"),
    M("ai_jobs_total", "counter", ("op", "state"), "failure", "Jobs by final state (completed, failed, cancelled)", "queue", "planned"),
    M("ai_job_attempts_total", "counter", ("op",), "failure", "Job attempts, so retries and dead-lettered jobs are visible", "queue", "planned"),
    M("ai_worker_resident_memory_bytes", "gauge", ("tier",), "saturation", "Resident memory per worker (Day 60: 19 MB to 154 MB by profile)", "backend", "planned"),
    M("ai_cache_hit_ratio", "gauge", ("cache",), "saturation", "Hit rate of each Day 60 cache (utils.perf.all_cache_stats)", "service", "planned"),
    M("ai_human_override_total", "counter", ("recommended", "final"), "accuracy", "Recruiter changes to the AI recommendation (the online accuracy proxy)", "backend", "planned"),
    M("ai_agreement_with_human_ratio", "gauge", ("op",), "accuracy", "Agreement with human ratings on a labelled sample (needs the Day 58 F3 ratings)", "evaluation", "planned"),
    M("ai_decision_audit_missing_total", "counter", ("op",), "audit", "Decisions with no matching audit entry (must stay zero)", "audit", "planned"),
    M("ai_audit_chain_verified", "gauge", (), "audit", "1 when the latest audit-chain verification passed, 0 when it failed", "audit", "planned"),
)
METRIC_BY_NAME: Dict[str, MetricDef] = {m.name: m for m in METRICS}

# Service level objectives (PROPOSED). The availability SLO counts only SERVER errors: a candidate's bad file is not an outage.
SLOS: Dict[str, Dict[str, Any]] = {
    "sync_availability": {"target": 0.999, "window_days": 30, "bad_event": "server error (5xx: internal_error, timeout, service_unavailable)", "good_event": "any other response"},
    "sync_latency": {"target": 0.95, "threshold_ms": 50, "basis": "compute time inside the service (Day 60: ATS p95 3-6 ms, so 50 ms leaves wide room); the gateway adds its own budget"},
    "async_start_delay": {"target": 0.95, "threshold_s": 30, "basis": "job waits no longer than 30 s to start, at the busiest hour (Day 60 target)"},
}

# p95 compute-time thresholds per operation, in ms (PROPOSED; each sits far above the Day 60 measured p95 so only a real regression crosses it)
LATENCY_P95_MS: Dict[str, float] = {"score_ats": 50.0, "score_screening": 50.0, "score_interview": 50.0, "recommend_decision": 50.0, "parse_resume": 300.0, "score_ats_batch": 2000.0}

SERVER_CODES = frozenset(c for c, r in ERROR_RULES.items() if r.http_status >= 500)
PARSE_FAILURE_CODES = frozenset({"empty_file", "corrupt_file", "unsupported_type", "file_not_found"})

# ======================================================================================================================
# 2. Drift
# ======================================================================================================================
SCORE_BINS = tuple(range(0, 101, 10))          # ten bins of width 10


def _bin_counts(values: Iterable[float], bins: Sequence[float] = SCORE_BINS) -> List[int]:
    counts = [0] * (len(bins) - 1)
    for v in values:
        i = min(len(counts) - 1, max(0, bisect.bisect_right(bins, v) - 1))
        counts[i] += 1
    return counts


def psi(baseline: Sequence[float], current: Sequence[float], bins: Sequence[float] = SCORE_BINS, epsilon: float = 1e-4) -> float:
    """Population Stability Index between two samples of scores: sum((cur% - base%) * ln(cur% / base%)) over the bins.
    0 means identical distributions. A common convention (not a law): under 0.1 stable, 0.1 to 0.25 moderate shift, over 0.25 major shift."""
    if not baseline or not current:
        raise ValueError("both samples need at least one value")
    b, c = _bin_counts(baseline, bins), _bin_counts(current, bins)
    nb, nc = sum(b), sum(c)
    total = 0.0
    for x, y in zip(b, c):
        pb, pc = max(x / nb, epsilon), max(y / nc, epsilon)
        total += (pc - pb) * math.log(pc / pb)
    return total


def psi_band(value: float) -> str:
    return "stable" if value < 0.1 else ("moderate" if value < 0.25 else "major")


# ======================================================================================================================
# 3. Time series built from log events, and the alert rules
# ======================================================================================================================
@dataclass
class Stats:
    """Everything the rules need about one stretch of time; merging two stretches adds them."""
    requests: Counter = field(default_factory=Counter)          # (op, status, error_class)
    errors: Counter = field(default_factory=Counter)            # (op, code)
    durations: Dict[str, List[float]] = field(default_factory=lambda: defaultdict(list))
    ats_scores: List[float] = field(default_factory=list)
    zones: Counter = field(default_factory=Counter)
    decisions: Counter = field(default_factory=Counter)
    decisions_human_review: int = 0
    invariant_violations: int = 0
    screening: Counter = field(default_factory=Counter)
    parse: Counter = field(default_factory=Counter)             # outcome

    def merge(self, other: "Stats") -> "Stats":
        self.requests.update(other.requests)
        self.errors.update(other.errors)
        for k, v in other.durations.items():
            self.durations[k].extend(v)
        self.ats_scores.extend(other.ats_scores)
        self.zones.update(other.zones)
        self.decisions.update(other.decisions)
        self.decisions_human_review += other.decisions_human_review
        self.invariant_violations += other.invariant_violations
        self.screening.update(other.screening)
        self.parse.update(other.parse)
        return self

    def total(self) -> int:
        return sum(self.requests.values())

    def count_where(self, status: Optional[str] = None, error_class: Optional[str] = None, op: Optional[str] = None) -> int:
        return sum(n for (o, s, e), n in self.requests.items() if (status is None or s == status) and (error_class is None or e == error_class) and (op is None or o == op))


def p95(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, int(0.95 * (len(s) - 1) + 0.5))]


class TimeSeriesStore:
    """Per-minute buckets of Stats, filled from log events (what a metrics backend does with a counter that is scraped every minute)."""

    def __init__(self) -> None:
        self._buckets: Dict[int, Stats] = {}

    def ingest(self, t: float, event: Mapping[str, Any]) -> None:
        s = self._buckets.setdefault(int(t // 60), Stats())
        kind, op = event.get("event"), event.get("op_id")
        if kind == "api_request":
            s.requests[(op, event.get("status"), event.get("error_class"))] += 1
            if event.get("duration_ms") is not None:
                s.durations[op].append(float(event["duration_ms"]))
            if event.get("status") == "error":
                s.errors[(op, event.get("error_code"))] += 1
                if op == "parse_resume":
                    s.parse[str(event.get("error_code"))] += 1
        elif kind == "model_output":
            out = event.get("outputs") or {}
            if op == "score_ats" and out.get("scoring_mode") == "ats_engine":
                s.ats_scores.append(float(out["ats_score"]))
                s.zones[out.get("zone")] += 1
            elif op == "recommend_decision":
                s.decisions[out.get("decision")] += 1
                s.decisions_human_review += 1 if out.get("human_review_required") else 0
                if out.get("decision") == "rejected" and (not out.get("human_confirmation_required") or out.get("automated_action") != "none"):
                    s.invariant_violations += 1
            elif op == "score_screening":
                s.screening[out.get("call_status")] += 1
            elif op == "parse_resume":
                s.parse["parsed" if out.get("has_text") else "no_text"] += 1

    def window(self, end_t: float, seconds: float) -> Stats:
        out = Stats()
        hi, lo = int(end_t // 60), int((end_t - seconds) // 60) + 1
        for minute in range(lo, hi + 1):
            b = self._buckets.get(minute)
            if b:
                out.merge(b)
        return out


@dataclass(frozen=True)
class AlertRule:
    rule_id: str
    name: str
    severity: str                  # page | ticket
    kind: str                      # burn_rate | latency | ratio | psi | zone_shift | band | surge | absence | invariant | extra
    window_s: int
    for_s: int                     # the condition must hold this long before the alert fires (kills one-minute blips)
    interval_s: int                # how often the rule is evaluated
    params: Dict[str, Any]
    description: str
    runbook: str
    owner: str
    status: str = "evaluable"      # evaluable | planned (needs data or infrastructure that does not exist yet)
    blocked_by: Optional[str] = None


def _r(*a: Any, **k: Any) -> AlertRule:
    return AlertRule(*a, **k)


ALERT_RULES: Tuple[AlertRule, ...] = (
    _r("A01", "availability_fast_burn", "page", "burn_rate", 300, 0, 60, {"long_s": 3600, "short_s": 300, "slo": 0.999, "burn": 14.4, "min_events": 30},
       "Server errors are using the 30-day error budget 14 times too fast, on both the last hour and the last 5 minutes",
       "Open the gateway and worker dashboards; check the last deploy and warm-up status; roll back if a deploy preceded it.", "on-call engineer"),
    _r("A02", "availability_slow_burn", "ticket", "burn_rate", 1800, 0, 300, {"long_s": 21600, "short_s": 1800, "slo": 0.999, "burn": 6.0, "min_events": 60},
       "A slow leak of server errors: 6 times the sustainable rate over 6 hours and 30 minutes",
       "Group errors by code and operation; look for one failing dependency or one worker.", "service owner"),
    # The window (5 min) is deliberately SHORTER than the for-duration (10 min). With a 10-minute window and a 10-minute wait, a 4-minute slow spell
    # kept p95 high for the 10 minutes it stayed in the window and fired anyway: a p95 is "sticky", so the window must be short for `for` to filter blips.
    # The absolute thresholds come from the SLO and sit far above normal (ATS: 50 ms against a 3 ms median), so on their own they miss a large slowdown that
    # stays under them (the first run did not notice ATS getting 15 times slower, to 45 ms). The relative test compares with the operation's own baseline.
    _r("A03", "latency_p95_regression", "ticket", "latency", 300, 600, 60, {"thresholds_ms": LATENCY_P95_MS, "relative_factor": 5.0, "relative_floor_ms": 5.0, "min_events": 20},
       "p95 compute time of an operation above its SLO threshold, or above 5 times its own baseline (and over 5 ms), measured over 5 minutes, for 10 minutes running",
       "Compare with the last benchmark (run_day60_benchmark.py); check cache hit rates, cold workers, input sizes.", "service owner"),
    _r("A04", "client_error_spike", "ticket", "ratio", 900, 300, 60, {"numerator": "client_errors", "threshold": 0.25, "min_events": 50},
       "More than a quarter of requests were refused as invalid: an upstream caller is sending bad requests (not an outage)",
       "Group by error code and field; tell the calling team; do NOT page the AI team.", "integration owner"),
    _r("A05", "resume_parse_failure_ratio", "ticket", "ratio", 3600, 0, 300, {"numerator": "parse_failures", "threshold": 0.10, "min_events": 20},
       "More than one resume in ten could not be read (empty, corrupt, unsupported or missing file)",
       "Look at the error-code mix: unsupported_type means an upload form problem, corrupt_file a storage or extractor problem.", "service owner"),
    _r("A06", "ats_score_drift", "ticket", "psi", 21600, 0, 1800, {"psi_threshold": 0.25, "min_events": 300},
       "The distribution of ATS scores over 6 hours differs from the baseline (PSI above 0.25)",
       "Check for a new job-description template, a changed upload source, or a config change; compare with the evaluation set before trusting new scores.", "model owner"),
    _r("A07", "zone_mix_shift", "ticket", "zone_shift", 21600, 0, 1800, {"points": 0.15, "min_events": 300},
       "The share of ATS shortlist results moved by more than 15 points from the baseline",
       "Same as A06; a shift in who is shortlisted is the visible symptom of drift.", "model owner"),
    _r("A08", "automated_rejection_invariant", "page", "invariant", 300, 0, 60, {"min_events": 1},
       "A rejection was recommended without human confirmation required, or with an automated action: a rule of the system was broken",
       "Stop the automated path for that tenant; this must never happen (Day 52, Day 55 R6); capture the request id and open an incident.", "on-call engineer + compliance"),
    _r("A09", "human_review_rate_band", "ticket", "band", 86400, 0, 3600, {"lo": 0.0, "hi": 0.9, "min_events": 100},
       "The share of decisions asking for human review left its expected band",
       "Too many: a rule or an upstream score changed. Too few: a review rule may have stopped firing.", "model owner"),
    _r("A10", "screening_call_failure_surge", "ticket", "surge", 3600, 600, 300, {"statuses": ("incomplete", "ended_early"), "threshold": 0.5, "min_events": 30},
       "More than half of screening conversations ended early or incomplete",
       "Check speech-to-text and telephony health first (silent calls); then the conversation flow.", "service owner"),
    _r("A11", "no_traffic", "page", "absence", 900, 0, 60, {},
       "No API requests at all for 15 minutes on a tier that normally has traffic (a silent failure looks like a quiet system)",
       "Check the load balancer and gateway; a healthy-looking service with no requests is usually an upstream outage.", "on-call engineer"),
    _r("A12", "decision_audit_gap", "page", "extra", 900, 0, 300, {"extra": "decisions_without_audit"},
       "A decision was produced and no audit entry exists for it",
       "Compliance issue: find the request id, write the missing entry from the log, and fix the recorder.", "on-call engineer + compliance"),
    _r("A13", "log_policy_violation", "ticket", "extra", 3600, 0, 300, {"extra": "log_policy_violations"},
       "The logger refused an event because it contained a forbidden field or free text: code is trying to log personal content",
       "Find the call site from the request id; the event was NOT written, but the bug must be fixed.", "service owner"),
    _r("A14", "job_queue_oldest_age", "ticket", "extra", 300, 300, 60, {"threshold_s": 30}, "The oldest waiting job is older than 30 seconds at the busiest hour (the Day 60 autoscaling signal)",
       "Scale out the async tier; check for a stuck consumer.", "service owner", "planned", "needs the job queue (Day 59 gateway and queue are not built)"),
    _r("A15", "human_override_rate", "ticket", "extra", 604800, 0, 3600, {}, "Recruiters change the AI recommendation much more often than before (the online accuracy proxy)",
       "Review a sample of the overridden cases with the model owner.", "model owner", "planned", "needs recruiter review outcomes recorded (ai_human_override_total)"),
    _r("A16", "selection_rate_gap", "ticket", "extra", 2592000, 0, 86400, {}, "Selection rates differ between groups beyond an agreed limit (Day 58 F6)",
       "Fairness review; see the bias-monitoring plan.", "model owner + compliance", "planned",
       "needs consented, separately stored demographic data; the platform deliberately does not collect it (Day 55); cannot be built from the logs"),
)
RULE_BY_ID: Dict[str, AlertRule] = {r.rule_id: r for r in ALERT_RULES}


@dataclass
class AlertEvent:
    rule_id: str
    severity: str
    state: str                     # firing | resolved
    at: float
    value: Optional[float]
    detail: str


@dataclass
class Baseline:
    ats_scores: Sequence[float] = ()
    shortlist_share: Optional[float] = None
    latency_p95_ms: Mapping[str, float] = field(default_factory=dict)        # per operation, from a WARMED worker (a cold first request would poison it)


class AlertManager:
    """Evaluates every evaluable rule at each tick and remembers which are pending or firing (so `for_s` and resolution work)."""

    def __init__(self, store: TimeSeriesStore, baseline: Optional[Baseline] = None, rules: Sequence[AlertRule] = ALERT_RULES) -> None:
        self.store = store
        self.baseline = baseline or Baseline()
        self.rules = [r for r in rules if r.status == "evaluable"]
        self._pending_since: Dict[str, float] = {}
        self._firing: Dict[str, bool] = {}
        self._last_eval: Dict[str, float] = {}
        self.history: List[AlertEvent] = []

    def tick(self, t: float, extras: Optional[Mapping[str, float]] = None) -> List[AlertEvent]:
        out: List[AlertEvent] = []
        for rule in self.rules:
            if t - self._last_eval.get(rule.rule_id, -1e18) < rule.interval_s:
                continue
            self._last_eval[rule.rule_id] = t
            cond, value, detail = self._evaluate(rule, t, extras or {})
            if cond is None:
                continue                                                    # not enough data to judge: neither fire nor resolve
            if cond:
                since = self._pending_since.setdefault(rule.rule_id, t)
                if not self._firing.get(rule.rule_id) and t - since >= rule.for_s:
                    self._firing[rule.rule_id] = True
                    out.append(AlertEvent(rule.rule_id, rule.severity, "firing", t, value, detail))
            else:
                self._pending_since.pop(rule.rule_id, None)
                if self._firing.pop(rule.rule_id, False):
                    out.append(AlertEvent(rule.rule_id, rule.severity, "resolved", t, value, detail))
        self.history.extend(out)
        return out

    # ------------------------------------------------------------------------------------------------------------------
    def _evaluate(self, rule: AlertRule, t: float, extras: Mapping[str, float]) -> Tuple[Optional[bool], Optional[float], str]:
        p, w = rule.params, self.store.window(t, rule.window_s)
        k = rule.kind
        if k == "burn_rate":
            budget = (1 - p["slo"]) * p["burn"]
            ratios = []
            for secs in (p["long_s"], p["short_s"]):
                s = self.store.window(t, secs)
                total = s.total()
                if total < p["min_events"] * (secs / p["long_s"]):
                    return None, None, "not enough traffic"
                ratios.append(s.count_where(error_class="server") / total)
            return all(r > budget for r in ratios), ratios[0], f"server-error ratio {ratios[0]:.2%} (1 h/6 h) and {ratios[1]:.2%} (short) vs {budget:.2%}"
        if k == "latency":
            for op, limit in p["thresholds_ms"].items():
                d = w.durations.get(op, [])
                if len(d) >= p["min_events"] and p95(d) > limit:
                    return True, p95(d), f"{op} p95 {p95(d):.1f} ms over {limit} ms"
                base = self.baseline.latency_p95_ms.get(op)
                if base is not None and len(d) >= p["min_events"] and p95(d) > max(p["relative_factor"] * base, p["relative_floor_ms"]):
                    return True, p95(d), f"{op} p95 {p95(d):.1f} ms is over {p['relative_factor']:g} times its baseline of {base:.1f} ms"
            return (False, None, "") if w.total() >= p["min_events"] else (None, None, "not enough traffic")
        if k == "ratio":
            total = w.total() if p["numerator"] == "client_errors" else sum(w.parse.values())
            if total < p["min_events"]:
                return None, None, "not enough traffic"
            num = w.count_where(error_class="client") if p["numerator"] == "client_errors" else sum(w.parse[c] for c in PARSE_FAILURE_CODES)
            return num / total > p["threshold"], num / total, f"{p['numerator']} {num / total:.1%} of {total}"
        if k == "psi":
            if len(w.ats_scores) < p["min_events"] or not self.baseline.ats_scores:
                return None, None, "not enough data"
            v = psi(self.baseline.ats_scores, w.ats_scores)
            return v > p["psi_threshold"], v, f"PSI {v:.3f} ({psi_band(v)})"
        if k == "zone_shift":
            n = sum(w.zones.values())
            if n < p["min_events"] or self.baseline.shortlist_share is None:
                return None, None, "not enough data"
            share = w.zones["shortlist"] / n
            return abs(share - self.baseline.shortlist_share) > p["points"], share, f"shortlist share {share:.1%} vs baseline {self.baseline.shortlist_share:.1%}"
        if k == "band":
            n = sum(w.decisions.values())
            if n < p["min_events"]:
                return None, None, "not enough data"
            share = w.decisions_human_review / n
            return not (p["lo"] <= share <= p["hi"]), share, f"human-review share {share:.1%}"
        if k == "surge":
            n = sum(w.screening.values()) - w.screening["not_started"]
            if n < p["min_events"]:
                return None, None, "not enough data"
            bad = sum(w.screening[s] for s in p["statuses"])
            return bad / n > p["threshold"], bad / n, f"{bad / n:.1%} of {n} screening calls ended early or incomplete"
        if k == "absence":
            return w.total() == 0, float(w.total()), "no requests in the window"
        if k == "invariant":
            return w.invariant_violations >= p["min_events"], float(w.invariant_violations), f"{w.invariant_violations} invariant violation(s)"
        if k == "extra":
            if p.get("extra") in extras:
                v = float(extras[p["extra"]])
                return v > 0, v, f"{p['extra']} = {v:g}"
            return None, None, "input not provided"
        return None, None, "unknown rule kind"


# ======================================================================================================================
# 4. Dashboards
# ======================================================================================================================
SMALL_CELL = 5       # PROPOSED: any group smaller than this is shown as "<5", so a dashboard cannot single out a person


@dataclass(frozen=True)
class Panel:
    panel_id: str
    title: str
    kind: str                      # stat | timeseries | bar | funnel | histogram | table
    metrics: Tuple[str, ...]
    query: str
    unit: str
    audience: Tuple[str, ...]
    description: str
    alert_rules: Tuple[str, ...] = ()
    privacy: str = "aggregate"      # aggregate | aggregate_k5 (breakdowns suppressed under SMALL_CELL)


def _p(*a: Any, **k: Any) -> Panel:
    return Panel(*a, **k)


ENG, REC, ADM, AUD = "engineer", "recruiter", "admin", "auditor"
DASHBOARDS: Dict[str, Dict[str, Any]] = {
    "service_health": {"title": "AI service health", "audience": (ENG, ADM), "refresh_s": 15, "panels": (
        _p("sh1", "Requests per second by operation", "timeseries", ("ai_requests_total",), "sum by (op) (rate(ai_requests_total[1m]))", "req/s", (ENG, ADM), "Traffic shape; the first thing to look at in an incident", ("A11",)),
        _p("sh2", "Error ratio by class", "timeseries", ("ai_requests_total",), "sum by (error_class) (rate(ai_requests_total{status='error'}[5m])) / sum(rate(ai_requests_total[5m]))", "ratio", (ENG, ADM),
           "Server errors count against the SLO; client errors point at the caller", ("A01", "A02", "A04")),
        _p("sh3", "Latency p50, p95, p99 by operation", "timeseries", ("ai_request_duration_seconds",), "histogram_quantile(0.95, sum by (op, le) (rate(ai_request_duration_seconds_bucket[5m])))", "ms", (ENG, ADM),
           "Compute time against each operation's threshold", ("A03",)),
        _p("sh4", "Error budget remaining (30 days)", "stat", ("ai_requests_total",), "1 - (server errors / requests) over 30 d, against the 99.9 % SLO", "%", (ENG, ADM), "How much of the monthly budget is left", ("A01", "A02")),
        _p("sh5", "Top error codes", "table", ("ai_errors_total",), "topk(10, sum by (op, code) (increase(ai_errors_total[1h])))", "count", (ENG,), "What is failing, by code and operation"),
        _p("sh6", "Caches, warm-up and memory", "table", ("ai_cache_hit_ratio", "ai_worker_resident_memory_bytes"), "latest value per cache and tier", "ratio / MB", (ENG,), "Day 60 saturation signals (planned metrics)"),
    )},
    "candidate_processing": {"title": "Candidate processing", "audience": (REC, ADM), "refresh_s": 60, "panels": (
        _p("cp1", "Candidate funnel today", "funnel", ("ai_resume_parses_total", "ai_zone_total", "ai_decision_total"),
           "parsed -> scored -> shortlisted -> decision recommended -> human review required", "candidates", (REC, ADM), "Where candidates are in the pipeline; counts only, never names"),
        _p("cp2", "Resumes parsed vs failed, by reason", "bar", ("ai_resume_parses_total",), "sum by (outcome) (increase(ai_resume_parses_total[1d]))", "count", (REC, ADM),
           "Failures by reason; a spike means an upload problem, not weaker candidates", ("A05",), "aggregate_k5"),
        _p("cp3", "ATS zone mix", "bar", ("ai_zone_total",), "sum by (zone) (increase(ai_zone_total[1d]))", "count", (REC, ADM), "Shortlist, review and reject shares", ("A07",)),
        _p("cp4", "Recommendations by outcome", "bar", ("ai_decision_total",), "sum by (decision, hold_kind) (increase(ai_decision_total[1d]))", "count", (REC, ADM),
           "Selected, hold for review (and why), rejected-pending-human-confirmation", ("A08", "A09")),
        _p("cp5", "Human review required", "stat", ("ai_human_review_required_total", "ai_decision_total"), "review required / decisions", "%", (REC, ADM), "How often a person must look", ("A09",)),
        _p("cp6", "Processing time per stage (p50)", "table", ("ai_request_duration_seconds",), "p50 by op", "ms", (ADM, ENG), "Compute time per stage, not candidate waiting time (that needs the queue metrics)"),
    )},
    "interview_success": {"title": "Interview success rates", "audience": (REC, ADM), "refresh_s": 60, "panels": (
        _p("is1", "Screening calls by how they ended", "bar", ("ai_screening_calls_total",), "sum by (call_status) (increase(ai_screening_calls_total[1d]))", "count", (REC, ADM),
           "Completed vs incomplete vs ended early. Process success, not candidate quality", ("A10",)),
        _p("is2", "Screening completion rate", "stat", ("ai_screening_calls_total",), "completed / (completed + incomplete + ended_early)", "%", (REC, ADM), "Share of started conversations that finished", ("A10",)),
        _p("is3", "Interview scoring status by type", "bar", ("ai_interviews_total",), "sum by (interview_type, interview_status) (increase(ai_interviews_total[1d]))", "count", (REC, ADM), "Scored vs not started, HR and technical"),
        _p("is4", "Substantive answer rate", "stat", ("ai_score_value",), "1 - non_substantive_answers / answers_scored (from model_output logs)", "%", (REC, ADM), "How many answers carried enough content to score"),
        _p("is5", "Score distribution by round", "histogram", ("ai_score_value",), "histogram of hr_score, technical_score, screening_score (10 bins)", "score", (REC, ADM, ENG),
           "Shape of scores; a sudden change is a drift signal, not a verdict on candidates", ("A06",), "aggregate_k5"),
    )},
    "model_quality": {"title": "Model quality and drift", "audience": (ENG, ADM), "refresh_s": 300, "panels": (
        _p("mq1", "ATS score distribution vs baseline", "histogram", ("ai_score_value",), "current 6 h histogram next to the baseline", "score", (ENG, ADM), "The picture behind the PSI number", ("A06",)),
        _p("mq2", "PSI over time", "timeseries", ("ai_score_value",), "psi(baseline, 6 h window) every 30 min", "PSI", (ENG, ADM), "Under 0.1 stable, 0.1 to 0.25 moderate, over 0.25 major", ("A06", "A07")),
        _p("mq3", "Agreement with human ratings", "stat", ("ai_agreement_with_human_ratio",), "latest evaluation run", "%", (ENG, ADM), "Offline accuracy on a labelled sample (planned: needs the Day 58 human ratings)"),
        _p("mq4", "Recruiter override rate", "timeseries", ("ai_human_override_total",), "overrides / recommendations", "%", (ENG, ADM), "The online accuracy proxy (planned: needs review outcomes recorded)", ("A15",)),
    )},
    "audit_compliance": {"title": "Decision audit and compliance", "audience": (AUD, ADM), "refresh_s": 300, "panels": (
        _p("ac1", "Audit entries by event type", "bar", ("ai_decision_audit_missing_total",), "count by event_type from the audit log", "count", (AUD, ADM), "Volume of score, decision, final-decision, access and consent entries"),
        _p("ac2", "Decisions without an audit entry", "stat", ("ai_decision_audit_missing_total",), "decisions logged - decisions audited (must be 0)", "count", (AUD, ADM), "Completeness of the audit trail", ("A12",)),
        _p("ac3", "Audit chain verification", "stat", ("ai_audit_chain_verified",), "result of AuditLog.verify() against the external anchor", "pass/fail", (AUD, ADM), "Tamper evidence", ("A12",)),
        _p("ac4", "Rejections awaiting human confirmation", "stat", ("ai_decision_total",), "rejected recommendations without a final_decision entry", "count", (AUD, REC, ADM), "No rejection is final until a named person confirms it", ("A08",)),
        _p("ac5", "Invariant violations", "stat", ("ai_invariant_violations_total",), "sum(increase(ai_invariant_violations_total[7d])) (must be 0)", "count", (AUD, ADM, ENG), "Broken must-never-happen rules", ("A08",)),
        _p("ac6", "Log events refused by the privacy guard", "stat", ("ai_log_dropped_total",), "increase(ai_log_dropped_total{reason='policy_violation'}[7d])", "count", (ENG, AUD), "Attempts to log personal content", ("A13",)),
    )},
}


def suppress_small(counts: Mapping[str, int], k: int = SMALL_CELL) -> Dict[str, Any]:
    """Replace every count below k with '<k'. A dashboard that shows a group of one person has shown that person."""
    return {key: (n if n >= k else f"<{k}") for key, n in counts.items()}


def _pctl(values: Sequence[float], q: float) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    return round(s[min(len(s) - 1, int(q * (len(s) - 1) + 0.5))], 3)


def build_dashboard_data(events: Iterable[Mapping[str, Any]], baseline_ats: Sequence[float] = ()) -> Dict[str, Any]:
    """Compute the panel values from log events. Counts and distributions only; candidate references are counted, never listed."""
    evs = list(events)
    api = [e for e in evs if e.get("event") == "api_request"]
    outs = [e for e in evs if e.get("event") == "model_output"]
    by_op: Dict[str, List[float]] = defaultdict(list)
    for e in api:
        if e.get("duration_ms") is not None:
            by_op[e["op_id"]].append(float(e["duration_ms"]))
    total = len(api)
    err_class = Counter(e.get("error_class") for e in api)
    health = {"requests": total, "error_ratio": {c: round(err_class[c] / total, 4) if total else 0.0 for c in ("client", "server")},
              "latency_ms": {op: {"p50": _pctl(v, 0.5), "p95": _pctl(v, 0.95), "p99": _pctl(v, 0.99), "n": len(v)} for op, v in sorted(by_op.items())},
              "top_error_codes": Counter((e["op_id"], e.get("error_code")) for e in api if e.get("status") == "error").most_common(5)}

    def outputs(op: str) -> List[Mapping[str, Any]]:
        return [e.get("outputs", {}) for e in outs if e.get("op_id") == op]

    parse = Counter()
    for e in api:
        if e["op_id"] == "parse_resume" and e.get("status") == "error":
            parse[e.get("error_code")] += 1
    for o in outputs("parse_resume"):
        parse["parsed" if o.get("has_text") else "no_text"] += 1
    ats = [o for o in outputs("score_ats") if o.get("scoring_mode") == "ats_engine"]
    zones, decisions = Counter(o.get("zone") for o in ats), Counter(o.get("decision") for o in outputs("recommend_decision"))
    decs = outputs("recommend_decision")
    review = sum(1 for o in decs if o.get("human_review_required"))
    refs = {s: len({e.get("candidate_ref") for e in outs if e.get("op_id") == op and e.get("candidate_ref")}) for s, op in
            (("scored", "score_ats"), ("screened", "score_screening"), ("interviewed", "score_interview"), ("decided", "recommend_decision"))}
    processing = {"candidates_seen_by_stage": refs, "resumes_by_outcome": suppress_small(parse), "zones": suppress_small(zones), "decisions": suppress_small(decisions),
                  "human_review_required_share": round(review / len(decs), 4) if decs else None,
                  "rejections_recommended": sum(1 for o in decs if o.get("decision") == "rejected")}

    calls = Counter(o.get("call_status") for o in outputs("score_screening"))
    started = sum(n for s, n in calls.items() if s != "not_started")
    iv = Counter((o.get("interview_type"), o.get("interview_status")) for o in outputs("score_interview"))
    hr = [o for o in outputs("score_interview") if o.get("interview_type") == "hr" and o.get("interview_status") == "scored"]
    answers = sum(o.get("answers_scored", 0) for o in hr)
    nonsub = sum(o.get("non_substantive_answers", 0) for o in hr)
    interviews = {"screening_calls": suppress_small(calls), "screening_completion_rate": round(calls["completed"] / started, 4) if started else None,
                  "interview_status": suppress_small({f"{t}/{s}": n for (t, s), n in iv.items()}),
                  "substantive_answer_rate": round(1 - nonsub / answers, 4) if answers else None}

    def hist(values: Sequence[float]) -> List[int]:
        return _bin_counts(values)

    scores = {"ats_score": [o["ats_score"] for o in ats], "hr_score": [o["hr_score"] for o in outputs("score_interview") if o.get("hr_score") is not None],
              "technical_score": [o["technical_score"] for o in outputs("score_interview") if o.get("technical_score") is not None],
              "screening_score": [o["screening_score"] for o in outputs("score_screening") if o.get("screening_score") is not None]}
    quality = {"histograms_10_bins": {k: hist(v) for k, v in scores.items()}, "ats_psi_vs_baseline": (round(psi(baseline_ats, scores["ats_score"]), 4) if baseline_ats and scores["ats_score"] else None)}
    if quality["ats_psi_vs_baseline"] is not None:
        quality["ats_psi_band"] = psi_band(quality["ats_psi_vs_baseline"])
    return {"service_health": health, "candidate_processing": processing, "interview_success": interviews, "model_quality": quality}


# ======================================================================================================================
# 5. Synthetic traffic from real events, with incident injectors
# ======================================================================================================================
DEFAULT_MIX = {"score_ats": 0.40, "score_interview": 0.20, "score_screening": 0.15, "recommend_decision": 0.15, "parse_resume": 0.10}
EpochEvent = Tuple[float, Dict[str, Any]]


@dataclass(frozen=True)
class Incident:
    kind: str                      # latency | server_errors | client_errors | score_shift | outage | invariant | parse_failures | silent_calls
    start: float                   # seconds from the start of the stream
    end: float
    magnitude: float = 1.0
    op: Optional[str] = None


def _iso(t: float) -> str:
    return datetime.fromtimestamp(t, tz=timezone.utc).isoformat(timespec="milliseconds")


def generate_stream(pools: Mapping[str, List[List[Dict[str, Any]]]], client_error_pool: List[List[Dict[str, Any]]], seed: int, hours: float, rate_per_s: float = 1.0,
                    mix: Mapping[str, float] = DEFAULT_MIX, incidents: Sequence[Incident] = (), epoch0: float = 1_762_300_800.0,
                    background_client_error: float = 0.02, background_server_error: float = 0.0005) -> List[EpochEvent]:
    """Events for `hours` of traffic. `pools[op]` holds real [api_request, model_output?] event groups; each arrival copies one. Background errors and
    every incident are synthetic. Returns (epoch seconds, event) pairs sorted by time."""
    rng = random.Random(seed)
    ops, weights = list(mix), [mix[o] for o in mix]
    horizon = hours * 3600.0
    out: List[EpochEvent] = []
    t = 0.0
    n = 0
    while True:
        t += rng.expovariate(rate_per_s)
        if t >= horizon:
            break
        n += 1
        live = [i for i in incidents if i.start <= t < i.end]
        if any(i.kind == "outage" for i in live):
            continue
        op = rng.choices(ops, weights)[0]
        group = [dict(e) for e in rng.choice(pools[op])]
        for e in group:
            e["op_id"] = op
        u = rng.random()
        if u < background_client_error and client_error_pool:
            group = [dict(e) for e in rng.choice(client_error_pool)]
            for e in group:
                e["op_id"] = op
        elif u < background_client_error + background_server_error:
            group = [_server_error(group[0], "timeout")]
        for inc in live:
            group = _apply(inc, group, rng, client_error_pool, op)
        rid = f"req-{seed:02d}{n:08x}"
        for e in group:
            e["request_id"] = rid
            e["ts"] = _iso(epoch0 + t)
            out.append((epoch0 + t, e))
    return out


def _server_error(api: Dict[str, Any], code: str) -> Dict[str, Any]:
    e = dict(api)
    e.update(status="error", error_code=code, error_class="server", http_status=ERROR_RULES[code].http_status)
    e.pop("warnings", None)
    return e


def _apply(inc: Incident, group: List[Dict[str, Any]], rng: random.Random, client_pool: List[List[Dict[str, Any]]], op: str) -> List[Dict[str, Any]]:
    if inc.op and inc.op != op and inc.kind in ("latency", "score_shift", "silent_calls", "parse_failures", "invariant"):
        return group
    api = group[0]
    if inc.kind == "latency":
        api["duration_ms"] = round(api["duration_ms"] * inc.magnitude, 3)
    elif inc.kind == "server_errors" and rng.random() < inc.magnitude:
        return [_server_error(api, rng.choice(["internal_error", "timeout", "service_unavailable"]))]
    elif inc.kind == "client_errors" and rng.random() < inc.magnitude and client_pool:
        g = [dict(e) for e in rng.choice(client_pool)]
        for e in g:
            e["op_id"] = op
        return g
    elif inc.kind == "score_shift" and op == "score_ats":
        for e in group[1:]:
            o = dict(e.get("outputs", {}))
            if "ats_score" in o:
                o["ats_score"] = round(min(100.0, max(0.0, o["ats_score"] + inc.magnitude)), 1)
                o["zone"] = "shortlist" if o["ats_score"] >= 60 else ("review" if o["ats_score"] >= 40 else "reject")        # simulation-only mapping
                e["outputs"] = o
    elif inc.kind == "silent_calls" and op == "score_screening" and rng.random() < inc.magnitude:
        for e in group[1:]:
            o = dict(e.get("outputs", {}))
            o["call_status"] = "ended_early"
            e["outputs"] = o
    elif inc.kind == "parse_failures" and op == "parse_resume" and rng.random() < inc.magnitude:
        e = dict(api)
        e.update(status="error", error_code="corrupt_file", error_class="client", http_status=422)
        e.pop("warnings", None)
        return [e]
    elif inc.kind == "invariant" and op == "recommend_decision" and len(group) > 1 and not any(g.get("_violated") for g in group):
        for e in group[1:]:
            o = dict(e.get("outputs", {}))
            o.update(decision="rejected", human_confirmation_required=False, automated_action="auto_reject")
            e["outputs"] = o
    return group


def run_alerts(stream: Sequence[EpochEvent], baseline: Baseline, rules: Sequence[AlertRule] = ALERT_RULES, tick_s: int = 60,
               extras_at: Optional[Callable[[float], Mapping[str, float]]] = None) -> Tuple[List[AlertEvent], TimeSeriesStore]:
    """Replay a stream through the store and the alert manager, one tick per minute. Returns every firing/resolved event."""
    store = TimeSeriesStore()
    mgr = AlertManager(store, baseline, rules)
    if not stream:
        return [], store
    t0, t1 = stream[0][0], stream[-1][0]
    i, t = 0, math.ceil(t0 / tick_s) * tick_s
    while t <= t1 + tick_s:
        while i < len(stream) and stream[i][0] <= t:
            store.ingest(stream[i][0], stream[i][1])
            i += 1
        mgr.tick(t, extras_at(t) if extras_at else None)
        t += tick_s
    return mgr.history, store
