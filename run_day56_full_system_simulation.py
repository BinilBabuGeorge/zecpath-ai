"""
Day 56 demo -- Full System Simulation. Regenerates every number quoted in
docs/day56_full_system_simulation.md:

  1. UPLOAD         real PDF/DOCX extraction: fidelity against plain text, and what bad files do.
  2. ATS vs HUMAN   12 human-labelled resume/JD pairs, plus how much the calendar date alone changes the answer.
  3. JOURNEYS       8 scripted candidates through every real stage to a recruiter report.
  4. INCONSISTENCIES  what the stages disagree about.
  5. AI vs HUMAN    what can and cannot be compared today; blank human rating sheet written.
  6. PROBES         screening read in isolation; technical scoring under four phrasings.
  7. PERFORMANCE    per-stage cost of the scoring layer (5 repeats of all 8 journeys).

Writes logs/day56_simulation_run.log, data/results/day56_simulation_report.json, data/results/day56_reports/*.md
and data/human_review/day56_human_review_worksheet.csv.

HONESTY NOTES: the 8 candidates are SCRIPTED; their expected outcomes ('acceptable') were written before the run and are the
author's design intent, not human judgement. Timings are the scoring layer only (no speech, video or network). The clock is
frozen at AS_OF so results do not drift with the day this is run.
"""

from __future__ import annotations

import json
import logging
import tempfile
import time
from collections import Counter
from datetime import date
from pathlib import Path

logging.disable(logging.CRITICAL)

from docx import Document

from parsers.ats_scoring_engine import score_candidate
from parsers.pipeline_simulation import (GATE_MIN, STAGES, ats_vs_human, ats_zone_drift, build_matcher, frozen_today, human_agreement,
                                         intent_check, load_ats_human_labels, load_human_ratings, load_scenarios, run_journey,
                                         screening_isolation_probe, stage_timing, tier_drift, technical_phrasing_probe, try_upload, upload_resume,
                                         write_human_worksheet)

AS_OF = date(2026, 10, 30)
EARLIER = date(2025, 1, 1)
SAMPLES = Path("data/samples")
LOG_PATH, REPORT_PATH = "logs/day56_simulation_run.log", "data/results/day56_simulation_report.json"
WORKSHEET, RATINGS = "data/human_review/day56_human_review_worksheet.csv", "data/human_review/day56_human_ratings.csv"
Path("logs").mkdir(exist_ok=True); Path("data/results/day56_reports").mkdir(parents=True, exist_ok=True)
_lines, report = [], {}


def say(s=""):
    print(s); _lines.append(s)


def head(s):
    say(); say("=" * 78); say(s); say("=" * 78)


def make_docx(text: str, path: Path) -> None:
    d = Document()
    for ln in text.splitlines():
        d.add_paragraph(ln)
    d.save(str(path))


def make_pdf(text: str, path: Path) -> bool:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except ImportError:
        return False
    c = canvas.Canvas(str(path), pagesize=A4); y = 800
    for ln in text.splitlines():
        if y < 50:
            c.showPage(); y = 800
        c.drawString(40, y, ln[:110]); y -= 13
    c.save()
    return True


tmp = Path(tempfile.mkdtemp(prefix="day56_"))
say(f"clock frozen at {AS_OF} for every result below (the experience parser reads 'Present' from today's date)")
t0 = time.perf_counter(); matcher = build_matcher(SAMPLES); matcher_build_ms = (time.perf_counter() - t0) * 1000
say(f"semantic matcher built from {len(list((SAMPLES / 'resumes').glob('*.txt')) + list((SAMPLES / 'jds').glob('*.txt')))} sample documents in {matcher_build_ms:.0f} ms")

