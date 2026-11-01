import csv
from datetime import date
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from docx import Document

from parsers import experience_parser
from parsers.pipeline_simulation import (GATE_MIN, OUTCOMES, STAGES, ats_vs_human, ats_zone_drift, build_matcher, find_inconsistencies, frozen_today,
                                         funnel_outcome, human_agreement, intent_check, load_human_ratings, load_scenarios, parsed_years_asof,
                                         percentile, reactive_screening_turns, run_journey, screening_isolation_probe, stage_timing,
                                         technical_phrasing_probe, tier_drift, try_upload, upload_resume, write_human_worksheet)

AS_OF = date(2026, 10, 30)
SC_PATH = "data/simulation/day56_scenarios.json"
SAMPLES = Path("data/samples")


@pytest.fixture(scope="module")
def matcher():
    return build_matcher(SAMPLES)


@pytest.fixture(scope="module")
def scenarios():
    return {s.id: s for s in load_scenarios(SC_PATH)}


def docx_of(sc, tmp_path):
    p = tmp_path / f"{sc.id}.docx"
    d = Document()
    for ln in (SAMPLES / "resumes" / f"{sc.resume}.txt").read_text(encoding="utf-8").splitlines():
        d.add_paragraph(ln)
    d.save(str(p))
    return p


def journey(sc, matcher, tmp_path):
    return run_journey(sc, matcher, docx_of(sc, tmp_path), (SAMPLES / "jds" / f"{sc.jd}.txt").read_text(encoding="utf-8"), AS_OF, generated_at="2026-10-30")


# ---------------------------------------------------------------- clock
def test_frozen_today_pins_the_experience_parser_and_restores_it():
    text = "Experience:\n- Engineer, Acme (Jan 2024 - Present)\n"
    with frozen_today(date(2025, 1, 1)):
        a = experience_parser.compute_total_experience(experience_parser.parse_experience(text)).total_years
    with frozen_today(date(2026, 1, 1)):
        b = experience_parser.compute_total_experience(experience_parser.parse_experience(text)).total_years
    assert b - a == pytest.approx(1.0, abs=0.1)
    assert experience_parser.date is date             # the real class is back


def test_parsed_years_depend_on_the_date_for_a_present_job():
    t = (SAMPLES / "resumes" / "resume_01_mern_developer.txt").read_text(encoding="utf-8")
    assert parsed_years_asof(t, date(2026, 10, 30)) > parsed_years_asof(t, date(2025, 1, 1)) + 1.5


# ------------------------------------------------------------- scenarios
def test_scenarios_load_and_are_well_formed(scenarios):
    assert len(scenarios) == 8
    for sc in scenarios.values():
        assert len(sc.screening) == 7 and len(sc.hr) == 6
        assert set(sc.acceptable) <= set(OUTCOMES) and sc.rationale
        assert (SAMPLES / "resumes" / f"{sc.resume}.txt").exists() and (SAMPLES / "jds" / f"{sc.jd}.txt").exists()
        if sc.role_type == "technical":
            assert set(sc.technical) == {"basics", "intermediate", "advanced"} and all(len(v) == 5 for v in sc.technical.values())
        else:
            assert sc.technical is None


def test_scenario_file_says_it_is_scripted_not_human():
    import json
    assert "not independent human judgement" in json.load(open(SC_PATH))["_note"]


# -------------------------------------------------------------- screening
def test_reactive_candidate_reanswers_a_reasked_question_with_the_short_answer(scenarios):
    turns = reactive_screening_turns(scenarios["S1"])
    assert len(turns) > 7                                              # S1's rich introduction is judged off-topic and re-asked
    assert turns[1].text == scenarios["S1"].reask["introduction"]


def test_reactive_candidate_with_no_reask_needed_uses_one_turn_per_category(scenarios):
    assert len(reactive_screening_turns(scenarios["S4"])) <= 8


