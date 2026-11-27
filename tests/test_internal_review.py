"""
Day 64 tests: the internal review is repeatable, honest about feedback, and its documents quote the evidence

WHAT IS CHECKED
  * the small maths the probes use (rank, Spearman) is right;
  * the evidence has every probe and the deterministic part equals what was committed (re-run `python run_day64_internal_review.py` if not);
  * the improvement list follows its own rules: unique ids, every field present, the priority is the published formula, harm items at impact 4
    or 5 are P0, every Day 58 link exists, every dependency exists, three items are gates, every item is in exactly one wave;
  * the acceptance targets point at real improvements and are computed from the evidence;
  * reviewer feedback is NEVER invented: the committed log is empty or the documents say how many entries it holds; a recorded entry becomes a
    triage item; an empty log adds nothing;
  * the four documents quote the numbers of the evidence (counts, negative controls, the worst file-format gap) and every P0 item appears in
    the list and the plan.

WHAT IS NOT PINNED. Individual probe values are not asserted (a legitimate fix will change them, and that is the point of the targets).
Timings are excluded everywhere: they differ by machine.
"""

import json
import tempfile
from pathlib import Path

from parsers import internal_review as ir
from parsers import review_plan as rp

ROOT = Path(__file__).resolve().parent.parent
REVIEW = ROOT / "data" / "review"
DOCS = ROOT / "docs"
REPORT = (DOCS / "day64_internal_review_report.md")
LIST = (DOCS / "day64_improvement_list.md")
PLAN = (DOCS / "day64_action_plan.md")
KIT = (DOCS / "day64_review_session_kit.md")
REQUIRED = ("id", "area", "title", "problem", "fix", "impact", "confidence", "effort_days", "harm", "links", "acceptance", "decision_needed", "depends_on",
            "priority", "priority_score", "gate_before_real_use", "basis")

_EV = None


def _evidence():
    global _EV
    if _EV is None:
        _EV = ir.collect_evidence(measure_performance=False)
    return _EV


def _items():
    ev = _evidence()
    items = rp.improvements(dict(ev, performance_measured=json.loads((REVIEW / "day64_performance_measured.json").read_text(encoding="utf-8"))))
    rp.merge_feedback(items)
    return items


# ------------------------------------------------------------------------------------------------------------ the maths
def test_rank_gives_tied_values_the_average_rank():
    assert list(ir._rank([10, 20, 20, 30])) == [1.0, 2.5, 2.5, 4.0]


def test_spearman_is_one_for_the_same_order_and_minus_one_for_the_reverse():
    assert round(ir.spearman([1, 2, 3, 4], [10, 20, 30, 40]), 6) == 1.0
    assert round(ir.spearman([1, 2, 3, 4], [40, 30, 20, 10]), 6) == -1.0
    assert ir.spearman([1, 1, 1], [1, 2, 3]) == 0.0           # no variation, no agreement to measure


# ------------------------------------------------------------------------------------------------------------ evidence
def test_the_evidence_contains_every_probe():
    ev = _evidence()
    assert set(ev) >= {"walkthrough", "accuracy", "ux", "engineering", "findings_from_day63"}
    assert len(ev["walkthrough"]) == 5 and all(len(w["stages"]) >= 4 for w in ev["walkthrough"])
    a = ev["accuracy"]
    for key in ("rank_agreement_with_hiring_fit", "score_spread", "format_invariance", "robustness", "name_swap", "negative_controls", "round_disagreement_flagged"):
        assert key in a, key
    assert len(ev["ux"]["error_rows"]) == 25 and set(ev["ux"]) >= {"error_messages", "reports", "pitfalls"}


def test_the_negative_controls_cover_every_round_and_the_high_scoring_list_is_computed():
    nc = _evidence()["accuracy"]["negative_controls"]
    for key in ("screening_gibberish", "hr_off_topic", "technical_gibberish", "machine_test_broken_code", "ats_unrelated_resume"):
        assert isinstance(nc[key], (int, float)), key
    assert nc["high_scoring_nonsense"] == sorted(k for k, v in nc.items() if isinstance(v, (int, float)) and v >= 50)


