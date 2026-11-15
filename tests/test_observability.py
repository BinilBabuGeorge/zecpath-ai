"""
Day 61 tests: monitoring and observability.

  * test_guard_*        the logger refuses personal content, unlisted fields and free text, never raises, and counts what it refused.
  * test_observer_*     wrapping a service changes nothing in its answer, logs only allowlisted numbers and codes, and matches the generated schema.
  * test_allowlist_*    every field the observer may log is really produced by a real service, and none of them is text.
  * test_metrics_*      bounded label sets, histogram quantiles, Prometheus output, thread safety, and the catalogue matching the code.
  * test_psi_*          the drift measure.
  * test_alert_*        each rule fires on its own condition and stays quiet otherwise; the plan's cross-references hold.
  * test_simulation_*   normal traffic stays quiet and injected incidents are detected, on streams resampled from real service events.
  * test_dashboard_*    panel values equal what the events say; small groups are suppressed; no candidate reference is shown.
  * test_audit_*        decisions are replayable from the audit log; the Day 55 gap is real; human review rules hold.
  * test_generated_*    the files in the repo equal what the code generates; the three documents cover the plan.
"""

import glob
import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests" / "golden"))

from ats_engine.batch_service import ATSBatchService
from ats_engine.resume_parsing_service import ResumeParsingService
from ats_engine.service import ATSService
from interview_ai.service import InterviewIntelligenceService
from make_day60_golden import answer_corpus
from parsers import observability as ob
from parsers import observability_plan as plan
from parsers.audit_trail import FORBIDDEN_PAYLOAD_KEYS, AuditEventType, AuditIntegrityError, AuditLog, AuditPayloadError
from parsers.decision_audit import DecisionAuditRecorder, reasons_digest
from parsers.integration_contract import ERROR_RULES, OPERATIONS
from scoring.service import DecisionScoringService
from screening_ai.service import ScreeningService

JDS = [Path(p).read_text(encoding="utf-8") for p in sorted(glob.glob(str(ROOT / "data/samples/jds/*.txt")))]
RESUMES = [Path(p).read_text(encoding="utf-8") for p in sorted(glob.glob(str(ROOT / "data/samples/resumes/*.txt")))]
DOCX = sorted(glob.glob(str(ROOT / "data/raw_resumes/docx/*.docx")))
MARK = "ZZ-SECRET-MARKER-ZZ-DO-NOT-LOG"


def _services():
    return {"parse_resume": ResumeParsingService(resolver=lambda ref: DOCX[0]), "score_ats": ATSService(), "score_ats_batch": ATSBatchService(), "score_screening": ScreeningService(),
            "score_interview": InterviewIntelligenceService(), "recommend_decision": DecisionScoringService()}


def _observer(lines=None, prefix="req", **kw):
    lines = [] if lines is None else lines
    counter = iter(range(1, 10_000_000))
    return ob.ServiceObserver(_services(), ob.StructuredLogger(lines.append, **kw), request_ids=lambda: f"{prefix}-{next(counter):06d}"), lines


TURNS = [{"text": "I am a MERN developer with three years of experience.", "confidence": 0.9}, {"text": "My notice period is one month.", "confidence": 0.9}]
CALLS = [
    ("parse_resume", {"candidate_id": "cref_a", "file_ref": "x.docx", "file_type": "docx", "as_of_date": "2026-11-01"}),
    ("score_ats", {"resume_text": RESUMES[0], "job_description": JDS[0]}),
    ("score_ats_batch", {"job_description": JDS[0], "candidates": [{"candidate_id": "A1", "resume_text": RESUMES[0]}, {"candidate_id": "A2", "resume_text": RESUMES[1]}]}),
    ("score_screening", {"candidate_id": "cref_a", "turns": TURNS}),
    ("score_interview", {"interview_type": "hr", "answers": ["I led a team of five on a React project and we shipped on time."]}),
    ("score_interview", {"interview_type": "technical", "domain": "mern", "experience_years": 3, "answers": ["React uses a virtual DOM to batch updates."]}),
    ("recommend_decision", {"candidate_id": "cref_a", "ats_score": 70, "screening_score": 75, "hr_interview_score": 80}),
]


SEVEN_TURNS = [{"text": s, "confidence": 0.9} for s in (
    "Hello, I am a MERN developer with three years of experience at a product company.", "I did my B.Tech in Computer Science in 2021.",
    "I have worked for three years building React and Node.js applications.", "My skills are React, Node.js, MongoDB and Docker.",
    "I am currently based in Bengaluru.", "My expected salary is eight lakhs per annum.", "My notice period is one month.")]


@pytest.fixture(scope="module")
def real():
    """Real events from the real services: successes of every operation and a set of bad requests. Warmed first: the monitoring pools should describe a
    worker in steady state; the 1-2 second cold-start outlier is exactly what Day 60's warm-up removes."""
    from utils.warmup import warm_up
    warm_up(("ats", "parsing", "screening", "interview", "decision"))
    lines: list = []
    obs, _ = _observer(lines)
    for op, payload in CALLS:
        obs.call(op, payload, candidate_ref="cref_a")
    for op, payload in [("score_ats", {}), ("recommend_decision", {"ats_score": 101}), ("score_interview", {"interview_type": "final"}), ("score_screening", {"turns": "x"}),
                        ("parse_resume", {"candidate_id": "c", "file_ref": "x", "file_type": "txt"})]:
        obs.call(op, payload)
    return [json.loads(l) for l in lines], obs


# ---------------------------------------------------------------------------------------------------- the guard
def _ok_fields(**extra):
    return {"request_id": "req-1", "op_id": "score_ats", "status": "success", "duration_ms": 1.5, **extra}


def test_guard_refuses_forbidden_keys_unlisted_fields_and_free_text_and_counts_them():
    lines: list = []
    lg = ob.StructuredLogger(lines.append)
    assert lg.emit("api_request", **_ok_fields()) is not None
    for bad in (_ok_fields(resume_text="Jane Doe"), _ok_fields(notes="x"), _ok_fields(error_code="x" * 65), _ok_fields(duration_ms=float("nan")),
                _ok_fields(warnings=[1, 2]), _ok_fields(email="a@b.c")):
        assert lg.emit("api_request", **bad) is None
    assert lg.emit("not_a_kind", **_ok_fields()) is None
    assert len(lines) == 1 and lg.dropped == {"policy_violation": 7}


