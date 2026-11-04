import copy
import json
from pathlib import Path

import pytest

from parsers.roadmap_planner import Backlog, Feature, build_order, load_backlog, not_recommended, render_markdown, roadmap_by_phase, validate_backlog

PATH = "data/roadmap/day58_feature_backlog.json"
ROOT = "."


@pytest.fixture()
def backlog():
    return load_backlog(PATH)


def mutated(backlog, fid, **changes):
    b = copy.deepcopy(backlog)
    f = b.by_id()[fid]
    for k, v in changes.items():
        setattr(f, k, v)
    return b


def problems(b, root=None):
    return validate_backlog(b, root)


# ------------------------------------------------------------------ the real backlog
def test_the_real_backlog_is_internally_consistent_and_every_module_it_names_exists(backlog):
    assert problems(backlog, ROOT) == []


def test_shape_of_the_real_backlog(backlog):
    assert len(backlog.features) == 24 and len({f.id for f in backlog.features}) == 24
    assert [p["phase"] for p in backlog.phases] == [0, 1, 2, 3, 4]
    assert {f.id for f in not_recommended(backlog)} == {"V2", "V3", "V5"}


def test_the_prohibited_emotion_inference_is_excluded_and_flagged_for_a_decision(backlog):
    v2 = backlog.by_id()["V2"]
    assert v2.legal_status == "prohibited_in_recruitment_eu" and v2.evidence == "contradicted" and v2.affect_inference and not v2.scheduled and v2.decision_needed
    assert "Phases 18, 41 and 87" in v2.title and "Emotion & confidence analysis" in v2.title
    assert not any(f.scheduled and f.affect_inference for f in backlog.features)


def test_regulatory_deadlines_land_early(backlog):
    due = {f.id: f.phase for f in backlog.features if f.deadline}
    assert due == {"F4": 1, "F6": 2}


def test_the_quick_wins_are_first(backlog):
    p1 = {f.id for f in backlog.features if f.phase == 1}
    assert p1 == {"F1", "F2", "F3", "F4", "R1", "C1"}


def test_every_source_is_cited_somewhere_and_every_citation_resolves(backlog):
    cited = {s for f in backlog.features for s in f.source_ids}
    assert cited <= set(backlog.sources) and set(backlog.sources) - cited == set()


def test_candidate_facing_coaching_is_firewalled_from_hiring(backlog):
    guards = " ".join(backlog.by_id()["C2"].guardrails).lower()
    assert "firewalled" in guards and "different question variants" in guards and "opt-in" in guards


# -------------------------------------------------------------------- ordering and score
def test_priority_score_formula(backlog):
    c1 = backlog.by_id()["C1"]
    assert c1.priority_score == 2 * 5 + 5 - 1 == 14
    assert backlog.by_id()["V2"].priority_score is None


def test_build_order_respects_dependencies_and_phases(backlog):
    order = build_order(backlog)
    pos = {f.id: i for i, f in enumerate(order)}
    assert len(order) == 21
    for f in order:
        assert all(pos[d] < pos[f.id] for d in f.depends_on)
    assert [f.phase for f in order] == sorted(f.phase for f in order)


def test_roadmap_by_phase_covers_every_scheduled_feature_once(backlog):
    flat = [f.id for fs in roadmap_by_phase(backlog).values() for f in fs]
    assert len(flat) == len(set(flat)) == 21 and roadmap_by_phase(backlog)[0] == []


def test_markdown_lists_every_feature_and_the_exclusions(backlog):
    md = render_markdown(backlog)
    assert all(f"| {f.id} |" in md for f in backlog.features if f.scheduled)
    assert "Not recommended (decision needed)" in md and "V2" in md and "V3" in md and "V5" in md


# --------------------------------------------------------- each rule fires when broken
@pytest.mark.parametrize("fid,changes,needle", [
    ("V2", dict(phase=3), "prohibited in recruitment"),
    ("V2", dict(legal_status="allowed", phase=3), "evidence is contradicted"),
    ("V3", dict(phase=3, guardrails=["x"], success_metric="m"), "infers emotion"),
    ("V3", dict(decision_needed=False), "decision_needed"),
    ("C2", dict(guardrails=[]), "no guardrails"),
    ("C1", dict(success_metric=None), "no success metric"),
    ("F4", dict(phase=3), "regulatory deadline"),
    ("F6", dict(phase=None), "not scheduled"),
    ("S3", dict(guardrails=[], legal_status="allowed"), "unvalidated evidence"),
    ("C3", dict(depends_on=["NOPE"]), "unknown feature"),
    ("C3", dict(depends_on=["C3"]), "depends on itself"),
    ("C3", dict(phase=1), "later phase"),
    ("F1", dict(source_ids=["MISSING"]), "unknown source"),
    ("F1", dict(value=9), "value must be"),
    ("F1", dict(effort=0), "effort must be"),
    ("F1", dict(feasibility=True), "feasibility must be"),
    ("F1", dict(legal_status="legal-ish"), "unknown legal_status"),
    ("F1", dict(evidence="vibes"), "unknown evidence"),
    ("F1", dict(phase=7), "not a defined phase"),
    ("F1", dict(builds_on=["parsers/does_not_exist.py"]), "does not exist"),
])
def test_each_validation_rule_fires(backlog, fid, changes, needle):
    found = problems(mutated(backlog, fid, **changes), ROOT)
    assert any(needle in p for p in found), found


def test_a_scheduled_feature_cannot_depend_on_an_unscheduled_one(backlog):
    b = mutated(backlog, "F2", depends_on=["V5"])
    assert any("which is not scheduled" in p for p in problems(b))


def test_dependency_cycles_are_found(backlog):
    b = mutated(backlog, "F1", depends_on=["F4"])
    assert any("dependency cycle" in p for p in problems(b))


def test_duplicate_ids_are_found(backlog):
    b = copy.deepcopy(backlog)
    b.features.append(copy.deepcopy(b.features[0]))
    assert any("duplicate feature id" in p for p in problems(b))


def test_build_order_refuses_an_impossible_backlog(backlog):
    b = mutated(backlog, "F1", depends_on=["F4"])
    with pytest.raises(ValueError):
        build_order(b)


def test_the_backlog_file_states_that_estimates_are_judgement_and_not_legal_advice():
    note = json.loads(Path(PATH).read_text(encoding="utf-8"))["_note"]
    assert "judgement, not measurement" in note and "NOT legal advice" in note
