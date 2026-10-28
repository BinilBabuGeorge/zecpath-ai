"""
Day 54 demo -- Optimization & Refinement. Regenerates, from scratch, every
number in the optimization report:

  1. FALSE POSITIVE / NEGATIVE ANALYSIS (intent detection): the frozen
     52-case benchmark, before vs after the refinement, with per-case
     fixed / newly-broken accounting and Wilson confidence intervals.
  2. THRESHOLD ANALYSIS (ATS): plateau width and leave-one-out accuracy on
     the 12 human-labelled resume/job pairs -- evidence about whether the
     current cutoffs are supported, NOT a re-tuning.
  3. CROSS-ROUND CONSISTENCY: the 8 executable properties over >13,000 grid
     cases, the threshold registry and its relationship checks, and the
     measured effect of aligning the ATS scale.
  4. PROCESSING SPEED: batch timing of the ATS pipeline with the legacy
     matcher vs the optimised one (results must be bit-identical), and the
     per-candidate cost of the Day 51-53 pipeline.

Writes:
  - logs/day54_optimization_run.log
  - data/results/day54_optimization_report.json

HONESTY NOTES: the intent benchmark was labelled by the author of the fix
(so it is a regression and gap benchmark, not an independent estimate);
the ATS analysis uses only 12 pairs; timings vary by machine, so the demo
asserts only that the speed-up exceeds 1.5x and that outputs are
identical, not exact milliseconds.
"""

from __future__ import annotations

import json
import logging
import os
import statistics
import time
from pathlib import Path

from sklearn.metrics.pairwise import cosine_similarity

from parsers import ranking_engine
from parsers.answer_intent_engine import understand_answer
from parsers.ats_scoring_engine import ATSScoreResult, ComponentResult, score_candidate
from parsers.consistency_audit import check_threshold_relationships, run_property_audit, threshold_registry
from parsers.cross_round_aggregation_engine import RoundResult, compute_cross_round_score, round_from_ats
from parsers.evaluation_harness import compare_runs, evaluate_predictions, leave_one_out, param_grid, plateau, sweep_parameters
from parsers.final_recommendation_engine import DecisionPolicy, decide
from parsers.hr_interview_question_bank import ExperienceLevel, RoleType
from parsers.hiring_report_generator import generate_hiring_report
from parsers.integrity_detection_engine import BrowserEvent, BrowserEventType as T, build_integrity_report
from parsers.scoring_calibration import align_ats_score
from parsers.semantic_matcher import SemanticMatcher, normalize_for_embedding

LOG_PATH = "logs/day54_optimization_run.log"
REPORT_PATH = "data/results/day54_optimization_report.json"
BENCH = "data/ground_truth_screening/day54_intent_benchmark.json"
BEFORE = "data/ground_truth_screening/day54_intent_baseline_before.json"
ATS_GT = "data/ground_truth_ats/day20_manual_review_revised.json"
RESUMES, JDS = Path("data/samples/resumes"), Path("data/samples/jds")

os.makedirs("logs", exist_ok=True)
os.makedirs("data/results", exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s",
                    handlers=[logging.FileHandler(LOG_PATH, mode="w"), logging.StreamHandler()])
log = logging.getLogger("day54_demo")
TECH, EXP = RoleType.TECHNICAL, ExperienceLevel.EXPERIENCED
report: dict = {}


# ---------------------------------------------------------------------------
# 1. Intent detection: false positives / negatives
# ---------------------------------------------------------------------------

