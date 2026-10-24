import json
import os
import tempfile
from types import SimpleNamespace

import pytest

from parsers.answer_intent_engine import AnswerQuality
from parsers.ats_scoring_engine import ATSScoreResult, ComponentResult
from parsers.behavioral_signal_engine import (
    BehavioralInsightReport,
    DistractionSpikeResult,
    FocusConsistencyResult,
    VerbalHesitationSummary,
)
from parsers.cross_round_aggregation_engine import RoundResult, compute_cross_round_score, compute_from_round_outputs
from parsers.final_recommendation_engine import DecisionOutcome, HoldKind, decide
from parsers.hiring_report_generator import (
    LIMITATIONS,
    MAX_FINDINGS_PER_SOURCE,
    NOT_IMPLEMENTED,
    STRENGTH_MIN,
    WEAKNESS_MAX,
    FindingKind,
    Severity,
    _classify,
    export_report,
    generate_hiring_report,
)
from parsers.hr_interview_question_bank import ExperienceLevel, RoleType
from parsers.hr_interview_scoring_engine import ConsistencyAssessment, HRInterviewScoreReport, WeightConfig
from parsers.integrity_detection_engine import BrowserEvent, BrowserEventType as T, build_integrity_report
from parsers.interview_summary_generator import CulturalFitIndicator, InterviewSummaryReport, RiskFlag, ScoredNote
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

TECH, NON_TECH = RoleType.TECHNICAL, RoleType.NON_TECHNICAL
EXP = ExperienceLevel.EXPERIENCED
AT = "2026-10-23T09:00:00+00:00"


# ---------------------------------------------------------------------------
# Real-object builders
# ---------------------------------------------------------------------------

def component(name, score, details=None, available=True):
    return ComponentResult(name, score, 0.25, 0.25, score * 0.25, available, details or {})


def make_ats(skill=90.0, experience=80.0, semantic=30.0, overall=72.0, notes=None):
    return ATSScoreResult(overall, "tech", [
        component("skill_match", skill, {"matched_skills": ["python", "sql", "flask", "git"], "missing_skills": ["docker"],
                                        "required_count": 5, "matched_count": 4}),
        component("experience", experience), component("semantic", semantic),
        component("education", 0.0, {"reason": "no degree stated"}, available=False),
    ], notes or [])


def qscore(category, total):
    return QuestionScore("t", category, AnswerQuality.OK, {"clarity": ScoreComponent(total)}, total)


def make_screening(total=70.0, findings=None):
    return ScreeningScoreResult(total, [qscore("skills", 90.0), qscore("skills", 80.0), qscore("salary", 40.0), qscore("location", 60.0)], findings or [])


def make_hr(rel=80.0, comm=90.0, conf=45.0, overall=72.0, findings=None, answered=5):
    return HRInterviewScoreReport(overall, WeightConfig(), [], rel, comm, conf,
                                  ConsistencyAssessment(1, 0, 0.2, 3.0, findings if findings is not None else ["Confidence swings between answers"]), answered)


def make_technical(breakdown=None, shallow=2, total=4, overall=75.0):
    evals = [SimpleNamespace(classification=ShallowDeepClassification.SHALLOW) for _ in range(shallow)]
    evals += [SimpleNamespace(classification=ShallowDeepClassification.DEEP) for _ in range(total - shallow)]
    return TechnicalEvaluationReport(evals, overall, breakdown if breakdown is not None else {"react": 88.0, "node": 72.0, "docker": 35.0})


def make_machine_test(pass_all=True, hidden_fail=False):
    cases = [CaseSpec("v1"), CaseSpec("v2"), CaseSpec("h1", visible=False), CaseSpec("h2", visible=False)]
    task = MachineTestTask("coding-two-sum", MachineTestType.CODING, "Two sum", DifficultyTier.INTERMEDIATE, 1800.0, "python", cases, reference_runtime_ms=100.0)
    code = 'def two_sum(a, t):\n    """Return indices."""\n    seen = {}\n    for i, v in enumerate(a):\n        if t - v in seen:\n            return seen[t - v], i\n        seen[v] = i\n'
    if hidden_fail:
        passed = {"v1", "v2"}
    else:
        passed = {"v1", "v2", "h1", "h2"} if pass_all else {"v1"}
    run = ExecutionRun(300.0, [CaseResult(c.case_id, c.case_id in passed, 100.0 if c.case_id in passed else None) for c in cases])
    attempt = TaskAttempt(task, [CodeSnapshot(100, code), CodeSnapshot(200, code), CodeSnapshot(290, code)], [run], submitted_at=310.0)
    return build_machine_test_report([attempt])