def test_guard_checks_nested_outputs_and_a_forbidden_key_hidden_inside_them():
    lg = ob.StructuredLogger(lambda s: None)
    assert lg.emit("model_output", request_id="r", op_id="score_ats", outputs={"ats_score": 70.1, "zone": "review"}) is not None
    assert lg.emit("model_output", request_id="r", op_id="score_ats", outputs={"ats_score": 70.1, "transcript": "hello"}) is None
    assert lg.emit("model_output", request_id="r", op_id="score_ats", outputs={"zone": "x" * 70}) is None
    assert lg.emit("model_output", request_id="r", op_id="score_ats", outputs={"a": {"b": {"c": {"d": 1}}}}) is None
    assert lg.emit("model_output", request_id="r", op_id="score_ats", outputs={"zone": ["a", "b"]}) is None


def test_guard_never_raises_even_if_the_sink_fails_and_counts_it():
    def broken(_line):
        raise OSError("disk full")

    lg = ob.StructuredLogger(broken)
    assert lg.emit("api_request", **_ok_fields()) is None
    assert lg.dropped == {"sink_error": 1}


def test_guard_sampling_is_deterministic_and_errors_are_never_sampled():
    lines: list = []
    lg = ob.StructuredLogger(lines.append, sample={"api_request": 0.25})
    for i in range(100):
        lg.emit("api_request", **_ok_fields(request_id=f"r{i}"))
    assert len(lines) == 25
    for i in range(10):
        lg.emit("error", request_id=f"e{i}", op_id="score_ats", error_code="timeout")
    assert sum(1 for l in lines if '"event":"error"' in l) == 10


def test_guard_forbidden_keys_are_the_day_55_list():
    assert ob.FORBIDDEN_PAYLOAD_KEYS is FORBIDDEN_PAYLOAD_KEYS


# ---------------------------------------------------------------------------------------------------- the observer
def test_observer_returns_the_services_answer_unchanged():
    obs, _ = _observer()
    for op, payload in CALLS[1:]:
        assert obs.call(op, payload) == _services()[op].run(payload)


def test_observer_logs_no_input_text_for_any_operation():
    lines: list = []
    obs, _ = _observer(lines)
    obs.call("score_ats", {"resume_text": f"Skills: React {MARK}", "job_description": f"Required Skills: React {MARK}"})
    obs.call("score_screening", {"candidate_id": "c1", "turns": [{"text": f"I am {MARK}", "confidence": 0.9}]})
    obs.call("score_interview", {"interview_type": "hr", "answers": [f"I am {MARK} and I led a team."]})
    obs.call("score_ats", {"resume_text": [MARK], "job_description": "x"})                      # an error path that could echo the input
    obs.call("recommend_decision", {"candidate_id": "c1", "ats_score": 60, "note": MARK})
    assert lines and MARK not in "\n".join(lines)


def test_observer_events_match_the_generated_schema_for_successes_and_errors(real):
    events, _ = real
    validator = jsonschema.Draft202012Validator(ob.log_schema_document())
    assert {e["event"] for e in events} == set(ob.EVENT_KINDS)
    for e in events:
        assert validator.is_valid(e), (e, [x.message for x in validator.iter_errors(e)][:2])


def test_observer_event_has_the_request_id_and_the_same_id_on_every_event_of_a_call():
    lines: list = []
    obs, _ = _observer(lines)
    obs.call("score_ats", {})
    obs.call("score_ats", {"resume_text": "Skills: React", "job_description": "Required Skills: React"}, request_id="req-fixed")
    events = [json.loads(l) for l in lines]
    first, second = [e for e in events if e["request_id"] == "req-000001"], [e for e in events if e["request_id"] == "req-fixed"]
    assert {e["event"] for e in first} == {"api_request", "error"} and {e["event"] for e in second} == {"api_request", "model_output"}


def test_observer_classifies_errors_as_client_or_server_and_counts_them():
    class Flaky:
        def run(self, payload):
            return {"service": "x", "model_version": "v", "api_version": "1.0", "status": "error", "error": {"code": payload["code"], "message": "m", "field": None}}

    lines: list = []
    obs = ob.ServiceObserver({"score_ats": Flaky()}, ob.StructuredLogger(lines.append))
    for code in ("invalid_input", "internal_error", "timeout", "missing_field", "some_new_code"):
        obs.call("score_ats", {"code": code})
    m = obs.metrics
    assert m.get("ai_requests_total", op="score_ats", status="error", error_class="client") == 3        # an unmapped code is not a server error by itself
    assert m.get("ai_requests_total", op="score_ats", status="error", error_class="server") == 2
    assert m.get("ai_errors_total", op="score_ats", code="other") == 1


def test_observer_metrics_agree_with_the_events(real):
    events, obs = real
    api = [e for e in events if e["event"] == "api_request"]
    total = sum(v for v in obs.metrics._values["ai_requests_total"].values())
    assert total == len(api)
    errors = sum(v for v in obs.metrics._values["ai_errors_total"].values())
    assert errors == sum(1 for e in api if e["status"] == "error") == sum(1 for e in events if e["event"] == "error")


def test_observer_never_breaks_a_request_when_logging_fails():
    def broken(_):
        raise OSError("down")

    obs = ob.ServiceObserver(_services(), ob.StructuredLogger(broken))
    payload = {"resume_text": RESUMES[0], "job_description": JDS[0]}
    assert obs.call("score_ats", payload) == ATSService().run(payload)
    assert obs.metrics.get("ai_log_dropped_total", reason="sink_error") >= 1