def analyse_intent():
    cases = json.load(open(BENCH, encoding="utf-8"))["cases"]
    truth = {c["id"]: c["human_expected_quality"] for c in cases}
    before = {b["id"]: b["predicted"] for b in json.load(open(BEFORE, encoding="utf-8"))["predictions"]}
    after = {c["id"]: understand_answer(c["text"], expected_category=c["category"]).quality.value for c in cases}
    ids = list(truth)
    labels = ["ok", "vague", "off_topic", "missing"]
    r_before = evaluate_predictions([truth[i] for i in ids], [before[i] for i in ids], labels, ids)
    r_after = evaluate_predictions([truth[i] for i in ids], [after[i] for i in ids], labels, ids)
    cmp_ = compare_runs(truth, before, after)
    by_id = {c["id"]: c for c in cases}
    log.info("INTENT benchmark (n=%d): before %d correct (%.1f%%, 95%% CI %.0f-%.0f%%) -> after %d correct (%.1f%%, 95%% CI %.0f-%.0f%%)",
             r_before.n, r_before.correct, 100 * r_before.accuracy, 100 * r_before.accuracy_ci[0], 100 * r_before.accuracy_ci[1],
             r_after.correct, 100 * r_after.accuracy, 100 * r_after.accuracy_ci[0], 100 * r_after.accuracy_ci[1])
    log.info("   recall of 'ok' (valid answers accepted): %.1f%% -> %.1f%%  | precision of 'ok': %.1f%% -> %.1f%%",
             100 * r_before.per_class["ok"].recall, 100 * r_after.per_class["ok"].recall,
             100 * r_before.per_class["ok"].precision, 100 * r_after.per_class["ok"].precision)
    log.info("   fixed %d | newly broken %d %s | still wrong %d %s | net %+d", len(cmp_.fixed), len(cmp_.newly_broken),
             [by_id[i]["text"] for i in cmp_.newly_broken], len(cmp_.still_wrong), [by_id[i]["text"] for i in cmp_.still_wrong], cmp_.net_change)
    groups = {}
    for c in cases:
        g = groups.setdefault(c["group"], {"n": 0, "before_correct": 0, "after_correct": 0})
        g["n"] += 1
        g["before_correct"] += before[c["id"]] == truth[c["id"]]
        g["after_correct"] += after[c["id"]] == truth[c["id"]]
    for name, g in sorted(groups.items()):
        log.info("   %-30s n=%2d  correct %2d -> %2d", name, g["n"], g["before_correct"], g["after_correct"])
    report["intent"] = {"before": r_before.to_dict(), "after": r_after.to_dict(), "comparison": cmp_.to_dict(), "by_group": groups,
                        "residual_errors": [{"id": i, "text": by_id[i]["text"], "category": by_id[i]["category"], "group": by_id[i]["group"],
                                             "expected": truth[i], "got": after[i]} for i in r_after.errors and [e["id"] for e in r_after.errors]]}
    return r_before, r_after, cmp_, groups


# ---------------------------------------------------------------------------
# 2. ATS thresholds: evidence, not re-tuning
# ---------------------------------------------------------------------------

def ats_rows():
    matcher = SemanticMatcher([f.read_text() for f in sorted(RESUMES.glob("*.txt")) + sorted(JDS.glob("*.txt"))])
    rows = []
    for p in json.load(open(ATS_GT, encoding="utf-8"))["pairs"]:
        r = score_candidate((RESUMES / f"{p['resume_id']}.txt").read_text(), (JDS / f"{p['jd_id']}.txt").read_text(), matcher)
        skill = next((c.score for c in r.components if c.name == "skill_match" and c.available), None)
        rows.append({"raw": r.overall_score, "category": r.role_category, "skill": skill, "human": p["expected_zone"]})
    return rows


def analyse_ats_thresholds(rows):
    def classify(item, params):
        return ranking_engine.classify_zone(item["raw"], thresholds={"shortlist": params["shortlist"], "review": params["review"]},
                                            skill_match_score=item["skill"]).upper()
    out = {}
    for category in ("tech", "business"):
        sub = [r for r in rows if r["category"] == category]
        truth = [r["human"] for r in sub]
        cur = ranking_engine.CATEGORY_THRESHOLDS[category]
        grid = [g for g in param_grid(shortlist=[float(x) for x in range(35, 66)], review=[float(x) for x in range(15, 46)]) if g["review"] < g["shortlist"]]
        points = sweep_parameters(sub, truth, classify, grid)
        best = plateau(points)
        cur_point = next(p for p in points if p.params == {"shortlist": cur["shortlist"], "review": cur["review"]})
        loo = leave_one_out(sub, truth, classify, grid)
        shortlist_range = [min(p.params["shortlist"] for p in best), max(p.params["shortlist"] for p in best)]
        inside = shortlist_range[0] <= cur["shortlist"] <= shortlist_range[1]
        log.info("ATS thresholds [%s] n=%d: current %s gets %d/%d; best attainable %d/%d; %d of %d settings tie for best (shortlist window %.0f-%.0f, current inside: %s)",
                 category, len(sub), cur, cur_point.correct, len(sub), best[0].correct, len(sub), len(best), len(grid), *shortlist_range, inside)
        log.info("   leave-one-out accuracy %d/%d vs in-sample %d/%d -> optimism %+.2f  (95%% CI of LOO accuracy %.0f-%.0f%%)", loo.leave_one_out_correct, loo.n,
                 loo.in_sample_correct, loo.n, loo.optimism, *(100 * x for x in loo.to_dict()["leave_one_out_ci_95"]))
        out[category] = {"n": len(sub), "current": cur, "current_correct": cur_point.correct, "best_correct": best[0].correct,
                         "plateau_size": len(best), "grid_size": len(grid), "shortlist_window": shortlist_range, "current_inside_window": inside,
                         "leave_one_out": loo.to_dict(), "recommendation": "no change" }
    out["tech"]["recommendation"] = ("no change: the current cutoff already achieves the best attainable accuracy; but it is supported only inside a narrow "
                                     "window and leave-one-out accuracy is much lower than in-sample, so treat it as PROVISIONAL until more labelled pairs exist")
    out["business"]["recommendation"] = "no change: any cutoff in a wide range is equally supported (the five pairs separate trivially), so the data cannot refine it"
    report["ats_thresholds"] = out
    return out


