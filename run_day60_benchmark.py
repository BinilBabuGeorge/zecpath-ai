"""
Day 60 benchmark harness.

Measures the SAME workloads on whichever copy of the code it is run from, so "before" and "after" come from one script:

    python run_day60_benchmark.py --label before --out data/results/day60_bench_before.json     (run inside the pre-Day-60 copy)
    python run_day60_benchmark.py --label after  --out data/results/day60_bench_after.json      (run inside the optimized repo)

It only calls interfaces that exist in both versions (the four services, ResumeParsingService, ATSBatchService), so nothing here
is tied to the optimization. Every workload also records a FINGERPRINT (SHA-256 of its results), so a speed-up that changed an
answer would show as a different fingerprint, not just a faster number.

What is measured: compute only, on one machine, in one process. No network, storage, queue, speech-to-text or authentication.
Timings are wall-clock (time.perf_counter); memory is Python allocations from tracemalloc, measured in a separate pass because
tracemalloc itself slows code down.
"""

import argparse
import glob
import hashlib
import json
import logging
import os
import platform
import statistics
import subprocess
import sys
import time
import tracemalloc
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
logging.disable(logging.CRITICAL)           # logging cost is measured on its own, below

AS_OF = date(2026, 11, 1)


def fingerprint(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def pct(sorted_samples, q):
    return sorted_samples[min(len(sorted_samples) - 1, int(q * (len(sorted_samples) - 1) + 0.5))]


def summarize(samples_ms):
    s = sorted(samples_ms)
    return {"n": len(s), "p50_ms": round(statistics.median(s), 3), "p95_ms": round(pct(s, 0.95), 3), "p99_ms": round(pct(s, 0.99), 3),
            "mean_ms": round(statistics.mean(s), 3), "total_ms": round(sum(s), 1)}


def clear_named_cache(name):
    """Empty one of the Day 60 caches if this copy of the code has it (the 'before' code does not)."""
    try:
        from utils.perf import clear_cache
        clear_cache(name)
    except ImportError:
        pass


def run_calls(fn, items, repeats, before_each=None):
    """Call fn(item, rep) on every item `repeats` times after one untimed warm pass (rep = -1). `rep` lets a workload make each
    repeat's INPUT different, so a cache keyed on the whole input cannot answer from the previous repeat. Returns (timings, results of
    the LAST pass)."""
    for it in items:
        fn(it, -1)
    samples, last = [], []
    for r in range(repeats):
        last = []
        for it in items:
            if before_each:
                before_each()
            t = time.perf_counter()
            out = fn(it, r)
            samples.append((time.perf_counter() - t) * 1000)
            last.append(out)
    return samples, last


def vary(text, rep):
    return text + f"\nReference note {rep}: available for interview on weekdays."


def load_inputs():
    jds = [Path(p).read_text(encoding="utf-8") for p in sorted(glob.glob(str(ROOT / "data/samples/jds/*.txt")))]
    resumes = [Path(p).read_text(encoding="utf-8") for p in sorted(glob.glob(str(ROOT / "data/samples/resumes/*.txt")))]
    docx = sorted(glob.glob(str(ROOT / "data/raw_resumes/docx/*.docx")))
    pdfs = sorted(glob.glob(str(ROOT / "data/raw_resumes/pdf/*.pdf")))
    return jds, resumes, docx, pdfs


def variants(resumes, n):
    """n distinct resumes built from the real ones (a unique note is appended so no resume-level cache can hit by accident)."""
    return [resumes[i % len(resumes)] + f"\nReference note {i}: available for interview on weekdays." for i in range(n)]


def workloads():
    from ats_engine.batch_service import ATSBatchService
    from ats_engine.resume_parsing_service import ResumeParsingService
    from ats_engine.service import ATSService
    from interview_ai.service import InterviewIntelligenceService
    from scoring.service import DecisionScoringService
    from screening_ai.service import ScreeningService

    jds, resumes, docx, pdfs = load_inputs()
    jd = jds[0]
    out = {}

    def ats(item, rep):
        r, j = item
        return ATSService().run({"resume_text": vary(r, rep), "job_description": j})

    s, res = run_calls(ats, [(r, jd) for r in resumes], 3)
    out["ats_single_same_jd"] = {**summarize(s), "fingerprint": fingerprint(res)}
    pairs = [(r, j) for j in jds[:4] for r in resumes]
    s, res = run_calls(ats, pairs, 2)
    out["ats_single_four_jds"] = {**summarize(s), "pairs": len(pairs), "fingerprint": fingerprint(res)}

    for n in (16, 100):
        body = {"job_description": jd, "candidates": [{"candidate_id": f"C{i:03d}", "resume_text": t} for i, t in enumerate(variants(resumes, n))]}
        samples, last = [], None
        for _ in range(3 if n == 16 else 2):
            t = time.perf_counter()
            last = ATSBatchService().run(body)
            samples.append((time.perf_counter() - t) * 1000)
        out[f"ats_batch_{n}"] = {"runs": len(samples), "best_ms": round(min(samples), 1), "median_ms": round(statistics.median(samples), 1),
                                 "per_candidate_ms": round(statistics.median(samples) / n, 3), "fingerprint": fingerprint(last)}

    def parse(item, rep):
        path, ftype = item
        return ResumeParsingService(resolver=lambda ref: path).run({"candidate_id": "C1", "file_ref": os.path.basename(path), "file_type": ftype,
                                                                  "as_of_date": AS_OF.isoformat()})

    # parse workloads clear the parse-result cache before every call, so they measure the cost of a FIRST parse of a file
    s, res = run_calls(parse, [(p, "docx") for p in docx], 3, before_each=lambda: clear_named_cache("resume_parse"))
    out["parse_docx"] = {**summarize(s), "fingerprint": fingerprint(res)}
    s, res = run_calls(parse, [(p, "pdf") for p in pdfs], 3, before_each=lambda: clear_named_cache("resume_parse"))
    out["parse_pdf"] = {**summarize(s), "fingerprint": fingerprint(res)}
    s, res = run_calls(parse, [(p, "pdf") for p in pdfs], 3)
    out["parse_pdf_same_file_again"] = {**summarize(s), "note": "the same files parsed again (a retried job or re-upload); caches left on", "fingerprint": fingerprint(res)}

    turns = [{"text": t, "confidence": 0.9} for t in [
        "Hello, I am a MERN developer with three years of experience at a product company.", "I did my B.Tech in Computer Science in 2021.",
        "I have worked for three years building React and Node.js applications.", "My skills are React, Node.js, MongoDB and Docker.",
        "I am currently based in Bengaluru.", "My expected salary is eight lakhs per annum.", "My notice period is one month."]]
    def screen(_, rep):
        t = [dict(x) for x in turns]
        t[3]["text"] = t[3]["text"] + f" Also {rep} side projects."
        return ScreeningService().run({"candidate_id": "C01", "turns": t})

    s, res = run_calls(screen, [0] * 20, 5)
    out["screening_7_turns"] = {**summarize(s), "fingerprint": fingerprint(res[:1])}
    hr_answers = ["I am a full stack developer with three years of experience building web applications.", "I led the migration of our API to TypeScript.",
                  "I prefer small teams and I review code daily.", "My weakness was estimating tasks, so I break work into small pieces."]
    s, res = run_calls(lambda _, rep: InterviewIntelligenceService().run({"interview_type": "hr", "role_type": "technical", "experience_level": "experienced",
                                                                         "answers": [hr_answers[0] + f" Project {rep}."] + hr_answers[1:]}), [0] * 20, 5)
    out["interview_hr_4_answers"] = {**summarize(s), "fingerprint": fingerprint(res[:1])}
    tech = ["React uses a virtual DOM to batch updates.", "Node.js is single threaded with an event loop.", "Indexes speed up queries but slow down writes."]
    s, res = run_calls(lambda _, rep: InterviewIntelligenceService().run({"interview_type": "technical", "domain": "mern", "experience_years": 3,
                                                                         "answers": [tech[0] + f" Case {rep}."] + tech[1:]}), [0] * 20, 5)
    out["interview_technical_3_answers"] = {**summarize(s), "fingerprint": fingerprint(res[:1])}
    s, res = run_calls(lambda _, rep: DecisionScoringService().run({"candidate_id": "C1", "ats_score": 70 + rep, "screening_score": 75, "hr_interview_score": 80,
                                                                   "technical_score": 60}), [0] * 50, 5)
    out["decision"] = {**summarize(s), "fingerprint": fingerprint(res[:1])}
    return out


def logging_cost():
    """What the services' own INFO log lines cost, with the project's real handlers (console + rotating file) attached."""
    from ats_engine.service import ATSService
    from utils.logger import get_logger
    jds, resumes, _, _ = load_inputs()
    svc = ATSService()
    body = {"resume_text": resumes[0], "job_description": jds[0]}
    svc.run(body)

    def timed_loop(n=60):
        t = time.perf_counter()
        for _ in range(n):
            svc.run(body)
        return (time.perf_counter() - t) * 1000 / n

    logging.disable(logging.CRITICAL)
    off = min(timed_loop() for _ in range(3))
    get_logger("day60")                     # attaches the project handlers, exactly as production would
    logging.disable(logging.NOTSET)
    devnull = open(os.devnull, "w")
    for h in logging.getLogger().handlers:
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
            h.stream = devnull
    on = min(timed_loop() for _ in range(3))
    logging.disable(logging.CRITICAL)
    return {"logging_off_ms": round(off, 3), "logging_on_ms": round(on, 3), "overhead_ms": round(on - off, 3)}


COLD_SNIPPET = r"""
import time, sys, json, logging
logging.disable(logging.CRITICAL)
sys.path.insert(0, %r)
t0 = time.perf_counter()
from ats_engine.service import ATSService
t1 = time.perf_counter()
jd = open(%r, encoding='utf-8').read(); r = open(%r, encoding='utf-8').read()
s = ATSService()
warm_ms = None
try:
    from utils.warmup import warm_up
    tw = time.perf_counter(); warm_up(('ats',)); warm_ms = (time.perf_counter() - tw) * 1000
except ImportError:
    pass
t2 = time.perf_counter(); s.run({'resume_text': r, 'job_description': jd}); t3 = time.perf_counter()
s.run({'resume_text': r, 'job_description': jd}); t4 = time.perf_counter()
print(json.dumps({'import_ms': (t1-t0)*1000, 'warmup_ms': warm_ms, 'first_call_ms': (t3-t2)*1000, 'second_call_ms': (t4-t3)*1000}))
"""


def cold_start(repeats=3):
    jds, resumes, _, _ = load_inputs()
    jd_path = sorted(glob.glob(str(ROOT / "data/samples/jds/*.txt")))[0]
    r_path = sorted(glob.glob(str(ROOT / "data/samples/resumes/*.txt")))[0]
    runs = []
    for _ in range(repeats):
        res = subprocess.run([sys.executable, "-c", COLD_SNIPPET % (str(ROOT), jd_path, r_path)], capture_output=True, text=True, cwd=str(ROOT))
        runs.append(json.loads(res.stdout.strip().splitlines()[-1]))
    return {k: (round(statistics.median(r[k] for r in runs), 1) if runs[0][k] is not None else None) for k in runs[0]}


def memory_profile():
    from ats_engine.batch_service import ATSBatchService
    jds, resumes, _, _ = load_inputs()
    body = {"job_description": jds[0], "candidates": [{"candidate_id": f"C{i:03d}", "resume_text": t} for i, t in enumerate(variants(resumes, 100))]}
    input_bytes = sum(len(c["resume_text"].encode("utf-8")) for c in body["candidates"]) + len(body["job_description"].encode("utf-8"))
    ATSBatchService().run(body)
    tracemalloc.start()
    before = tracemalloc.get_traced_memory()[0]
    ATSBatchService().run(body)
    after_run, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    try:
        import resource
        rss_mb = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 if sys.platform != "darwin" else 1024 * 1024), 1)
    except Exception:
        rss_mb = None
    return {"batch_100_peak_python_mb": round((peak - before) / 1_048_576, 2), "batch_100_retained_after_mb": round((after_run - before) / 1_048_576, 2),
            "batch_100_input_kb": round(input_bytes / 1024, 1), "harness_process_peak_rss_mb": rss_mb}


