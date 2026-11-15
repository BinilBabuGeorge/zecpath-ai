"""
Day 61 demo: AI monitoring and observability design, proven on real service output.

    python run_day61_observability_demo.py          (about 1 minute)

  1. runs the REAL services through the observer on the sample data and writes the structured log events;
  2. proves no input text reached the log, and that every event matches the generated JSON Schema;
  3. measures what logging costs per call;
  4. computes the dashboard panels from the events and draws the mock-up;
  5. replays synthetic traffic (resampled real events) through the alert rules: normal days must stay quiet, each injected incident must fire;
  6. records decisions in the Day 55 audit log with the Day 61 recorder: replay, tamper check, completeness check, and the Day 55 gap.

Writes: schemas/observability_log_schemas.json, data/observability/*, data/results/day61_observability_report.json, logs/day61_observability_run.log
"""

import dataclasses
import glob
import json
import logging
import random
import statistics
import sys
import time
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "golden"))
logging.disable(logging.CRITICAL)
(ROOT / "logs").mkdir(exist_ok=True)
(ROOT / "data" / "observability").mkdir(parents=True, exist_ok=True)
LOG = open(ROOT / "logs" / "day61_observability_run.log", "w", encoding="utf-8")

from ats_engine.resume_parsing_service import ResumeParsingService
from ats_engine.service import ATSService
from interview_ai.service import InterviewIntelligenceService
from make_day60_golden import answer_corpus
from parsers import observability as ob
from parsers import observability_plan as plan
from parsers.audit_trail import AuditIntegrityError, AuditLog
from parsers.data_governance import pseudonymise
from parsers.decision_audit import DecisionAuditRecorder
from scoring.service import DecisionScoringService
from screening_ai.service import ScreeningService

AS_OF = "2026-11-01"
FILES: dict = {}


def say(msg=""):
    print(msg)
    LOG.write(msg + "\n")


def ref(label: str) -> str:
    return pseudonymise(label, b"d" * 32)                                     # already a "cref_..." reference


