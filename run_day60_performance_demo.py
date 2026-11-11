"""
Day 60 summary: reads the recorded before/after benchmark runs (data/results/day60_runs/), checks that every answer is unchanged, and
prints the tables used in docs/day60_performance_benchmark_report.md. Also measures what the caches do on a realistic batch.

    python run_day60_performance_demo.py

The runs themselves come from run_day60_benchmark.py (one script, run once on the pre-Day-60 code and once on the optimized code, three
times each). Writes data/results/day60_benchmark_summary.json and logs/day60_performance_run.log.
"""

import glob
import json
import logging
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
(ROOT / "logs").mkdir(exist_ok=True)
logging.disable(logging.CRITICAL)
LOG = open(ROOT / "logs" / "day60_performance_run.log", "w", encoding="utf-8")


def say(msg=""):
    print(msg)
    LOG.write(msg + "\n")


def runs(label):
    return [json.loads(Path(p).read_text(encoding="utf-8")) for p in sorted(glob.glob(str(ROOT / f"data/results/day60_runs/day60_bench_{label}_*.json")))]


def main():
    before, after, nocache = runs("before"), runs("after"), runs("nocache")
    if not before or not after:
        say("No recorded runs found in data/results/day60_runs/. Run run_day60_benchmark.py first (see the document).")
        return 1
    summary = {"runs_before": len(before), "runs_after": len(after), "cpu_count": after[0]["cpu_count"], "python": after[0]["python"], "workloads": {}}

    say("=== 1. Are the answers unchanged? (SHA-256 fingerprint of every workload's results, before vs after, all runs) ===")
    same_all = True
    for name in before[0]["workloads"]:
        fps = {r["workloads"][name]["fingerprint"] for r in before + after + nocache}
        same = len(fps) == 1
        same_all &= same
        say(f"  {name:32s} {'identical in all %d runs' % (len(before) + len(after) + len(nocache)) if same else 'DIFFERENT'}")
    summary["answers_unchanged"] = same_all

    say("\n=== 2. Speed (median of %d runs each; p50 per request, or median per batch; 'caches OFF' = the optimized code with ZECPATH_CACHE=off) ===" % len(before))
    say(f"  {'workload':32s} {'before':>10s} {'after':>10s} {'speed-up':>9s}   {'caches OFF':>10s} {'speed-up':>9s}")
    for name, w in before[0]["workloads"].items():
        field = "p50_ms" if "p50_ms" in w else "median_ms"
        b = statistics.median(r["workloads"][name][field] for r in before)
        a = statistics.median(r["workloads"][name][field] for r in after)
        p95b = statistics.median(r["workloads"][name]["p95_ms"] for r in before) if field == "p50_ms" else None
        p95a = statistics.median(r["workloads"][name]["p95_ms"] for r in after) if field == "p50_ms" else None
        n = statistics.median(r["workloads"][name][field] for r in nocache) if nocache else None
        summary["workloads"][name] = {"before": b, "after": a, "speedup": round(b / a, 2), "after_caches_off": n, "speedup_caches_off": round(b / n, 2) if n else None,
                                      "p95_before": p95b, "p95_after": p95a, "unit": "ms"}
        say(f"  {name:32s} {b:9.3f}ms {a:9.3f}ms {b / a:8.2f}x   " + (f"{n:9.3f}ms {b / n:8.2f}x" if n else "") + (f"   (p95 {p95b:.2f} -> {p95a:.2f} ms)" if p95b is not None else ""))

    say("\n=== 3. Cold start (first request after a process starts) ===")
    b, a = before[0]["cold_start"], after[0]["cold_start"]
    summary["cold_start"] = {"before": b, "after": a}
    say(f"  before: import {b['import_ms']} ms, FIRST request {b['first_call_ms']} ms, second {b['second_call_ms']} ms")
    say(f"  after : import {a['import_ms']} ms, warm-up {a['warmup_ms']} ms (at start-up), FIRST request {a['first_call_ms']} ms, second {a['second_call_ms']} ms")

    say("\n=== 4. Memory ===")
    mb, ma = before[0]["memory_by_service_mb"], after[0]["memory_by_service_mb"]
    summary["memory_by_service_mb"] = {"before": mb, "after": ma}
    say(f"  {'process that has served only...':34s} {'before':>9s} {'after':>9s}")
    for k in ("nothing", "decision", "interview", "screening", "ats", "parsing"):
        label = {"nothing": "(an idle Python process)", "parsing": "(parsing libraries loaded, no request)"}.get(k, k)
        say(f"  {label:34s} {mb[k]:7.1f}MB {ma[k]:7.1f}MB")
    summary["batch_100_python_memory_mb"] = {"before": before[0]["memory"]["batch_100_peak_python_mb"], "after": after[0]["memory"]["batch_100_peak_python_mb"],
                                              "input_kb": after[0]["memory"]["batch_100_input_kb"]}
    say(f"  100-candidate batch, Python allocations at peak: {before[0]['memory']['batch_100_peak_python_mb']} MB before, {after[0]['memory']['batch_100_peak_python_mb']} MB after "
        f"(input {after[0]['memory']['batch_100_input_kb']} KB; retained afterwards {after[0]['memory']['batch_100_retained_after_mb']} MB)")

    say("\n=== 5. Logging cost per ATS request (project handlers attached) ===")
    lg = [r["logging"] for r in (before + after) if "logging" in r]
    say("  " + ", ".join(f"{x['overhead_ms']} ms" for x in lg) + "  (noise level; no change made)")
    summary["logging_overhead_ms"] = [x["overhead_ms"] for x in lg]

    say("\n=== 6. What the caches do on a realistic 100-candidate batch (new resumes, one job description) ===")
    from ats_engine.batch_service import ATSBatchService
    from utils import perf
    from utils.warmup import warm_up
    warm_up(("ats",))
    jd = Path(sorted(glob.glob(str(ROOT / "data/samples/jds/*.txt")))[0]).read_text(encoding="utf-8")
    resumes = [Path(p).read_text(encoding="utf-8") for p in sorted(glob.glob(str(ROOT / "data/samples/resumes/*.txt")))]
    body = {"job_description": jd, "candidates": [{"candidate_id": f"C{i:03d}", "resume_text": resumes[i % len(resumes)] + f"\nReference note {i}."} for i in range(100)]}
    perf.clear_all_caches()
    ATSBatchService().run(body)
    stats = perf.all_cache_stats()
    summary["cache_stats_batch_100"] = stats
    for name, s in stats.items():
        hr = f"{s['hit_rate'] * 100:.0f}%" if s["hit_rate"] is not None else "n/a"
        say(f"  {name:20s} entries {s['entries']:5d}/{s['max_items']:<5d} hits {s['hits']:5d} misses {s['misses']:5d} hit rate {hr:>5s}  ~{s['approx_bytes'] / 1024:7.1f} KB of {((s['max_bytes'] or 0) / 1024):9.1f} KB")
    ceiling = sum(s["max_bytes"] for s in stats.values() if s["max_bytes"])
    summary["cache_memory_ceiling_mb"] = round(ceiling / 1_048_576, 1)
    say(f"  combined byte ceiling of all Day 60 caches: {ceiling / 1_048_576:.1f} MB (a hard limit, however long a worker runs)")

    Path(ROOT / "data/results/day60_benchmark_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    say("\nWrote data/results/day60_benchmark_summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