def make_behavior(spikes=0, focus=90.0, hesitation=3.0):
    return BehavioralInsightReport(
        FocusConsistencyResult([30.0, 31.0], 30.5, 0.5, 0.02, focus),
        DistractionSpikeResult([f"q{i}" for i in range(spikes)], spikes, 30.0, 100.0 - 30 * spikes),
        VerbalHesitationSummary({}, hesitation))


def burst_integrity():
    events = [BrowserEvent(T.TAB_HIDDEN, 100), BrowserEvent(T.TAB_VISIBLE, 104), BrowserEvent(T.TAB_HIDDEN, 120),
              BrowserEvent(T.TAB_VISIBLE, 124), BrowserEvent(T.TAB_HIDDEN, 140), BrowserEvent(T.TAB_VISIBLE, 144)]
    return build_integrity_report(events, session_end=1800)


class Case:
    """A fully assembled candidate: result objects, Day 51 score, Day 52 decision."""

    def __init__(self, cid="cand-1", role=TECH, behavior=None, integrity=None, **objs):
        self.objs = {"ats": make_ats(), "screening": make_screening(), "hr": make_hr(), "technical": make_technical(),
                     "machine_test": make_machine_test()}
        self.objs.update(objs)
        self.behavior, self.integrity = behavior, integrity
        self.score = compute_from_round_outputs(role_type=role, experience_level=EXP, candidate_id=cid,
                                                integrity_risk_tag=integrity.risk_tag if integrity else None, **self.objs)
        self.decision = decide(self.score, integrity_report=integrity, behavior_report=behavior)

    def report(self, **kw):
        extra = dict(self.objs)
        extra.update(kw)
        return generate_hiring_report(self.decision, self.score, behavior=self.behavior, integrity=self.integrity, generated_at=AT, **extra)


def finding(report, area):
    return next(f for f in report.strengths + report.weaknesses if f.area == area)


# ---------------------------------------------------------------------------
# Input validation: the pieces must belong together
# ---------------------------------------------------------------------------

def test_decision_and_score_for_different_candidates_are_rejected():
    a, b = Case("a"), Case("b")
    with pytest.raises(ValueError):
        generate_hiring_report(a.decision, b.score, generated_at=AT)


def test_a_decision_not_built_from_this_score_is_rejected():
    a = Case("same", ats=make_ats(overall=95.0))
    b = Case("same", ats=make_ats(overall=20.0))
    with pytest.raises(ValueError):
        generate_hiring_report(a.decision, b.score, generated_at=AT)


# ---------------------------------------------------------------------------
# The recommendation is read, never recomputed
# ---------------------------------------------------------------------------

def test_recommendation_block_mirrors_the_day_52_decision():
    case = Case()
    rec = case.report().recommendation
    d = case.decision
    assert rec["outcome"] == d.outcome.value and rec["hiring_fit_percentage"] == d.hiring_fit_percentage
    assert rec["confidence_score"] == d.confidence.score and rec["reasons"] == d.reasons
    assert rec["requires_human_confirmation"] == d.requires_human_confirmation and rec["automated_action"] == "none"


def test_every_outcome_and_hold_kind_gets_a_label_and_next_steps():
    selected = Case(ats=make_ats(overall=92.0), screening=make_screening(90.0), hr=make_hr(overall=90.0, findings=[]),
                    technical=make_technical(overall=90.0), machine_test=make_machine_test())
    pending = Case(technical=None, machine_test=None)
    cases = [selected.report(), pending.report()]
    for r in cases:
        assert r.recommendation["outcome_label"] and r.recommendation["next_steps"]
    assert pending.decision.hold_kind is HoldKind.PENDING_EVIDENCE
    assert "remaining round" in pending.report().recommendation["next_steps"][0]


def test_rejection_next_steps_say_it_is_only_a_recommendation():
    weak = Case(ats=make_ats(overall=20.0), screening=make_screening(20.0), hr=make_hr(overall=20.0), technical=make_technical(overall=20.0),
                machine_test=build_machine_test_report([TaskAttempt(MachineTestTask(
                    "t", MachineTestType.CODING, "t", DifficultyTier.BASICS, 100, cases=[CaseSpec("v1")]), [CodeSnapshot(5, "x = 1")],
                    [ExecutionRun(10, [CaseResult("v1", False)])], submitted_at=10)]))
    r = weak.report()
    assert weak.decision.outcome is DecisionOutcome.REJECTED
    assert "nothing is rejected automatically" in r.recommendation["next_steps"][0]
    assert any("under review" in s for s in r.recommendation["next_steps"])


