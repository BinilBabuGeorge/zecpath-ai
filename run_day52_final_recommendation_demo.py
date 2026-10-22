"""
Day 52 demo -- runs ten candidates through the final recommendation
engine to show the rule + score hybrid logic, the confidence score, the
risk factors (integrity, behavior), the explainable output and the
human-confirmation flow. Writes:
  - logs/day52_final_recommendation_run.log
  - data/results/day52_final_recommendation_report.json

HONESTY NOTE: the per-round scores are synthetic stand-ins for what the
five earlier engines would output, and the behavior metrics are
hand-set. The integrity input is a REAL Day 49 report built from browser
events; every decision, rule, confidence value and notice is produced by
the real engine.
"""

from __future__ import annotations

import json
import logging
import os

from parsers.behavioral_signal_engine import (
    BehavioralInsightReport,
    DistractionSpikeResult,
    FocusConsistencyResult,
    VerbalHesitationSummary,
)
from parsers.cross_round_aggregation_engine import RoundResult, compute_cross_round_score
from parsers.final_recommendation_engine import (
    NOTICES,
    DecisionOutcome,
    DecisionPolicy,
    HoldKind,
    HumanReview,
    decide,
    finalize_automatically,
    finalize_with_human,
)
from parsers.hr_interview_question_bank import ExperienceLevel, RoleType
from parsers.integrity_detection_engine import BrowserEvent, BrowserEventType as T, build_integrity_report

LOG_PATH = "logs/day52_final_recommendation_run.log"
REPORT_PATH = "data/results/day52_final_recommendation_report.json"

os.makedirs("logs", exist_ok=True)
os.makedirs("data/results", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, mode="w"), logging.StreamHandler()],
)
log = logging.getLogger("day52_demo")

TECH = RoleType.TECHNICAL
EXP, FRESH = ExperienceLevel.EXPERIENCED, ExperienceLevel.FRESHER
SELECTED, HOLD, REJECTED = DecisionOutcome.SELECTED, DecisionOutcome.HOLD_REVIEW, DecisionOutcome.REJECTED


def score(cid, ats, screening, hr, tech, machine, exp=EXP, drop=()):
    values = {"ats": ats, "screening": screening, "hr_interview": hr, "technical_interview": tech, "machine_test": machine}
    rounds = [RoundResult(n, v) for n, v in values.items() if n not in drop]
    return compute_cross_round_score(rounds, TECH, exp, cid)


def behavior(spikes=0, focus=90.0, hesitation=2.0):
    return BehavioralInsightReport(
        FocusConsistencyResult([30.0, 31.0], 30.5, 0.5, 0.02, focus),
        DistractionSpikeResult([f"q{i + 1}" for i in range(spikes)], spikes, 30.0, 100.0 - 30 * spikes),
        VerbalHesitationSummary({}, hesitation),
    )


def burst_integrity_report():
    events = [BrowserEvent(T.TAB_HIDDEN, 100), BrowserEvent(T.TAB_VISIBLE, 104), BrowserEvent(T.TAB_HIDDEN, 120),
              BrowserEvent(T.TAB_VISIBLE, 124), BrowserEvent(T.TAB_HIDDEN, 140), BrowserEvent(T.TAB_VISIBLE, 144)]
    return build_integrity_report(events, session_end=1800)


