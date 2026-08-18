from pathlib import Path

import pytest

from parsers.semantic_matcher import SemanticMatcher
from parsers.ats_scoring_engine import score_candidate
from parsers.ranking_engine import (
    rank_candidates,
    classify_zone,
    top_candidates,
    filter_by_zone,
    zone_counts,
    to_recruiter_view,
    DEFAULT_THRESHOLDS,
)

RESUME_DIR = Path("data/samples/resumes")
JD_DIR = Path("data/samples/jds")


@pytest.fixture(scope="module")
def matcher():
    resume_files = sorted(RESUME_DIR.glob("*.txt"))
    jd_files = sorted(JD_DIR.glob("*.txt"))
    corpus = [f.read_text() for f in resume_files + jd_files]
    return SemanticMatcher(corpus)


@pytest.fixture(scope="module")
def scored_batch(matcher):
    """Score several real candidates against one JD -- a mix of strong,
    partial, missing-data, and mismatched candidates so all zones get
    exercised in the tests below."""
    jd_text = (JD_DIR / "jd_01_mern_developer.txt").read_text()
    candidate_ids = [
        "resume_01_mern_developer",
        "resume_12_partial_mern_match",
        "resume_13_fresher_no_experience",
        "resume_14_no_education",
        "resume_03_sales_executive",
    ]
    scored = []
    for cid in candidate_ids:
        resume_text = (RESUME_DIR / f"{cid}.txt").read_text()
        result = score_candidate(resume_text, jd_text, matcher)
        scored.append((cid, "jd_01_mern_developer", result))
    return scored


# ---------------------------------------------------------------------------
# Zone classification (pure function -- no fixtures needed)
# ---------------------------------------------------------------------------

def test_classify_zone_shortlist_at_and_above_cutoff():
    assert classify_zone(55.0) == "shortlist"
    assert classify_zone(90.0) == "shortlist"


def test_classify_zone_review_band():
    assert classify_zone(54.9) == "review"
    assert classify_zone(25.0) == "review"


def test_classify_zone_reject_below_review_cutoff():
    assert classify_zone(24.9) == "reject"
    assert classify_zone(0.0) == "reject"


def test_classify_zone_respects_custom_thresholds():
    custom = {"shortlist": 80.0, "review": 50.0}
    assert classify_zone(70.0, custom) == "review"
    assert classify_zone(85.0, custom) == "shortlist"
    assert classify_zone(30.0, custom) == "reject"


def test_default_thresholds_shortlist_above_review():
    assert DEFAULT_THRESHOLDS["shortlist"] > DEFAULT_THRESHOLDS["review"]


# ---------------------------------------------------------------------------
# Sorting by score
# ---------------------------------------------------------------------------

def test_rank_candidates_sorted_descending_by_score(scored_batch):
    ranked = rank_candidates(scored_batch)
    scores = [r.overall_score for r in ranked]
    assert scores == sorted(scores, reverse=True)


def test_rank_candidates_assigns_sequential_ranks(scored_batch):
    ranked = rank_candidates(scored_batch)
    assert [r.rank for r in ranked] == list(range(1, len(ranked) + 1))


def test_rank_candidates_tie_break_is_deterministic():
    # Two synthetic candidates with identical scores -- tie should break
    # alphabetically by candidate_id, not by insertion order.
    from parsers.ats_scoring_engine import ATSScoreResult, ComponentResult
    dummy_component = ComponentResult(
        name="skill_match", score=50.0, base_weight=1.0, effective_weight=1.0,
        contribution=50.0, available=True,
    )
    same_result = ATSScoreResult(overall_score=50.0, role_category="tech", components=[dummy_component])
    scored = [("zebra_candidate", "jd_x", same_result), ("apple_candidate", "jd_x", same_result)]
    ranked = rank_candidates(scored)
    assert [r.candidate_id for r in ranked] == ["apple_candidate", "zebra_candidate"]


# ---------------------------------------------------------------------------
# Shortlisting thresholds / auto-reject / review zones
# ---------------------------------------------------------------------------

def test_rank_candidates_every_row_has_a_valid_zone(scored_batch):
    ranked = rank_candidates(scored_batch)
    assert all(r.zone in ("shortlist", "review", "reject") for r in ranked)


def test_rank_candidates_zone_matches_score_thresholds(scored_batch):
    ranked = rank_candidates(scored_batch)
    for r in ranked:
        assert r.zone == classify_zone(r.overall_score)


def test_mismatched_candidate_lands_in_reject_or_review_not_shortlist(scored_batch):
    ranked = rank_candidates(scored_batch)
    sales_row = [r for r in ranked if r.candidate_id == "resume_03_sales_executive"][0]
    assert sales_row.zone in ("review", "reject")


def test_filter_by_zone_returns_only_that_zone(scored_batch):
    ranked = rank_candidates(scored_batch)
    rejected = filter_by_zone(ranked, "reject")
    assert all(r.zone == "reject" for r in rejected)


def test_filter_by_zone_rejects_unknown_zone_name(scored_batch):
    ranked = rank_candidates(scored_batch)
    with pytest.raises(ValueError):
        filter_by_zone(ranked, "maybe")


def test_zone_counts_sum_to_total_candidates(scored_batch):
    ranked = rank_candidates(scored_batch)
    counts = zone_counts(ranked)
    assert sum(counts.values()) == len(ranked)


# ---------------------------------------------------------------------------
# Top candidate lists
# ---------------------------------------------------------------------------

def test_top_candidates_returns_requested_count(scored_batch):
    ranked = rank_candidates(scored_batch)
    top2 = top_candidates(ranked, n=2)
    assert len(top2) == 2
    assert top2[0].rank == 1 and top2[1].rank == 2


def test_top_candidates_handles_n_larger_than_batch(scored_batch):
    ranked = rank_candidates(scored_batch)
    top_all = top_candidates(ranked, n=100)
    assert len(top_all) == len(ranked)


# ---------------------------------------------------------------------------
# Recruiter-friendly output
# ---------------------------------------------------------------------------

def test_to_recruiter_view_returns_flat_dicts(scored_batch):
    ranked = rank_candidates(scored_batch)
    rows = to_recruiter_view(ranked)
    assert len(rows) == len(ranked)
    expected_keys = {"rank", "candidate", "job", "score", "zone", "role_category", "strongest_factor", "flags"}
    assert all(set(row.keys()) == expected_keys for row in rows)


def test_to_recruiter_view_zone_is_uppercase(scored_batch):
    ranked = rank_candidates(scored_batch)
    rows = to_recruiter_view(ranked)
    assert all(row["zone"] in ("SHORTLIST", "REVIEW", "REJECT") for row in rows)


def test_to_recruiter_view_flags_missing_data_candidates(scored_batch):
    ranked = rank_candidates(scored_batch)
    rows = {row["candidate"]: row for row in to_recruiter_view(ranked)}
    assert rows["resume_13_fresher_no_experience"]["flags"] != "-"
    assert rows["resume_01_mern_developer"]["flags"] == "-"
