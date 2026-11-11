"""
Day 60 load test.

    python run_day60_load_test.py                 (about 1 minute; add --seconds 2 for a quicker run)

Three parts, kept apart because they prove different things:

  A. THREADS   (measured)   N threads calling the ATS service in a loop. Shows the interpreter lock: more threads add no throughput.
  B. PROCESSES (measured)   N worker processes, each warmed up first, calling the ATS service in a loop. Throughput can grow with N only
                            if the machine has the cores: the output states how many it has, because on a 1-core machine this part
                            CANNOT show a gain and must not be read as if it did. Run it on a multi-core machine to see scaling.
  C. SIMULATION (model)     load-balancing policies and dedicated pools, using the benchmark's measured service times (see
                            parsers/scaling_model.py for what the model is and is not), plus the capacity plan.

Writes data/results/day60_load_test.json. Nothing here touches a network, a queue or a database.
"""

import argparse
import glob
import json
import logging
import multiprocessing
import os
import statistics
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
logging.disable(logging.CRITICAL)


def load_inputs():
    jd = Path(sorted(glob.glob(str(ROOT / "data/samples/jds/*.txt")))[0]).read_text(encoding="utf-8")
    resumes = [Path(p).read_text(encoding="utf-8") for p in sorted(glob.glob(str(ROOT / "data/samples/resumes/*.txt")))]
    return jd, resumes


def distinct(resume: str, n: int) -> str:
    return resume + f"\nReference note {n}: available for interview on weekdays."


def summarize(latencies_ms, seconds):
    s = sorted(latencies_ms)
    pick = lambda q: s[min(len(s) - 1, int(q * (len(s) - 1) + 0.5))]
    return {"requests": len(s), "throughput_per_s": round(len(s) / seconds, 1), "p50_ms": round(pick(0.5), 2), "p95_ms": round(pick(0.95), 2),
            "p99_ms": round(pick(0.99), 2), "max_ms": round(s[-1], 2)}


# ---------------------------------------------------------------------------------------------------- A. threads
def thread_level(n_threads: int, seconds: float):
    from ats_engine.service import ATSService
    jd, resumes = load_inputs()
    ATSService().run({"resume_text": resumes[0], "job_description": jd})
    barrier = threading.Barrier(n_threads + 1)
    results = [[] for _ in range(n_threads)]

    def work(idx):
        svc = ATSService()
        barrier.wait()
        end = time.perf_counter() + seconds
        i = 0
        while time.perf_counter() < end:
            t = time.perf_counter()
            svc.run({"resume_text": distinct(resumes[i % len(resumes)], idx * 1_000_000 + i), "job_description": jd})
            results[idx].append((time.perf_counter() - t) * 1000)
            i += 1

    threads = [threading.Thread(target=work, args=(k,)) for k in range(n_threads)]
    for t in threads:
        t.start()
    barrier.wait()
    for t in threads:
        t.join()
    return summarize([x for r in results for x in r], seconds)


# ---------------------------------------------------------------------------------------------------- B. processes
def process_worker(idx, barrier, seconds, out_q):
    sys.path.insert(0, str(ROOT))
    logging.disable(logging.CRITICAL)
    try:
        from utils.warmup import warm_up
        warm_up(("ats",))
    except ImportError:
        pass
    from ats_engine.service import ATSService
    jd, resumes = load_inputs()
    svc = ATSService()
    barrier.wait()
    end = time.perf_counter() + seconds
    lat, i = [], 0
    while time.perf_counter() < end:
        t = time.perf_counter()
        svc.run({"resume_text": distinct(resumes[i % len(resumes)], idx * 1_000_000 + i), "job_description": jd})
        lat.append((time.perf_counter() - t) * 1000)
        i += 1
    out_q.put((idx, lat))


