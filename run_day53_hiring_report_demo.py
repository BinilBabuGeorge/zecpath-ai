"""
Day 53 demo -- generates recruiter-facing Hiring Intelligence Reports for
four candidates from REAL result objects (ATS, screening, HR, technical,
machine test, behavioral, integrity), through the real Day 51 aggregate
and Day 52 decision, then exports each in JSON, Markdown and a
self-contained HTML page. Writes:
  - logs/day53_hiring_report_run.log
  - data/results/day53_reports/<report id>.{json,md,html}   (12 files)
  - data/results/day53_hiring_report_summary.json

HONESTY NOTE: the round result objects are hand-built stand-ins for what
the five earlier engines would output (no live pipeline feeds this
project), and the machine-test results come from hand-written sandbox
stand-ins because no sandbox exists. The report generation, findings,
risk indicators, rendering, escaping and export are 100% real.
"""

from __future__ import annotations

import json
import logging
import os
from types import SimpleNamespace

from parsers.answer_intent_engine import AnswerQuality
from parsers.ats_scoring_engine import ATSScoreResult, ComponentResult
from parsers.behavioral_signal_engine import (
    BehavioralInsightReport,
    DistractionSpikeResult,
    FocusConsistencyResult,
    VerbalHesitationSummary,
)
from parsers.cross_round_aggregation_engine import compute_from_round_outputs
from parsers.final_recommendation_engine import DecisionOutcome, decide
from parsers.hiring_report_generator import FindingKind, Severity, export_report, generate_hiring_report
from parsers.hr_interview_question_bank import ExperienceLevel, RoleType
from parsers.hr_interview_scoring_engine import ConsistencyAssessment, HRInterviewScoreReport, WeightConfig
from parsers.integrity_detection_engine import BrowserEvent, BrowserEventType as T, build_integrity_report
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
from parsers.screening_report_generator import ReportHighlights, ScreeningReport
from parsers.screening_scoring_engine import QuestionScore, ScoreComponent, ScreeningScoreResult
from parsers.technical_interview_question_bank import DifficultyTier
from parsers.technical_skill_scoring_engine import ShallowDeepClassification, TechnicalEvaluationReport

LOG_PATH = "logs/day53_hiring_report_run.log"
OUT_DIR = "data/results/day53_reports"
SUMMARY_PATH = "data/results/day53_hiring_report_summary.json"

os.makedirs("logs", exist_ok=True)
os.makedirs("data/results", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, mode="w"), logging.StreamHandler()],
)
log = logging.getLogger("day53_demo")

TECH, EXP = RoleType.TECHNICAL, ExperienceLevel.EXPERIENCED
GENERATED_AT = "2026-10-23T09:30:00+00:00"
SECRET = "SECRET-ANSWER-TEXT-MUST-NOT-APPEAR"


# ---------------------------------------------------------------------------
# Stand-in round results, built from the real result classes
# ---------------------------------------------------------------------------

def ats(skill, experience, semantic, overall, missing=("docker",), matched=("python", "sql", "flask", "git")):
    def comp(name, score, details=None, available=True):
        return ComponentResult(name, score, 0.25, 0.25, score * 0.25, available, details or {})
    return ATSScoreResult(overall, "tech", [
        comp("skill_match", skill, {"matched_skills": list(matched), "missing_skills": list(missing),
                                    "required_count": len(matched) + len(missing), "matched_count": len(matched)}),
        comp("experience", experience), comp("semantic", semantic), comp("education", 0.0, {"reason": "no degree stated"}, available=False)])


def screening(total, categories, findings=()):
    qs = [QuestionScore("t", cat, AnswerQuality.OK, {"clarity": ScoreComponent(v)}, v) for cat, v in categories]
    return ScreeningScoreResult(total, qs, list(findings))


def hr(overall, rel, comm, conf, findings=()):
    return HRInterviewScoreReport(overall, WeightConfig(), [], rel, comm, conf, ConsistencyAssessment(len(findings), 0, 0.2 if findings else 0.0, 0.0, list(findings)), 5)


def technical(overall, breakdown, shallow, total):
    evals = [SimpleNamespace(classification=ShallowDeepClassification.SHALLOW)] * shallow
    evals += [SimpleNamespace(classification=ShallowDeepClassification.DEEP)] * (total - shallow)
    return TechnicalEvaluationReport(evals, overall, breakdown)


def machine_test(passed):
    cases = [CaseSpec("v1"), CaseSpec("v2"), CaseSpec("h1", visible=False), CaseSpec("h2", visible=False)]
    task = MachineTestTask("coding-two-sum", MachineTestType.CODING, "Two sum", DifficultyTier.INTERMEDIATE, 1800.0, "python", cases, reference_runtime_ms=100.0)
    code = 'def two_sum(a, t):\n    """Return indices."""\n    seen = {}\n    for i, v in enumerate(a):\n        if t - v in seen:\n            return seen[t - v], i\n        seen[v] = i\n'
    run = ExecutionRun(300.0, [CaseResult(c.case_id, c.case_id in passed, 100.0 if c.case_id in passed else None) for c in cases])
    return build_machine_test_report([TaskAttempt(task, [CodeSnapshot(100, code), CodeSnapshot(200, code), CodeSnapshot(290, code)], [run], submitted_at=310.0)])


