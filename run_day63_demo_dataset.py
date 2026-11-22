"""
Day 63 demo: builds the demo dataset, checks it, and runs it end to end through the real engines.

    python run_day63_demo_dataset.py        (about 10 seconds)

STEPS
  1. build data/demo_dataset/ (6 jobs, 30 resumes as DOCX/PDF, answers, machine-test attempts, browser events, 4 edge files);
  2. verify the dataset is internally consistent and that the upload path refuses the edge files politely;
  3. run all 30 candidates through every round (ATS, screening, HR, technical, machine test + integrity, Hiring Fit, recommendation, report);
  4. write the simulated results to data/demo_dataset/simulated/ and print what the run shows, including the expectations the system missed.

Writes: data/demo_dataset/** , data/results/day63_demo_report.json, logs/day63_demo_run.log
"""

import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
logging.disable(logging.CRITICAL)

from parsers import demo_dataset_builder, demo_environment as env  # noqa: E402

LOG = ROOT / "logs" / "day63_demo_run.log"
REPORT = ROOT / "data" / "results" / "day63_demo_report.json"
lines = []


def say(text=""):
    print(text)
    lines.append(text)


def main():
    t0 = time.perf_counter()
    say("=== 1. build the dataset ===")
    built = demo_dataset_builder.build_dataset()
    for key, value in built.items():
        say(f"  {key:24} {value}")

    ds = env.load_dataset()
    say("\n=== 2. check the dataset ===")
    problems = env.verify_dataset(ds)
    say(f"  dataset problems: {len(problems)}" + ("" if not problems else "  " + "; ".join(problems)))
    for item in env.edge_file_results():
        say(f"  edge file {item['file']:24} -> {item['result']}: {item.get('error', '')[:70]}")

    say("\n=== 3. run every candidate through every round ===")
    runs = env.run_environment(ds)
    say(f"{'id':6} {'job':12} {'ATS':>5} {'zone':9} {'scr':>5} {'HR':>5} {'tech':>5} {'mach':>5} {'integ':6} {'fit':>5}  {'outcome':12} {'expected':26} met")
    for r in runs:
        w = env._row(r)
        say(f"{w['id']:6} {w['job'][:12]:12} {w['ats_score']:>5} {w['ats_zone']:9} {w['screening_score']:>5} {w['hr_score']:>5} {str(w['technical_score']):>5} "
            f"{str(w['machine_test_score']):>5} {str(w['integrity_tag']):6} {w['hiring_fit']:>5}  {w['outcome']:12} {w['expected']:26} {'yes' if w['met'] else 'NO'}")

    summary = env.write_outputs(runs)
    say("\n=== 4. what the run shows ===")
    say(f"  outcomes: {summary['outcomes']}    ATS zones: {summary['ats_zones']}")
    say(f"  expected outcome met: {summary['expected_outcome_met']} of {summary['candidates']}    missed: {', '.join(summary['expected_outcome_missed'])}")
    say(f"  automated rejections: {summary['automated_rejections']}    errors: {len(summary['with_errors'])}    integrity tags: {summary['integrity_tags']}")
    say("  by job: " + "; ".join(f"{k} {v['met']}/{v['candidates']}" for k, v in summary["by_job"].items()))
    findings = env.probe_findings(runs, ds)
    say("\n  FINDINGS (computed from this run):")
    for f in findings:
        say(f"   {f['id']:4} {f['title']}\n        {f['statement']}")

    elapsed = time.perf_counter() - t0
    say(f"\n  scoring time for 30 candidates: {summary['total_ms']:.0f} ms; whole script {elapsed:.1f} s")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({"built": built, "problems": problems, "summary": summary, "findings": findings,
                                  "edge_files": env.edge_file_results()}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
    say(f"\nWrote {REPORT.relative_to(ROOT)}, {LOG.relative_to(ROOT)} and data/demo_dataset/simulated/*")


if __name__ == "__main__":
    main()