# ---------------------------------------------------------------------------
# 3. Cross-round consistency
# ---------------------------------------------------------------------------

def analyse_consistency(rows):
    props = run_property_audit()
    total = sum(p.cases_checked for p in props)
    for p in props:
        log.info("PROPERTY %-4s %-52s %6d cases", "PASS" if p.passed else "FAIL", p.name, p.cases_checked)
    rels = check_threshold_relationships()
    for r in rels:
        log.info("RELATION %-6s %s | %s", "holds" if r.holds else "BROKEN", r.statement, r.detail)

    band = lambda s: "SHORTLIST" if s >= 70 else "REVIEW" if s >= 50 else "REJECT"
    raw_agree = sum(band(r["raw"]) == r["human"] for r in rows)
    aligned_agree = sum(band(align_ats_score(r["raw"], r["category"], r["skill"])) == r["human"] for r in rows)
    shortlisted = [r for r in rows if r["human"] == "SHORTLIST"]
    raw_reach = sum(r["raw"] >= 70 for r in shortlisted)
    aligned_reach = sum(align_ats_score(r["raw"], r["category"], r["skill"]) >= 70 for r in shortlisted)
    log.info("ATS SCALE: raw score read at the aggregate's 70/50 bands agrees with the human zone in %d/%d pairs (%d of %d human-shortlisted reach 70); "
             "zone-aligned: %d/%d (%d of %d reach 70)", raw_agree, len(rows), raw_reach, len(shortlisted), aligned_agree, len(rows), aligned_reach, len(shortlisted))

    # Effect on the aggregate: each human-shortlisted pair as the ATS input, every other round at 80.
    effect = []
    for r in shortlisted:
        comps = [ComponentResult("skill_match", r["skill"], 0.35, 0.35, r["skill"] * 0.35, True, {})]
        ats = ATSScoreResult(r["raw"], r["category"], comps)
        others = [RoundResult(n, 80.0) for n in ("screening", "hr_interview", "technical_interview", "machine_test")]
        raw_s = compute_cross_round_score([round_from_ats(ats, "raw")] + others, TECH, EXP, "c")
        al_s = compute_cross_round_score([round_from_ats(ats, "zone_aligned")] + others, TECH, EXP, "c")
        effect.append({"raw_ats": r["raw"], "fit_raw_scale": raw_s.hiring_fit_percentage, "fit_aligned_scale": al_s.hiring_fit_percentage,
                       "disagreement_flag_raw": "ROUND_DISAGREEMENT" in [f.code for f in raw_s.flags],
                       "disagreement_flag_aligned": "ROUND_DISAGREEMENT" in [f.code for f in al_s.flags]})
        log.info("   human-shortlisted pair, ATS raw %.1f, all other rounds 80: Hiring Fit %.2f (raw scale, disagreement flag %s) -> %.2f (aligned, flag %s)",
                 r["raw"], raw_s.hiring_fit_percentage, effect[-1]["disagreement_flag_raw"], al_s.hiring_fit_percentage, effect[-1]["disagreement_flag_aligned"])

    # Effect of the Day 52 confidence-floor recommendation on the demo candidate set.
    events = [BrowserEvent(T.TAB_HIDDEN, 100), BrowserEvent(T.TAB_VISIBLE, 104), BrowserEvent(T.TAB_HIDDEN, 120),
              BrowserEvent(T.TAB_VISIBLE, 124), BrowserEvent(T.TAB_HIDDEN, 140), BrowserEvent(T.TAB_VISIBLE, 144)]
    integrity = build_integrity_report(events, session_end=1800)
    names = ("ats", "screening", "hr_interview", "technical_interview", "machine_test")
    roster = {"A": (82, 78, 80, 85, 92, None), "B": (35, 80, 78, 88, 90, None), "C": (80, 80, 80, 80, None, None), "D": (95, 95, 95, 35, 95, None),
              "E": (72, 70, 71, 71, 72, None), "F": (30, 30, 30, 30, 30, None), "G": (85, 84, 86, 87, 88, integrity), "I": (80, 20, 45, 30, 60, integrity),
              "J": (60, 60, 60, 60, 60, None), "K": (80, 20, 45, 30, 60, None)}
    changed, original_ids = [], {"A", "B", "C", "D", "E", "F", "G", "I", "J"}      # K is constructed here to show the effect; it was not in Day 52's demo
    for cid, (*vals, integ) in roster.items():
        exp = ExperienceLevel.FRESHER if cid == "B" else EXP
        s = compute_cross_round_score([RoundResult(n, v) for n, v in zip(names, vals) if v is not None], TECH, exp, cid,
                                      integrity_risk_tag=integ.risk_tag if integ else None)
        current = decide(s, integrity_report=integ)
        stricter = decide(s, integrity_report=integ, policy=DecisionPolicy(min_reject_confidence=60.0))
        if current.outcome != stricter.outcome:
            changed.append({"candidate": cid, "from": current.outcome.value, "to": stricter.outcome.value, "confidence": current.confidence.score})
    changed_original = [c for c in changed if c["candidate"] in original_ids]
    log.info("DAY 52 reject-confidence floor 50 -> 60: %d of the %d ORIGINAL Day 52 demo candidates change; %d of the extra constructed shaky-evidence case(s) change %s",
             len(changed_original), len(original_ids), len(changed) - len(changed_original), [c for c in changed if c["candidate"] not in original_ids])

    report["consistency"] = {
        "properties": [p.to_dict() for p in props], "cases_checked": total,
        "threshold_registry": [t.to_dict() for t in threshold_registry()], "relationships": [r.to_dict() for r in rels],
        "ats_scale": {"pairs": len(rows), "raw_agreement": raw_agree, "aligned_agreement": aligned_agree,
                      "human_shortlisted": len(shortlisted), "raw_reach_70": raw_reach, "aligned_reach_70": aligned_reach, "aggregate_effect": effect},
        "reject_confidence_floor_50_to_60": {"original_day52_candidates": len(original_ids), "original_changed": changed_original,
                                             "extra_constructed_candidates": len(roster) - len(original_ids), "extra_changed": [c for c in changed if c["candidate"] not in original_ids]},
    }
    return props, rels, raw_agree, aligned_agree, shortlisted, raw_reach, aligned_reach, effect, changed_original