def test_next_steps_include_the_decisions_what_would_change_conditions():
    case = Case(integrity=burst_integrity(),
                ats=make_ats(overall=92.0), screening=make_screening(90.0), hr=make_hr(overall=90.0, findings=[]),
                technical=make_technical(overall=90.0))
    steps = case.report().recommendation["next_steps"]
    assert case.decision.hold_kind is HoldKind.SELECTION_BLOCKED
    assert any("integrity" in s.lower() for s in steps)


# ---------------------------------------------------------------------------
# Executive summary
# ---------------------------------------------------------------------------

def test_executive_summary_states_outcome_fit_confidence_evidence_and_next_step():
    r = Case().report(role_title="Backend Developer")
    text = "\n".join(r.executive_summary)
    assert r.recommendation["outcome_label"] in text and f"{r.recommendation['hiring_fit_percentage']}%" in text
    assert "confidence" in text and "Evidence:" in text and "Next step:" in text and "Backend Developer" in text
    assert len(r.executive_summary) <= 6


def test_summary_lists_at_most_three_strengths():
    line = next(l for l in Case().report().executive_summary if l.startswith("Strongest areas"))
    assert line.count("(") <= 3


def test_summary_strengths_show_breadth_across_rounds_not_one_chatty_round():
    r = Case().report()
    line = next(l for l in r.executive_summary if l.startswith("Strongest areas"))
    sources = [name for name in ("ATS resume match", "Screening call", "HR interview", "Technical interview", "Machine test") if name in line]
    assert len(sources) == 3 and len({f.source for f in r.strengths}) >= 3


def test_summary_breadth_still_fills_up_when_only_one_round_has_strengths():
    only_ats = Case(ats=make_ats(95, 90, 85, 90), screening=ScreeningScoreResult(55.0, [qscore("skills", 55.0)]), hr=make_hr(60, 60, 60, 60, []),
                    technical=make_technical({"react": 60.0}, 0, 2, 60.0), machine_test=None).report()
    line = next(l for l in only_ats.executive_summary if l.startswith("Strongest areas"))
    assert line.count("ATS resume match") == 3


def test_summary_says_so_when_nothing_clears_the_strength_bar():
    weak = Case(ats=make_ats(60, 60, 60, 60), screening=ScreeningScoreResult(55.0, [qscore("skills", 55.0)]), hr=make_hr(60, 60, 60, 60, []),
                technical=make_technical({"react": 60.0}, shallow=0, total=2, overall=60.0), machine_test=None)
    line = next(l for l in weak.report().executive_summary if l.startswith("Strongest areas"))
    assert "none at or above 75" in line


def test_summary_concerns_have_no_doubled_punctuation():
    text = "\n".join(Case().report().executive_summary)
    assert ".;" not in text and ".." not in text


def test_to_text_summary_is_the_executive_summary():
    r = Case().report()
    assert r.to_text_summary() == "\n".join(r.executive_summary)


# ---------------------------------------------------------------------------
# Strengths and weaknesses
# ---------------------------------------------------------------------------

def test_classification_thresholds_are_75_and_50():
    assert _classify("ats", "x", 75.0, "e").kind is FindingKind.STRENGTH
    assert _classify("ats", "x", 74.9, "e") is None
    assert _classify("ats", "x", 50.0, "e") is None
    assert _classify("ats", "x", 49.9, "e").kind is FindingKind.WEAKNESS
    assert STRENGTH_MIN == 75.0 and WEAKNESS_MAX == 50.0


def test_every_finding_carries_source_area_score_and_evidence():
    r = Case().report()
    assert r.strengths and r.weaknesses
    for f in r.strengths + r.weaknesses:
        assert f.source and f.area and f.evidence and 0.0 <= f.score <= 100.0
    for f in r.strengths:
        assert f.score >= STRENGTH_MIN
    for f in r.weaknesses:
        assert f.score < WEAKNESS_MAX


def test_findings_are_capped_per_source_and_sorted_by_how_extreme_they_are():
    r = Case(ats=make_ats(95, 90, 85, 80)).report()
    ats_strengths = [f for f in r.strengths if f.source == "ats"]
    assert len(ats_strengths) <= MAX_FINDINGS_PER_SOURCE
    scores = [f.score for f in r.strengths]
    assert scores == sorted(scores, reverse=True)
    weak_scores = [f.score for f in r.weaknesses]
    assert weak_scores == sorted(weak_scores)