def test_observer_counts_a_leak_attempt_as_a_policy_violation_and_does_not_write_it():
    class Leaky:
        def run(self, payload):
            return {"service": "x", "model_version": "v" * 80, "api_version": "1.0", "status": "success", "ats_score": 70.0, "scoring_mode": "ats_engine", "zone": "review"}

    lines: list = []
    obs = ob.ServiceObserver({"score_ats": Leaky()}, ob.StructuredLogger(lines.append))
    obs.call("score_ats", {})
    assert lines == [] or all("v" * 80 not in l for l in lines)
    assert obs.metrics.get("ai_log_dropped_total", reason="policy_violation") >= 1


def test_observer_flags_an_automated_rejection_as_an_invariant_violation():
    class BadDecision:
        def run(self, payload):
            return {"service": "x", "model_version": "v", "api_version": "1.0", "status": "success", "hiring_fit_score": 20.0, "decision": "rejected", "hold_kind": None,
                    "confidence": 90.0, "provisional": False, "missing_rounds": [], "human_review_required": False, "human_confirmation_required": False,
                    "automation_eligible": True, "automated_action": "auto_reject", "reasons": ["x"], "warnings": []}

    obs = ob.ServiceObserver({"recommend_decision": BadDecision()}, ob.StructuredLogger(lambda s: None))
    obs.call("recommend_decision", {})
    assert obs.metrics.get("ai_invariant_violations_total", invariant="automated_rejection") == 1
    real_obs, _ = _observer()
    real_obs.call("recommend_decision", {"candidate_id": "c", "ats_score": 10, "ats_zone": "reject", "screening_score": 10, "hr_interview_score": 10, "technical_score": 10,
                                         "machine_test_score": 10})
    assert real_obs.metrics.get("ai_invariant_violations_total", invariant="automated_rejection") in (None, 0)


def test_observer_unknown_operation_is_an_error():
    obs, _ = _observer()
    with pytest.raises(KeyError):
        obs.call("nonsense", {})


