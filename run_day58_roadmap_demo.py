"""
Day 58 demo -- Advanced Feature Proposal. Regenerates every number quoted in docs/day58_ai_roadmap_and_innovation_proposal.md:

  1. BACKLOG     24 features validated for internal consistency (dependencies, phases, legal/evidence gates, module paths).
  2. ROADMAP     the phased plan, in build order, with priority scores and exit gates.
  3. EXCLUSIONS  what is deliberately NOT recommended, and why.
  4. FACTS       the existing-system facts the proposal rests on, read from the code.
  5. PROTOTYPE   the resume readiness check on the sample resumes and on awkward ones, and what a missed heading would cost.

Writes logs/day58_roadmap_run.log, data/results/day58_roadmap.json and data/results/day58_roadmap.md.

HONESTY NOTES: value / effort / feasibility are the author's 1-5 estimates (judgement, not measurement). Legal and evidence statements
come from cited secondary sources as of Nov 2026 and are not legal advice. No cost, headcount or calendar dates are claimed beyond
the regulators' own dates.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

logging.disable(logging.CRITICAL)

from ats_engine.service import ATSService
from parsers.hr_interview_scoring_engine import WeightConfig
from parsers.resume_readiness import check_resume_readiness
from parsers.roadmap_planner import build_order, load_backlog, not_recommended, render_markdown, roadmap_by_phase, validate_backlog

LOG_PATH, JSON_PATH, MD_PATH = "logs/day58_roadmap_run.log", "data/results/day58_roadmap.json", "data/results/day58_roadmap.md"
Path("logs").mkdir(exist_ok=True); Path("data/results").mkdir(parents=True, exist_ok=True)
_lines, report = [], {}
SAMPLES = Path("data/samples")
AS_OF = date(2026, 10, 30)


def say(s=""):
    print(s); _lines.append(s)


def head(s):
    say(); say("=" * 78); say(s); say("=" * 78)


# ------------------------------------------------------------------ 1 backlog
head("1. BACKLOG  validated for internal consistency")
b = load_backlog()
problems = validate_backlog(b, ".")
sched = [f for f in b.features if f.scheduled]
say(f"{len(b.features)} features: {len(sched)} scheduled across phases 1-4, {len(not_recommended(b))} deliberately not scheduled")
say(f"validation problems: {problems or 'none'}  (checks: unique ids, 1-5 ratings, known sources, dependencies exist and are acyclic,")
say("   no feature before its prerequisites, nothing prohibited / contradicted / emotion-inferring is scheduled, restricted features carry guardrails,")
say("   scheduled features have a success metric, regulatory-deadline features are early, every module named exists in the repository)")
paths = sorted({p for f in b.features for p in f.builds_on})
say(f"{len(paths)} distinct existing modules are referenced; all exist: {all(Path(p).exists() for p in paths)}")
assert problems == []
report["backlog"] = {"features": len(b.features), "scheduled": len(sched), "unscheduled": [f.id for f in not_recommended(b)], "problems": problems, "modules_referenced": len(paths)}

# ------------------------------------------------------------------ 2 roadmap
head("2. ROADMAP  build order, priority = 2*value + feasibility - effort")
by_phase = roadmap_by_phase(b)
for p in b.phases:
    say(f"Phase {p['phase']}  {p['name']}")
    say(f"    exit gate (proposed): {p['exit_gate']}")
    for f in by_phase[p["phase"]]:
        say(f"    {f.id:3} prio {f.priority_score:>2}  v{f.value} e{f.effort} f{f.feasibility}  {f.title[:62]}{'   [deadline: ' + f.deadline + ']' if f.deadline else ''}")
order = build_order(b)
say(f"build order respects every dependency: {all(order.index(next(x for x in order if x.id == d)) < order.index(f) for f in order for d in f.depends_on)}")
top = sorted(sched, key=lambda f: (-f.priority_score, f.id))[:5]
say("top five by priority score: " + ", ".join(f"{f.id} ({f.priority_score})" for f in top))
dl = [(f.id, f.deadline) for f in b.features if f.deadline]
say("regulatory deadlines that shape the order: " + "; ".join(f"{i}: {d}" for i, d in dl))
report["roadmap"] = {str(p): [f.id for f in fs] for p, fs in by_phase.items()}
report["top_priorities"] = [(f.id, f.priority_score) for f in top]

# ------------------------------------------------------------------ 3 exclusions
head("3. NOT RECOMMENDED  and why (each needs a product-owner decision)")
for f in not_recommended(b):
    say(f"  {f.id}  [{f.legal_status}; evidence: {f.evidence}]  {f.title[:80]}")
    say(f"       sources: {', '.join(f.source_ids)}")
report["not_recommended"] = [{"id": f.id, "legal_status": f.legal_status, "evidence": f.evidence} for f in not_recommended(b)]

# ------------------------------------------------------------------ 4 facts
head("4. FACTS FROM THE CODE  what the proposal rests on")
w = WeightConfig()
say(f"HR answer score weights: relevance {w.relevance}, communication {w.communication}, confidence {w.confidence}, consistency {w.consistency}")
say(f"-> the text-based 'confidence' signal carries {w.confidence:.0%} of every HR answer score, with no validation data behind it (item R1)")
say(f"modules in parsers/: {len(list(Path('parsers').glob('*.py')))};  camera/video libraries imported anywhere: "
    f"{sum(any(k in p.read_text(encoding='utf-8', errors='ignore') for k in ('import cv2', 'import mediapipe', 'import dlib')) for p in Path('parsers').glob('*.py'))}  (Days 48-49: no video pipeline by design)")
report["facts"] = {"confidence_weight": w.confidence}

# ------------------------------------------------------------------ 5 prototype
head("5. PROTOTYPE  resume readiness check")
jd = (SAMPLES / "jds/jd_01_mern_developer.txt").read_text(encoding="utf-8")
rows = []
for p in sorted((SAMPLES / "resumes").glob("*.txt")):
    r = check_resume_readiness(p.read_text(encoding="utf-8"), jd, AS_OF)
    rows.append((p.stem, r))
ready = sum(r.ready for _, r in rows)
say(f"{len(rows)} sample resumes: {ready} ready, {len(rows) - ready} blocked; most common notes: " +
    str(dict(sorted(__import__('collections').Counter(i.code for _, r in rows for i in r.issues).items(), key=lambda kv: -kv[1]))))
body = "React.js, Node.js, MongoDB, Express.js, REST API, Git, TypeScript, Docker"
tmpl = "Summary:\nMERN developer. " + "delivered " * 90 + "\n{h}\n" + body + "\nExperience:\n- Developer, Acme (Jan 2022 - Jan 2025)\n"
say("what a heading the system cannot read costs the candidate (same content, only the skills heading differs):")
costs = {}
for heading in ("Skills:", "Technical Skills", "Tools I use"):
    text = tmpl.format(h=heading)
    rep = check_resume_readiness(text, jd, AS_OF)
    score = ATSService().run({"resume_text": text, "job_description": jd})["ats_score"]
    costs[heading] = {"ats_score": score, "ready": rep.ready, "blockers": [i.code for i in rep.issues if i.severity == "blocker"]}
    say(f"   heading {heading!r:20} ATS score {score:5}   readiness check: {'ready' if rep.ready else 'BLOCKED ' + str(costs[heading]['blockers'])}")
assert costs["Skills:"]["ats_score"] == costs["Technical Skills"]["ats_score"] > costs["Tools I use"]["ats_score"] and not costs["Tools I use"]["ready"]
awk = ("Priya Rao\nTechnical Skills\nReact, Node.js, MongoDB\nWork Experience\n- Dev, Acme (Mar 2024 - Jan 2023)\nPROJECTS\nShop app\n")
a = check_resume_readiness(awk, jd, AS_OF)
say("an awkward resume (bad dates, an unread PROJECTS heading, very short):")
for i in a.issues:
    say(f"   {i.severity:8} {i.code:26} {i.message[:70]}")
say("design rules enforced by tests: no resume text, no ATS score or weights in the report; skill hints say 'add only if you genuinely have it'.")
report["prototype"] = {"sample_resumes": len(rows), "ready": ready, "heading_cost": costs}

Path(MD_PATH).write_text(render_markdown(b), encoding="utf-8")
Path(LOG_PATH).write_text("\n".join(_lines) + "\n", encoding="utf-8")
Path(JSON_PATH).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
say(f"\nwrote {LOG_PATH}, {JSON_PATH} and {MD_PATH}")