def test_ats_skill_finding_names_matched_and_missing_skills():
    r = Case().report()
    ev = finding(r, "skill_match").evidence
    assert "Matched 4 of 5 required skills" in ev and "docker" in ev
    ats_round = next(s for s in r.rounds if s.round_name == "ats")
    assert any("Matched skills: python" in f for f in ats_round.key_facts) and any("Missing skills: docker" in f for f in ats_round.key_facts)


def test_an_unavailable_ats_component_is_shown_as_not_available_not_scored():
    r = Case().report()
    ats_round = next(s for s in r.rounds if s.round_name == "ats")
    assert any("education: not available" in f and "no degree stated" in f for f in ats_round.key_facts)
    assert not any(f.area == "education" for f in r.strengths + r.weaknesses)


def test_ats_missing_data_notes_appear_in_the_round_notes():
    r = Case(ats=make_ats(notes=["No education section found"])).report()
    assert any("No education section found" in n for n in next(s for s in r.rounds if s.round_name == "ats").notes)


def test_screening_findings_are_by_question_category_average():
    r = Case().report()
    assert finding(r, "skills").score == 85.0 and finding(r, "skills").kind is FindingKind.STRENGTH
    assert finding(r, "salary").kind is FindingKind.WEAKNESS


def test_screening_consistency_findings_become_low_severity_risks():
    r = Case(screening=make_screening(findings=["Stated 2 years vs 5 years in resume"])).report()
    hit = [x for x in r.risk_indicators if "Screening consistency" in x.message]
    assert hit and hit[0].severity is Severity.LOW and hit[0].category == "consistency"


def test_hr_findings_derive_from_the_three_averages_when_no_summary_is_supplied():
    r = Case().report()
    assert finding(r, "communication").kind is FindingKind.STRENGTH and finding(r, "confidence").kind is FindingKind.WEAKNESS
    assert finding(r, "relevance").score == 80.0


def test_a_day_39_interview_summary_replaces_the_derived_hr_findings_and_adds_culture_fit_and_flags():
    summary = InterviewSummaryReport(
        78.0, "Strong", 72.0, None,
        [ScoredNote("ownership", 91.0, "Described concrete end-to-end ownership")], [ScoredNote("conflict handling", 41.0, "Avoided the conflict question")],
        CulturalFitIndicator(70.0, "Good", "One teamwork answer, solid"), [RiskFlag("Short answers", "Three answers under 20 words")])
    r = Case().report(interview_summary=summary)
    assert finding(r, "ownership").evidence == "Described concrete end-to-end ownership"
    assert finding(r, "conflict handling").kind is FindingKind.WEAKNESS
    assert not any(f.area == "relevance" for f in r.strengths + r.weaknesses)
    hr_round = next(s for s in r.rounds if s.round_name == "hr_interview")
    assert any("Culture-fit indicator (Good)" in n for n in hr_round.notes)
    assert any("Short answers" in x.message for x in r.risk_indicators)


def test_technical_findings_come_from_the_skill_breakdown():
    r = Case().report()
    assert finding(r, "react").kind is FindingKind.STRENGTH and finding(r, "docker").kind is FindingKind.WEAKNESS
    assert not any(f.area == "node" for f in r.strengths + r.weaknesses)           # 72 is neither


def test_a_mostly_shallow_technical_interview_is_called_out():
    r = Case(technical=make_technical(shallow=3, total=4)).report()
    depth = finding(r, "answer_depth")
    assert depth.kind is FindingKind.WEAKNESS and "3 of 4" in depth.evidence
    assert any("Answer depth:" in f for f in next(s for s in r.rounds if s.round_name == "technical_interview").key_facts)


def test_a_mostly_deep_technical_interview_raises_no_depth_weakness():
    assert not any(f.area == "answer_depth" for f in Case(technical=make_technical(shallow=1, total=4)).report().weaknesses)


def test_exactly_half_shallow_is_not_called_a_weakness_so_every_weakness_stays_below_the_bar():
    r = Case(technical=make_technical(shallow=2, total=4)).report()
    assert not any(f.area == "answer_depth" for f in r.weaknesses)
    worst = Case(technical=make_technical(shallow=4, total=4)).report()
    depth = finding(worst, "answer_depth")
    assert depth.score == 0.0 and depth.score < WEAKNESS_MAX