# ------------------------------------------------------------------ 1 upload
head("1. UPLOAD  real extraction (PDF/DOCX only) -> ATS, vs the plain-text score")
labels = load_ats_human_labels()
fid = []
pdf_ok = True
with frozen_today(AS_OF):
    for i, lab in enumerate(labels):
        txt = (SAMPLES / "resumes" / f"{lab['resume']}.txt").read_text(encoding="utf-8")
        jd = (SAMPLES / "jds" / f"{lab['jd']}.txt").read_text(encoding="utf-8")
        base = score_candidate(txt, jd, matcher).overall_score
        row = {"pair": lab["resume"][:24], "txt": round(base, 1)}
        dp = tmp / f"r{i}.docx"; make_docx(txt, dp)
        row["docx"] = round(score_candidate(upload_resume(dp)[0], jd, matcher).overall_score, 1)
        pp = tmp / f"r{i}.pdf"
        if make_pdf(txt, pp):
            row["pdf"] = round(score_candidate(upload_resume(pp)[0], jd, matcher).overall_score, 1)
        else:
            pdf_ok = False
        fid.append(row)
d_docx = max(abs(r["txt"] - r["docx"]) for r in fid)
d_pdf = max((abs(r["txt"] - r["pdf"]) for r in fid if "pdf" in r), default=None)
say(f"{len(fid)} resumes uploaded as DOCX{' and PDF' if pdf_ok else ''}: max score difference vs plain text  DOCX {d_docx:.1f}" + (f"  PDF {d_pdf:.1f}" if d_pdf is not None else "  (PDF skipped: reportlab not installed)"))
say("caveat: the uploads are clean synthetic files built from the same text; real two-column, table-heavy or scanned resumes are NOT tested here")
bad = []
for name, content in [("resume.txt", b"plain text"), ("resume.doc", b"\xd0\xcf\x11\xe0 legacy word"), ("corrupt.pdf", b"not a pdf"), ("zero_bytes.docx", b"")]:
    p = tmp / name; p.write_bytes(content); bad.append(try_upload(p))
Document().save(str(tmp / "blank.docx")); bad.append(try_upload(tmp / "blank.docx"))
for b in bad:
    say(f"  {b['file']:16} -> {b['result']:11} {b.get('error', '')}")
report["upload"] = {"docx_max_diff": d_docx, "pdf_max_diff": d_pdf, "bad_files": bad}

# ------------------------------------------------------------------ 2 ATS vs human
head("2. ATS vs HUMAN  12 human-labelled pairs (labels from the Day 20 review file)")
rows = ats_vs_human(matcher, AS_OF, SAMPLES)
agree = sum(r["agree"] for r in rows)
for r in rows:
    say(f"  {'OK ' if r['agree'] else 'DIFF'} {r['resume'][:30]:30} score {r['score']:5.1f}  AI {r['ai_zone']:9} human {r['human_zone']}")
mis = [r for r in rows if not r["agree"]]
lenient = [r for r in mis if {"reject": 0, "review": 1, "shortlist": 2}[r["ai_zone"]] > {"reject": 0, "review": 1, "shortlist": 2}[r["human_zone"].lower()]]
say(f"zone agreement {agree}/{len(rows)}; the {len(mis)} disagreements: AI more lenient than the human in {len(lenient)}, stricter in {len(mis) - len(lenient)}")
say("caveat: the ATS cutoffs were calibrated on these same pairs (Days 17-20), so this agreement is optimistic")
drift = ats_zone_drift(matcher, EARLIER, AS_OF, samples_dir=SAMPLES)
say(f"calendar drift: the same 12 pairs scored as of {EARLIER} vs {AS_OF}: {drift['zone_changes']} zone change(s), largest score shift {drift['max_score_shift']}")
for c in drift["changes"]:
    say(f"    {c[0][:28]}: {c[1]} -> {c[2]}")
tech_ids = sorted({sc.resume for sc in load_scenarios("data/simulation/day56_scenarios.json") if sc.role_type == "technical"})
td = tier_drift({r: (SAMPLES / "resumes" / f"{r}.txt").read_text(encoding="utf-8") for r in tech_ids}, EARLIER, AS_OF)
for r in td:
    say(f"  tier drift {r['resume'][:30]:30} {r['years_a']:>4}y -> {r['years_b']:>4}y   tier {r['tier_a']:12} -> {r['tier_b']:12} {'CHANGED' if r['changed'] else ''}")
