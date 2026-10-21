"""
Day 51 demo -- aggregates seven candidates for a technical role across all
five rounds, shows what the weighting, fresher normalization, provisional
scoring, review rules and ranking actually do, proves continuity with Day
41 for a non-technical role, and runs one candidate end to end through the
adapters using REAL earlier result objects (including a real Day 50 machine
test report and the "0.0 with no evidence is MISSING, not zero" rule).
Writes:
  - logs/day51_cross_round_aggregation_run.log
  - data/results/day51_cross_round_aggregation_report.json

HONESTY NOTE: the per-round scores for candidates A-G are synthetic
stand-ins for what the five earlier engines would output; the aggregation,
weighting, normalization, flags, sensitivity and ranking that consume them
are 100% real. Candidate H's inputs are real result objects from the
earlier modules.
"""

from __future__ import annotations

import json
import logging
import os

from parsers import unified_scoring_engine as day41
from parsers.ats_scoring_engine import ATSScoreResult, ComponentResult
from parsers.cross_round_aggregation_engine import (
    RoundResult,
    compute_cross_round_score,
    compute_from_round_outputs,
    rank_candidates,
)
from parsers.hr_interview_question_bank import ExperienceLevel, RoleType
from parsers.hr_interview_scoring_engine import ConsistencyAssessment, HRInterviewScoreReport, WeightConfig
from parsers.integrity_detection_engine import IntegrityRiskTag
from parsers.machine_test_evaluation_engine import (
    CaseResult,
    CaseSpec,
    CodeSnapshot,
    ExecutionRun,
    MachineTestTask,
    MachineTestType,
    TaskAttempt,
    build_machine_test_report,
)
from parsers.screening_scoring_engine import ScreeningScoreResult
from parsers.technical_interview_question_bank import DifficultyTier
from parsers.technical_skill_scoring_engine import TechnicalEvaluationReport

LOG_PATH = "logs/day51_cross_round_aggregation_run.log"
REPORT_PATH = "data/results/day51_cross_round_aggregation_report.json"

os.makedirs("logs", exist_ok=True)
os.makedirs("data/results", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, mode="w"), logging.StreamHandler()],
)
log = logging.getLogger("day51_demo")

TECH, NON_TECH = RoleType.TECHNICAL, RoleType.NON_TECHNICAL
EXP, FRESH = ExperienceLevel.EXPERIENCED, ExperienceLevel.FRESHER


def rounds(ats, screening, hr, tech, machine):
    values = {"ats": ats, "screening": screening, "hr_interview": hr, "technical_interview": tech, "machine_test": machine}
    return [RoundResult(name, score) for name, score in values.items()]


def real_machine_test_report():
    """A real Day 50 report built from hand-written sandbox stand-ins (no sandbox exists yet)."""
    cases = [CaseSpec("v1"), CaseSpec("v2"), CaseSpec("h1", visible=False), CaseSpec("h2", visible=False)]
    task = MachineTestTask("coding-two-sum", MachineTestType.CODING, "Two sum", DifficultyTier.INTERMEDIATE, 1800.0, "python", cases,
                           reference_runtime_ms=120.0)
    code = 'def two_sum(numbers, target):\n    """Return indices adding to target."""\n    seen = {}\n    for i, v in enumerate(numbers):\n        if target - v in seen:\n            return seen[target - v], i\n        seen[v] = i\n'
    run_ok = ExecutionRun(400.0, [CaseResult(c.case_id, True, 125.0) for c in cases])
    attempt = TaskAttempt(task, [CodeSnapshot(100, code), CodeSnapshot(250, code), CodeSnapshot(390, code)],
                          [ExecutionRun(200.0, [CaseResult("v1", True, 120.0)] + [CaseResult(c, False) for c in ("v2", "h1", "h2")]), run_ok],
                          submitted_at=410.0)
    return build_machine_test_report([attempt], integrity_risk_tag=IntegrityRiskTag.MEDIUM)