def test_machine_test_metrics_become_findings_and_the_sandbox_note_is_shown():
    r = Case().report()
    assert any(f.source == "machine_test" for f in r.strengths)
    mt = next(s for s in r.rounds if s.round_name == "machine_test")
    assert any("sandbox" in n for n in mt.notes) and any("coding-two-sum" in f for f in mt.key_facts)


def test_a_machine_test_that_passes_visible_but_fails_hidden_cases_is_a_medium_risk():
    r = Case(machine_test=make_machine_test(hidden_fail=True)).report()
    hit = [x for x in r.risk_indicators if "special-casing" in x.message or "visible" in x.message.lower()]
    assert hit and hit[0].severity is Severity.MEDIUM and hit[0].category == "machine_test"


# ---------------------------------------------------------------------------
# Missing and not-applicable rounds
# ---------------------------------------------------------------------------

def test_a_missing_round_is_not_yet_available_and_explicitly_not_zero():
    r = Case(machine_test=None).report()
    mt = next(s for s in r.rounds if s.round_name == "machine_test")
    assert mt.status == "missing" and mt.score is None and "NOT counted as zero" in mt.headline
    assert any(x.category == "evidence" and x.severity is Severity.MEDIUM for x in r.risk_indicators)


def test_a_round_the_role_does_not_use_is_marked_not_used():
    case = Case(role=NON_TECH, technical=None, machine_test=None)
    r = case.report()
    for name in ("technical_interview", "machine_test"):
        section = next(s for s in r.rounds if s.round_name == name)
        assert section.status == "not_applicable" and "Not used for this role" in section.headline
    assert not any(x.category == "evidence" for x in r.risk_indicators)


def test_a_scored_round_without_detail_objects_shows_its_score_and_says_detail_is_missing():
    case = Case()
    r = generate_hiring_report(case.decision, case.score, generated_at=AT)            # no round result objects supplied
    ats = next(s for s in r.rounds if s.round_name == "ats")
    assert ats.status == "scored" and ats.score is not None and any("only its score is shown" in n for n in ats.notes)


def test_all_five_rounds_always_appear_in_the_report():
    assert [s.round_name for s in Case().report().rounds] == ["ats", "screening", "hr_interview", "technical_interview", "machine_test"]


# ---------------------------------------------------------------------------
# Risk indicators
# ---------------------------------------------------------------------------

def test_a_medium_integrity_tag_is_a_medium_risk_and_a_high_tag_is_high():
    medium = Case(integrity=burst_integrity()).report()
    assert any(x.category == "integrity" and x.severity is Severity.MEDIUM for x in medium.risk_indicators)
    high = Case(ats=make_ats(overall=90.0))
    high_decision = decide(compute_from_round_outputs(role_type=TECH, experience_level=EXP, candidate_id="cand-1", integrity_risk_tag="high",
                                                      **high.objs))
    score = compute_from_round_outputs(role_type=TECH, experience_level=EXP, candidate_id="cand-1", integrity_risk_tag="high", **high.objs)
    r = generate_hiring_report(high_decision, score, generated_at=AT, **high.objs)
    assert any(x.category == "integrity" and x.severity is Severity.HIGH for x in r.risk_indicators)


def test_risk_indicators_are_sorted_worst_first():
    r = Case(integrity=burst_integrity(), screening=make_screening(findings=["x"])).report()
    order = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2, Severity.INFO: 3}
    ranks = [order[x.severity] for x in r.risk_indicators]
    assert ranks == sorted(ranks)


def test_behavioral_timing_is_never_rated_above_low_severity():
    r = Case(behavior=make_behavior(spikes=3, focus=20.0)).report()
    behavior_risks = [x for x in r.risk_indicators if x.category == "behavior"]
    assert behavior_risks and all(x.severity in (Severity.LOW, Severity.INFO) for x in behavior_risks)
    assert "Weak evidence" in behavior_risks[0].message


def test_round_disagreement_and_borderline_scores_are_flagged_as_scoring_risks():
    disagree = Case(ats=make_ats(overall=95.0), screening=make_screening(95.0), hr=make_hr(overall=95.0), technical=make_technical(overall=40.0))
    assert any("disagree" in x.message.lower() or "differ" in x.message.lower() for x in disagree.report().risk_indicators)


def test_low_confidence_is_listed_as_a_risk():
    r = Case(technical=None, machine_test=None, hr=None).report()
    assert r.recommendation["confidence_band"] == "low"
    assert any(x.category == "confidence" for x in r.risk_indicators)


def test_risk_indicators_have_no_duplicates():
    r = Case(integrity=burst_integrity()).report()
    keys = [(x.category, x.message) for x in r.risk_indicators]
    assert len(keys) == len(set(keys))