# ---------------------------------------------------------------------------------------------------- 1. real events
def build_real_events():
    """Run every service on real inputs through the observer. Returns events, the input strings (for the privacy scan) and the decision calls."""
    for p in sorted(glob.glob(str(ROOT / "data/raw_resumes/docx/*.docx")) + glob.glob(str(ROOT / "data/raw_resumes/pdf/*.pdf"))):
        FILES[Path(p).name] = p
    jds = [Path(p).read_text(encoding="utf-8") for p in sorted(glob.glob(str(ROOT / "data/samples/jds/*.txt")))]
    resumes = [Path(p).read_text(encoding="utf-8") for p in sorted(glob.glob(str(ROOT / "data/samples/resumes/*.txt")))]
    lines: list = []
    counter = iter(range(1, 10_000_000))
    clock_start = 1_762_300_800.0
    tick = iter(range(10_000_000))
    from datetime import datetime, timezone
    logger = ob.StructuredLogger(lines.append, clock=lambda: datetime.fromtimestamp(clock_start + next(tick), tz=timezone.utc))
    services = {"parse_resume": ResumeParsingService(resolver=lambda r: FILES[r]), "score_ats": ATSService(), "score_screening": ScreeningService(),
                "score_interview": InterviewIntelligenceService(), "recommend_decision": DecisionScoringService()}
    observer = ob.ServiceObserver(services, logger, request_ids=lambda: f"req-{next(counter):06d}")
    inputs: list = []
    decisions: list = []
    rng = random.Random(61)

    from utils.warmup import warm_up
    warm_up()                                                                  # steady-state pools: Day 60's warm-up removes the 1-2 s cold-start outlier
    for name, path in sorted(FILES.items()):
        observer.call("parse_resume", {"candidate_id": ref(name), "file_ref": name, "file_type": Path(name).suffix.lstrip("."), "as_of_date": AS_OF}, candidate_ref=ref(name))
    for ji, jd in enumerate(jds):
        for ri, r in enumerate(resumes):
            observer.call("score_ats", {"resume_text": r, "job_description": jd}, candidate_ref=ref(f"resume-{ri}"))
            inputs += [r, jd]
    turn_texts = ["Hello, I am a MERN developer with three years of experience at a product company.", "I did my B.Tech in Computer Science in 2021.",
                  "I have worked for three years building React and Node.js applications.", "My skills are React, Node.js, MongoDB and Docker.",
                  "I am currently based in Bengaluru.", "My expected salary is eight lakhs per annum.", "My notice period is one month."]
    for i in range(40):
        n = 7 if i % 5 else rng.randint(1, 5)
        turns = [{"text": t, "confidence": 0.9} for t in turn_texts[:n]]
        if i % 9 == 0:
            turns = [{"text": "", "confidence": 0.2, "is_silent": True} for _ in range(rng.randint(1, 4))]
        observer.call("score_screening", {"candidate_id": ref(f"screen-{i}"), "turns": turns}, candidate_ref=ref(f"screen-{i}"))
        inputs += [t["text"] for t in turns]
    answers = answer_corpus()
    for i in range(40):
        a = answers[i * 4:(i * 4) + rng.randint(2, 4)]
        observer.call("score_interview", {"interview_type": "hr", "answers": a}, candidate_ref=ref(f"hr-{i}"))
        inputs += a
    for i in range(25):
        a = answers[100 + i * 3:100 + i * 3 + 3]
        observer.call("score_interview", {"interview_type": "technical", "domain": ["mern", "java", "devops"][i % 3], "experience_years": i % 8, "answers": a}, candidate_ref=ref(f"tech-{i}"))
        inputs += a
    for i in range(40):
        req = {"candidate_id": ref(f"cand-{i}"), "role_type": rng.choice(["technical", "non_technical"]), "experience_level": rng.choice(["fresher", "experienced"]),
               "ats_zone": rng.choices(["shortlist", "review", "reject"], [0.5, 0.3, 0.2])[0], "ats_score": round(rng.uniform(25, 90), 1)}
        for key in ("screening_score", "hr_interview_score", "technical_score", "machine_test_score"):
            if rng.random() < 0.8:
                req[key] = round(rng.uniform(25, 95), 1)
        rid = f"req-{next(counter):06d}"
        env = observer.call("recommend_decision", req, candidate_ref=req["candidate_id"], request_id=rid)
        decisions.append((rid, req, env))
    bad = [("score_ats", {}), ("score_ats", {"resume_text": "x", "job_description": "   "}), ("score_ats", {"resume_text": 5, "job_description": "x"}),
           ("recommend_decision", {}), ("recommend_decision", {"ats_score": 101}), ("score_interview", {"interview_type": "final"}),
           ("score_interview", {"interview_type": "technical"}), ("score_screening", {"turns": "x"}),
           ("parse_resume", {"candidate_id": "c1", "file_ref": "missing.pdf", "file_type": "pdf"}), ("parse_resume", {"candidate_id": "c1", "file_ref": "x", "file_type": "txt"})]
    FILES["missing.pdf"] = str(ROOT / "data" / "does_not_exist.pdf")
    for op, payload in bad:
        observer.call(op, payload)
    return lines, observer, logger, inputs, decisions