def behavior(spikes, focus, hesitation):
    return BehavioralInsightReport(FocusConsistencyResult([30.0, 31.0], 30.5, 0.5, 0.02, focus),
                                   DistractionSpikeResult([f"q{i}" for i in range(spikes)], spikes, 30.0, 100.0 - 30 * spikes),
                                   VerbalHesitationSummary({}, hesitation))


def integrity_burst():
    events = [BrowserEvent(T.TAB_HIDDEN, 100), BrowserEvent(T.TAB_VISIBLE, 104), BrowserEvent(T.TAB_HIDDEN, 120),
              BrowserEvent(T.TAB_VISIBLE, 124), BrowserEvent(T.TAB_HIDDEN, 140), BrowserEvent(T.TAB_VISIBLE, 144)]
    return build_integrity_report(events, session_end=1800)


def screening_report():
    return ScreeningReport("cand-A", "Backend Developer", GENERATED_AT, 82.0, 85.0, [{"answer": SECRET}], ["Clear communicator"], [],
                           ["Notice period not stated"], ReportHighlights([{"amount": 1400000, "currency": "INR"}], [{"notice_days": 30}], ["python", "sql", "flask"]))


def build(cid, objs, behavior_report=None, integrity_report=None, label=None):
    objs = dict(objs)
    day31_report = objs.pop("screening_report", None)          # only the report generator takes the Day 31 report
    score = compute_from_round_outputs(role_type=TECH, experience_level=EXP, candidate_id=cid,
                                       integrity_risk_tag=integrity_report.risk_tag if integrity_report else None, **objs)
    decision = decide(score, integrity_report=integrity_report, behavior_report=behavior_report)
    report = generate_hiring_report(decision, score, behavior=behavior_report, integrity=integrity_report, generated_at=GENERATED_AT,
                                    role_title="Backend Developer", candidate_label=label, screening_report=day31_report, **objs)
    return decision, report