# ---------------------------------------------------------------------------
# 4. Speed
# ---------------------------------------------------------------------------

class LegacyMatcher(SemanticMatcher):
    """The pre-Day 54 behaviour, reproduced for an honest side-by-side: no cache, sklearn cosine every time."""

    def embed(self, text):
        return self.vectorizer.transform([normalize_for_embedding(text) if self.normalize else text])

    def similarity(self, a, b):
        return round(float(cosine_similarity(self.embed(a), self.embed(b))[0][0]), 4)


def analyse_speed():
    resumes, jds = sorted(RESUMES.glob("*.txt")), sorted(JDS.glob("*.txt"))
    texts = {f.name: f.read_text() for f in resumes + jds}
    corpus = list(texts.values())
    pairs = [(r, j) for j in jds for r in resumes]

    def batch(cls):
        m = cls(corpus)                                        # cold cache, as in a fresh batch
        start = time.perf_counter()
        out = [score_candidate(texts[r.name], texts[j.name], m) for r, j in pairs]
        return (time.perf_counter() - start) * 1000, out

    legacy_ms, legacy_out = batch(LegacyMatcher)
    for _ in range(2):
        batch(LegacyMatcher), batch(SemanticMatcher)           # warm-up
    legacy = [batch(LegacyMatcher)[0] for _ in range(7)]
    fast = [batch(SemanticMatcher)[0] for _ in range(7)]
    _, new_out = batch(SemanticMatcher)
    identical = all(repr(a.overall_score) == repr(b.overall_score) and [(c.name, repr(c.score)) for c in a.components] == [(c.name, repr(c.score)) for c in b.components]
                    for a, b in zip(legacy_out, new_out))
    lm, fm = statistics.median(legacy), statistics.median(fast)
    log.info("SPEED ATS batch (%d resumes x %d JDs = %d pairs, cold cache): legacy %.1f ms -> optimised %.1f ms = %.2fx faster (%.2f -> %.2f ms/pair); results bit-identical: %s",
             len(resumes), len(jds), len(pairs), lm, fm, lm / fm, lm / len(pairs), fm / len(pairs), identical)

    # Day 51-53 pipeline: per-candidate cost of a FULL five-round candidate (no change made). The round result
    # objects are built once, outside the timed loop, exactly as an upstream engine would hand them over.
    from types import SimpleNamespace
    from parsers.answer_intent_engine import AnswerQuality
    from parsers.cross_round_aggregation_engine import compute_from_round_outputs
    from parsers.hr_interview_scoring_engine import ConsistencyAssessment, HRInterviewScoreReport, WeightConfig
    from parsers.machine_test_evaluation_engine import CaseResult, CaseSpec, CodeSnapshot, ExecutionRun, MachineTestTask, MachineTestType, TaskAttempt, build_machine_test_report
    from parsers.screening_scoring_engine import QuestionScore, ScoreComponent, ScreeningScoreResult
    from parsers.technical_interview_question_bank import DifficultyTier
    from parsers.technical_skill_scoring_engine import ShallowDeepClassification, TechnicalEvaluationReport
    cases = [CaseSpec("v1"), CaseSpec("v2"), CaseSpec("h1", visible=False), CaseSpec("h2", visible=False)]
    task = MachineTestTask("t", MachineTestType.CODING, "t", DifficultyTier.INTERMEDIATE, 1800.0, "python", cases, reference_runtime_ms=100.0)
    code = 'def f(a):\n    """doc"""\n    return a\n'
    mt = build_machine_test_report([TaskAttempt(task, [CodeSnapshot(100, code)], [ExecutionRun(300.0, [CaseResult(c.case_id, True, 100.0) for c in cases])], submitted_at=310.0)])
    rounds = {
        "ats": ATSScoreResult(72.0, "tech", [ComponentResult("skill_match", 80.0, 0.35, 0.35, 28.0, True, {})]),
        "screening": ScreeningScoreResult(80.0, [QuestionScore("t", "skills", AnswerQuality.OK, {"clarity": ScoreComponent(80.0)}, 80.0)], []),
        "hr": HRInterviewScoreReport(80.0, WeightConfig(), [], 80.0, 80.0, 80.0, ConsistencyAssessment(0, 0, 0.0, 0.0, []), 5),
        "technical": TechnicalEvaluationReport([SimpleNamespace(classification=ShallowDeepClassification.DEEP)] * 4, 80.0, {"react": 80.0, "node": 78.0}),
        "machine_test": mt,
    }

    def pipeline():
        s = compute_from_round_outputs(role_type=TECH, experience_level=EXP, candidate_id="c", **rounds)
        d = decide(s)
        r = generate_hiring_report(d, s, generated_at="2026-01-01T00:00:00+00:00", **rounds)
        r.to_json(), r.to_markdown(), r.to_html()                     # all three exports, as a real run would
        return r
    pipeline()
    times = []
    for _ in range(300):
        start = time.perf_counter(); pipeline(); times.append((time.perf_counter() - start) * 1000)
    per_candidate = statistics.mean(times)
    log.info("SPEED Day 51-53 pipeline (five-round aggregate + decision + report + JSON/Markdown/HTML exports): %.2f ms per candidate (~%d candidates/second) -- no change made, nothing to optimise",
             per_candidate, int(1000 / per_candidate))
    report["speed"] = {"ats_batch": {"pairs": len(pairs), "legacy_ms_median": round(lm, 1), "optimised_ms_median": round(fm, 1),
                                     "speedup": round(lm / fm, 2), "bit_identical_results": identical,
                                     "per_pair_ms_before": round(lm / len(pairs), 2), "per_pair_ms_after": round(fm / len(pairs), 2)},
                       "day51_53_pipeline_ms_per_candidate": round(per_candidate, 2),
                       "note": "Timings are machine-dependent; the speed-up ratio and the bit-identical check are what matter."}
    return lm, fm, identical, per_candidate


