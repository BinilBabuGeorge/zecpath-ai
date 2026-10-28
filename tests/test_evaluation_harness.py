import pytest

from parsers.evaluation_harness import (
    ClassMetrics,
    LeaveOneOutResult,
    SweepPoint,
    compare_runs,
    cost_weighted_error,
    evaluate_predictions,
    leave_one_out,
    param_grid,
    plateau,
    sweep_parameters,
    wilson_interval,
)


# ---------------------------------------------------------------------------
# Wilson interval
# ---------------------------------------------------------------------------

def test_wilson_interval_known_values():
    lo, hi = wilson_interval(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-3) and hi == pytest.approx(0.7634, abs=1e-3)
    lo, hi = wilson_interval(10, 12)           # "83% of 12" is really about 55% to 95%
    assert lo == pytest.approx(0.552, abs=1e-3) and hi == pytest.approx(0.953, abs=1e-3)


def test_wilson_interval_extremes_stay_inside_zero_and_one():
    assert wilson_interval(0, 10)[0] == 0.0 and wilson_interval(10, 10)[1] == 1.0
    lo, hi = wilson_interval(10, 10)
    assert 0.7 < lo < 1.0                       # perfect score on 10 cases is NOT proof of perfection


def test_wilson_interval_with_no_data_is_the_whole_range():
    assert wilson_interval(0, 0) == (0.0, 1.0)


def test_wilson_interval_narrows_as_n_grows():
    narrow = wilson_interval(80, 100)
    wide = wilson_interval(8, 10)
    assert (narrow[1] - narrow[0]) < (wide[1] - wide[0])


def test_wilson_interval_rejects_impossible_counts():
    for bad in ((-1, 5), (6, 5)):
        with pytest.raises(ValueError):
            wilson_interval(*bad)


# ---------------------------------------------------------------------------
# evaluate_predictions
# ---------------------------------------------------------------------------

TRUTH = ["a", "a", "a", "b", "b", "c"]
PRED = ["a", "a", "b", "b", "a", "c"]


def test_accuracy_and_counts():
    r = evaluate_predictions(TRUTH, PRED)
    assert (r.n, r.correct) == (6, 4) and r.accuracy == pytest.approx(4 / 6)


def test_confusion_matrix_is_indexed_true_then_predicted():
    r = evaluate_predictions(TRUTH, PRED)
    assert r.confusion["a"] == {"a": 2, "b": 1, "c": 0}
    assert r.confusion["b"] == {"a": 1, "b": 1, "c": 0}
    assert r.confusion["c"] == {"a": 0, "b": 0, "c": 1}


def test_per_class_precision_recall_f1_and_error_counts():
    m = evaluate_predictions(TRUTH, PRED).per_class
    assert m["a"].precision == pytest.approx(2 / 3) and m["a"].recall == pytest.approx(2 / 3)
    assert m["b"].false_positives == 1 and m["b"].false_negatives == 1
    assert m["c"].f1 == 1.0 and m["c"].support == 1
    assert m["a"].f1 == pytest.approx(2 / 3)


def test_errors_list_names_every_wrong_case_with_ids():
    r = evaluate_predictions(TRUTH, PRED, ids=["w", "x", "y", "z", "u", "v"])
    assert r.errors == [{"id": "y", "true": "a", "predicted": "b"}, {"id": "u", "true": "b", "predicted": "a"}]


def test_a_class_never_predicted_has_zero_precision_not_an_error():
    r = evaluate_predictions(["a", "b"], ["a", "a"], labels=["a", "b"])
    assert r.per_class["b"].precision == 0.0 and r.per_class["b"].recall == 0.0 and r.per_class["b"].f1 == 0.0


def test_declared_labels_can_include_unseen_classes():
    r = evaluate_predictions(["a"], ["a"], labels=["a", "b", "c"])
    assert set(r.confusion) == {"a", "b", "c"} and r.per_class["c"].support == 0