RSS_SNIPPET = r"""
import sys, json, logging
logging.disable(logging.CRITICAL)
sys.path.insert(0, %r)
which = %r
def rss():
    # CURRENT resident memory of this fresh process, read from /proc (Linux). getrusage's peak would also count the parent it was forked from.
    try:
        for line in open('/proc/self/status'):
            if line.startswith('VmRSS:'):
                return int(line.split()[1]) / 1024.0
    except OSError:
        return None
if which == 'ats':
    from ats_engine.service import ATSService
    ATSService().run({'resume_text': 'Skills: React, Node.js', 'job_description': 'Required Skills: React, Node.js'})
elif which == 'parsing':
    import docx, pdfplumber
    from ats_engine.resume_parsing_service import ResumeParsingService
elif which == 'screening':
    from screening_ai.service import ScreeningService
    ScreeningService().run({'candidate_id': 'c', 'turns': [{'text': 'I have three years of experience.'}]})
elif which == 'interview':
    from interview_ai.service import InterviewIntelligenceService
    InterviewIntelligenceService().run({'interview_type': 'hr', 'answers': ['I led a team.']})
elif which == 'decision':
    from scoring.service import DecisionScoringService
    DecisionScoringService().run({'candidate_id': 'c', 'ats_score': 60, 'hr_interview_score': 70})
print(json.dumps({'rss_mb': rss()}))
"""


