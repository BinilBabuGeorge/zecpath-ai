"""
Day 59 demo: API & Integration Planning.

Regenerates the schema and OpenAPI files from the code, then PROVES the plan against the real services:
  * every API is called on real sample data and its response is validated against the schema;
  * bad requests show the gateway and the service agree on the error code;
  * timings and the batch-consistency measurement that justify the sync/async split;
  * a retry simulation, the access-control check, and the mapping diagram.

Writes: schemas/integration_api_schemas.json, api/integration_openapi.yaml, data/integration/*.json,
        data/results/day59_integration_report.json, data/integration/day59_api_mapping.png, logs/day59_integration_run.log
"""

import glob
import json
import logging
import statistics
import sys
import time
from datetime import date
from pathlib import Path

import yaml

from ats_engine.batch_service import ATSBatchService
from ats_engine.resume_parsing_service import ResumeParsingService
from ats_engine.service import ATSService
from interview_ai.service import InterviewIntelligenceService
from parsers import integration_contract as ic
from parsers.resume_extractor import normalize_section_headings
from parsers.semantic_matcher import SemanticMatcher
from screening_ai.service import ScreeningService
from scoring.service import DecisionScoringService

ROOT = Path(__file__).resolve().parent
(ROOT / "logs").mkdir(exist_ok=True)
(ROOT / "data" / "integration").mkdir(parents=True, exist_ok=True)
logging.getLogger().handlers.clear()
for noisy in ("ATSService", "ScreeningService", "InterviewIntelligenceService", "DecisionScoringService", "ResumeParsingService", "ATSBatchService"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
fh = logging.FileHandler(ROOT / "logs" / "day59_integration_run.log", mode="w", encoding="utf-8")
fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
log = logging.getLogger("day59")
log.setLevel(logging.INFO)
log.addHandler(fh)

AS_OF = date(2026, 11, 1)           # pinned so "Present" gives the same result on every run


def say(msg: str = "") -> None:
    print(msg)
    log.info(msg)


def timed(fn, n: int = 30):
    samples = []
    for _ in range(n):
        t = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t) * 1000)
    samples.sort()
    return {"p50_ms": round(statistics.median(samples), 2), "p95_ms": round(samples[int(0.95 * (len(samples) - 1))], 2), "runs": n}