def main() -> None:
    log.info("Starting Day 53 hiring report demo (recruiter-facing, template-based, no language model).")
    integrity = integrity_burst()

    candidates = {
        "cand-A": ("Strong everywhere, clean session", dict(
            ats=ats(92, 85, 78, 88), screening=screening(82, [("skills", 90), ("skills", 85), ("location", 70)]), hr=hr(84, 86, 88, 78),
            technical=technical(86, {"react": 90.0, "node": 84.0, "sql": 78.0}, 0, 4), machine_test=machine_test({"v1", "v2", "h1", "h2"}),
            screening_report=screening_report())),
        "cand-B": ("Strong scores but integrity MEDIUM and timing spikes", dict(
            ats=ats(88, 80, 70, 82), screening=screening(80, [("skills", 88), ("salary", 40)], ["Stated 2 years vs 5 in resume"]),
            hr=hr(80, 82, 90, 45, ["Confidence swings between answers"]), technical=technical(82, {"react": 88.0, "docker": 35.0}, 1, 4),
            machine_test=machine_test({"v1", "v2", "h1", "h2"}))),
        "cand-C": ("Weak across the board", dict(
            ats=ats(35, 30, 40, 36, missing=("react", "node", "docker"), matched=("python",)),
            screening=screening(38, [("skills", 35), ("introduction", 40)]), hr=hr(40, 38, 45, 36), technical=technical(34, {"react": 30.0, "node": 38.0}, 3, 4),
            machine_test=machine_test({"v1"}))),
        "cand-D": ("Machine test not taken yet", dict(
            ats=ats(85, 78, 74, 80), screening=screening(78, [("skills", 82), ("location", 74)]), hr=hr(76, 78, 80, 70),
            technical=technical(79, {"react": 82.0, "node": 76.0}, 1, 4), machine_test=None)),
    }
    built, summary = {}, {}
    for cid, (title, objs) in candidates.items():
        b = behavior(3, 30.0, 25.0) if cid == "cand-B" else behavior(0, 92.0, 3.0)
        i = integrity if cid == "cand-B" else None
        decision, report = build(cid, objs, b, i)
        built[cid] = (decision, report)
        log.info("-" * 70)
        log.info("%s: %s", cid, title)
        log.info("   REPORT %s | outcome %s | fit %s | confidence %s | strengths %d, weaknesses %d, risks %d",
                 report.report_id, report.recommendation["outcome"], report.recommendation["hiring_fit_percentage"],
                 report.recommendation["confidence_score"], len(report.strengths), len(report.weaknesses), len(report.risk_indicators))
        for line in report.executive_summary:
            log.info("   | %s", line)
        paths = export_report(report, OUT_DIR)
        log.info("   exported: %s", ", ".join(os.path.basename(p) for p in paths.values()))
        summary[cid] = {"title": title, "report_id": report.report_id, "outcome": report.recommendation["outcome"],
                        "hiring_fit_percentage": report.recommendation["hiring_fit_percentage"], "files": [os.path.basename(p) for p in paths.values()],
                        "preview": report.to_preview_dict()}

    print("\n" + built["cand-B"][1].to_markdown()[:2600])

    # A hostile candidate label, to show escaping end to end.
    hostile_decision, hostile = build("cand-A", candidates["cand-A"][1], behavior(0, 92.0, 3.0), None, label="<script>alert('x')</script> & Co")
    log.info("-" * 70)
    log.info("Hostile label rendered safely in HTML: %s", "&lt;script&gt;" in hostile.to_html() and "<script>" not in hostile.to_html())

    # Sanity checks the demo itself verifies, not just claims:
    a, b, c, d = (built[k] for k in ("cand-A", "cand-B", "cand-C", "cand-D"))

    assert a[0].outcome is DecisionOutcome.SELECTED and a[1].strengths
    assert not [x for x in a[1].risk_indicators if x.severity in (Severity.HIGH, Severity.MEDIUM)]
    log.info("Sanity check passed: cand-A's report recommends SELECTED with %d strengths and no high/medium risk.", len(a[1].strengths))

    assert b[0].outcome is DecisionOutcome.HOLD_REVIEW
    assert any(x.category == "integrity" and x.severity is Severity.MEDIUM for x in b[1].risk_indicators)
    assert all(x.severity in (Severity.LOW, Severity.INFO) for x in b[1].risk_indicators if x.category == "behavior")
    log.info("Sanity check passed: cand-B is held; the integrity tag is a MEDIUM risk while behavior timing stays at LOW or below.")

    hesitation = next(l for l in b[1].behavioral_flags if l.startswith("Verbal hesitation"))
    assert "NOT used" in hesitation
    log.info("Sanity check passed: verbal hesitation is displayed but labelled as not used in the recommendation.")

    assert c[0].outcome is DecisionOutcome.REJECTED and "nothing is rejected automatically" in c[1].recommendation["next_steps"][0]
    assert c[1].weaknesses and c[1].recommendation["requires_human_confirmation"]
    log.info("Sanity check passed: cand-C's report says a rejection is only a recommendation and needs human confirmation.")

    mt = next(s for s in d[1].rounds if s.round_name == "machine_test")
    assert mt.status == "missing" and "NOT counted as zero" in mt.headline
    log.info("Sanity check passed: cand-D's missing machine test is 'not yet available', not a zero.")

    assert "&lt;script&gt;" in hostile.to_html() and "<script>" not in hostile.to_html()
    assert "a\\|b" not in hostile.to_markdown() and "\\<script\\>" in hostile.to_markdown()
    log.info("Sanity check passed: hostile candidate text is escaped in HTML and Markdown.")

    for cid, (_, report) in built.items():
        assert all(f.score >= 75.0 for f in report.strengths) and all(f.score < 50.0 for f in report.weaknesses)
    log.info("Sanity check passed: across all reports every strength scores >= 75 and every weakness < 50.")

    for cid, (_, report) in built.items():
        for ext, render in (("json", report.to_json()), ("md", report.to_markdown()), ("html", report.to_html())):
            assert SECRET not in render
            with open(os.path.join(OUT_DIR, f"{report.report_id}.{ext}"), encoding="utf-8") as fh:
                assert fh.read() == render
    log.info("Sanity check passed: the 12 exported files match the renderers exactly and no raw screening answer text appears in any of them.")

    again = build("cand-A", candidates["cand-A"][1], behavior(0, 92.0, 3.0))[1]
    ids = [r.report_id for _, r in built.values()]
    assert again.report_id == a[1].report_id and len(set(ids)) == 4
    log.info("Sanity check passed: report ids are stable for the same inputs and unique across candidates.")

    for cid, (_, report) in built.items():
        preview = report.to_preview_dict()
        assert set(preview) == {"schema_version", "report_id", "candidate_id", "outcome", "hiring_fit_percentage", "access_level", "note"}
    log.info("Sanity check passed: the preview view holds only outcome and score (access control itself is not built).")

    html_text = a[1].to_html()
    assert all(token not in html_text for token in ("<script", "http://", "https://", "src=", "<link", "<img")) and "@page" in html_text
    log.info("Sanity check passed: the HTML export is self-contained (no scripts or external resources) with a print stylesheet.")

    with open(SUMMARY_PATH, "w", encoding="utf-8") as out:
        json.dump(summary, out, indent=2)
    log.info("Reports written to %s and summary to %s", OUT_DIR, SUMMARY_PATH)


if __name__ == "__main__":
    main()