def test_screening_isolation_probe_flags_exactly_the_four_rich_introductions(scenarios):
    rows = screening_isolation_probe(list(scenarios.values()))
    flagged = {(r["candidate"], r["category"]) for r in rows if r["quality"] in ("off_topic", "missing")}
    assert len(rows) == 56 and flagged == {("S1", "introduction"), ("S2", "introduction"), ("S6", "introduction"), ("S7", "introduction")}


# ----------------------------------------------------------------- upload
def test_docx_upload_extracts_text(scenarios, tmp_path):
    text, _ = upload_resume(docx_of(scenarios["S1"], tmp_path))
    assert "MongoDB" in text and "Ananya" in text


def test_unsupported_and_broken_files_are_reported_never_raised(tmp_path):
    for name, content in [("a.txt", b"x"), ("b.doc", b"\xd0\xcf\x11\xe0"), ("c.pdf", b"not a pdf"), ("d.docx", b"")]:
        p = tmp_path / name; p.write_bytes(content)
        r = try_upload(p)
        assert r["result"] == "error" and r["error"]
    Document().save(str(tmp_path / "blank.docx"))
    assert try_upload(tmp_path / "blank.docx")["result"] == "empty_text"


# ---------------------------------------------------------- end to end
def test_non_technical_journey_runs_every_real_stage_to_a_report(scenarios, matcher, tmp_path):
    j = journey(scenarios["S7"], matcher, tmp_path)
    assert not j.errors and all(s.status != "error" for s in j.stages.values())
    assert j.stages["technical_interview"].status == "skipped" and j.technical is None
    assert j.report is not None and j.outcome == "selected" and not j.score_raw.provisional
    assert set(j.stages) == set(STAGES)


def test_technical_journey_is_pending_evidence_because_no_machine_test_is_run(scenarios, matcher, tmp_path):
    j = journey(scenarios["S2"], matcher, tmp_path)
    assert j.technical is not None and j.score_raw.provisional and "machine_test" in j.score_raw.missing_rounds
    assert j.outcome == "hold_review" and j.decision_raw.hold_kind.value == "pending_evidence" and not j.decision_raw.automation_eligible


def test_every_scripted_candidate_completes_and_no_rejection_is_automatic(scenarios, matcher, tmp_path):
    for sc in scenarios.values():
        j = journey(sc, matcher, tmp_path)
        assert j.report is not None and not j.errors, sc.id
        assert j.decision_raw.automated_action in ("none", None) or "reject" not in str(j.decision_raw.automated_action).lower()


def test_journey_is_deterministic_under_the_frozen_clock(scenarios, matcher, tmp_path):
    a, b = journey(scenarios["S5"], matcher, tmp_path), journey(scenarios["S5"], matcher, tmp_path)
    assert a.score_raw.hiring_fit_percentage == b.score_raw.hiring_fit_percentage and a.tier_used == b.tier_used


def test_resume_dates_move_the_technical_tier_with_the_calendar_alone(scenarios):
    rows = tier_drift({"r": (SAMPLES / "resumes" / "resume_01_mern_developer.txt").read_text(encoding="utf-8")}, date(2025, 1, 1), AS_OF)
    assert rows[0]["tier_a"] == "intermediate" and rows[0]["tier_b"] == "advanced" and rows[0]["changed"]


def test_inflater_is_flagged_and_not_selected(scenarios, matcher, tmp_path):
    j = journey(scenarios["S5"], matcher, tmp_path)
    assert "EXP_CLAIM_VS_RESUME" in {i.code for i in j.inconsistencies} and j.outcome != "selected"


def test_ats_reject_with_strong_interviews_flags_the_gate_bypass_under_zone_aligned_scaling(scenarios, matcher, tmp_path):
    j = journey(scenarios["S8"], matcher, tmp_path)
    codes = {i.code for i in j.inconsistencies}
    assert j.zone == "reject" and j.funnel_stage == "stopped_at_ats"
    assert j.outcome_aligned == "selected" and "ATS_GATE_BYPASSED" in codes


# ------------------------------------------------------------------ funnel
def fj(zone="shortlist", role="technical", screening=80, hr=80, tech=80, ats=True):
    return NS(ats=object() if ats else None, zone=zone, scenario=NS(role_type=role),
              screening=NS(total_score=screening), hr=NS(overall_hr_score=hr), technical=NS(overall_score=tech) if role == "technical" else None)