say(f"technical question tier changes with the calendar alone for {sum(r['changed'] for r in td)} of {len(td)} technical-role resumes (ATS zones: {drift['zone_changes']} of {drift['pairs']})")
report["tier_drift"] = td
report["ats_vs_human"] = {"agree": agree, "pairs": len(rows), "lenient": len(lenient), "rows": rows, "drift": drift}

# ------------------------------------------------------------------ 3 journeys
head("3. JOURNEYS  8 scripted candidates through the real engines")
scs = load_scenarios("data/simulation/day56_scenarios.json")
journeys, files = [], {}
for sc in scs:
    txt = (SAMPLES / "resumes" / f"{sc.resume}.txt").read_text(encoding="utf-8")
    f = tmp / f"{sc.id}.docx"; make_docx(txt, f); files[sc.id] = (f, (SAMPLES / "jds" / f"{sc.jd}.txt").read_text(encoding="utf-8"))
    j = run_journey(sc, matcher, f, files[sc.id][1], AS_OF, generated_at=str(AS_OF))
    journeys.append(j)
    assert not j.errors and all(s.status != "error" for s in j.stages.values()), f"{sc.id}: {[s.note for s in j.stages.values() if s.status == 'error']}"
    if j.report is not None:
        Path(f"data/results/day56_reports/{sc.id}.md").write_text(j.report.to_markdown(), encoding="utf-8")
say(f"{'id':3} {'ATS':>9} {'scr':>5} {'HR':>5} {'tech':>5} {'tier':9} {'turns':>5} {'fit':>5}  outcome(raw / aligned)        funnel")
for j in journeys:
    s = {k: v.summary for k, v in j.stages.items()}
    say(f"{j.scenario.id:3} {j.ats.overall_score:5.1f} {j.zone[:4]:4} {s['screening']['score']:5.1f} {s['hr_interview']['score']:5.1f} "
        f"{s.get('technical_interview', {}).get('score', float('nan')):5.1f} {str(j.tier_used or '-'):9} {s['screening']['turns']:5} {j.score_raw.hiring_fit_percentage:5.1f}  "
        f"{j.outcome:11} / {j.outcome_aligned:11} {j.funnel_stage}")
done = sum(1 for j in journeys if j.report is not None)
say(f"{done}/{len(journeys)} journeys ran upload -> report with every stage on real objects and no hand-built input")
out_counts = Counter(j.outcome for j in journeys)
pend = [j.scenario.id for j in journeys if j.score_raw.provisional]
say(f"outcomes (raw ATS scale): {dict(out_counts)};  {len(pend)} technical-role journeys are PENDING_EVIDENCE waiting on machine_test: {pend}")
w = {c.round_name: c.effective_weight for c in journeys[6].score_raw.contributions}
say(f"non-technical weights actually applied: { {k: round(v, 2) for k, v in w.items()} }")
report["journeys"] = [{"id": j.scenario.id, "zone": j.zone, "ats": round(j.ats.overall_score, 1), "screening": round(j.screening.total_score, 1), "hr": round(j.hr.overall_hr_score, 1),
                       "technical": round(j.technical.overall_score, 1) if j.technical else None, "tier": j.tier_used, "turns": j.stages["screening"].summary["turns"],
                       "fit": round(j.score_raw.hiring_fit_percentage, 1), "fit_aligned": round(j.score_aligned.hiring_fit_percentage, 1), "outcome": j.outcome,
                       "outcome_aligned": j.outcome_aligned, "funnel": j.funnel_stage, "provisional": j.score_raw.provisional, "years_parsed": j.resume_years_parsed,
                       "years_stated": j.resume_years_stated, "years_claimed": j.claimed_years} for j in journeys]

# ------------------------------------------------------------------ 4 inconsistencies
head("4. INCONSISTENCIES  where the stages disagree about the same person")
allinc = []
for j in journeys:
    for i in j.inconsistencies:
        allinc.append((j.scenario.id, i))
by_code = Counter(i.code for _, i in allinc)
for cid, i in allinc:
    if i.severity != "info":
        say(f"  {i.severity.upper():8} {cid} {i.code}: {i.detail}")