def test_empty_input_gives_zero_accuracy_and_the_whole_interval():
    r = evaluate_predictions([], [])
    assert r.n == 0 and r.accuracy == 0.0 and r.accuracy_ci == (0.0, 1.0)


def test_mismatched_lengths_and_unknown_labels_are_rejected():
    with pytest.raises(ValueError):
        evaluate_predictions(["a"], ["a", "b"])
    with pytest.raises(ValueError):
        evaluate_predictions(["a"], ["a"], ids=[1, 2])
    with pytest.raises(ValueError):
        evaluate_predictions(["a", "z"], ["a", "a"], labels=["a"])


def test_result_serialises_to_plain_values():
    import json
    data = evaluate_predictions(TRUTH, PRED).to_dict()
    json.dumps(data)
    assert data["accuracy"] == pytest.approx(0.6667, abs=1e-4) and data["per_class"]["a"]["support"] == 3


# ---------------------------------------------------------------------------
# compare_runs
# ---------------------------------------------------------------------------

def test_compare_runs_separates_fixed_from_newly_broken():
    truth = {1: "x", 2: "x", 3: "x", 4: "x"}
    before = {1: "x", 2: "y", 3: "y", 4: "x"}
    after = {1: "y", 2: "x", 3: "y", 4: "x"}
    c = compare_runs(truth, before, after)
    assert c.fixed == [2] and c.newly_broken == [1] and c.still_wrong == [3] and sorted(c.still_right) == [4]
    assert c.net_change == 0                      # a flat headline hides one fix and one regression


def test_compare_runs_requires_identical_case_sets():
    with pytest.raises(ValueError):
        compare_runs({1: "x"}, {1: "x"}, {2: "x"})


def test_compare_runs_reports_a_pure_improvement():
    c = compare_runs({1: "x", 2: "x"}, {1: "y", 2: "y"}, {1: "x", 2: "x"})
    assert c.net_change == 2 and not c.newly_broken
    assert c.to_dict()["fixed"] == [1, 2]


# ---------------------------------------------------------------------------
# cost_weighted_error
# ---------------------------------------------------------------------------

def test_cost_weighted_error_uses_asymmetric_costs():
    truth = ["good", "good", "bad", "bad"]
    pred = ["bad", "good", "good", "bad"]
    costs = {("good", "bad"): 5.0, ("bad", "good"): 1.0}            # wrongly rejecting a good candidate costs 5x
    assert cost_weighted_error(truth, pred, costs) == pytest.approx((5.0 + 1.0) / 4)


def test_cost_weighted_error_defaults_and_empty():
    assert cost_weighted_error(["a", "b"], ["b", "b"], {}, default_cost=2.0) == pytest.approx(1.0)
    assert cost_weighted_error([], [], {}) == 0.0
    with pytest.raises(ValueError):
        cost_weighted_error(["a"], [], {})


# ---------------------------------------------------------------------------
# param_grid, sweep, plateau
# ---------------------------------------------------------------------------

def threshold_classifier(item, params):
    return "hi" if item >= params["cut"] else "lo"


def test_param_grid_is_a_deterministic_cartesian_product():
    grid = param_grid(b=[1, 2], a=[10, 20])
    assert grid == [{"a": 10, "b": 1}, {"a": 10, "b": 2}, {"a": 20, "b": 1}, {"a": 20, "b": 2}]
    assert param_grid() == [{}]


def test_sweep_scores_every_grid_point():
    items = [1, 2, 8, 9]
    truth = ["lo", "lo", "hi", "hi"]
    pts = sweep_parameters(items, truth, threshold_classifier, param_grid(cut=[0, 5, 10]))
    assert [p.correct for p in pts] == [2, 4, 2] and pts[1].accuracy == 1.0