def test_a_clean_candidate_has_no_high_or_medium_risks():
    clean = Case(ats=make_ats(overall=92.0), screening=make_screening(90.0), hr=make_hr(overall=90.0, findings=[]), technical=make_technical(overall=90.0))
    assert not [x for x in clean.report().risk_indicators if x.severity in (Severity.HIGH, Severity.MEDIUM)]


# ---------------------------------------------------------------------------
# Behavioral flags section
# ---------------------------------------------------------------------------

def test_hesitation_is_shown_but_labelled_as_not_used():
    lines = Case(behavior=make_behavior(hesitation=30.0)).report().behavioral_flags
    hes = next(l for l in lines if l.startswith("Verbal hesitation"))
    assert "NOT used" in hes and "30" in hes


def test_integrity_report_flags_are_listed_in_the_behavioral_section():
    lines = Case(integrity=burst_integrity()).report().behavioral_flags
    assert any("MEDIUM" in l and "BURST_SWITCHING" in l for l in lines)


def test_behavioral_section_always_states_that_timing_signals_are_weak():
    assert any("weak evidence" in l for l in Case().report().behavioral_flags)


# ---------------------------------------------------------------------------
# Screening highlights (Day 31)
# ---------------------------------------------------------------------------

def make_screening_report():
    return ScreeningReport("cand-1", "Backend", AT, 70.0, 80.0, [{"answer": "SECRET-ANSWER-TEXT"}], ["clear"], ["vague"], ["notice period not stated"],
                           ReportHighlights([{"amount": 1200000, "currency": "INR", "note": None}], [{"notice_days": 30}], ["python", "sql"]))


def test_screening_highlights_show_skills_salary_availability_and_missing_data():
    h = Case().report(screening_report=make_screening_report()).screening_highlights
    assert h["confirmed_skills"] == ["python", "sql"] and "amount: 1200000" in h["salary_expectation"][0]
    assert "note" not in h["salary_expectation"][0] and h["availability"] == ["notice_days: 30"] and h["missing_data"] == ["notice period not stated"]


def test_raw_screening_answers_never_appear_in_any_export():
    r = Case().report(screening_report=make_screening_report())
    for text in (r.to_json(), r.to_markdown(), r.to_html()):
        assert "SECRET-ANSWER-TEXT" not in text


# ---------------------------------------------------------------------------
# Identity, determinism, schema
# ---------------------------------------------------------------------------

def test_same_inputs_give_the_same_report_id_and_content():
    a, b = Case().report(), Case().report()
    assert a.report_id == b.report_id and a.to_json() == b.to_json()


def test_the_report_id_ignores_the_timestamp_but_changes_with_content():
    case = Case()
    early = generate_hiring_report(case.decision, case.score, generated_at="2026-01-01T00:00:00+00:00", **case.objs)
    late = generate_hiring_report(case.decision, case.score, generated_at="2027-01-01T00:00:00+00:00", **case.objs)
    other = Case(ats=make_ats(skill=60.0)).report()
    assert early.report_id == late.report_id and early.report_id != other.report_id and early.report_id.startswith("HIR-")


def test_generated_at_defaults_to_an_iso_timestamp():
    case = Case()
    r = generate_hiring_report(case.decision, case.score)
    assert "T" in r.generated_at and r.generated_at.endswith("+00:00")


def test_json_export_is_valid_versioned_and_complete():
    data = json.loads(Case().report().to_json())
    for key in ("schema_version", "report_id", "generated_at", "confidentiality", "candidate", "recommendation", "executive_summary", "strengths",
                "weaknesses", "risk_indicators", "rounds", "behavioral_flags", "score_breakdown", "rule_trace", "about"):
        assert key in data
    assert data["schema_version"] == "1.0" and data["recommendation"]["automated_action"] == "none"
    assert data["candidate"]["id"] == "cand-1" and "CONFIDENTIAL" in data["confidentiality"]


def test_json_contains_plain_values_only():
    data = Case().report().to_dict()
    json.dumps(data)                         # would raise on enums or objects
    assert data["strengths"][0]["kind"] == "strength" and data["risk_indicators"][0]["severity"] in ("high", "medium", "low", "info")


def test_the_report_does_not_include_per_answer_transcript_style_fields():
    text = Case().report().to_json()
    for banned in ("response_text", "transcript", "question_id"):
        assert banned not in text


# ---------------------------------------------------------------------------
# Markdown and HTML renderers
# ---------------------------------------------------------------------------

