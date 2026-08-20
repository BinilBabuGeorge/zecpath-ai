import json
from pathlib import Path

import pytest

from parsers.semantic_matcher import SemanticMatcher
import run_day17_testing as harness

RESUME_DIR = Path("data/samples/resumes")
JD_DIR = Path("data/samples/jds")

# NOTE: these tests validate that the TESTING HARNESS computes correctly
# (confusion matrix arithmetic, precision/recall formulas, ground truth
# structure) -- they deliberately do NOT assert the AI achieves some
# target accuracy. Day 17's actual run found 41.7% agreement with manual
# review; asserting a high accuracy threshold here would just be
# asserting a number we know is false. See docs/day17_testing_report.md
# for the real result and docs/day17_improvement_backlog.md for what
# follows from it.


@pytest.fixture(scope="module")
def matcher():
    resume_files = sorted(RESUME_DIR.glob("*.txt"))
    jd_files = sorted(JD_DIR.glob("*.txt"))
    corpus = [f.read_text() for f in resume_files + jd_files]
    return SemanticMatcher(corpus)


@pytest.fixture(scope="module")
def ground_truth():
    return harness.load_ground_truth()


# ---------------------------------------------------------------------------
# Ground truth structure
# ---------------------------------------------------------------------------

def test_ground_truth_has_twelve_pairs(ground_truth):
    assert len(ground_truth) == 12


def test_ground_truth_covers_tech_and_non_tech(ground_truth):
    categories = {p["category"] for p in ground_truth}
    assert categories == {"tech", "non-tech"}


def test_ground_truth_covers_fresher_mid_and_senior(ground_truth):
    levels = {p["experience_level"] for p in ground_truth}
    assert levels == {"fresher", "mid", "senior"}


def test_ground_truth_every_pair_has_required_fields(ground_truth):
    required = {"resume_id", "jd_id", "category", "experience_level", "expected_zone", "reasoning"}
    for pair in ground_truth:
        assert required <= set(pair.keys())


def test_ground_truth_expected_zones_are_valid(ground_truth):
    for pair in ground_truth:
        assert pair["expected_zone"] in harness.ZONES


def test_ground_truth_every_resume_and_jd_file_exists(ground_truth):
    for pair in ground_truth:
        assert (RESUME_DIR / f"{pair['resume_id']}.txt").exists(), pair["resume_id"]
        assert (JD_DIR / f"{pair['jd_id']}.txt").exists(), pair["jd_id"]


def test_new_senior_resume_has_years_of_experience_stated():
    text = (RESUME_DIR / "resume_16_senior_backend_lead.txt").read_text()
    assert "6.5 years" in text


def test_new_senior_resume_has_core_mern_skills():
    text = (RESUME_DIR / "resume_16_senior_backend_lead.txt").read_text()
    for skill in ["React.js", "Node.js", "MongoDB", "Express.js"]:
        assert skill in text


# ---------------------------------------------------------------------------
# Pipeline execution (does it run without error, does it return valid data)
# ---------------------------------------------------------------------------

def test_run_pipeline_returns_valid_zone_for_every_pair(matcher, ground_truth):
    for pair in ground_truth:
        _, zone = harness.run_pipeline(matcher, pair)
        assert zone in harness.ZONES


def test_run_pipeline_score_in_valid_range(matcher, ground_truth):
    for pair in ground_truth:
        result, _ = harness.run_pipeline(matcher, pair)
        assert 0.0 <= result.overall_score <= 100.0


# ---------------------------------------------------------------------------
# Precision / recall / F1 arithmetic -- checked against hand-computed values
# ---------------------------------------------------------------------------

def test_precision_recall_f1_matches_hand_computed_example():
    # Hand-computed: SHORTLIST has 2 TP, 1 FP, 3 FN
    # precision = 2/(2+1) = 0.667, recall = 2/(2+3) = 0.4, f1 = 2*.667*.4/(.667+.4) = 0.5
    confusion = {"SHORTLIST": {"tp": 2, "fp": 1, "fn": 3}}
    metrics = harness.precision_recall_f1(confusion)
    assert metrics["SHORTLIST"]["precision"] == pytest.approx(0.667, abs=0.001)
    assert metrics["SHORTLIST"]["recall"] == pytest.approx(0.4, abs=0.001)
    assert metrics["SHORTLIST"]["f1"] == pytest.approx(0.5, abs=0.001)


def test_precision_recall_f1_handles_zero_predictions():
    # A zone the AI never predicted: tp=0, fp=0, fn=2 -- precision should be
    # 0 (not a divide-by-zero crash), recall 0, f1 0.
    confusion = {"REJECT": {"tp": 0, "fp": 0, "fn": 2}}
    metrics = harness.precision_recall_f1(confusion)
    assert metrics["REJECT"] == {"precision": 0.0, "recall": 0.0, "f1": 0.0}


def test_precision_recall_f1_perfect_zone_scores_one():
    confusion = {"REVIEW": {"tp": 5, "fp": 0, "fn": 0}}
    metrics = harness.precision_recall_f1(confusion)
    assert metrics["REVIEW"] == {"precision": 1.0, "recall": 1.0, "f1": 1.0}


# ---------------------------------------------------------------------------
# Full run: internal consistency of the aggregated report
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def full_report(tmp_path_factory, matcher, ground_truth):
    # Run the real harness end-to-end once and reuse across consistency checks.
    return harness.run()


def test_full_run_mismatch_count_equals_incorrect_count(full_report):
    incorrect = full_report["total_pairs"] - full_report["correct"]
    assert len(full_report["mismatches"]) == incorrect


def test_full_run_all_rows_count_matches_total_pairs(full_report):
    assert len(full_report["all_rows"]) == full_report["total_pairs"]


def test_full_run_confusion_matrix_tp_sum_equals_correct_count(full_report):
    total_tp = sum(c["tp"] for c in full_report["confusion_matrix"].values())
    assert total_tp == full_report["correct"]


def test_full_run_category_totals_sum_to_overall_total(full_report):
    total = sum(v["total"] for v in full_report["accuracy_by_category"].values())
    assert total == full_report["total_pairs"]


def test_full_run_experience_level_totals_sum_to_overall_total(full_report):
    total = sum(v["total"] for v in full_report["accuracy_by_experience_level"].values())
    assert total == full_report["total_pairs"]


def test_full_run_every_mismatch_has_manual_and_ai_explanation(full_report):
    for m in full_report["mismatches"]:
        assert m["manual_reasoning"]
        assert m["ai_explanation"]