say(f"counts by code: {dict(by_code)}")
sev = Counter(i.severity for _, i in allinc)
say(f"by severity: {dict(sev)}")
report["inconsistencies"] = {"by_code": dict(by_code), "by_severity": dict(sev), "items": [{"candidate": c, "code": i.code, "severity": i.severity, "detail": i.detail} for c, i in allinc]}

# ------------------------------------------------------------------ 5 AI vs human
head("5. AI vs HUMAN JUDGEMENT  what exists, what does not")
say(f"ATS vs real human labels: {agree}/{len(rows)} zones agree (optimistic, see section 2)")
ok = [j.scenario.id for j in journeys if intent_check(j)]
miss = [j.scenario.id for j in journeys if not intent_check(j)]
say(f"final outcome vs the AUTHOR's pre-run expectation (design intent, not human judgement): {len(ok)}/{len(journeys)} within the acceptable set")
for j in journeys:
    if not intent_check(j):
        say(f"   miss {j.scenario.id}: expected {j.scenario.acceptable}, got {j.outcome} ({j.decision_raw.hold_kind.value if j.decision_raw.hold_kind else 'n/a'}) -- {j.scenario.rationale}")
n = write_human_worksheet(journeys, WORKSHEET)
ha = human_agreement({j.scenario.id: j.outcome for j in journeys}, load_human_ratings(RATINGS))
say(f"human rating sheet written for {n} candidates: {WORKSHEET}")
say(f"human ratings found in {RATINGS}: {ha['ratings']}  -> agreement: {ha['agreement'] if ha['agreement'] is not None else 'not measurable yet (no human ratings)'}")
report["ai_vs_human"] = {"ats_agree": agree, "ats_pairs": len(rows), "intent_ok": ok, "intent_miss": miss, "human": ha}

# ------------------------------------------------------------------ 6 probes
head("6. PROBES  isolating two mechanisms the journeys exposed")
sp = screening_isolation_probe(scs)
flagged = [(r["candidate"], r["category"]) for r in sp if r["quality"] in ("off_topic", "missing")]
say(f"screening answers read ALONE against their own question: {len(flagged)} of {len(sp)} flagged off-topic/missing: {flagged}")
reasks = {j.scenario.id: j.stages["screening"].summary["reasks"] for j in journeys}
say(f"extra turns forced by re-asks in the live conversation: {reasks}")
tp = technical_phrasing_probe()
say("technical scoring, ONE answer (Node event loop) varied, all else equal:")
for k, v in tp.items():
    say(f"   {k:20} {v:5.1f}")
report["probes"] = {"screening_flagged": flagged, "screening_total": len(sp), "reasks": reasks, "technical_phrasing": tp}

# ------------------------------------------------------------------ 7 performance
head("7. PERFORMANCE  scoring layer only, 5 repeats x 8 journeys (this machine)")
reps = []
for _ in range(5):
    for sc in scs:
        f, jd = files[sc.id]
        reps.append(run_journey(sc, matcher, f, jd, AS_OF, generated_at=str(AS_OF)))
tm = stage_timing(reps)
for st in STAGES:
    if st in tm:
        say(f"  {st:20} median {tm[st]['median_ms']:8.2f} ms   p95 {tm[st]['p95_ms']:8.2f} ms   max {tm[st]['max_ms']:8.2f} ms   (n={tm[st]['n']})")
tot = sorted(j.total_ms for j in reps)
med = tot[len(tot) // 2]
say(f"  whole journey: median {med:.1f} ms, slowest {tot[-1]:.1f} ms; one process scores about {60000 / med:.0f} candidates/min; matcher build (once) {matcher_build_ms:.0f} ms")
slow = max(tm, key=lambda k: tm[k]["median_ms"])
say(f"  slowest stage by median: {slow}")
report["performance"] = {"stages": tm, "journey_median_ms": round(med, 1), "journey_max_ms": round(tot[-1], 1), "matcher_build_ms": round(matcher_build_ms), "slowest_stage": slow}

Path(LOG_PATH).write_text("\n".join(_lines) + "\n", encoding="utf-8")
Path(REPORT_PATH).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
say(f"\nwrote {LOG_PATH}, {REPORT_PATH}, data/results/day56_reports/*.md and {WORKSHEET}")