def test_funnel_stops_where_the_prd_would():
    assert funnel_outcome(fj("reject"))[0] == "stopped_at_ats"
    assert funnel_outcome(fj("review"))[0] == "held_at_ats"
    assert funnel_outcome(fj(screening=GATE_MIN["screening"] - 1))[0] == "stopped_at_screening"
    assert funnel_outcome(fj(hr=10))[0] == "stopped_at_hr_interview"
    assert funnel_outcome(fj(tech=10))[0] == "stopped_at_technical_interview"
    assert funnel_outcome(fj())[0] == "reached_final_decision"
    assert funnel_outcome(fj(role="non_technical"))[0] == "reached_final_decision"
    assert funnel_outcome(fj(ats=False))[0] == "error"


# ----------------------------------------------------------- inconsistencies
def ij(**o):
    base = dict(resume_years_parsed=3.0, resume_years_stated=3.0, claimed_years=3.0, tier_used="intermediate", zone="shortlist", funnel_stage="reached_final_decision",
                screening=NS(total_score=80), hr=NS(overall_hr_score=80), technical=NS(overall_score=80), stages={}, outcome="hold_review", outcome_aligned="hold_review",
                score_raw=NS(provisional=False, missing_rounds=[]), decision_raw=NS(automation_eligible=False),
                decision_aligned=NS(), score_aligned=NS(contributions=[NS(round_name="ats", score=70), NS(round_name="screening", score=80), NS(round_name="hr_interview", score=80)]))
    base.update(o)
    return NS(**base)


def codes(j):
    return {i.code for i in find_inconsistencies(j)}


def test_consistent_candidate_has_no_findings():
    assert codes(ij()) == set()


def test_experience_claim_beyond_tolerance_is_serious_and_within_tolerance_is_not():
    assert "EXP_CLAIM_VS_RESUME" in codes(ij(claimed_years=8.0))
    assert "EXP_CLAIM_VS_RESUME" not in codes(ij(claimed_years=4.0))


def test_claim_matching_either_the_stated_or_the_date_figure_is_accepted():
    assert "EXP_CLAIM_VS_RESUME" not in codes(ij(resume_years_parsed=5.3, resume_years_stated=3.0, claimed_years=5.0))
    assert "EXP_CLAIM_VS_RESUME" not in codes(ij(resume_years_parsed=5.3, resume_years_stated=3.0, claimed_years=3.0))


def test_resume_stated_vs_date_mismatch_and_tier_source():
    c = codes(ij(resume_years_parsed=5.3, resume_years_stated=3.0, tier_used="advanced"))
    assert {"RESUME_STATED_VS_DATES", "TECH_TIER_SOURCE"} <= c


def test_round_spread_needs_three_rounds_and_a_30_point_gap():
    wide = NS(contributions=[NS(round_name="ats", score=70), NS(round_name="screening", score=90), NS(round_name="technical_interview", score=30)])
    assert "ROUND_SPREAD" in codes(ij(score_aligned=wide))
    narrow = NS(contributions=[NS(round_name="ats", score=70), NS(round_name="screening", score=80), NS(round_name="technical_interview", score=60)])
    assert "ROUND_SPREAD" not in codes(ij(score_aligned=narrow))


def test_ats_versus_interview_divergence_in_both_directions():
    assert "ATS_BELOW_INTERVIEWS" in codes(ij(zone="reject"))
    assert "ATS_ABOVE_INTERVIEWS" in codes(ij(screening=NS(total_score=30), hr=NS(overall_hr_score=40), technical=NS(overall_score=20)))


def test_funnel_and_decision_disagreements():
    assert "FUNNEL_VS_DECISION" in codes(ij(funnel_stage="stopped_at_screening", outcome="selected"))
    assert "FUNNEL_VS_DECISION" in codes(ij(outcome="rejected"))
    assert "ATS_GATE_BYPASSED" in codes(ij(funnel_stage="held_at_ats", outcome_aligned="selected"))
    assert "ATS_GATE_BYPASSED" not in codes(ij(funnel_stage="held_at_ats"))
    assert "ATS_SCALE_CHANGES_OUTCOME" in codes(ij(outcome="hold_review", outcome_aligned="selected"))