def test_markdown_has_the_expected_sections_in_reading_order():
    md = Case().report().to_markdown()
    order = ["# Hiring Intelligence Report", "## Executive summary", "## Recommendation", "## Strengths", "## Weaknesses", "## Risk indicators",
             "## Behavioral flags", "## Round-by-round results", "## How the Hiring Fit was calculated", "## Decision rule trace", "## About this report"]
    positions = [md.index(h) for h in order]
    assert positions == sorted(positions)


def test_markdown_escapes_pipes_and_formatting_characters():
    case = Case()
    r = generate_hiring_report(case.decision, case.score, generated_at=AT, candidate_label="a|b*c_d[e]", **case.objs)
    md = r.to_markdown()
    assert "a\\|b\\*c\\_d\\[e\\]" in md


def test_html_is_a_self_contained_printable_page():
    html_text = Case().report().to_html()
    assert html_text.startswith("<!DOCTYPE html>") and "@page" in html_text and "@media print" in html_text
    for forbidden in ("<script", "http://", "https://", "src=", "<link", "<img"):
        assert forbidden not in html_text


def test_html_escapes_hostile_candidate_text():
    case = Case(cid="<script>alert(1)</script>")
    r = case.report(candidate_label="<img src=x onerror=alert(1)>")
    ats = make_ats()
    ats.components[0].details["missing_skills"] = ["<b>evil</b>"]
    r2 = generate_hiring_report(case.decision, case.score, ats=ats, generated_at=AT, candidate_label="<img src=x onerror=alert(1)>")
    for page in (r.to_html(), r2.to_html()):
        assert "<script>" not in page and "<img" not in page and "<b>evil</b>" not in page
    assert "&lt;img src=x onerror=alert(1)&gt;" in r.to_html() and "&lt;b&gt;evil&lt;/b&gt;" in r2.to_html()


def test_html_banner_has_a_text_label_not_only_a_colour():
    page = Case().report().to_html()
    assert 'class="banner' in page and "HOLD / REVIEW" in page or "SELECTED" in page or "REJECTION" in page


def test_html_banner_class_matches_the_outcome():
    for case in (Case(), Case(technical=None, machine_test=None)):
        r = case.report()
        assert f'banner {r.recommendation["outcome"]}' in r.to_html()


def test_all_three_formats_carry_the_same_key_facts():
    r = Case().report()
    outputs = {"json": r.to_json(), "md": r.to_markdown(), "html": r.to_html()}
    area = r.strengths[0].area
    for fmt, text in outputs.items():
        assert r.report_id.replace("_", "\\_" if fmt == "md" else "_") in text or r.report_id in text
        assert r.recommendation["outcome_label"].split(" (")[0] in text
        assert "CONFIDENTIAL" in text and "sandbox" in text
        assert (area.replace("_", "\\_") if fmt == "md" else area) in text and f"{r.recommendation['hiring_fit_percentage']}" in text


def test_the_about_section_is_present_in_every_format():
    r = Case().report()
    for text in (r.to_json(), r.to_markdown(), r.to_html()):
        assert "no language model" in text.lower()
        assert "bias audit" in text.lower().replace("_", " ")
    assert set(r.about["not_implemented"]) == set(NOT_IMPLEMENTED) and r.about["limitations"] == LIMITATIONS


def test_the_rule_trace_lists_every_decision_rule():
    r = Case().report()
    assert [t["rule_id"] for t in r.rule_trace][0] == "R1_EVIDENCE_COMPLETE" and len(r.rule_trace) == len(Case().decision.rule_trace)
    assert "R7\\_REJECTION\\_NEEDS\\_HUMAN" in r.to_markdown()          # markdown escapes underscores; it renders normally
    assert "R7_REJECTION_NEEDS_HUMAN" in r.to_html()


def test_score_breakdown_shows_profile_weights_and_sensitivity():
    b = Case().report().score_breakdown
    assert b["weight_profile_id"] == "technical/experienced/v1" and len(b["contributions"]) == 5 and b["sensitivity"]
    assert "Hiring Fit if a round were left out" in Case().report().to_markdown()


def test_long_findings_lists_are_trimmed_in_markdown_and_html_but_complete_in_json():
    r = Case(ats=make_ats(95, 90, 85, 90), screening=make_screening(90.0), hr=make_hr(90, 90, 90, 90, []),
             technical=make_technical({"react": 95.0, "node": 92.0, "sql": 90.0, "git": 88.0}, 0, 4, 90.0)).report()
    assert len(r.strengths) > 8
    md = r.to_markdown()
    assert f"{len(r.strengths) - 8} more strength(s) not shown here" in md and f"lists all {len(r.strengths)}" in md
    assert f"{len(r.strengths) - 8} more strength(s) not shown here" in r.to_html()
    assert len(json.loads(r.to_json())["strengths"]) == len(r.strengths)


