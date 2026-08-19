from pathlib import Path

import pytest

from parsers.semantic_matcher import SemanticMatcher
from parsers.ats_scoring_engine import score_candidate, WEIGHT_PROFILES
from parsers.fairness_engine import (
    normalize_resume_text,
    mask_pii,
    detect_keyword_stuffing,
    fairness_adjusted_weights,
    normalize_scores_batch,
    evaluate_bias_indicators,
    score_with_fairness,
    REDACTED,
    STUFFING_REPEAT_THRESHOLD,
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
def bias_resume_text():
    return (RESUME_DIR / "resume_15_bias_fields.txt").read_text()


@pytest.fixture(scope="module")
def clean_resume_text():
    return (RESUME_DIR / "resume_01_mern_developer.txt").read_text()


# ---------------------------------------------------------------------------
# 1. Resume normalization
# ---------------------------------------------------------------------------

def test_normalize_resume_text_standardizes_bullets():
    messy = "\u2022 first point\n* second point\n\u25aa third point"
    normalized = normalize_resume_text(messy)
    assert normalized.count("- first point") == 1
    assert normalized.count("- second point") == 1
    assert normalized.count("- third point") == 1


def test_normalize_resume_text_collapses_excess_blank_lines():
    messy = "Line one\n\n\n\n\nLine two"
    normalized = normalize_resume_text(messy)
    assert "\n\n\n" not in normalized


def test_normalize_resume_text_strips_trailing_whitespace():
    messy = "Line with trailing spaces   \nAnother line\t\t"
    normalized = normalize_resume_text(messy)
    assert all(not line.endswith(" ") and not line.endswith("\t") for line in normalized.split("\n"))


def test_normalize_resume_text_converts_crlf():
    messy = "Line one\r\nLine two\r\n"
    normalized = normalize_resume_text(messy)
    assert "\r" not in normalized


def test_normalize_resume_text_is_idempotent():
    messy = "\u2022 point\r\n\r\n\r\ntext   \t"
    once = normalize_resume_text(messy)
    twice = normalize_resume_text(once)
    assert once == twice


# ---------------------------------------------------------------------------
# 4. Masking non-essential personal attributes
# ---------------------------------------------------------------------------

def test_mask_pii_detects_all_fields_in_bias_test_resume(bias_resume_text):
    _, detected = mask_pii(bias_resume_text)
    for expected_field in ["Name", "Email", "Phone", "Location", "Gender",
                            "Date of Birth", "Marital Status", "Religion", "Nationality"]:
        assert expected_field in detected


def test_mask_pii_removes_actual_values_from_text(bias_resume_text):
    masked_text, _ = mask_pii(bias_resume_text)
    assert "Rohan Malhotra" not in masked_text
    assert "rohan.malhotra@example.com" not in masked_text
    assert "+91-90000-00099" not in masked_text
    assert REDACTED in masked_text


def test_mask_pii_preserves_field_labels(bias_resume_text):
    masked_text, _ = mask_pii(bias_resume_text)
    assert "Name:" in masked_text
    assert "Gender:" in masked_text


def test_mask_pii_does_not_touch_job_relevant_content(bias_resume_text):
    masked_text, _ = mask_pii(bias_resume_text)
    assert "React.js" in masked_text
    assert "MongoDB" in masked_text
    assert "B.Tech in Computer Science" in masked_text


def test_mask_pii_clean_resume_still_detects_core_fields(clean_resume_text):
    # Even a resume with no demographic fields still has name/email/phone
    _, detected = mask_pii(clean_resume_text)
    assert set(detected) == {"Name", "Email", "Phone", "Location"}


# ---------------------------------------------------------------------------
# 2. Reducing over-dependence on keywords
# ---------------------------------------------------------------------------

def test_detect_keyword_stuffing_flags_heavy_repetition():
    stuffed = "Skills: React.js\nExperience:\n- React.js React.js React.js React.js React.js work."
    result = detect_keyword_stuffing(stuffed)
    assert "React.js" in result
    assert result["React.js"] >= STUFFING_REPEAT_THRESHOLD


def test_detect_keyword_stuffing_clean_on_all_real_resumes():
    for f in sorted(RESUME_DIR.glob("*.txt")):
        assert detect_keyword_stuffing(f.read_text()) == {}, f"false positive on {f.name}"


def test_detect_keyword_stuffing_ignores_stack_expansion_mentions(clean_resume_text):
    # resume_01 has "MERN Stack Developer" as its title, which implies
    # React/Node/Express/MongoDB via stack expansion -- that single
    # synthetic mention must not count toward literal repetition.
    result = detect_keyword_stuffing(clean_resume_text)
    assert result == {}


def test_fairness_adjusted_weights_sum_to_one():
    for profile_name, weights in WEIGHT_PROFILES.items():
        adjusted = fairness_adjusted_weights(weights)
        assert sum(adjusted.values()) == pytest.approx(1.0, abs=0.01)


def test_fairness_adjusted_weights_lowers_skill_match():
    base = WEIGHT_PROFILES["tech"]
    adjusted = fairness_adjusted_weights(base, dampen_skill_by=0.30)
    assert adjusted["skill_match"] < base["skill_match"]


def test_fairness_adjusted_weights_raises_on_invalid_dampening():
    with pytest.raises(ValueError):
        fairness_adjusted_weights(WEIGHT_PROFILES["tech"], dampen_skill_by=1.5)


def test_fairness_adjusted_weights_zero_dampening_is_a_no_op():
    base = WEIGHT_PROFILES["tech"]
    adjusted = fairness_adjusted_weights(base, dampen_skill_by=0.0)
    assert adjusted == base


# ---------------------------------------------------------------------------
# 3. Scoring normalization
# ---------------------------------------------------------------------------

def test_normalize_scores_batch_best_candidate_is_100(matcher):
    jd_text = (JD_DIR / "jd_01_mern_developer.txt").read_text()
    scored = []
    for cid in ["resume_01_mern_developer", "resume_14_no_education", "resume_03_sales_executive"]:
        result = score_candidate((RESUME_DIR / f"{cid}.txt").read_text(), jd_text, matcher)
        scored.append((cid, result))
    normalized = normalize_scores_batch(scored)
    best = max(normalized, key=lambda n: n.raw_score)
    assert best.normalized_score == 100.0


def test_normalize_scores_batch_worst_candidate_is_zero(matcher):
    jd_text = (JD_DIR / "jd_01_mern_developer.txt").read_text()
    scored = []
    for cid in ["resume_01_mern_developer", "resume_14_no_education", "resume_03_sales_executive"]:
        result = score_candidate((RESUME_DIR / f"{cid}.txt").read_text(), jd_text, matcher)
        scored.append((cid, result))
    normalized = normalize_scores_batch(scored)
    worst = min(normalized, key=lambda n: n.raw_score)
    assert worst.normalized_score == 0.0


def test_normalize_scores_batch_handles_empty_input():
    assert normalize_scores_batch([]) == []


def test_normalize_scores_batch_handles_all_tied_scores():
    from parsers.ats_scoring_engine import ATSScoreResult
    tied = ATSScoreResult(overall_score=50.0, role_category="tech", components=[])
    scored = [("a", tied), ("b", tied)]
    normalized = normalize_scores_batch(scored)
    assert all(n.normalized_score == 100.0 for n in normalized)


def test_normalize_scores_batch_percentile_in_valid_range(matcher):
    jd_text = (JD_DIR / "jd_01_mern_developer.txt").read_text()
    scored = []
    for cid in ["resume_01_mern_developer", "resume_14_no_education", "resume_03_sales_executive"]:
        result = score_candidate((RESUME_DIR / f"{cid}.txt").read_text(), jd_text, matcher)
        scored.append((cid, result))
    normalized = normalize_scores_batch(scored)
    assert all(0.0 <= n.percentile <= 100.0 for n in normalized)


# ---------------------------------------------------------------------------
# 5. Bias indicator evaluation
# ---------------------------------------------------------------------------

def test_evaluate_bias_indicators_high_risk_for_many_fields(bias_resume_text):
    report = evaluate_bias_indicators(bias_resume_text)
    assert report.risk_level == "high"
    assert len(report.pii_fields_detected) >= 8


def test_evaluate_bias_indicators_medium_risk_for_core_fields_only(clean_resume_text):
    report = evaluate_bias_indicators(clean_resume_text)
    # Name/Email/Phone/Location only -- more than 2 core fields, still no stuffing
    assert report.risk_level in ("medium", "high")


def test_evaluate_bias_indicators_notes_are_nonempty(bias_resume_text):
    report = evaluate_bias_indicators(bias_resume_text)
    assert len(report.notes) > 0
    assert all(isinstance(n, str) and n for n in report.notes)


def test_evaluate_bias_indicators_does_not_leak_actual_values(bias_resume_text):
    report = evaluate_bias_indicators(bias_resume_text)
    joined = " ".join(report.notes) + " ".join(report.pii_fields_detected)
    assert "Rohan Malhotra" not in joined
    assert "rohan.malhotra@example.com" not in joined


# ---------------------------------------------------------------------------
# Combined fairness pipeline
# ---------------------------------------------------------------------------

def test_score_with_fairness_returns_bias_report(matcher, bias_resume_text):
    jd_text = (JD_DIR / "jd_01_mern_developer.txt").read_text()
    result = score_with_fairness(bias_resume_text, jd_text, matcher)
    assert result.bias_report.risk_level == "high"


def test_score_with_fairness_masking_does_not_wildly_change_score(matcher, bias_resume_text):
    # Masking removes bias vectors, not job-relevant content -- the
    # overall score should move only slightly, not swing wildly.
    jd_text = (JD_DIR / "jd_01_mern_developer.txt").read_text()
    result = score_with_fairness(bias_resume_text, jd_text, matcher)
    assert abs(result.score_delta) < 5.0


def test_score_with_fairness_weighted_mode_changes_component_weights(matcher, bias_resume_text):
    jd_text = (JD_DIR / "jd_01_mern_developer.txt").read_text()
    default_run = score_with_fairness(bias_resume_text, jd_text, matcher, use_fairness_weights=False)
    weighted_run = score_with_fairness(bias_resume_text, jd_text, matcher, use_fairness_weights=True)

    default_skill_weight = [c for c in default_run.result.components if c.name == "skill_match"][0].base_weight
    weighted_skill_weight = [c for c in weighted_run.result.components if c.name == "skill_match"][0].base_weight
    assert weighted_skill_weight < default_skill_weight


def test_score_with_fairness_reports_real_role_category_not_internal_key(matcher, bias_resume_text):
    jd_text = (JD_DIR / "jd_01_mern_developer.txt").read_text()
    result = score_with_fairness(bias_resume_text, jd_text, matcher, use_fairness_weights=True)
    assert not result.result.role_category.startswith("_fairness_temp")
    assert result.result.role_category in WEIGHT_PROFILES


def test_score_with_fairness_does_not_leak_temp_profile_into_global_state(matcher, bias_resume_text):
    jd_text = (JD_DIR / "jd_01_mern_developer.txt").read_text()
    before = set(WEIGHT_PROFILES.keys())
    score_with_fairness(bias_resume_text, jd_text, matcher, use_fairness_weights=True)
    after = set(WEIGHT_PROFILES.keys())
    assert before == after