def test_the_deterministic_evidence_matches_the_committed_evidence():
    committed = json.loads((REVIEW / "day64_evidence.json").read_text(encoding="utf-8"))
    fresh = json.loads(json.dumps(_evidence()))
    for key in committed:
        if key == "engineering":                              # describes the repository itself, which changes whenever a file is added
            assert set(committed[key]) == set(fresh[key])
            continue
        assert committed[key] == fresh[key], f"{key} changed: run python run_day64_internal_review.py and read what moved"


def test_name_swap_and_demographic_header_do_not_move_the_ats_score():
    ev = _evidence()
    assert ev["accuracy"]["name_swap"]["max_difference"] <= 0.5
    f4 = next(f for f in ev["findings_from_day63"] if f["id"] == "F4")
    assert f4["evidence"]["difference"] <= 0.5


def test_the_recorded_performance_measurements_have_the_stages_and_are_marked_as_measured_here():
    perf = json.loads((REVIEW / "day64_performance_measured.json").read_text(encoding="utf-8"))
    assert {"ats", "screening", "hr_interview", "technical_interview", "whole candidate"} <= set(perf["stage_ms"])
    assert perf["ats_single_process"]["per_second"] > 0 and "one shared machine" in perf["note"]


# ------------------------------------------------------------------------------------------------------------ the improvement list
def test_every_item_has_every_field_and_ids_are_unique():
    items = _items()
    assert len({i["id"] for i in items}) == len(items) >= 20
    for i in items:
        for key in REQUIRED:
            assert key in i, (i["id"], key)
        assert i["area"] in rp.AREAS and 1 <= i["impact"] <= 5 and 1 <= i["confidence"] <= 3 and i["effort_days"] > 0
        assert len(i["problem"]) > 30 and len(i["fix"]) > 20 and i["acceptance"], i["id"]


def test_the_priority_is_the_published_formula():
    for i in _items():
        assert i["priority_score"] == round(i["impact"] * i["confidence"] / i["effort_days"], 1), i["id"]
        if i["harm"] and i["impact"] >= 4:
            assert i["priority"] == "P0", i["id"]
        else:
            assert i["priority"] == ("P1" if i["priority_score"] >= 3.0 else "P2" if i["priority_score"] >= 1.5 else "P3"), i["id"]


def test_links_and_dependencies_point_at_things_that_exist():
    roadmap = {f["id"] for f in json.loads((ROOT / "data" / "roadmap" / "day58_feature_backlog.json").read_text(encoding="utf-8"))["features"]}
    ids = {i["id"] for i in _items()}
    for i in _items():
        assert set(i["links"]) <= roadmap, (i["id"], i["links"])
        assert set(i["depends_on"]) <= ids, (i["id"], i["depends_on"])


def test_three_items_are_gates_before_real_use():
    assert {i["id"] for i in _items() if i["gate_before_real_use"]} == {"GOV-01", "GOV-02", "ACC-13"}


def test_every_problem_statement_quotes_a_measured_number():
    missing = [i["id"] for i in _items() if i["basis"] == "measured" and not any(ch.isdigit() for ch in i["problem"])]
    assert missing == [], missing
    assert {i["id"] for i in _items() if i["basis"] == "design"} == {"ACC-13", "ACC-14", "ENG-07", "GOV-01", "GOV-02"}


# ------------------------------------------------------------------------------------------------------------ targets and plan
def test_acceptance_targets_point_at_real_improvements_and_are_computed():
    ids = {i["id"] for i in _items()}
    targets = rp.acceptance_targets(_evidence())
    assert len(targets) == 11
    for t in targets:
        assert all(part in ids for part in t["improvement"].split("/")) or t["improvement"] == "ACC-06/07", t["id"]
        assert t["met"] == {"<=": t["current"] <= t["goal"], "<": t["current"] < t["goal"], "==": t["current"] == t["goal"]}[t["operator"]], t["id"]


def test_every_item_is_in_exactly_one_wave_and_every_p0_and_p1_is_in_waves_zero_to_two():
    items = {i["id"]: i for i in _items() if not i["id"].startswith("FB-")}
    placed = [x for w in rp.WAVES for x in w["items"]]
    assert sorted(placed) == sorted(items) and len(placed) == len(set(placed))
    early = {x for w in rp.WAVES[:3] for x in w["items"]}
    assert all(i in early for i, it in items.items() if it["priority"] in ("P0", "P1"))