def process_level(n_procs: int, seconds: float):
    ctx = multiprocessing.get_context("spawn")
    barrier, q = ctx.Barrier(n_procs + 1), ctx.Queue()
    procs = [ctx.Process(target=process_worker, args=(k, barrier, seconds, q)) for k in range(n_procs)]
    for p in procs:
        p.start()
    barrier.wait(timeout=180)
    collected = [q.get(timeout=seconds + 120) for _ in procs]
    for p in procs:
        p.join()
    return summarize([x for _, lat in collected for x in lat], seconds)


# ---------------------------------------------------------------------------------------------------- C. simulation
def measured_service_times():
    """Median of the 'after' benchmark runs, in seconds. Falls back to documented defaults if the runs are missing."""
    runs = [json.load(open(f, encoding="utf-8")) for f in sorted(glob.glob(str(ROOT / "data/results/day60_runs/day60_bench_after_*.json")))]
    fallback = {"ats": 0.003, "parse_pdf": 0.016, "screening": 0.0017, "interview_hr": 0.0012, "interview_technical": 0.00004, "decision": 0.00007, "ats_batch_100": 0.30}
    if not runs:
        return fallback, False
    med = lambda key, field="p50_ms": statistics.median(r["workloads"][key][field] for r in runs) / 1000.0
    return {"ats": med("ats_single_same_jd"), "parse_pdf": med("parse_pdf"), "screening": med("screening_7_turns"), "interview_hr": med("interview_hr_4_answers"),
            "interview_technical": med("interview_technical_3_answers"), "decision": med("decision"),
            "ats_batch_100": med("ats_batch_100", "median_ms")}, True


def simulation(horizon_s=600.0, seed=60):
    from parsers import scaling_model as sm
    svc, from_runs = measured_service_times()
    workers = 4
    base = [sm.RequestClass("ats_score", 1.0, svc["ats"]), sm.RequestClass("interview_hr", 1.0, svc["interview_hr"]), sm.RequestClass("screening", 1.0, svc["screening"]),
            sm.RequestClass("parse_pdf", 1.0, svc["parse_pdf"], cv=0.5), sm.RequestClass("ats_batch_100", 1.0, svc["ats_batch_100"], cv=0.2)]
    mix = {"ats_score": 40.0, "interview_hr": 40.0, "screening": 20.0, "parse_pdf": 15.0, "ats_batch_100": 0.3}      # relative rates
    per_unit = sum(mix[c.name] * c.mean_service_s for c in base)
    scale = 0.6 * workers / per_unit                                       # choose the rate multiplier that makes utilization 0.6
    classes = [sm.RequestClass(c.name, mix[c.name] * scale, c.mean_service_s, c.cv) for c in base]
    arrivals = sm.generate_arrivals(classes, horizon_s, seed)
    out = {"service_times_s": {k: round(v, 6) for k, v in svc.items()}, "service_times_from_benchmark_runs": from_runs, "workers": workers,
           "target_utilization": 0.6, "horizon_s": horizon_s, "requests": len(arrivals), "rate_per_s": {c.name: round(c.rate_per_s, 2) for c in classes}, "policies": {}}
    quick = ("ats_score", "interview_hr", "screening")
    for policy in sm.POLICIES:
        lat = sm.simulate(arrivals, workers, policy, seed)
        out["policies"][policy] = {"quick_requests": sm.summarize_latencies([x for c in quick for x in lat.get(c, [])]),
                                   "ats_score": sm.summarize_latencies(lat["ats_score"])}
    fast_arr, slow_arr = sm.split_by_pool(arrivals, quick)
    lat_fast = sm.simulate(fast_arr, 2, "shared_queue", seed)
    lat_slow = sm.simulate(slow_arr, 2, "shared_queue", seed)
    out["dedicated_pools_2_plus_2"] = {"quick_requests": sm.summarize_latencies([x for v in lat_fast.values() for x in v]),
                                       "ats_score": sm.summarize_latencies(lat_fast["ats_score"]),
                                       "slow_jobs": sm.summarize_latencies([x for v in lat_slow.values() for x in v])}
    return out