def memory_by_service():
    """Resident memory of a fresh process that has loaded and served ONE kind of request (Linux only; None elsewhere)."""
    out = {}
    for which in ("nothing", "decision", "interview", "screening", "ats", "parsing"):
        res = subprocess.run([sys.executable, "-c", RSS_SNIPPET % (str(ROOT), which)], capture_output=True, text=True, cwd=str(ROOT))
        try:
            v = json.loads(res.stdout.strip().splitlines()[-1])["rss_mb"]
            out[which] = round(v, 1) if v is not None else None
        except Exception:
            out[which] = None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--quick", action="store_true", help="skip the slower cold-start and memory passes")
    args = ap.parse_args()
    report = {"label": args.label, "python": platform.python_version(), "cpu_count": os.cpu_count(), "platform": platform.platform()}
    print(f"[{args.label}] workloads ...")
    report["workloads"] = workloads()
    if not args.quick:
        print(f"[{args.label}] logging cost ...")
        report["logging"] = logging_cost()
        print(f"[{args.label}] cold start ...")
        report["cold_start"] = cold_start()
        print(f"[{args.label}] memory ...")
        report["memory"] = memory_profile()
        print(f"[{args.label}] memory by service ...")
        report["memory_by_service_mb"] = memory_by_service()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for name, w in report["workloads"].items():
        line = f"  {name:32s}"
        line += f" p50 {w['p50_ms']:8.3f} ms  p95 {w['p95_ms']:8.3f} ms" if "p50_ms" in w else f" median {w['median_ms']:8.1f} ms  ({w['per_candidate_ms']} ms/candidate)"
        print(line + f"   fp {w['fingerprint']}")
    for k in ("logging", "cold_start", "memory", "memory_by_service_mb"):
        if k in report:
            print(f"  {k}: {report[k]}")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