def test_a_dependency_is_never_scheduled_after_the_item_that_needs_it():
    wave_of = {x: n for n, w in enumerate(rp.WAVES) for x in w["items"]}
    for i in _items():
        for d in i["depends_on"]:
            if i["id"] in wave_of:
                assert wave_of[d] <= wave_of[i["id"]], (i["id"], d)


# ------------------------------------------------------------------------------------------------------------ feedback is never invented
def test_an_empty_feedback_log_adds_nothing_and_the_committed_log_is_empty_or_reported():
    log = json.loads((REVIEW / "feedback_log.json").read_text(encoding="utf-8"))
    n = len(log["entries"])
    items = rp.improvements(_evidence_with_perf())
    got = rp.merge_feedback(items)
    assert got["count"] == n and sum(1 for i in items if i["id"].startswith("FB-")) == n
    assert f"{n} entries recorded" in REPORT.read_text(encoding="utf-8")


def test_a_recorded_comment_becomes_a_triage_item():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "log.json"
        path.write_text(json.dumps({"entries": [{"reviewer": "AB", "role": "mentor", "date": "2026-11-24", "stage": "Screening", "kind": "accuracy",
                                                 "comment": "Gibberish should not score.", "severity": 5, "suggestion": "gate answers"}]}), encoding="utf-8")
        items = []
        got = rp.merge_feedback(items, path)
        assert got["count"] == 1 and items[0]["id"] == "FB-001" and items[0]["impact"] == 5 and items[0]["from_reviewer"].startswith("AB (mentor)")
        assert items[0]["priority_score"] == round(5 * 2 / 2.0, 1) and items[0]["priority"] == "P1"


def _evidence_with_perf():
    return dict(_evidence(), performance_measured=json.loads((REVIEW / "day64_performance_measured.json").read_text(encoding="utf-8")))


# ------------------------------------------------------------------------------------------------------------ documents quote the evidence
def test_the_report_quotes_the_counts_and_key_measurements():
    text = REPORT.read_text(encoding="utf-8")
    ev = _evidence()
    items = _items()
    counts = {p: sum(1 for i in items if i["priority"] == p) for p in ("P0", "P1", "P2", "P3")}
    assert f"**{len(items)} improvements**" in text and f"**{counts['P0']} at P0**" in text
    a = ev["accuracy"]
    assert f"{a['expected_outcome_met']} of {a['candidates']}" in text
    nc = a["negative_controls"]
    for key in ("screening_gibberish", "hr_off_topic", "technical_gibberish"):
        assert str(nc[key]) in text, key
    fi = a["format_invariance"]
    assert str(abs(fi["worst"]["delta"])) in text and fi["worst"]["id"] in text
    assert f"{a['round_disagreement_flagged']} of {a['candidates']}" in text


def test_every_p0_item_appears_in_the_list_and_the_plan_and_every_wave_is_described():
    list_text, plan_text = LIST.read_text(encoding="utf-8"), PLAN.read_text(encoding="utf-8")
    for i in _items():
        assert f"### {i['id']}:" in list_text, i["id"]
        if i["priority"] == "P0":
            assert i["id"] in plan_text, i["id"]
    for wave in rp.WAVES:
        assert wave["id"] in plan_text and wave["exit"] in plan_text


def test_the_list_states_its_priority_rule_and_the_targets_table_is_complete():
    text = LIST.read_text(encoding="utf-8")
    assert "priority score = impact x confidence / effort" in text and "GATE" in text
    for t in rp.acceptance_targets(_evidence()):
        assert f"| {t['id']} |" in text, t["id"]


def test_the_session_kit_has_the_form_the_log_and_the_agenda():
    text = KIT.read_text(encoding="utf-8")
    for needle in ("Agenda (45 minutes)", "Feedback form", "data/review/feedback_log.json", "FB-001", "No feedback is included in the review report until it is recorded"):
        assert needle in text, needle


def test_the_documents_are_substantial_and_the_csv_matches_the_json():
    assert len(REPORT.read_text(encoding="utf-8").split()) > 3000 and len(LIST.read_text(encoding="utf-8").split()) > 2500
    data = json.loads((REVIEW / "day64_improvement_list.json").read_text(encoding="utf-8"))
    rows = (REVIEW / "day64_improvement_list.csv").read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) - 1 == len(data["items"])