def privacy_scan(lines, inputs):
    blob = "\n".join(lines)
    checked = hits = 0
    for s in {x for x in inputs if isinstance(x, str) and len(x) >= 40}:
        for start in (0, len(s) // 2, max(0, len(s) - 30)):
            piece = s[start:start + 30]
            checked += 1
            hits += piece in blob
    return {"input_strings": len({x for x in inputs if isinstance(x, str) and len(x) >= 40}), "slices_checked": checked, "slices_found_in_logs": hits}


def group_by_request(events):
    groups: dict = {}
    for e in events:
        groups.setdefault(e["request_id"], []).append(e)
    pools: dict = {}
    client_pool: list = []
    for g in groups.values():
        api = g[0]
        if api.get("status") == "error":
            client_pool.append(g)
        else:
            pools.setdefault(api["op_id"], []).append(g)
    return pools, client_pool


# ---------------------------------------------------------------------------------------------------- 4. dashboard picture
def draw_dashboard(data, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 3, figsize=(16, 9))
    fig.suptitle("AI monitoring dashboard design: sample data from real service runs on the sample resumes (not production)", fontsize=13, fontweight="bold")
    h, p, i, q = data["service_health"], data["candidate_processing"], data["interview_success"], data["model_quality"]
    ax = axes[0][0]
    ops = [o for o in h["latency_ms"]]
    ax.barh(ops, [h["latency_ms"][o]["p95"] for o in ops], color="#4c78a8")
    for o, y in zip(ops, range(len(ops))):
        ax.text(h["latency_ms"][o]["p95"], y, f" {h['latency_ms'][o]['p95']:.1f} ms", va="center", fontsize=8)
    ax.set_title("Service health: p95 compute time by operation\n(alert A03 above 50 ms; parse 300 ms)", fontsize=9)
    ax.set_xlabel("ms")
    ax = axes[0][1]
    ax.bar(["client errors", "server errors"], [h["error_ratio"]["client"] * 100, h["error_ratio"]["server"] * 100], color=["#f2a541", "#d1495b"])
    ax.set_title(f"Service health: error ratio ({h['requests']} requests)\nserver errors burn the SLO; client errors do not page", fontsize=9)
    ax.set_ylabel("% of requests")
    ax = axes[0][2]
    st = p["candidate_seen_by_stage"] if "candidate_seen_by_stage" in p else p["candidates_seen_by_stage"]
    ax.bar(list(st), list(st.values()), color="#59a14f")
    ax.set_title("Candidate processing: distinct candidates by stage\n(counts only, no names)", fontsize=9)
    ax.tick_params(axis="x", labelsize=8)
    ax = axes[1][0]
    calls = {k: (v if isinstance(v, int) else 0) for k, v in i["screening_calls"].items()}
    ax.bar(list(calls), list(calls.values()), color=["#59a14f" if k == "completed" else "#e15759" for k in calls])
    ax.set_title(f"Interview success: screening calls by how they ended\ncompletion rate {i['screening_completion_rate']:.0%}; substantive answers {i['substantive_answer_rate']:.0%}", fontsize=9)
    ax.tick_params(axis="x", labelsize=8)
    ax = axes[1][1]
    base = q["histograms_10_bins"]["ats_score"]
    ax.bar(range(10), base, color="#4c78a8")
    ax.set_xticks(range(10))
    ax.set_xticklabels([f"{b}-{b + 10}" for b in range(0, 100, 10)], fontsize=6, rotation=45)
    ax.set_title("Model quality: ATS score distribution (10 bins)\nPSI against the baseline drives alerts A06 and A07", fontsize=9)
    ax = axes[1][2]
    dec = {k: (v if isinstance(v, int) else 0) for k, v in p["decisions"].items()}
    ax.bar(list(dec), list(dec.values()), color=["#59a14f", "#f2a541", "#e15759"][:len(dec)])
    ax.set_title(f"Recommendations by outcome\nhuman review required {p['human_review_required_share']:.0%}; {p['rejections_recommended']} rejections need a person", fontsize=9)
    plt.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(path, dpi=120)
    plt.close(fig)


# ---------------------------------------------------------------------------------------------------- 5. alert simulation
def scenario_list():
    H = 3600.0
    I = plan.Incident
    return [
        ("latency_regression (ATS 15x slower for 30 min)", [I("latency", 6 * H, 6.5 * H, 15.0, op="score_ats")], 12, {"A03"}, None),
        ("server_error_burst (15% server errors for 10 min)", [I("server_errors", 6 * H, 6 * H + 600, 0.15)], 12, {"A01"}, None),
        ("client_error_spike (50% bad requests for 30 min)", [I("client_errors", 6 * H, 6.5 * H, 0.5)], 12, {"A04"}, None),
        ("score_drift (ATS scores +18 points from hour 4)", [I("score_shift", 4 * H, 14 * H, 18.0, op="score_ats")], 14, {"A06"}, None),
        ("outage (no traffic for 20 min)", [I("outage", 6 * H, 6 * H + 1200)], 12, {"A11"}, None),
        ("automated_rejection (rule broken for 10 min)", [I("invariant", 6 * H, 6 * H + 600, op="recommend_decision")], 12, {"A08"}, None),
        ("silent_call_surge (80% of calls end early for 4 h)", [I("silent_calls", 4 * H, 8 * H, 0.8, op="score_screening")], 12, {"A10"}, None),
        ("resume_parse_failures (40% unreadable for 4 h)", [I("parse_failures", 4 * H, 8 * H, 0.4, op="parse_resume")], 12, {"A05"}, None),
        ("audit_gap (a decision without an audit entry)", [], 12, {"A12"}, lambda t0: (lambda t: {"decisions_without_audit": 1.0 if t0 + 6 * H <= t < t0 + 6 * H + 900 else 0.0})),
        ("log_policy_violation (logger refused an event)", [], 12, {"A13"}, lambda t0: (lambda t: {"log_policy_violations": 1.0 if t0 + 6 * H <= t < t0 + 6 * H + 600 else 0.0})),
    ]


def simulate_alerts(events, report):
    pools, client_pool = group_by_request(events)
    ats_scores = [g[1]["outputs"]["ats_score"] for g in pools["score_ats"] if len(g) > 1 and "ats_score" in g[1].get("outputs", {})]
    zones = [g[1]["outputs"].get("zone") for g in pools["score_ats"] if len(g) > 1]
    decs = [g[1]["outputs"] for g in pools["recommend_decision"] if len(g) > 1]
    calls = [g[1]["outputs"].get("call_status") for g in pools["score_screening"] if len(g) > 1]
    latency = {op: plan.p95([g[0]["duration_ms"] for g in groups]) for op, groups in pools.items()}
    baseline = plan.Baseline(ats_scores=ats_scores, shortlist_share=zones.count("shortlist") / len(zones), latency_p95_ms=latency)
    review_share = sum(1 for d in decs if d.get("human_review_required")) / len(decs)
    bad_call_share = sum(1 for c in calls if c in ("incomplete", "ended_early")) / len(calls)
    say(f"  baselines from the real events: shortlist share {baseline.shortlist_share:.0%}, human-review share {review_share:.0%}, early/incomplete calls {bad_call_share:.0%}, "
        f"{len(ats_scores)} ATS scores")
    # rules whose bands depend on the baseline are set from it at deployment time (here, from the real events)
    rules = []
    for r in plan.ALERT_RULES:
        if r.rule_id == "A09":
            r = dataclasses.replace(r, params={**r.params, "lo": max(0.0, review_share - 0.25), "hi": min(1.0, review_share + 0.25)})
        if r.rule_id == "A10":
            r = dataclasses.replace(r, params={**r.params, "threshold": min(0.95, bad_call_share + 0.25)})
        rules.append(r)
    rate = 0.4
    out = {"baseline": {"shortlist_share": round(baseline.shortlist_share, 3), "human_review_share": round(review_share, 3), "bad_call_share": round(bad_call_share, 3)}, "normal_days": [],
           "incidents": []}

    say(f"\n  Normal traffic (3 simulated days of {int(rate * 86400):,} requests each): every firing is a FALSE POSITIVE")
    for seed in (1, 2, 3):
        stream = plan.generate_stream(pools, client_pool, seed, 24, rate)
        hist, _ = plan.run_alerts(stream, baseline, rules)
        firing = [h for h in hist if h.state == "firing"]
        out["normal_days"].append({"seed": seed, "requests": int(len({e['request_id'] for _, e in stream})), "false_positives": [(h.rule_id, h.severity) for h in firing]})
        say(f"    day {seed}: {out['normal_days'][-1]['requests']:,} requests, false positives: {[h.rule_id for h in firing] or 'none'}")

    say("\n  Injected incidents (resampled real events plus an invented incident; delay = minutes from the start of the incident to the first alert)")
    say(f"    {'incident':58s} {'expected':9s} {'fired':16s} {'delay':>8s}  unexpected")
    epoch0 = 1_762_300_800.0
    for name, incidents, hours, expected, extras_factory in scenario_list():
        stream = plan.generate_stream(pools, client_pool, 10, hours, rate, incidents=incidents)
        extras = extras_factory(epoch0) if extras_factory else None
        hist, _ = plan.run_alerts(stream, baseline, rules, extras_at=extras)
        firing = {}
        for h in hist:
            if h.state == "firing":
                firing.setdefault(h.rule_id, h)
        start = (incidents[0].start if incidents else 6 * 3600.0) + epoch0
        hit = [firing[r] for r in expected if r in firing]
        delay = round((min(h.at for h in hit) - start) / 60, 1) if hit else None
        unexpected = sorted(set(firing) - expected)
        pages = sorted(r for r, h in firing.items() if h.severity == "page" and r not in expected)
        out["incidents"].append({"incident": name, "expected": sorted(expected), "fired": sorted(firing), "detected": bool(hit), "delay_minutes": delay, "unexpected": unexpected,
                                 "unexpected_pages": pages})
        say(f"    {name:58s} {','.join(sorted(expected)):9s} {','.join(sorted(firing)) or '-':16s} {('%.1f min' % delay) if delay is not None else 'MISSED':>8s}  {unexpected or '-'}")
    return out


# ---------------------------------------------------------------------------------------------------- 6. decision audit
def audit_demo(decisions, events):
    from parsers.cross_round_aggregation_engine import RoundResult, compute_cross_round_score, zone_review_reasons
    from parsers.final_recommendation_engine import decide
    from parsers.hr_interview_question_bank import ExperienceLevel, RoleType
    out = {}
    # the Day 55 gap
    rows = {}
    for zone in ("shortlist", "reject"):
        env = DecisionScoringService().run({"candidate_id": "cref_x", "role_type": "technical", "experience_level": "experienced", "ats_zone": zone, "ats_score": 70, "screening_score": 85,
                                            "hr_interview_score": 85, "technical_score": 85, "machine_test_score": 85})
        rounds = [RoundResult("ats", 70, review_reasons=zone_review_reasons(zone)), RoundResult("screening", 85), RoundResult("hr_interview", 85), RoundResult("technical_interview", 85),
                  RoundResult("machine_test", 85)]
        score = compute_cross_round_score(rounds, RoleType.TECHNICAL, ExperienceLevel.EXPERIENCED, "cref_x")
        log = AuditLog()
        a, b = log.log_hiring_fit(score, "v0.1.0", "cref_x"), log.log_decision(decide(score), "v0.1.0", "cref_x")
        rows[zone] = {"decision": env["decision"], "hold_kind": env["hold_kind"], "day55_score_payload": a.payload, "day55_decision_rule": b.payload["rules_fired"]}
    out["day55_gap"] = {"outcomes": {z: (r["decision"], r["hold_kind"]) for z, r in rows.items()}, "score_entries_identical": rows["shortlist"]["day55_score_payload"] == rows["reject"]["day55_score_payload"],
                        "rules_fired": {z: r["day55_decision_rule"] for z, r in rows.items()}}
    say(f"  Day 55 typed loggers, same scores with ATS zone shortlist vs reject: outcomes {out['day55_gap']['outcomes']}, score entries identical: {out['day55_gap']['score_entries_identical']}")

    log = AuditLog()
    rec = DecisionAuditRecorder(log)
    skipped = {decisions[7][0], decisions[23][0]}                              # two decisions the recorder is "never told about"
    recorded = [(rid, req, env) for rid, req, env in decisions if rid not in skipped and env["status"] == "success"]
    for rid, req, env in recorded:
        rec.record(req, env, rid, req["candidate_id"])
    rejected = [(rid, req) for rid, req, env in recorded if env["decision"] == "rejected"]
    for rid, req in rejected[:-1]:
        rec.record_human_review(req["candidate_id"], rid, "human:r-17", "confirmed", "rejected")
    replays = [rec.replay(rid) for rid, _, _ in recorded]
    all_ids = [e["request_id"] for e in events if e["event"] == "model_output" and e["op_id"] == "recommend_decision"]
    missing = rec.completeness(all_ids)
    text = log.export_jsonl()
    lines = text.split("\n")
    broken = lines[:]
    idx = next(i for i, l in enumerate(broken) if '"hold_review"' in l or '"selected"' in l)
    broken[idx] = broken[idx].replace('"hold_review"', '"selected"', 1) if '"hold_review"' in broken[idx] else broken[idx].replace('"selected"', '"hold_review"', 1)
    try:
        AuditLog.from_jsonl("\n".join(broken))
        tamper_detected = False
    except AuditIntegrityError:
        tamper_detected = True
    out.update({"decisions_recorded": len(recorded), "audit_entries": len(log), "chain_valid": log.verify().valid, "replay_matched": sum(r.match for r in replays), "replay_total": len(replays),
                "decisions_without_audit_found": missing, "decisions_without_audit_expected": sorted(skipped), "rejections_total": len(rejected), "rejections_pending_human": rec.rejections_pending(),
                "tamper_detected": tamper_detected})
    say(f"  recorded {len(recorded)} decisions as {len(log)} chained entries; chain valid: {out['chain_valid']}; replay matched {out['replay_matched']}/{out['replay_total']}")
    say(f"  completeness check found the {len(missing)} decisions never audited: {missing == sorted(skipped)}; rejections awaiting a named human: {len(out['rejections_pending_human'])} of {len(rejected)}")
    say(f"  one edited entry in the exported log: tampering detected on reload: {tamper_detected}")
    cand = recorded[0][1]["candidate_id"]
    say("  explain() timeline for one candidate reference:")
    for line in rec.explain(cand):
        say("    " + line[:150])
    (ROOT / "data/observability/day61_decision_audit_sample.jsonl").write_text("\n".join(lines[:12]) + "\n", encoding="utf-8")
    return out


def main():
    report = {}
    say("=== 1. Real services through the observer ===")
    lines, observer, logger, inputs, decisions = build_real_events()
    events = [json.loads(l) for l in lines]
    kinds = {k: sum(1 for e in events if e["event"] == k) for k in ob.EVENT_KINDS}
    say(f"  {len(events)} events: {kinds}; dropped by the guard: {logger.dropped or 'none'}")
    (ROOT / "data/observability/day61_sample_events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    report["events"] = {"total": len(events), **kinds}

    say("\n=== 2. Privacy and schema ===")
    scan = privacy_scan(lines, inputs)
    say(f"  {scan['slices_checked']} 30-character slices of {scan['input_strings']} input texts (resumes, answers, transcripts, job descriptions): found in the logs: {scan['slices_found_in_logs']}")
    schema = ob.log_schema_document()
    Path(ROOT / "schemas/observability_log_schemas.json").write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    validator = jsonschema.Draft202012Validator(schema)
    valid = sum(validator.is_valid(e) for e in events)
    say(f"  {valid}/{len(events)} events valid against schemas/observability_log_schemas.json")
    refusals = []
    probe = ob.StructuredLogger(lambda s: None)
    for label, fields in {"forbidden key": {"request_id": "r", "op_id": "score_ats", "status": "success", "duration_ms": 1.0, "resume_text": "Jane Doe"},
                          "unlisted field": {"request_id": "r", "op_id": "score_ats", "status": "success", "duration_ms": 1.0, "notes": "x"},
                          "free text in an allowed field": {"request_id": "r" * 80, "op_id": "score_ats", "status": "success", "duration_ms": 1.0}}.items():
        refusals.append((label, probe.emit("api_request", **fields) is None))
    say(f"  the guard refused: {refusals}; counted as {probe.dropped}")
    report["privacy"] = {**scan, "schema_valid": valid, "schema_total": len(events), "guard_refusals": refusals}

    say("\n=== 3. Metrics ===")
    m = observer.metrics
    exact = sorted(e["duration_ms"] for e in events if e["event"] == "api_request" and e["op_id"] == "score_ats" and e["status"] == "success")
    est = m.quantile("ai_request_duration_seconds", 0.95, op="score_ats") * 1000
    true95 = exact[int(0.95 * (len(exact) - 1) + 0.5)]
    say(f"  ATS p95 from the histogram {est:.2f} ms against exact {true95:.2f} ms (bucket-width accuracy)")
    (ROOT / "data/observability/day61_metrics_sample.prom").write_text(m.render_prometheus(), encoding="utf-8")
    report["metrics"] = {"series_overflowed": m.overflowed, "p95_hist_ms": round(est, 3), "p95_exact_ms": round(true95, 3)}

    say("\n=== 4. Logging overhead ===")
    resumes = [Path(p).read_text(encoding="utf-8") for p in sorted(glob.glob(str(ROOT / "data/samples/resumes/*.txt")))]
    jd = Path(sorted(glob.glob(str(ROOT / "data/samples/jds/*.txt")))[0]).read_text(encoding="utf-8")
    svc = ATSService()
    obs2 = ob.ServiceObserver({"score_ats": ATSService()}, ob.StructuredLogger(lambda s: None))

    def loop(fn, n=150):
        ts = []
        for i in range(n):
            body = {"resume_text": resumes[i % len(resumes)] + f"\nNote {i}.", "job_description": jd}
            t = time.perf_counter()
            fn(body)
            ts.append((time.perf_counter() - t) * 1000)
        return statistics.median(ts)

    loop(svc.run, 20)
    direct = min(loop(svc.run) for _ in range(3))
    observed = min(loop(lambda b: obs2.call("score_ats", b)) for _ in range(3))
    say(f"  ATS request: {direct:.3f} ms direct, {observed:.3f} ms observed: overhead {observed - direct:.3f} ms ({(observed - direct) / direct:.1%})")
    report["overhead"] = {"direct_ms": round(direct, 3), "observed_ms": round(observed, 3), "overhead_ms": round(observed - direct, 3)}

    say("\n=== 5. Dashboard ===")
    pools, _ = group_by_request(events)
    baseline = [g[1]["outputs"]["ats_score"] for g in pools["score_ats"] if len(g) > 1 and "ats_score" in g[1]["outputs"]]
    data = plan.build_dashboard_data(events, baseline_ats=baseline)
    Path(ROOT / "data/observability/day61_dashboard_sample_data.json").write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")
    draw_dashboard(data, ROOT / "data/observability/day61_dashboard_mockup.png")
    layout = {name: {"title": d["title"], "audience": list(d["audience"]), "refresh_s": d["refresh_s"], "panels": [dataclasses.asdict(p) for p in d["panels"]]} for name, d in plan.DASHBOARDS.items()}
    Path(ROOT / "data/observability/day61_dashboards.json").write_text(json.dumps(layout, indent=2) + "\n", encoding="utf-8")
    Path(ROOT / "data/observability/day61_alert_rules.json").write_text(json.dumps([dataclasses.asdict(r) for r in plan.ALERT_RULES], indent=2, default=str) + "\n", encoding="utf-8")
    Path(ROOT / "data/observability/day61_metrics_catalogue.json").write_text(json.dumps([dataclasses.asdict(x) for x in plan.METRICS], indent=2) + "\n", encoding="utf-8")
    say(f"  {len(plan.DASHBOARDS)} dashboards, {sum(len(d['panels']) for d in plan.DASHBOARDS.values())} panels; mock-up: data/observability/day61_dashboard_mockup.png")
    say(f"  candidate processing: {data['candidate_processing']['candidates_seen_by_stage']}; screening completion {data['interview_success']['screening_completion_rate']:.0%}; "
        f"ATS PSI vs its own baseline {data['model_quality']['ats_psi_vs_baseline']}")
    report["dashboards"] = {"dashboards": len(plan.DASHBOARDS), "panels": sum(len(d["panels"]) for d in plan.DASHBOARDS.values())}

    say("\n=== 6. Alert rules on simulated traffic ===")
    say(f"  {sum(1 for r in plan.ALERT_RULES if r.status == 'evaluable')} rules evaluable now; {sum(1 for r in plan.ALERT_RULES if r.status != 'evaluable')} planned (need a queue, review outcomes, or demographic data that is not collected)")
    report["alerts"] = simulate_alerts(events, report)

    say("\n=== 7. Decision audit ===")
    report["audit"] = audit_demo(decisions, events)

    Path(ROOT / "data/results/day61_observability_report.json").write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    say("\nWrote data/results/day61_observability_report.json")


if __name__ == "__main__":
    main()