def test_provisional_evidence_and_stage_errors_are_reported():
    assert "PROVISIONAL_EVIDENCE" in codes(ij(score_raw=NS(provisional=True, missing_rounds=["machine_test"])))
    assert "STAGE_ERROR" in codes(ij(stages={"ats": NS(status="error", stage="ats", note="boom")}))


# ---------------------------------------------------------- AI vs human
def test_ats_agreement_with_the_human_labels_matches_the_day_54_record(matcher):
    rows = ats_vs_human(matcher, AS_OF, SAMPLES)
    assert len(rows) == 12 and sum(r["agree"] for r in rows) == 10
    assert all(r["ai_zone"] in ("shortlist", "review", "reject") for r in rows)


def test_ats_zones_do_not_drift_with_the_calendar_on_the_labelled_pairs(matcher):
    d = ats_zone_drift(matcher, date(2025, 1, 1), AS_OF, samples_dir=SAMPLES)
    assert d["zone_changes"] == 0 and d["pairs"] == 12


def test_human_worksheet_is_blank_for_humans_and_loading_it_back_gives_no_ratings(scenarios, matcher, tmp_path):
    js = [journey(scenarios[k], matcher, tmp_path) for k in ("S1", "S7")]
    p = tmp_path / "ws.csv"
    assert write_human_worksheet(js, p) == 2
    rows = list(csv.DictReader(open(p, encoding="utf-8")))
    assert [r["candidate_id"] for r in rows] == ["S1", "S7"] and all(r["human_final_outcome"] == "" and r["ai_outcome"] for r in rows)
    assert load_human_ratings(p) == {} and load_human_ratings(tmp_path / "missing.csv") == {}


def test_human_agreement_counts_the_costly_disagreements(tmp_path):
    p = tmp_path / "r.csv"
    p.write_text("candidate_id,human_final_outcome\nA,selected\nB,rejected\nC,rejected\nA,hold_review\nZ,selected\nB,not_a_value\n", encoding="utf-8")
    h = load_human_ratings(p)
    assert h == {"A": ["selected", "hold_review"], "B": ["rejected"], "C": ["rejected"], "Z": ["selected"]}
    r = human_agreement({"A": "selected", "B": "selected", "C": "rejected"}, h)
    assert r["ratings"] == 4 and r["agreement"] == 0.5 and r["ai_selected_human_rejected"] == 1 and r["ai_rejected_human_selected"] == 0
    assert human_agreement({"A": "selected"}, {})["agreement"] is None


def test_intent_check_uses_the_acceptable_set():
    j = NS(outcome="hold_review", scenario=NS(acceptable=["hold_review", "rejected"]))
    assert intent_check(j)
    assert not intent_check(NS(outcome="selected", scenario=NS(acceptable=["rejected"])))


# ----------------------------------------------------------- technical probe
def test_characterisation_technical_scoring_is_keyword_driven():
    """Documents CURRENT behaviour (see the Day 56 doc). If the technical scorer is improved, this test should be updated:
    a correct paraphrase should then beat a keyword list."""
    s = technical_phrasing_probe()
    assert set(s) == {"rubric_phrases", "correct_paraphrase", "keyword_salad", "wrong_but_confident"}
    assert s["keyword_salad"] > s["correct_paraphrase"]
    assert s["rubric_phrases"] > s["wrong_but_confident"]


# ------------------------------------------------------------------ performance
def test_percentile_and_stage_timing():
    assert percentile([1, 2, 3, 4, 5], 50) == 3 and percentile([1, 2, 3, 4], 100) == 4 and percentile([], 50) == 0.0
    j = NS(stages={"ats": NS(status="ran", ms=2.0), "upload": NS(status="error", ms=9.0)})
    t = stage_timing([j, j])
    assert t["ats"]["n"] == 2 and "upload" not in t