def main() -> None:
    log.info("Starting Day 52 final recommendation demo (decision support: rule + score hybrid, confidence, explainable).")
    integrity = burst_integrity_report()
    log.info("Real Day 49 integrity report used for cand-G and cand-I: tag %s, flags %s", integrity.risk_tag.value.upper(),
             [f.code for f in integrity.flags])

    decisions = {
        "cand-A": ("Strong everywhere, clean session", decide(score("cand-A", 82, 78, 80, 85, 92))),
        "cand-B": ("Fresher: weak resume, strong skills", decide(score("cand-B", 35, 80, 78, 88, 90, FRESH))),
        "cand-C": ("No machine test yet", decide(score("cand-C", 80, 80, 80, 80, 0, drop=("machine_test",)))),
        "cand-D": ("High average, failed the core technical round (35)", decide(score("cand-D", 95, 95, 95, 35, 95))),
        "cand-E": ("Borderline, all rounds about 71", decide(score("cand-E", 72, 70, 71, 71, 72))),
        "cand-F": ("Weak across the board", decide(score("cand-F", 30, 30, 30, 30, 30))),
        "cand-G": ("Strong scores, integrity tag MEDIUM (real Day 49 report)", decide(score("cand-G", 85, 84, 86, 87, 88), integrity_report=integrity)),
        "cand-H": ("Strong scores, response-time spikes and uneven pacing",
                   decide(score("cand-H", 85, 84, 86, 87, 88), behavior_report=behavior(spikes=2, focus=30.0, hesitation=25.0))),
        "cand-I": ("Weak, scattered rounds, integrity MEDIUM", decide(score("cand-I", 80, 20, 45, 30, 60), integrity_report=integrity)),
        "cand-J": ("Middle scorer", decide(score("cand-J", 60, 60, 60, 60, 60))),
    }
    results = {}
    for key, (title, d) in decisions.items():
        log.info("-" * 70)
        log.info("%s: %s", key, title)
        log.info("   OUTCOME %s%s | score band %s | fit %s | confidence %s (%s) | human confirmation required: %s",
                 d.outcome.value.upper(), f" [{d.hold_kind.value}]" if d.hold_kind else "", d.score_band.value, d.hiring_fit_percentage,
                 d.confidence.score, d.confidence.band, d.requires_human_confirmation)
        for r in d.rule_trace:
            if r.fired:
                log.info("   RULE FIRED %s: %s (%s)", r.rule_id, r.effect, r.detail)
        for f in d.risk_factors:
            log.info("   RISK %s=%s (%s) %s", f.category, f.level, f.effect, f.detail)
        results[key] = {"title": title, **d.to_dict()}

    a, b, c, d_, e, f, g, h, i, j = (decisions[k][1] for k in decisions)

    print("\n" + d_.explain())
    print("\n" + g.explain())
    print("\n" + f.to_summary_text())

    # Policy: auto-advance is opt-in, SELECTED-only, and still gated.
    auto_policy = DecisionPolicy(auto_apply={SELECTED: True})
    a_auto = decide(score("cand-A", 82, 78, 80, 85, 92), policy=auto_policy)
    f_auto = decide(score("cand-F", 30, 30, 30, 30, 30), policy=auto_policy)
    g_auto = decide(score("cand-G", 85, 84, 86, 87, 88), integrity_report=integrity, policy=auto_policy)
    log.info("-" * 70)
    log.info("Auto-advance policy ON: cand-A eligible=%s, cand-G (integrity) eligible=%s, cand-F (rejection) eligible=%s",
             a_auto.automation_eligible, g_auto.automation_eligible, f_auto.automation_eligible)
    auto_final = finalize_automatically(a_auto)
    log.info("cand-A finalized by %s -> %s", auto_final.decided_by, auto_final.final_outcome.value)

    refusals = {}
    for label, attempt in (("cand-F rejection", lambda: finalize_automatically(f_auto)), ("cand-G integrity hold", lambda: finalize_automatically(g_auto))):
        try:
            attempt()
            refusals[label] = "ALLOWED (bug)"
        except ValueError as exc:
            refusals[label] = f"refused: {exc}"
        log.info("Automatic finalization of %s -> %s", label, refusals[label])
    try:
        DecisionPolicy(auto_apply={REJECTED: True})
        policy_refusal = "ALLOWED (bug)"
    except ValueError as exc:
        policy_refusal = f"refused: {exc}"
    log.info("Configuring automatic rejection -> %s", policy_refusal)

    # Human confirmation flow for the rejection recommendation.
    log.info("-" * 70)
    log.info("cand-F notice BEFORE human confirmation: %s", f.candidate_notice())
    confirmed = finalize_with_human(f, HumanReview("recruiter-7", REJECTED))
    log.info("cand-F confirmed by %s -> notice: %s", confirmed.decided_by, confirmed.candidate_notice)
    override = finalize_with_human(f, HumanReview("recruiter-7", HOLD, note="Strong internal referral; schedule a re-interview before deciding."))
    log.info("cand-F override recorded: %s", override.audit_record())

    results["automation"] = {"auto_advance_cand_A": auto_final.audit_record(), "refusals": refusals, "policy_refusal": policy_refusal}
    results["human_flow_cand_F"] = {"before_confirmation_notice": f.candidate_notice(), "confirmed": confirmed.audit_record(),
                                    "override": override.audit_record()}

    # Sanity checks the demo itself verifies, not just claims:
    assert a.outcome is SELECTED and b.outcome is SELECTED and a.confidence.band == "high"
    log.info("Sanity check passed: clean strong candidates (A, fresher B) are SELECTED; A's confidence is %s (%s).", a.confidence.score, a.confidence.band)

    assert c.outcome is HOLD and c.hold_kind is HoldKind.PENDING_EVIDENCE
    log.info("Sanity check passed: cand-C is held PENDING EVIDENCE rather than decided on three of four applicable rounds.")

    assert d_.score_band is SELECTED and d_.outcome is HOLD and "R2_CRITICAL_ROUND_FLOORS" in [r.rule_id for r in d_.rule_trace if r.fired]
    log.info("Sanity check passed: rule R2 held cand-D even though the score alone says SELECTED (%s%%): the core skill round failed.", d_.hiring_fit_percentage)

    assert e.outcome is HOLD and "R4_REVIEW_FLAGS" in [r.rule_id for r in e.rule_trace if r.fired]
    log.info("Sanity check passed: the borderline candidate (E) is held for review, not selected.")

    assert f.outcome is REJECTED and f.requires_human_confirmation and f.candidate_notice() == NOTICES[HOLD]
    log.info("Sanity check passed: cand-F is recommended for rejection, needs a human, and the candidate is told only 'under review'.")

    clean_g = decide(score("cand-G", 85, 84, 86, 87, 88))
    assert g.outcome is HOLD and clean_g.outcome is SELECTED and g.hiring_fit_percentage == clean_g.hiring_fit_percentage
    log.info("Sanity check passed: the integrity tag held cand-G for review without changing the score (%s) and lowered confidence %s -> %s.",
             g.hiring_fit_percentage, clean_g.confidence.score, g.confidence.score)

    assert h.outcome is SELECTED and h.confidence.score < clean_g.confidence.score
    assert "NOT used" in next(r for r in h.risk_factors if r.category == "behavior").detail
    log.info("Sanity check passed: behavior spikes and uneven pacing lowered cand-H's confidence to %s but did not change the category; hesitation was not used.",
             h.confidence.score)

    assert i.outcome is HOLD and i.hold_kind is HoldKind.INSUFFICIENT_EVIDENCE_TO_REJECT
    log.info("Sanity check passed: cand-I's weak but shaky evidence became a REVIEW, not a rejection (risk factors only push toward review).")

    assert j.outcome is HOLD and j.hold_kind is HoldKind.MID_SCORE
    log.info("Sanity check passed: the middle scorer is held as a mid score.")

    assert a_auto.automation_eligible and not g_auto.automation_eligible and not f_auto.automation_eligible
    assert all(v.startswith("refused") for v in refusals.values()) and policy_refusal.startswith("refused")
    log.info("Sanity check passed: with auto-advance ON only the clean SELECTED candidate is eligible; rejections and flagged candidates are refused, "
             "and automatic rejection cannot even be configured.")

    assert override.overridden and override.note and not confirmed.overridden
    log.info("Sanity check passed: a human override is recorded with a note, a confirmation is recorded without one.")

    assert all(x.automated_action == "none" for x in (a, b, c, d_, e, f, g, h, i, j))
    log.info("Sanity check passed: the engine itself never acts (automated_action='none' on every decision).")

    with open(REPORT_PATH, "w", encoding="utf-8") as out:
        json.dump(results, out, indent=2)
    log.info("Report written to %s", REPORT_PATH)


if __name__ == "__main__":
    main()