def test_short_findings_lists_show_no_trimming_note():
    assert "not shown here" not in Case(ats=make_ats(60, 60, 60, 60), screening=ScreeningScoreResult(55.0, [qscore("skills", 55.0)]),
                                        hr=make_hr(60, 60, 60, 60, []), technical=make_technical({"react": 60.0}, 0, 2, 60.0),
                                        machine_test=None).report().to_markdown()


def test_long_skill_lists_are_truncated():
    ats = make_ats()
    ats.components[0].details["matched_skills"] = [f"skill{i}" for i in range(20)]
    r = Case(ats=ats).report()
    fact = next(f for s in r.rounds if s.round_name == "ats" for f in s.key_facts if f.startswith("Matched skills"))
    assert "(+12 more)" in fact


# ---------------------------------------------------------------------------
# Preview and export
# ---------------------------------------------------------------------------

def test_preview_contains_only_the_basic_outcome_and_score():
    r = Case().report()
    preview = r.to_preview_dict()
    assert set(preview) == {"schema_version", "report_id", "candidate_id", "outcome", "hiring_fit_percentage", "access_level", "note"}
    assert preview["access_level"] == "preview"
    data_text = json.dumps({k: v for k, v in preview.items() if k != "note"}).lower()
    for hidden in ("strength", "weakness", "risk", "react", "confidence", "reasons"):
        assert hidden not in data_text


def test_export_writes_each_requested_format_named_by_the_report_id():
    r = Case().report()
    folder = os.path.join(tempfile.mkdtemp(), "exports")
    paths = export_report(r, folder)
    assert set(paths) == {"json", "md", "html"}
    for fmt, path in paths.items():
        assert os.path.basename(path) == f"{r.report_id}.{fmt}" and os.path.getsize(path) > 0
    with open(paths["json"], encoding="utf-8") as fh:
        assert json.load(fh)["report_id"] == r.report_id
    with open(paths["html"], encoding="utf-8") as fh:
        assert fh.read() == r.to_html()


def test_export_can_write_a_single_format():
    r = Case().report()
    paths = export_report(r, tempfile.mkdtemp(), formats=("md",))
    assert list(paths) == ["md"]


def test_export_rejects_unsupported_formats_and_points_to_printing_html_for_pdf():
    with pytest.raises(ValueError) as err:
        export_report(Case().report(), tempfile.mkdtemp(), formats=("pdf",))
    assert "print the HTML" in str(err.value)


def test_export_file_names_never_come_from_candidate_text():
    folder = tempfile.mkdtemp()
    r = Case(cid="../../evil").report()
    paths = export_report(r, folder)
    for path in paths.values():
        assert os.path.dirname(os.path.abspath(path)) == os.path.abspath(folder)
        assert ".." not in os.path.basename(path)


# ---------------------------------------------------------------------------
# Whole-pipeline integration
# ---------------------------------------------------------------------------

def test_full_pipeline_with_every_optional_input_produces_a_coherent_report():
    case = Case(behavior=make_behavior(spikes=2, focus=30.0, hesitation=20.0), integrity=burst_integrity())
    r = case.report(screening_report=make_screening_report(), role_title="Backend Developer", candidate_label="Candidate 1")
    assert r.candidate_label == "Candidate 1" and r.role_title == "Backend Developer"
    assert r.recommendation["outcome"] == case.decision.outcome.value
    assert r.screening_highlights and r.behavioral_flags and r.risk_indicators and r.strengths and r.weaknesses
    for text in (r.to_json(), r.to_markdown(), r.to_html()):
        assert "Backend Developer" in text


def test_candidate_label_defaults_to_the_candidate_id():
    assert Case(cid="cand-77").report().candidate_label == "cand-77"


def test_a_candidate_with_no_scored_rounds_still_produces_a_report():
    score = compute_cross_round_score([], TECH, EXP, "empty")
    decision = decide(score)
    r = generate_hiring_report(decision, score, generated_at=AT)
    assert r.recommendation["hiring_fit_percentage"] is None and "n/a" in " ".join(r.executive_summary)
    assert all(s.status == "missing" for s in r.rounds)
    r.to_markdown(), r.to_html(), r.to_json()