def capacity(svc):
    from parsers import scaling_model as sm
    per_app = svc["parse_pdf"] + svc["ats"] + svc["screening"] + svc["interview_hr"] + svc["interview_technical"] + svc["decision"]
    rows = [sm.capacity_plan(n, per_app, name=name) for n, name in [(10_000, "10,000 applications a day"), (100_000, "100,000 a day"), (1_000_000, "1,000,000 a day"),
                                                                    (10_000_000, "10,000,000 a day")]]
    return {"cpu_ms_per_application": round(per_app * 1000, 2), "assumptions": {"busiest_hour_share": 0.15, "target_utilization": 0.6, "spare_workers": 1},
            "rows": [r.__dict__ for r in rows]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=3.0, help="how long each measured level runs")
    ap.add_argument("--max-procs", type=int, default=4)
    args = ap.parse_args()
    cpus = os.cpu_count() or 1
    report = {"cpu_count": cpus, "seconds_per_level": args.seconds}
    print(f"This machine reports {cpus} CPU(s).")

    print("\n=== A. Threads (measured): do more threads add throughput? ===")
    report["threads"] = {}
    for n in (1, 2, 4, 8):
        r = thread_level(n, args.seconds)
        report["threads"][str(n)] = r
        print(f"  {n} thread(s): {r['throughput_per_s']:7.1f} req/s   p50 {r['p50_ms']:7.2f}  p95 {r['p95_ms']:7.2f}  p99 {r['p99_ms']:7.2f} ms")

    print("\n=== B. Processes (measured): does throughput grow with worker processes? ===")
    report["processes"] = {}
    levels = [n for n in (1, 2, 4) if n <= args.max_procs]
    for n in levels:
        r = process_level(n, args.seconds)
        report["processes"][str(n)] = r
        print(f"  {n} process(es): {r['throughput_per_s']:7.1f} req/s   p50 {r['p50_ms']:7.2f}  p95 {r['p95_ms']:7.2f}  p99 {r['p99_ms']:7.2f} ms")
    base = report["processes"]["1"]["throughput_per_s"]
    for n in levels:
        report["processes"][str(n)]["speedup_vs_1"] = round(report["processes"][str(n)]["throughput_per_s"] / base, 2)
    print(f"  speed-up vs 1 process: {[report['processes'][str(n)]['speedup_vs_1'] for n in levels]}   (this machine has {cpus} CPU(s))")
    if cpus < 2:
        print("  NOTE: one CPU, so extra processes cannot run in parallel here; run this on a multi-core machine to see the scaling.")

    print("\n=== C. Simulation (model): load balancing and dedicated pools ===")
    sim = simulation()
    report["simulation"] = sim
    print(f"  {sim['requests']} requests over {sim['horizon_s']:.0f} s, 4 workers, utilization 0.6, service times from the benchmark")
    for policy, v in sim["policies"].items():
        q = v["quick_requests"]
        print(f"  mixed pool, {policy:18s} quick requests  p50 {q['p50_ms']:7.2f}  p95 {q['p95_ms']:8.2f}  p99 {q['p99_ms']:8.2f} ms")
    d = sim["dedicated_pools_2_plus_2"]["quick_requests"]
    print(f"  dedicated 2+2 pools                       quick requests  p50 {d['p50_ms']:7.2f}  p95 {d['p95_ms']:8.2f}  p99 {d['p99_ms']:8.2f} ms")

    print("\n=== D. Capacity plan (arithmetic from measured service times) ===")
    cap = capacity(sim["service_times_s"])
    report["capacity"] = cap
    print(f"  one application's compute: {cap['cpu_ms_per_application']} ms (parse + ATS + screening + HR + technical + decision)")
    for r in cap["rows"]:
        print(f"  {r['scenario']:28s} busiest hour {r['peak_per_s']:9.3f}/s   workers at 0.6 target: {r['cores_at_target']:4d}   with 1 spare: {r['workers_with_spare']:4d}")

    out = ROOT / "data/results/day60_load_test.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