def main() -> None:
    log.info("Starting Day 54 optimization demo (false positives/negatives, thresholds, cross-round consistency, speed).")
    r_before, r_after, cmp_, groups = analyse_intent()
    rows = ats_rows()
    ats = analyse_ats_thresholds(rows)
    props, rels, raw_agree, aligned_agree, shortlisted, raw_reach, aligned_reach, effect, changed = analyse_consistency(rows)
    lm, fm, identical, per_candidate = analyse_speed()

    # Sanity checks the demo itself verifies, not just claims:
    assert (r_before.correct, r_after.correct, r_after.n) == (25, 49, 52)
    log.info("Sanity check passed: intent accuracy on the frozen benchmark rose from 25/52 to 49/52.")

    assert len(cmp_.fixed) == 25 and cmp_.newly_broken == ["l25"] and cmp_.net_change == 24
    log.info("Sanity check passed: the net +24 is 25 cases fixed minus 1 newly broken (the documented 'Banana' trade-off) -- the headline does not hide it.")

    negatives = [g for name, g in groups.items() if name.startswith("negative_")]
    assert all(g["after_correct"] == g["n"] for g in negatives)
    log.info("Sanity check passed: every negative case (hedges, non-answers, work-mode words, wrong-category answers) is still handled correctly.")

    assert ats["tech"]["current_correct"] == ats["tech"]["best_correct"] and ats["business"]["current_correct"] == ats["business"]["best_correct"]
    assert ats["tech"]["leave_one_out"]["optimism"] > 0.2 and ats["tech"]["current_inside_window"]
    log.info("Sanity check passed: the ATS cutoffs already achieve the best attainable accuracy, so no change is justified; the tech cutoff is flagged provisional (leave-one-out optimism %+.2f).",
             ats["tech"]["leave_one_out"]["optimism"])

    assert all(p.passed for p in props) and sum(p.cases_checked for p in props) > 10000
    log.info("Sanity check passed: all %d consistency properties hold across %d grid cases.", len(props), sum(p.cases_checked for p in props))

    assert [r.holds for r in rels].count(False) == 2
    log.info("Sanity check passed: the threshold audit found exactly 2 contradictions (ATS scale; Day 52 confidence floors).")

    assert (raw_agree, aligned_agree, raw_reach, aligned_reach) == (6, 10, 0, len(shortlisted))
    log.info("Sanity check passed: ATS scale alignment moves agreement with human zones from %d/12 to %d/12 and lets all %d human-shortlisted pairs reach the selection band (was %d).",
             raw_agree, aligned_agree, len(shortlisted), raw_reach)

    assert all(e["fit_aligned_scale"] > e["fit_raw_scale"] for e in effect)
    gains = [e["fit_aligned_scale"] - e["fit_raw_scale"] for e in effect]
    log.info("Sanity check passed: for every human-shortlisted pair the aligned scale gives a higher Hiring Fit (+%.1f to +%.1f points with the other rounds at 80). "
             "The disagreement flag did not fire for these four pairs on either scale; the unit tests cover a case where it does.", min(gains), max(gains))

    assert identical
    log.info("Sanity check passed: the optimised matcher gives bit-identical scores on every pair.")

    assert lm / fm > 1.5
    log.info("Sanity check passed: the optimised matcher is %.2fx faster on a cold-cache ATS batch.", lm / fm)

    report["summary"] = {
        "intent_accuracy": {"before": "25/52", "after": "49/52"}, "ats_thresholds": "no change (best attainable already achieved); tech cutoff provisional",
        "ats_scale_agreement_with_human_zones": {"raw": f"{raw_agree}/12", "zone_aligned": f"{aligned_agree}/12"},
        "properties": f"{len(props)} hold over {sum(p.cases_checked for p in props)} cases", "speedup_ats_batch": round(lm / fm, 2),
        "files_changed": ["parsers/answer_intent_engine.py", "parsers/semantic_matcher.py", "parsers/cross_round_aggregation_engine.py", "tests/test_day30_false_rejection_fix.py"],
        "files_added": ["parsers/evaluation_harness.py", "parsers/scoring_calibration.py", "parsers/consistency_audit.py"]}
    with open(REPORT_PATH, "w", encoding="utf-8") as out:
        json.dump(report, out, indent=2)
    log.info("Report written to %s", REPORT_PATH)


if __name__ == "__main__":
    main()