def test_plateau_returns_every_tied_best_point():
    items, truth = [1, 2, 8, 9], ["lo", "lo", "hi", "hi"]
    pts = sweep_parameters(items, truth, threshold_classifier, param_grid(cut=[3, 4, 5, 6, 7, 20]))
    best = plateau(pts)
    assert [p.params["cut"] for p in best] == [3, 4, 5, 6, 7]          # a wide plateau: the exact cut does not matter


def test_a_sharp_peak_has_a_one_point_plateau():
    items, truth = [1, 5, 6, 9], ["lo", "lo", "hi", "hi"]
    pts = sweep_parameters(items, truth, threshold_classifier, param_grid(cut=[2, 5.5, 8]))
    assert [p.params["cut"] for p in plateau(pts)] == [5.5]


def test_sweep_and_plateau_edge_cases():
    assert plateau([]) == []
    with pytest.raises(ValueError):
        sweep_parameters([1], [], threshold_classifier, [{"cut": 1}])


# ---------------------------------------------------------------------------
# leave_one_out
# ---------------------------------------------------------------------------

def test_leave_one_out_on_cleanly_separable_data_has_no_optimism():
    items = [1, 2, 3, 7, 8, 9]
    truth = ["lo", "lo", "lo", "hi", "hi", "hi"]
    r = leave_one_out(items, truth, threshold_classifier, param_grid(cut=[float(x) for x in range(0, 12)]))
    assert r.in_sample_accuracy == 1.0 and r.leave_one_out_accuracy == 1.0 and r.optimism == 0.0


def test_leave_one_out_exposes_overfitting_to_noise():
    # One mislabelled-looking case forces a threshold that only works by memorising it.
    items = [1, 2, 3, 4, 5, 6, 7, 8]
    truth = ["lo", "lo", "hi", "lo", "lo", "hi", "hi", "hi"]           # the 3 -> "hi" is noise
    r = leave_one_out(items, truth, threshold_classifier, param_grid(cut=[float(x) / 2 for x in range(0, 20)]))
    assert r.leave_one_out_accuracy < r.in_sample_accuracy and r.optimism > 0


def test_leave_one_out_records_one_row_per_case_with_the_chosen_parameters():
    items = [1, 2, 8, 9]
    r = leave_one_out(items, ["lo", "lo", "hi", "hi"], threshold_classifier, param_grid(cut=[0.0, 5.0, 10.0]))
    assert len(r.per_case) == 4 and all("chosen_params" in row for row in r.per_case)


def test_leave_one_out_tie_break_is_deterministic_and_central():
    items = [1, 2, 8, 9]
    grid = param_grid(cut=[3.0, 4.0, 5.0, 6.0, 7.0])
    first = leave_one_out(items, ["lo", "lo", "hi", "hi"], threshold_classifier, grid)
    second = leave_one_out(items, ["lo", "lo", "hi", "hi"], threshold_classifier, grid)
    assert first.per_case == second.per_case
    assert all(row["chosen_params"]["cut"] in (4.0, 5.0, 6.0) for row in first.per_case)      # the middle of the plateau, not an edge


def test_leave_one_out_needs_at_least_two_cases():
    with pytest.raises(ValueError):
        leave_one_out([1], ["lo"], threshold_classifier, param_grid(cut=[1.0]))


def test_leave_one_out_result_serialises_with_a_confidence_interval():
    r = leave_one_out([1, 2, 8, 9], ["lo", "lo", "hi", "hi"], threshold_classifier, param_grid(cut=[0.0, 5.0, 10.0]))
    data = r.to_dict()
    assert data["leave_one_out_ci_95"][0] < data["leave_one_out_accuracy"] <= data["leave_one_out_ci_95"][1]


def test_dataclass_properties_handle_empty_cases():
    assert SweepPoint({}, 0, 0).accuracy == 0.0
    assert LeaveOneOutResult(0, 0, 0).in_sample_accuracy == 0.0 and LeaveOneOutResult(0, 0, 0).optimism == 0.0
    assert ClassMetrics(1.0, 1.0, 1.0, 1, 0, 0).to_dict()["f1"] == 1.0