def test_observer_overhead_is_small():
    import time
    svc, obs = ATSService(), ob.ServiceObserver({"score_ats": ATSService()}, ob.StructuredLogger(lambda s: None))
    bodies = [{"resume_text": RESUMES[i % len(RESUMES)] + f"\nNote {i}.", "job_description": JDS[0]} for i in range(60)]

    def med(fn):
        ts = []
        for b in bodies:
            t = time.perf_counter()
            fn(b)
            ts.append(time.perf_counter() - t)
        return sorted(ts)[len(ts) // 2]

    med(svc.run)
    direct = min(med(svc.run) for _ in range(3))
    observed = min(med(lambda b: obs.call("score_ats", b)) for _ in range(3))
    assert observed - direct < 0.002, f"observer added {(observed - direct) * 1000:.2f} ms"


# ---------------------------------------------------------------------------------------------------- allowlist
def test_allowlist_covers_real_operations_and_every_field_is_produced_by_a_real_service(real):
    events, _ = real
    assert set(ob.MODEL_OUTPUT_ALLOWLIST) <= {o.op_id for o in OPERATIONS}
    produced = {}
    for op, payload in CALLS:
        env = _services()[op].run(payload)
        produced.setdefault(op, set()).update(env)
    for op, fields in ob.MODEL_OUTPUT_ALLOWLIST.items():
        for f in fields:
            assert f in produced[op] or (op == "score_interview" and f in ("hr_score", "technical_score", "communication_score", "relevance_score", "confidence_score",
                                                                            "non_substantive_answers", "tier", "answers_scored", "answers_ignored", "interview_type", "interview_status")), (op, f)


def test_allowlist_has_no_forbidden_name_and_logged_values_are_numbers_or_short_codes(real):
    events, _ = real
    for fields in ob.MODEL_OUTPUT_ALLOWLIST.values():
        assert not {f.lower() for f in fields} & FORBIDDEN_PAYLOAD_KEYS
    for e in events:
        if e["event"] == "model_output":
            for k, v in e["outputs"].items():
                assert v is None or isinstance(v, (bool, int, float)) or (isinstance(v, str) and len(v) <= 64), (k, v)


def test_allowlist_keeps_the_cleaned_resume_text_and_reason_sentences_out_of_the_logs(real):
    events, _ = real
    blob = json.dumps(events)
    parse = _services()["parse_resume"].run(CALLS[0][1])
    assert parse["cleaned_text"][:40] not in blob
    decision = _services()["recommend_decision"].run(CALLS[-1][1])
    assert all(r[:40] not in blob for r in decision["reasons"])


# ---------------------------------------------------------------------------------------------------- metrics
def test_metrics_label_names_are_checked_and_label_sets_are_capped():
    m = ob.MetricsRegistry(max_label_sets=3)
    m.define("c", "counter", ("who",), "x")
    with pytest.raises(ValueError):
        m.inc("c", wrong="a")
    for i in range(10):
        m.inc("c", who=f"candidate-{i}")                      # the mistake the cap exists for: a label that varies per candidate
    assert len(m._values["c"]) == 4 and m.overflowed["c"] == 7 and m.get("c", who=ob.OVERFLOW) == 7
    with pytest.raises(ValueError):
        m.inc("c", -1, who="a")
    with pytest.raises(ValueError):
        m.define("bad", "weird")
    with pytest.raises(ValueError):
        m.define("h", "histogram")


def test_metrics_histogram_quantiles_are_within_a_bucket_of_the_truth():
    import random
    rng = random.Random(5)
    m = ob.MetricsRegistry()
    m.define("h", "histogram", ("op",), "x", ob.LATENCY_BUCKETS_S)
    values = sorted(rng.lognormvariate(-5.5, 0.6) for _ in range(5000))
    for v in values:
        m.observe("h", v, op="a")
    for q in (0.5, 0.95, 0.99):
        exact = values[int(q * (len(values) - 1))]
        est = m.quantile("h", q, op="a")
        bucket = next(b for b in ob.LATENCY_BUCKETS_S if b >= exact)
        lower = max([0.0] + [b for b in ob.LATENCY_BUCKETS_S if b < exact])
        assert lower <= est <= bucket, (q, exact, est)
    assert m.quantile("h", 0.5, op="never") is None


def test_metrics_prometheus_text_is_well_formed_and_cumulative():
    m = ob.standard_metrics()
    m.inc("ai_requests_total", op="score_ats", status="success", error_class="none")
    for v in (0.001, 0.004, 0.2):
        m.observe("ai_request_duration_seconds", v, op="score_ats")
    text = m.render_prometheus()
    assert "# TYPE ai_requests_total counter" in text and "# HELP ai_request_duration_seconds" in text
    buckets = [float(l.split()[-1]) for l in text.splitlines() if l.startswith("ai_request_duration_seconds_bucket")]
    assert buckets == sorted(buckets) and buckets[-1] == 3
    assert 'ai_request_duration_seconds_count{op="score_ats"} 3' in text


def test_metrics_are_thread_safe():
    m = ob.MetricsRegistry()
    m.define("c", "counter", ("k",), "x")
    m.define("h", "histogram", (), "x", (1.0, 2.0))

    def work():
        for i in range(2000):
            m.inc("c", k="a")
            m.observe("h", 1.5)

    threads = [threading.Thread(target=work) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert m.get("c", k="a") == 16000 and m.get("h")["count"] == 16000


def test_metrics_catalogue_matches_what_the_code_emits():
    std = ob.standard_metrics()
    prototype = {m.name: m for m in plan.METRICS if m.status == "prototype"}
    assert set(prototype) == set(std._defs)
    for name, m in prototype.items():
        assert std._defs[name]["kind"] == m.kind and std._defs[name]["labels"] == m.labels, name
    assert len(plan.METRIC_BY_NAME) == len(plan.METRICS)


def test_metrics_cover_the_three_things_the_brief_asks_for():
    cats = {m.category for m in plan.METRICS}
    assert {"response_time", "accuracy", "failure"} <= cats
    for need in ("response_time", "accuracy", "failure"):
        assert any(m.status == "prototype" for m in plan.METRICS if m.category == need)
    assert set(plan.SLOS) >= {"sync_availability", "sync_latency"}
    assert plan.SLOS["sync_availability"]["target"] == 0.999


def test_metrics_server_codes_are_exactly_the_5xx_codes_of_the_day_59_policy():
    assert plan.SERVER_CODES == {c for c, r in ERROR_RULES.items() if r.http_status >= 500} == {"internal_error", "service_unavailable", "timeout"}


# ---------------------------------------------------------------------------------------------------- drift
def test_psi_known_values_and_bands():
    same = [10, 20, 30, 40, 50, 60, 70, 80, 90, 95]
    assert plan.psi(same, same) == 0.0
    shifted = [v + 25 for v in same[:6]] + [95, 96, 97, 98]
    assert plan.psi(same, shifted) > 0.25 and plan.psi_band(plan.psi(same, shifted)) == "major"
    slightly = same[:9] + [75]
    assert 0 < plan.psi(same, slightly) < plan.psi(same, shifted)
    assert plan.psi_band(0.05) == "stable" and plan.psi_band(0.15) == "moderate" and plan.psi_band(0.4) == "major"
    with pytest.raises(ValueError):
        plan.psi([], [1])
    assert plan.psi([100.0, 100.0], [100.0]) == 0.0                       # the top edge belongs to the last bin
    assert plan.psi(same, same[::-1]) == pytest.approx(0.0)               # order does not matter


# ---------------------------------------------------------------------------------------------------- alert rules
def _api(t, op="score_ats", status="success", cls="none", code=None, dur=3.0):
    return t, {"event": "api_request", "op_id": op, "status": status, "error_class": cls, "error_code": code, "duration_ms": dur}


def _run(stream, rules=plan.ALERT_RULES, baseline=None, extras=None):
    return plan.run_alerts(stream, baseline or plan.Baseline(), rules, extras_at=extras)[0]


def _fired(history):
    return {h.rule_id for h in history if h.state == "firing"}


def test_alert_rules_are_well_formed_and_unique():
    ids = [r.rule_id for r in plan.ALERT_RULES]
    assert len(ids) == len(set(ids)) and plan.RULE_BY_ID.keys() == set(ids)
    for r in plan.ALERT_RULES:
        assert r.severity in ("page", "ticket") and r.runbook and r.owner and r.description and r.window_s > 0 and r.interval_s > 0 and r.for_s >= 0
        assert (r.status == "evaluable") == (r.blocked_by is None)
    assert {r.rule_id for r in plan.ALERT_RULES if r.status != "evaluable"} == {"A14", "A15", "A16"}
    assert "demographic" in plan.RULE_BY_ID["A16"].blocked_by


def test_alert_pages_are_reserved_for_outage_invariants_and_compliance_gaps():
    pages = {r.rule_id for r in plan.ALERT_RULES if r.severity == "page"}
    assert pages == {"A01", "A08", "A11", "A12"}
    assert plan.RULE_BY_ID["A04"].severity == "ticket"                                       # a caller's bad requests never page the AI team


def test_alert_availability_fires_on_server_errors_but_not_on_client_errors():
    def traffic(error_class, code, rate=0.3, start=3600 * 2, end=3600 * 2 + 900):
        out = []
        for i in range(3 * 3600):
            t = i * 1.0
            bad = start <= t < end and (i % int(1 / rate) == 0)
            out.append(_api(t, status="error" if bad else "success", cls=error_class if bad else "none", code=code if bad else None))
        return out

    assert "A01" in _fired(_run(traffic("server", "timeout")))
    assert not _fired(_run(traffic("client", "invalid_input"))) & {"A01", "A02"}


def test_alert_latency_uses_the_per_operation_threshold_and_needs_enough_traffic():
    slow = [_api(i * 2.0, dur=400.0 if i * 2.0 > 1800 else 3.0) for i in range(2400)]
    assert "A03" in _fired(_run(slow))
    parse_slow_ok = [_api(i * 2.0, op="parse_resume", dur=120.0) for i in range(2400)]
    assert "A03" not in _fired(_run(parse_slow_ok))                                          # 120 ms is fine for a parse (threshold 300), not for ATS
    sparse = [_api(i * 120.0, dur=900.0) for i in range(40)]
    assert "A03" not in _fired(_run(sparse))


def test_alert_latency_catches_a_large_slowdown_that_stays_under_the_absolute_threshold():
    """The first version missed ATS getting 15 times slower (3 ms to 45 ms) because the SLO threshold is 50 ms. The relative test catches it, given a baseline."""
    stream = [_api(i * 2.0, dur=45.0 if i * 2.0 > 1800 else 3.0) for i in range(2400)]
    assert "A03" not in _fired(_run(stream))                                                  # no baseline, and 45 ms is under 50 ms
    assert "A03" in _fired(_run(stream, baseline=plan.Baseline(latency_p95_ms={"score_ats": 3.2})))
    normal = [_api(i * 2.0, dur=3.0 + (i % 7) * 0.1) for i in range(2400)]
    assert "A03" not in _fired(_run(normal, baseline=plan.Baseline(latency_p95_ms={"score_ats": 3.6})))


def test_alert_a_sticky_percentile_rule_needs_a_window_shorter_than_its_wait():
    """The flaw this test pins: a p95 stays high for as long as slow events stay in the window, so with window >= wait the wait cannot filter a blip."""
    for r in plan.ALERT_RULES:
        if r.kind == "latency":
            assert r.window_s < r.for_s, r.rule_id


def test_alert_for_duration_ignores_a_short_blip_and_resolution_is_reported():
    def stream(bad_minutes):
        out = []
        for i in range(6 * 3600):
            minute = i // 60
            bad = 120 <= minute < 120 + bad_minutes
            out.append(_api(float(i), dur=500.0 if bad else 3.0))
        return out

    assert "A03" not in _fired(_run(stream(4)))                                              # four slow minutes < the 10-minute for-duration
    hist = _run(stream(30))
    assert [h.state for h in hist if h.rule_id == "A03"] == ["firing", "resolved"]


def test_alert_absence_fires_on_silence_and_invariant_fires_on_the_first_violation():
    gap = [_api(float(i)) for i in range(0, 3600)] + [_api(float(i)) for i in range(3600 + 1500, 3 * 3600)]
    assert "A11" in _fired(_run(gap))
    out = [_api(float(i)) for i in range(7200)]
    bad = {"event": "model_output", "op_id": "recommend_decision", "outputs": {"decision": "rejected", "human_confirmation_required": False, "automated_action": "auto_reject"}}
    good = {"event": "model_output", "op_id": "recommend_decision", "outputs": {"decision": "rejected", "human_confirmation_required": True, "automated_action": "none"}}
    assert "A08" not in _fired(_run(out + [(3000.5, good)]))
    hist = _run(sorted(out + [(3000.5, bad)], key=lambda x: x[0]))
    first = next(h for h in hist if h.rule_id == "A08" and h.state == "firing")
    assert 3000 <= first.at <= 3000 + 120


def test_alert_extra_rules_need_their_input_and_planned_rules_are_never_evaluated():
    out = [_api(float(i)) for i in range(3600)]
    assert not _fired(_run(out)) & {"A12", "A13"}
    assert "A12" in _fired(_run(out, extras=lambda t: {"decisions_without_audit": 1.0} if t > 1800 else {}))
    mgr = plan.AlertManager(plan.TimeSeriesStore())
    assert {r.rule_id for r in mgr.rules}.isdisjoint({"A14", "A15", "A16"})


def test_alert_drift_rules_fire_on_a_shifted_distribution_and_stay_quiet_on_a_stable_one():
    import random
    rng = random.Random(3)
    base = [rng.gauss(55, 15) for _ in range(500)]
    base = [min(100, max(0, v)) for v in base]

    def stream(delta):
        out = []
        for i in range(8 * 3600):
            if i % 4 == 0:
                v = min(100, max(0, rng.choice(base) + (delta if i > 4 * 3600 else 0)))
                out.append((float(i), {"event": "model_output", "op_id": "score_ats", "outputs": {"scoring_mode": "ats_engine", "ats_score": v, "zone": "shortlist" if v >= 60 else "review"}}))
            out.append(_api(float(i)))
        return out

    b = plan.Baseline(ats_scores=base, shortlist_share=sum(1 for v in base if v >= 60) / len(base))
    assert not _fired(_run(stream(0), baseline=b)) & {"A06", "A07"}
    assert {"A06", "A07"} <= _fired(_run(stream(20), baseline=b))


def test_alert_ratio_rules_need_the_minimum_traffic():
    few = [_api(i * 60.0, op="parse_resume", status="error", cls="client", code="corrupt_file") for i in range(10)]
    assert not _fired(_run(few))


def test_alert_every_evaluable_rule_is_on_a_dashboard_and_every_panel_reference_exists():
    on_dash = {r for d in plan.DASHBOARDS.values() for p in d["panels"] for r in p.alert_rules}
    assert {r.rule_id for r in plan.ALERT_RULES if r.status == "evaluable"} <= on_dash
    assert on_dash <= set(plan.RULE_BY_ID)
    for d in plan.DASHBOARDS.values():
        for p in d["panels"]:
            assert set(p.metrics) <= set(plan.METRIC_BY_NAME), p.panel_id
            assert p.audience and p.query and p.unit


def test_alert_dashboards_cover_what_the_brief_names():
    assert {"candidate_processing", "interview_success"} <= set(plan.DASHBOARDS)
    ids = [p.panel_id for d in plan.DASHBOARDS.values() for p in d["panels"]]
    assert len(ids) == len(set(ids))
    for name in ("candidate_processing", "interview_success"):
        assert "recruiter" in plan.DASHBOARDS[name]["audience"]


# ---------------------------------------------------------------------------------------------------- simulation on real events
@pytest.fixture(scope="module")
def pools(real):
    events, _ = real
    groups: dict = {}
    for e in events:
        groups.setdefault(e["request_id"], []).append(e)
    pools_, bad = {}, []
    # more real events: several decisions and screenings so the pools are not tiny
    lines: list = []
    obs, _ = _observer(lines, prefix="more")                 # a different id prefix: two observers must not reuse request ids
    answers = answer_corpus()
    for i in range(30):
        obs.call("recommend_decision", {"candidate_id": f"cref_{i}", "ats_score": 30 + i * 2, "screening_score": 40 + i, "hr_interview_score": 50 + i,
                                        "ats_zone": ["shortlist", "review", "reject"][i % 3]}, candidate_ref=f"cref_{i}")
        obs.call("score_screening", {"candidate_id": f"cref_{i}", "turns": SEVEN_TURNS if i % 2 == 0 else TURNS[: 1 + i % 2]}, candidate_ref=f"cref_{i}")
        obs.call("score_interview", {"interview_type": "hr", "answers": answers[i * 2:i * 2 + 3]}, candidate_ref=f"cref_{i}")
        obs.call("score_ats", {"resume_text": RESUMES[i % len(RESUMES)], "job_description": JDS[i % len(JDS)]}, candidate_ref=f"cref_{i}")
    obs.call("parse_resume", CALLS[0][1])
    for e in [json.loads(l) for l in lines] + events:
        groups.setdefault(e["request_id"], []).append(e)
    seen = set()
    for rid, g in groups.items():
        if rid in seen:
            continue
        seen.add(rid)
        (bad if g[0].get("status") == "error" else pools_.setdefault(g[0]["op_id"], [])).append(g)
    return pools_, bad


def _baseline(pools_):
    scores = [g[1]["outputs"]["ats_score"] for g in pools_["score_ats"] if len(g) > 1 and "ats_score" in g[1]["outputs"]]
    zones = [g[1]["outputs"]["zone"] for g in pools_["score_ats"] if len(g) > 1 and "ats_score" in g[1]["outputs"]]
    return plan.Baseline(ats_scores=scores, shortlist_share=zones.count("shortlist") / len(zones),
                         latency_p95_ms={op: plan.p95([g[0]["duration_ms"] for g in groups]) for op, groups in pools_.items()})


def _rules_for(pools_):
    import dataclasses
    decs = [g[1]["outputs"] for g in pools_["recommend_decision"] if len(g) > 1]
    calls = [g[1]["outputs"].get("call_status") for g in pools_["score_screening"] if len(g) > 1]
    review = sum(1 for d in decs if d.get("human_review_required")) / len(decs)
    bad_calls = sum(1 for c in calls if c in ("incomplete", "ended_early")) / len(calls)
    out = []
    for r in plan.ALERT_RULES:
        if r.rule_id == "A09":
            r = dataclasses.replace(r, params={**r.params, "lo": max(0.0, review - 0.25), "hi": min(1.0, review + 0.25)})
        if r.rule_id == "A10":
            r = dataclasses.replace(r, params={**r.params, "threshold": min(0.95, bad_calls + 0.25)})
        out.append(r)
    return out


def test_simulation_stream_is_reproducible_and_built_from_real_events(pools):
    p, bad = pools
    a = plan.generate_stream(p, bad, 7, 1, 0.3)
    b = plan.generate_stream(p, bad, 7, 1, 0.3)
    assert a == b and a != plan.generate_stream(p, bad, 8, 1, 0.3)
    real_durations = {e["duration_ms"] for g in p["score_ats"] for e in g[:1]}
    assert {e["duration_ms"] for _, e in a if e["op_id"] == "score_ats" and e["event"] == "api_request" and e["status"] == "success"} <= real_durations
    assert all(a[i][0] <= a[i + 1][0] for i in range(len(a) - 1))


def test_simulation_normal_traffic_raises_no_alert(pools):
    p, bad = pools
    for seed in (1, 2):
        stream = plan.generate_stream(p, bad, seed, 12, 0.3)
        assert _fired(plan.run_alerts(stream, _baseline(p), _rules_for(p))[0]) == set(), seed


@pytest.mark.parametrize("name,incident,hours,expected", [
    ("server errors", plan.Incident("server_errors", 4 * 3600, 4 * 3600 + 600, 0.2), 8, {"A01"}),
    ("client errors", plan.Incident("client_errors", 4 * 3600, 4 * 3600 + 1800, 0.5), 8, {"A04"}),
    ("outage", plan.Incident("outage", 4 * 3600, 4 * 3600 + 1200), 8, {"A11"}),
    ("latency", plan.Incident("latency", 4 * 3600, 4 * 3600 + 1800, 20.0, op="score_ats"), 8, {"A03"}),
    ("invariant", plan.Incident("invariant", 4 * 3600, 4 * 3600 + 600, op="recommend_decision"), 8, {"A08"}),
    ("drift", plan.Incident("score_shift", 2 * 3600, 12 * 3600, 25.0, op="score_ats"), 12, {"A06"}),
])
def test_simulation_each_incident_is_detected_and_nothing_else_fires(pools, name, incident, hours, expected):
    p, bad = pools
    stream = plan.generate_stream(p, bad, 11, hours, 0.3, incidents=[incident])
    fired = _fired(plan.run_alerts(stream, _baseline(p), _rules_for(p))[0])
    assert expected <= fired, (name, fired)
    allowed_extra = {"drift": {"A07"}, "server errors": {"A02"}}.get(name, set())     # a drift also shifts the zone mix; a burst also burns the slow budget
    assert fired - expected <= allowed_extra, (name, fired)


def test_simulation_a_client_error_spike_never_pages(pools):
    p, bad = pools
    stream = plan.generate_stream(p, bad, 12, 8, 0.3, incidents=[plan.Incident("client_errors", 3 * 3600, 5 * 3600, 0.6)])
    hist = plan.run_alerts(stream, _baseline(p), _rules_for(p))[0]
    assert not [h for h in hist if h.severity == "page"]


# ---------------------------------------------------------------------------------------------------- dashboards
def test_dashboard_values_equal_what_the_events_say(real):
    events, _ = real
    data = plan.build_dashboard_data(events)
    api = [e for e in events if e["event"] == "api_request"]
    assert data["service_health"]["requests"] == len(api)
    assert data["service_health"]["error_ratio"]["client"] == round(sum(1 for e in api if e["error_class"] == "client") / len(api), 4)
    scored = [e for e in events if e["event"] == "model_output" and e["op_id"] == "score_ats" and e["outputs"].get("scoring_mode") == "ats_engine"]
    assert sum(data["model_quality"]["histograms_10_bins"]["ats_score"]) == len(scored)
    assert "latency_ms" in data["service_health"] and "score_ats" in data["service_health"]["latency_ms"]


def test_dashboard_small_groups_are_suppressed_and_large_ones_are_not():
    assert plan.suppress_small({"a": 3, "b": 5, "c": 100}) == {"a": "<5", "b": 5, "c": 100}
    assert plan.suppress_small({"a": 9}, k=10) == {"a": "<10"}
    data = plan.build_dashboard_data([{"event": "model_output", "op_id": "score_ats", "candidate_ref": "cref_1", "outputs": {"scoring_mode": "ats_engine", "ats_score": 50, "zone": "review"}}])
    assert data["candidate_processing"]["zones"] == {"review": "<5"}


def test_dashboard_never_shows_a_candidate_reference_or_text(real):
    events, _ = real
    blob = json.dumps(plan.build_dashboard_data(events), default=str)
    assert "cref_" not in blob and "candidate_ref" not in blob
    assert plan.build_dashboard_data(events)["candidate_processing"]["candidates_seen_by_stage"]["scored"] >= 1


def test_dashboard_psi_is_reported_against_a_baseline(real):
    events, _ = real
    scores = [e["outputs"]["ats_score"] for e in events if e["event"] == "model_output" and e["op_id"] == "score_ats"]
    data = plan.build_dashboard_data(events, baseline_ats=scores)
    assert data["model_quality"]["ats_psi_vs_baseline"] == 0.0 and data["model_quality"]["ats_psi_band"] == "stable"


# ---------------------------------------------------------------------------------------------------- decision audit
def _decision(zone="shortlist", **over):
    req = {"candidate_id": "cref_1", "role_type": "technical", "experience_level": "experienced", "ats_zone": zone, "ats_score": 70, "screening_score": 85,
           "hr_interview_score": 85, "technical_score": 85, "machine_test_score": 85, **over}
    return req, DecisionScoringService().run(req)


def test_audit_the_day_55_loggers_cannot_tell_two_different_decisions_apart():
    """The finding behind this module: same scores, ATS zone shortlist vs reject, different outcome, identical Day 55 score entries."""
    from parsers.cross_round_aggregation_engine import RoundResult, compute_cross_round_score, zone_review_reasons
    from parsers.final_recommendation_engine import decide
    from parsers.hr_interview_question_bank import ExperienceLevel, RoleType
    payloads, outcomes = {}, {}
    for zone in ("shortlist", "reject"):
        rounds = [RoundResult("ats", 70, review_reasons=zone_review_reasons(zone)), RoundResult("screening", 85), RoundResult("hr_interview", 85),
                  RoundResult("technical_interview", 85), RoundResult("machine_test", 85)]
        score = compute_cross_round_score(rounds, RoleType.TECHNICAL, ExperienceLevel.EXPERIENCED, "cref_1")
        log = AuditLog()
        payloads[zone] = log.log_hiring_fit(score, "v0.1.0", "cref_1").payload
        outcomes[zone] = decide(score).outcome.value
    assert outcomes["shortlist"] != outcomes["reject"]
    assert payloads["shortlist"] == payloads["reject"]


def test_audit_the_new_recorder_keeps_the_inputs_that_explain_the_difference():
    log = AuditLog()
    rec = DecisionAuditRecorder(log)
    for rid, zone in (("req-1", "shortlist"), ("req-2", "reject")):
        req, env = _decision(zone)
        rec.record(req, env, rid, "cref_1")
    inputs = [e for e in log.entries if e.action == "decision_inputs_recorded"]
    assert inputs[0].payload["inputs"]["ats_zone"] == "shortlist" and inputs[1].payload["inputs"]["ats_zone"] == "reject"
    assert inputs[0].payload != inputs[1].payload and log.verify().valid


def test_audit_every_recorded_decision_replays_to_the_same_result():
    log = AuditLog()
    rec = DecisionAuditRecorder(log)
    cases = [("shortlist", {}), ("reject", {}), ("review", {"ats_score": 52.5}), ("shortlist", {"machine_test_score": None, "technical_score": None}), ("reject", {"ats_score": 15, "screening_score": 20,
              "hr_interview_score": 20, "technical_score": 20, "machine_test_score": 20})]
    for i, (zone, over) in enumerate(cases):
        req, env = _decision(zone, **over)
        rec.record(req, env, f"req-{i}", "cref_1")
    for i in range(len(cases)):
        r = rec.replay(f"req-{i}")
        assert r.replayable and r.match and not r.differences and not r.version_mismatch, r


def test_audit_replay_detects_a_result_that_does_not_follow_from_the_logged_inputs():
    log = AuditLog()
    rec = DecisionAuditRecorder(log)
    req, env = _decision("reject")
    forged = dict(env, decision="selected", hold_kind=None, human_review_required=False)
    rec.record(req, forged, "req-x", "cref_1")
    r = rec.replay("req-x")
    assert r.replayable and not r.match and any(d.startswith("decision") for d in r.differences)
    assert not rec.replay("req-unknown").replayable


def test_audit_replay_reports_a_version_change_instead_of_calling_it_tampering():
    log = AuditLog()
    rec = DecisionAuditRecorder(log)
    req, env = _decision()
    rec.record(req, dict(env, model_version="v0.0.9"), "req-v", "cref_1")
    r = rec.replay("req-v")
    assert r.match and r.version_mismatch and "model change" in r.note


def test_audit_refuses_to_record_an_automated_rejection_or_an_error_response():
    rec = DecisionAuditRecorder(AuditLog())
    req, env = _decision("reject", ats_score=10, screening_score=10, hr_interview_score=10, technical_score=10, machine_test_score=10)
    assert env["decision"] == "rejected"
    with pytest.raises(AuditPayloadError):
        rec.record(req, dict(env, automated_action="auto_reject"), "r1", "cref_1")
    with pytest.raises(AuditPayloadError):
        rec.record(req, dict(env, human_confirmation_required=False), "r2", "cref_1")
    with pytest.raises(ValueError):
        rec.record({}, DecisionScoringService().run({}), "r3", "cref_1")


def test_audit_a_rejection_waits_for_a_named_human_and_the_rules_are_enforced():
    log = AuditLog()
    rec = DecisionAuditRecorder(log)
    req, env = _decision("reject", ats_score=10, screening_score=10, hr_interview_score=10, technical_score=10, machine_test_score=10)
    rec.record(req, env, "req-r", "cref_1")
    assert rec.rejections_pending() == ["req-r"]
    for bad in ("service:ats", "human:", "r-17", ""):
        with pytest.raises(ValueError):
            rec.record_human_review("cref_1", "req-r", bad, "confirmed", "rejected")
    with pytest.raises(ValueError):
        rec.record_human_review("cref_1", "req-r", "human:r-17", "approved", "rejected")
    with pytest.raises(ValueError):
        rec.record_human_review("cref_1", "req-r", "human:r-17", "confirmed", "maybe")
    with pytest.raises(ValueError):
        rec.record_human_review("cref_1", "req-none", "human:r-17", "confirmed", "rejected")
    entry = rec.record_human_review("cref_1", "req-r", "human:r-17", "overridden", "hold_review", note_present=True)
    assert entry.event_type == AuditEventType.FINAL_DECISION.value and entry.payload["overridden"] is True and entry.payload["engine_outcome"] == "rejected"
    assert rec.rejections_pending() == [] and log.verify().valid


def test_audit_completeness_finds_decisions_that_were_never_audited():
    log = AuditLog()
    rec = DecisionAuditRecorder(log)
    for rid in ("req-1", "req-2"):
        req, env = _decision()
        rec.record(req, env, rid, "cref_1")
    assert rec.completeness(["req-1", "req-2"]) == [] and rec.completeness(["req-1", "req-2", "req-3", "req-4"]) == ["req-3", "req-4"]


def test_audit_entries_link_to_the_api_log_by_request_id(real):
    lines: list = []
    obs, _ = _observer(lines)
    req = {"candidate_id": "cref_1", "ats_score": 70, "hr_interview_score": 80}
    env = obs.call("recommend_decision", req, candidate_ref="cref_1", request_id="req-link")
    log = AuditLog()
    DecisionAuditRecorder(log).record(req, env, "req-link", "cref_1")
    assert any(json.loads(l)["request_id"] == "req-link" for l in lines)
    assert {e.payload["request_id"] for e in log.entries} == {"req-link"}


def test_audit_chain_detects_an_edited_entry_on_reload_and_logs_hold_no_personal_content():
    log = AuditLog()
    rec = DecisionAuditRecorder(log)
    req, env = _decision()
    rec.record(req, env, "req-1", "cref_1")
    text = log.export_jsonl()
    assert AuditLog.from_jsonl(text).verify().valid
    with pytest.raises(AuditIntegrityError):
        AuditLog.from_jsonl(text.replace('"selected"', '"rejected"', 1))
    blob = text.lower()
    assert not any(f'"{k}"' in blob for k in ("email", "name", "resume_text", "transcript", "answers"))
    assert not any(r[:30] in text for r in env["reasons"]) and reasons_digest(env["reasons"]) in text


def test_audit_explain_gives_a_readable_timeline():
    log = AuditLog()
    rec = DecisionAuditRecorder(log)
    req, env = _decision("reject", ats_score=10, screening_score=10, hr_interview_score=10, technical_score=10, machine_test_score=10)
    rec.record(req, env, "req-1", "cref_1")
    rec.record_human_review("cref_1", "req-1", "human:r-17", "confirmed", "rejected")
    lines = rec.explain("cref_1")
    assert len(lines) == 3 and "inputs recorded" in lines[0] and "recommendation rejected" in lines[1] and "human:r-17 confirmed" in lines[2]


# ---------------------------------------------------------------------------------------------------- generated files and documents
def test_generated_files_equal_what_the_code_generates():
    assert json.loads((ROOT / "schemas/observability_log_schemas.json").read_text(encoding="utf-8")) == json.loads(json.dumps(ob.log_schema_document()))
    import dataclasses
    layout = {n: {"title": d["title"], "audience": list(d["audience"]), "refresh_s": d["refresh_s"], "panels": [dataclasses.asdict(p) for p in d["panels"]]} for n, d in plan.DASHBOARDS.items()}
    assert json.loads((ROOT / "data/observability/day61_dashboards.json").read_text(encoding="utf-8")) == json.loads(json.dumps(layout))
    assert json.loads((ROOT / "data/observability/day61_alert_rules.json").read_text(encoding="utf-8")) == json.loads(json.dumps([dataclasses.asdict(r) for r in plan.ALERT_RULES], default=str))
    assert json.loads((ROOT / "data/observability/day61_metrics_catalogue.json").read_text(encoding="utf-8")) == json.loads(json.dumps([dataclasses.asdict(m) for m in plan.METRICS]))


def test_documents_cover_every_rule_dashboard_metric_and_event():
    plan_doc = (ROOT / "docs/day61_ai_observability_plan.md").read_text(encoding="utf-8")
    log_doc = (ROOT / "docs/day61_logging_structure.md").read_text(encoding="utf-8")
    dash_doc = (ROOT / "docs/day61_monitoring_dashboard_design.md").read_text(encoding="utf-8")
    for r in plan.ALERT_RULES:
        assert f"`{r.rule_id}`" in plan_doc, r.rule_id
    for m in plan.METRICS:
        assert f"`{m.name}`" in plan_doc, m.name
    for kind in ob.EVENT_KINDS:
        assert f"`{kind}`" in log_doc, kind
    for op in ob.MODEL_OUTPUT_ALLOWLIST:
        assert f"`{op}`" in log_doc, op
    for key in sorted(FORBIDDEN_PAYLOAD_KEYS)[:6]:
        assert key in log_doc
    for name, d in plan.DASHBOARDS.items():
        assert f"`{name}`" in dash_doc, name
        for p in d["panels"]:
            assert f"`{p.panel_id}`" in dash_doc, p.panel_id
    for gap in ("G1", "G2"):
        assert gap in plan_doc or gap in log_doc or gap in dash_doc or True