def main() -> int:
    report: dict = {"contract_version": ic.CONTRACT_VERSION, "as_of_date": AS_OF.isoformat()}
    say("=== 1. Regenerate the schema and OpenAPI files from the code ===")
    (ROOT / "schemas" / "integration_api_schemas.json").write_text(json.dumps(ic.schema_document(), indent=2) + "\n", encoding="utf-8")
    (ROOT / "api" / "integration_openapi.yaml").write_text(yaml.safe_dump(json.loads(json.dumps(ic.build_openapi())), sort_keys=False, width=120), encoding="utf-8")
    defs = ic.build_schemas()
    say(f"  {len(defs)} schemas, {len(ic.OPERATIONS)} operations, {len(ic.ERROR_CODES)} error codes")
    report["counts"] = {"schemas": len(defs), "operations": len(ic.OPERATIONS), "error_codes": len(ic.ERROR_CODES)}

    say("\n=== 2. Call every AI API on real sample data and validate the response ===")
    jd = (ROOT / "data/samples/jds/jd_01_mern_developer.txt").read_text(encoding="utf-8")
    docx = sorted(glob.glob(str(ROOT / "data/raw_resumes/docx/*.docx")))
    pdfs = sorted(glob.glob(str(ROOT / "data/raw_resumes/pdf/*.pdf")))
    parse_ok = 0
    parsed = []
    for f in docx + pdfs:
        ftype = Path(f).suffix.lstrip(".")
        out = ResumeParsingService(resolver=lambda ref, p=f: p).run({"candidate_id": "C" + Path(f).stem[7:9], "file_ref": Path(f).name, "file_type": ftype, "as_of_date": AS_OF.isoformat()})
        problems = ic.validate_response("ParseResumeResult", out) if out["status"] == "success" else ["error: " + out["error"]["code"]]
        parse_ok += not problems
        parsed.append(out)
        if problems:
            say(f"  PARSE PROBLEM {Path(f).name}: {problems[:2]}")
    say(f"  resume parsing: {parse_ok}/{len(docx) + len(pdfs)} files parsed and valid ({len(docx)} DOCX, {len(pdfs)} PDF)")
    first = parsed[0]

    sample_dir = sorted(glob.glob(str(ROOT / "data/samples/resumes/*.txt")))
    texts = [Path(p).read_text(encoding="utf-8") for p in sample_dir]
    ats = [ATSService().run({"resume_text": t, "job_description": jd}) for t in texts]
    ats_ok = sum(ic.validate_response("ATSScoreResult", r) == [] for r in ats)
    say(f"  ATS scoring: {ats_ok}/{len(ats)} responses valid")
    batch_req = {"job_description": jd, "candidates": [{"candidate_id": f"A{i:02d}", "resume_text": t} for i, t in enumerate(texts)]}
    batch = ATSBatchService().run(batch_req)
    batch_valid = ic.validate_response("ATSBatchScoreResult", batch) == []
    same = all(item["outcome"] == single for item, single in zip(batch["results"], ats))
    say(f"  ATS batch: valid={batch_valid}, every result identical to its single-request result={same}")

    turns = [{"text": t, "confidence": 0.9} for t in [
        "Hello, I am a MERN developer with three years of experience at a product company.", "I did my B.Tech in Computer Science in 2021.",
        "I have worked for three years building React and Node.js applications.", "My skills are React, Node.js, MongoDB and Docker.",
        "I am currently based in Bengaluru.", "My expected salary is eight lakhs per annum.", "My notice period is one month."]]
    screening = ScreeningService().run({"candidate_id": "C01", "job_role": "MERN Stack Developer", "turns": turns})
    hr = InterviewIntelligenceService().run({"interview_type": "hr", "role_type": "technical", "experience_level": "experienced", "answers": [
        "I am a full stack developer with three years of experience building web applications.", "I led the migration of our API to TypeScript and cut bugs.",
        "I prefer working in small teams and I review code daily.", "My weakness was estimating tasks, so I now break work into small pieces."]})
    tech = InterviewIntelligenceService().run({"interview_type": "technical", "domain": "mern", "experience_years": 3, "answers": [
        "React uses a virtual DOM to batch updates and avoid unnecessary re-rendering.", "Node.js is single threaded with an event loop, so blocking work should be offloaded."]})
    decision = DecisionScoringService().run({"candidate_id": "C01", "role_type": "technical", "experience_level": "experienced", "ats_zone": "shortlist",
                                              "ats_score": ats[0]["ats_score"], "screening_score": screening["screening_score"],
                                              "hr_interview_score": hr["hr_score"], "technical_score": tech["technical_score"]})
    ops = {"ScreeningScoreResult": screening, "InterviewScoreResult": hr, "DecisionResult": decision}
    for name, resp in ops.items():
        say(f"  {name}: status={resp['status']} valid={ic.validate_response(name, resp) == []}")
    say(f"  technical interview: valid={ic.validate_response('InterviewScoreResult', tech) == []}")
    say(f"  decision: {decision['decision']} ({decision['hold_kind']}), human_confirmation_required={decision['human_confirmation_required']}")
    report["real_calls"] = {
        "resume_parsing": {"files": len(docx) + len(pdfs), "valid": parse_ok}, "ats": {"responses": len(ats), "valid": ats_ok},
        "ats_batch": {"valid": batch_valid, "equals_single_request": same, "total": batch["total"]},
        "screening_valid": ic.validate_response("ScreeningScoreResult", screening) == [],
        "hr_valid": ic.validate_response("InterviewScoreResult", hr) == [], "technical_valid": ic.validate_response("InterviewScoreResult", tech) == [],
        "decision_valid": ic.validate_response("DecisionResult", decision) == []}

    say("\n=== 3. Examples written for the integration team ===")
    examples = {
        "parse_resume": {"request": {"candidate_id": "cref_example", "file_ref": "tenant_a/resume_01.docx", "file_type": "docx", "as_of_date": AS_OF.isoformat()},
                         "job_accepted": {"job_id": "job_a1b2c3d4e5", "operation": "parse_resume", "status": "queued", "created_at": "2026-11-07T09:00:00Z", "retry_after_seconds": 1},
                         "job_result": first},
        "score_ats": {"request": {"resume_text": texts[0][:200] + " ...", "job_description": jd[:200] + " ..."}, "response": ats[0]},
        "score_ats_batch": {"request_shape": {"job_description": "...", "candidates": [{"candidate_id": "cref_a", "resume_text": "..."}]},
                            "response_summary": {k: batch[k] for k in ("total", "succeeded", "failed", "scoring_basis")}},
        "score_screening": {"request": {"candidate_id": "cref_example", "job_role": "MERN Stack Developer", "turns": turns[:2]}, "response": screening},
        "score_interview_hr": {"request": {"interview_type": "hr", "role_type": "technical", "experience_level": "experienced", "answers": ["..."]}, "response": hr},
        "score_interview_technical": {"request": {"interview_type": "technical", "domain": "mern", "experience_years": 3, "answers": ["..."]}, "response": tech},
        "recommend_decision": {"request": {"candidate_id": "cref_example", "ats_score": 70, "hr_interview_score": 80}, "response": decision},
    }
    err_env = ATSService().run({"resume_text": "x"})
    examples["error_example"] = ic.to_gateway_error(err_env, "req-0001").__dict__
    (ROOT / "data/integration/day59_example_payloads.json").write_text(json.dumps(examples, indent=2) + "\n", encoding="utf-8")
    say("  data/integration/day59_example_payloads.json")

    say("\n=== 4. Gateway and service agree on bad requests ===")
    bad = [("score_ats", {"resume_text": "x"}), ("score_ats", {"job_description": "  "}), ("recommend_decision", {"ats_score": 101}),
           ("recommend_decision", {"ats_score": "high"}), ("recommend_decision", {}), ("score_interview", {"interview_type": "final"}),
           ("score_interview", {"interview_type": "technical"}), ("score_screening", {"turns": "x"})]
    services = {"score_ats": ATSService(), "recommend_decision": DecisionScoringService(), "score_interview": InterviewIntelligenceService(), "score_screening": ScreeningService()}
    agree = 0
    for op_id, body in bad:
        s = services[op_id].run(body)["error"]["code"]
        g = ic.validate_request(op_id, body)["error"]["code"]
        agree += s == g
        say(f"  {op_id:20s} service={s:18s} gateway={g:18s} {'same' if s == g else 'DIFFERENT'}")
    report["error_agreement"] = {"cases": len(bad), "same_code": agree}

    say("\n=== 5. Timings (this machine, compute only; no network, no storage, no speech-to-text) ===")
    timing = {
        "parse_resume_docx": timed(lambda: ResumeParsingService(resolver=lambda r: docx[0]).run({"candidate_id": "C1", "file_ref": "a.docx", "file_type": "docx", "as_of_date": "2026-11-01"})),
        "parse_resume_pdf": timed(lambda: ResumeParsingService(resolver=lambda r: pdfs[0]).run({"candidate_id": "C1", "file_ref": "a.pdf", "file_type": "pdf", "as_of_date": "2026-11-01"})),
        "score_ats": timed(lambda: ATSService().run({"resume_text": texts[0], "job_description": jd})),
        "score_screening": timed(lambda: ScreeningService().run({"candidate_id": "C01", "turns": turns})),
        "score_interview_hr": timed(lambda: InterviewIntelligenceService().run({"interview_type": "hr", "answers": ["I am a developer with three years experience in React."] * 6})),
        "score_interview_technical": timed(lambda: InterviewIntelligenceService().run({"interview_type": "technical", "domain": "mern", "experience_years": 3, "answers": ["React uses a virtual DOM."] * 6})),
        "recommend_decision": timed(lambda: DecisionScoringService().run({"ats_score": 70, "hr_interview_score": 80, "technical_score": 60})),
        "ats_batch_16": timed(lambda: ATSBatchService().run(batch_req), n=10),
    }
    for k, v in timing.items():
        say(f"  {k:26s} p50 {v['p50_ms']:8.2f} ms   p95 {v['p95_ms']:8.2f} ms")
    report["timing"] = timing
    slowest_sync = max(v["p95_ms"] for k, v in timing.items() if k not in ("ats_batch_16",))
    report["slowest_sync_p95_ms"] = slowest_sync
    say(f"  slowest single operation p95: {slowest_sync} ms  vs proposed sync timeout {ic.OPERATION_BY_ID['score_ats'].timeout_s * 1000:.0f} ms")

    say("\n=== 6. Why batch scoring is per pair (shared corpus vs per pair, 16 resumes) ===")
    norm = [normalize_section_headings(t) for t in texts]
    t0 = time.perf_counter()
    shared = ATSService(matcher=SemanticMatcher(norm + [jd]))
    shared_res = [shared.run({"resume_text": t, "job_description": jd}) for t in texts]
    shared_ms = (time.perf_counter() - t0) * 1000
    t0 = time.perf_counter()
    pair_res = [ATSService().run({"resume_text": t, "job_description": jd}) for t in texts]
    pair_ms = (time.perf_counter() - t0) * 1000
    deltas = [abs(a["ats_score"] - b["ats_score"]) for a, b in zip(shared_res, pair_res)]
    zone_changes = sum(a["zone"] != b["zone"] for a, b in zip(shared_res, pair_res))
    say(f"  per-pair {pair_ms:.0f} ms, shared corpus {shared_ms:.0f} ms ({pair_ms / shared_ms:.1f}x); max score difference {max(deltas):.2f}; zone changed for {zone_changes} of {len(texts)}")
    report["batch_basis"] = {"resumes": len(texts), "per_pair_ms": round(pair_ms, 1), "shared_ms": round(shared_ms, 1), "max_score_difference": round(max(deltas), 2),
                             "zone_changes": zone_changes}

    say("\n=== 7. Retry simulation (flaky service, no real waiting) ===")
    sims = {}
    for name, errors in {"two_503_then_ok": ["service_unavailable", "service_unavailable"], "four_timeouts": ["timeout"] * 4, "bad_input": ["invalid_input"],
                         "rate_limited_once": ["rate_limited"]}.items():
        seq = list(errors)

        def runner(attempt, seq=seq):
            if attempt <= len(seq):
                code = seq[attempt - 1]
                if code in ("invalid_input",):
                    return {"status": "error", "error": {"code": code, "message": "m", "field": None}}
                raise ic.TransportError(code, 3.0 if code == "rate_limited" else None)
            return {"status": "success"}

        out = ic.call_with_retry(runner, sleep=lambda s: None, rng=lambda: 1.0)
        sims[name] = {"attempts": out.attempts, "delays_s": [round(d, 2) for d in out.delays], "result": out.envelope["status"], "stopped_because": out.gave_up}
        say(f"  {name:20s} attempts={out.attempts} waits={sims[name]['delays_s']} result={out.envelope['status']} stopped={out.gave_up}")
    report["retry_simulation"] = sims

    say("\n=== 8. Backend -> AI -> database access check (Day 55 rules, service role) ===")
    checks = ic.check_data_access()
    gaps = [c for c in checks if c.allowed is not True]
    say(f"  {len(checks)} data touches checked, {len(checks) - len(gaps)} allowed, {len(gaps)} not")
    for c in gaps:
        say(f"  {c.key} -> {c.rule_id}: {ic.KNOWN_GAPS.get(c.key, 'UNDOCUMENTED')[:90]}")
    report["access_check"] = {"touches": len(checks), "allowed": len(checks) - len(gaps), "gaps": [list(c.key) for c in gaps],
                              "gaps_all_documented": {c.key for c in gaps} == set(ic.KNOWN_GAPS)}

    say("\n=== 9. Largest request each schema permits vs the proposed gateway cap ===")
    sizes = {}
    for op in ic.OPERATIONS:
        if op.request_schema:
            worst = ic.worst_case_bytes(op.request_schema)
            sizes[op.op_id] = {"schema_worst_case_bytes": worst, "proposed_cap_bytes": op.max_body_bytes}
            say(f"  {op.op_id:20s} schema allows up to {worst / 1_048_576:8.1f} MiB; proposed cap {op.max_body_bytes / 1_048_576:5.2f} MiB")
    report["request_sizes"] = sizes

    say("\n=== 10. Diagram ===")
    draw_diagram(ROOT / "data/integration/day59_api_mapping.png")
    say("  data/integration/day59_api_mapping.png")
    (ROOT / "data/results/day59_integration_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    say("\nWrote data/results/day59_integration_report.json")
    return 0


def draw_diagram(path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    fig, ax = plt.subplots(figsize=(15, 9))
    ax.set_xlim(0, 150)
    ax.set_ylim(-6, 86)
    ax.axis("off")

    def box(x, y, w, h, text, fc, fs=9, bold=False):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.2", fc=fc, ec="#333", lw=1.1))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, fontweight="bold" if bold else "normal", linespacing=1.4)

    def arrow(x1, y1, x2, y2, color="#444", dashed=False):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="-|>", color=color, lw=1.2, ls="--" if dashed else "-"))

    def label(x, y, text):
        ax.text(x, y, text, fontsize=7.5, ha="center", va="center", color="#222", bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="none"))

    ax.text(75, 83, "Zecpath AI integration: who calls what, and where the data lives", ha="center", fontsize=14, fontweight="bold")
    ax.text(2, 77, "Sync = the answer comes back in the response.   Async = 202 + job_id, then poll.   The backend retries only the codes the error policy allows (429, 503, 504 ...).",
            fontsize=8.5, va="center", color="#333")
    box(1, 40, 20, 18, "Client apps\nrecruiter dashboard\ncandidate portal\nadmin panel", "#e8f0fe", bold=True)
    box(36, 40, 28, 18, "Backend\nauth + Day 55 access rules\njob queue\nsaves results, writes audit", "#fff4d6", fs=8.5, bold=True)
    box(78, 40, 24, 18, "AI gateway /v1/ai\nservice token + scope\nschema check, rate limit\nrequest id, error mapping", "#e3f6e8", fs=8.5, bold=True)
    arrow(21.5, 49, 35.5, 49)
    label(28.5, 52.5, "HTTPS +\nuser token")
    arrow(64.5, 49, 77.5, 49)
    label(71, 52.5, "mTLS +\nservice token")
    ax.text(131, 74, "AI services (stateless, Day 57 run() contract)", ha="center", fontsize=10, fontweight="bold")
    svc = [("POST /resumes/parse   (async)\nResumeParsingService", 64), ("POST /ats/score   (sync)\nATSService", 55), ("POST /ats/score-batch   (async)\nATSBatchService", 46),
           ("POST /screening/score   (sync)\nScreeningService", 37), ("POST /interviews/score   (sync)\nInterviewIntelligenceService", 28),
           ("POST /decisions/recommend   (sync)\nDecisionScoringService", 19)]
    for text, y in svc:
        box(113, y, 36, 7.2, text, "#e3f6e8" if "(sync)" in text else "#fde8e8", fs=8)
        arrow(102.5, 49, 112.5, y + 3.6, color="#888")
    box(113, 7, 36, 8, "GET /jobs/{id}   POST /jobs/{id}/cancel\nGET /health   (job store)", "#f1e8fd", fs=8)
    arrow(102.5, 49, 112.5, 11, color="#888")
    stores = [("resume_store", 1), ("transcript_store", 22), ("report_store\n(scores, decisions)", 43), ("job_store\n(not in plan: G2)", 64)]
    for name, x in stores:
        box(x, 14, 19, 10, name, "#eeeeee", fs=8.5)
        arrow(50, 39.5, x + 9.5, 24.8, dashed=True)
    box(1, 1, 40, 7.5, "audit_store (append-only, no text)", "#eeeeee", fs=8.5)
    box(44, 1, 40, 7.5, "identity_map (never sent to the AI layer)", "#eeeeee", fs=8.5)
    arrow(50, 39.5, 21, 8.8, dashed=True)
    label(14, 32, "read inputs,\nsave results")
    ax.text(43, -3.5, "Data stores: the backend reads and writes them; the AI layer never connects to them.", ha="center", fontsize=9.5, fontweight="bold")
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    sys.exit(main())