def main() -> None:
    log.info("Starting Day 51 cross-round aggregation demo (five rounds, role-weighted, transparent).")
    candidates = {
        "cand-A": ("Experienced, strong everywhere", compute_cross_round_score(rounds(82, 78, 80, 85, 92), TECH, EXP, "cand-A")),
        "cand-B": ("Fresher: weak resume, strong skills", compute_cross_round_score(rounds(35, 80, 78, 88, 90), TECH, FRESH, "cand-B")),
        "cand-C": ("Experienced, machine test not taken yet", compute_cross_round_score(rounds(80, 80, 80, 80, None), TECH, EXP, "cand-C")),
        "cand-D": ("Strong except one round (technical 40)", compute_cross_round_score(rounds(92, 90, 88, 40, 85), TECH, EXP, "cand-D")),
        "cand-E": ("Borderline (all rounds about 71)", compute_cross_round_score(rounds(72, 70, 71, 71, 72), TECH, EXP, "cand-E")),
        "cand-F": ("Weak across the board", compute_cross_round_score(rounds(45, 40, 48, 38, 35), TECH, EXP, "cand-F")),
        "cand-G": ("Strong scores, Day 49 integrity tag HIGH",
                   compute_cross_round_score(rounds(85, 84, 86, 87, 88), TECH, EXP, "cand-G", integrity_risk_tag=IntegrityRiskTag.HIGH)),
    }
    results = {}
    for key, (title, score) in candidates.items():
        log.info("-" * 70)
        log.info("%s: %s -> fit %s -> %s | review=%s", key, title, score.hiring_fit_percentage, score.recommendation, score.human_review_required)
        for c in score.contributions:
            log.info("   %-20s %-14s score=%s base_w=%.3f adj_w=%.3f eff_w=%.3f points=%s", c.round_name, c.status.value,
                     c.score, c.base_weight, c.adjusted_weight, c.effective_weight, c.contribution)
        for f in score.flags:
            log.info("   FLAG %s: %s", f.code, f.message)
        results[key] = {"title": title, **score.to_dict()}

    a, b, c, d, e, f, g = (candidates[k][1] for k in ("cand-A", "cand-B", "cand-C", "cand-D", "cand-E", "cand-F", "cand-G"))

    print("\n" + b.explain())
    print("\n" + c.explain())
    print("\n" + d.to_summary_text())

    # Fresher normalization, shown by scoring the SAME rounds under both profiles.
    b_as_experienced = compute_cross_round_score(rounds(35, 80, 78, 88, 90), TECH, EXP, "cand-B")
    log.info("-" * 70)
    log.info("cand-B under the fresher profile: %s | under the experienced profile: %s", b.hiring_fit_percentage, b_as_experienced.hiring_fit_percentage)
    results["cand-B_profile_comparison"] = {"fresher_profile": b.hiring_fit_percentage, "experienced_profile": b_as_experienced.hiring_fit_percentage}

    # Day 41 continuity for a non-technical role.
    nt_new = compute_cross_round_score([RoundResult("ats", 62.0), RoundResult("screening", 75.0), RoundResult("hr_interview", 81.0)],
                                       NON_TECH, EXP, "nt-1")
    nt_old = day41.compute_unified_score(day41.RoundScores(62.0, 75.0, 81.0), RoleType.NON_TECHNICAL, "nt-1")
    log.info("Non-technical role: Day 51 fit %s vs Day 41 fit %s (rounds not used: %s)", nt_new.hiring_fit_percentage,
             nt_old.hiring_fit_percentage, nt_new.not_applicable_rounds)
    results["non_technical_vs_day41"] = {"day51": nt_new.hiring_fit_percentage, "day41": nt_old.hiring_fit_percentage}

    # Candidate H: REAL earlier-engine result objects through the adapters.
    ats_h = ATSScoreResult(78.0, "tech", [ComponentResult("skills", 78.0, 0.4, 0.4, 31.2, True)])
    hr_empty = HRInterviewScoreReport(0.0, WeightConfig(), [], 0.0, 0.0, 0.0, ConsistencyAssessment(0, 0, 0.0, 0.0, []), 0)
    screening_h = ScreeningScoreResult(74.0, [object(), object(), object()])
    technical_empty = TechnicalEvaluationReport([], 0.0, {})
    machine_h = real_machine_test_report()
    h = compute_from_round_outputs(ats=ats_h, screening=screening_h, hr=hr_empty, technical=technical_empty, machine_test=machine_h,
                                   role_type=TECH, experience_level=EXP, candidate_id="cand-H")
    log.info("-" * 70)
    log.info("cand-H (real result objects): fit %s -> %s | missing=%s | integrity=%s", h.hiring_fit_percentage, h.recommendation,
             h.missing_rounds, h.integrity_risk_tag)
    results["cand-H"] = {"title": "Real earlier-engine result objects via adapters", **h.to_dict()}

    ranking = rank_candidates([a, b, c, d, e, f, g, h])
    for r in ranking.ranked:
        log.info("RANK %d: %s fit=%s -> %s (review=%s, integrity=%s)", r.rank, r.candidate_id, r.hiring_fit_percentage,
                 r.recommendation, r.human_review_required, r.integrity_risk_tag)
    for n in ranking.not_comparable:
        log.info("NOT COMPARABLE: %s -- %s", n["candidate_id"], n["reason"])
    results["ranking"] = ranking.to_dict()

    # Sanity checks the demo itself verifies, not just claims:
    assert a.recommendation == "selected" and not a.human_review_required
    log.info("Sanity check passed: cand-A (strong everywhere) is SELECTED with no review needed.")

    assert b.hiring_fit_percentage > b_as_experienced.hiring_fit_percentage
    assert "ROUND_DISAGREEMENT" not in [x.code for x in b.flags] and not b.human_review_required
    assert "ROUND_DISAGREEMENT" in [x.code for x in b_as_experienced.flags]
    log.info("Sanity check passed: cand-B's thin resume is NOT flagged as round disagreement under the fresher profile (it is under the experienced one).")
    log.info("Sanity check passed: the fresher profile lifts cand-B from %s to %s because a thin resume no longer drags the score.",
             b_as_experienced.hiring_fit_percentage, b.hiring_fit_percentage)

    assert c.provisional and c.recommendation == "incomplete" and "cand-C" not in [r.candidate_id for r in ranking.ranked]
    log.info("Sanity check passed: cand-C is PROVISIONAL / incomplete and excluded from the ranking.")

    assert d.recommendation == "selected" and "ROUND_DISAGREEMENT" in [x.code for x in d.flags] and d.human_review_required
    log.info("Sanity check passed: cand-D's average (%s) looks selectable, but the technical-round disagreement forced human review.", d.hiring_fit_percentage)

    assert "BORDERLINE" in [x.code for x in e.flags] and e.human_review_required
    log.info("Sanity check passed: cand-E at %s is flagged borderline.", e.hiring_fit_percentage)

    assert f.recommendation == "rejected" and f.human_review_required
    log.info("Sanity check passed: cand-F's rejection recommendation still requires human review (nothing is rejected automatically).")

    g_clear = compute_cross_round_score(rounds(85, 84, 86, 87, 88), TECH, EXP, "cand-G")
    assert g.hiring_fit_percentage == g_clear.hiring_fit_percentage and g.human_review_required and not g_clear.human_review_required
    log.info("Sanity check passed: the HIGH integrity tag added review for cand-G without changing the score (%s).", g.hiring_fit_percentage)

    assert abs(nt_new.hiring_fit_percentage - nt_old.hiring_fit_percentage) <= 0.02 and nt_new.not_applicable_rounds == ["technical_interview", "machine_test"]
    log.info("Sanity check passed: a non-technical role reproduces Day 41's score (%s) and skips the technical rounds.", nt_new.hiring_fit_percentage)

    assert h.missing_rounds == ["hr_interview", "technical_interview"] and h.provisional
    log.info("Sanity check passed: Day 47/37-style results that report 0.0 with no answers were treated as MISSING, not as a real zero.")

    integrity_lines = [r for r in h.human_review_reasons if "integrity tag" in r.lower()]
    assert len(integrity_lines) == 1 and h.integrity_risk_tag == "medium"
    log.info("Sanity check passed: the real Day 50 report's Day 49 integrity tag produced exactly one consolidated review line.")

    for s in (a, b, c, d, e, f, g, h):
        assert abs(sum(x.effective_weight for x in s.contributions) - 1.0) < 1e-9 and s.automated_decision == "none"
    log.info("Sanity check passed: every score's effective weights sum to 1.0 and automated_decision is 'none'.")

    ordered = [r.candidate_id for r in ranking.ranked]
    assert ordered.index("cand-A") < ordered.index("cand-E") < ordered.index("cand-F")
    log.info("Sanity check passed: ranking order is sensible (%s).", " > ".join(ordered))

    with open(REPORT_PATH, "w", encoding="utf-8") as out:
        json.dump(results, out, indent=2)
    log.info("Report written to %s", REPORT_PATH)


if __name__ == "__main__":
    main()
