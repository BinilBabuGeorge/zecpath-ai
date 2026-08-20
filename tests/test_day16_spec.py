import json
from pathlib import Path

import pytest
import yaml

import validate_day16_spec as v

RESULTS_DIR = Path("data/results")


@pytest.fixture(scope="module")
def openapi_spec():
    with open(v.OPENAPI_PATH) as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def schema_defs():
    with open(v.SCHEMA_PATH) as f:
        return json.load(f)["$defs"]


# ---------------------------------------------------------------------------
# Structural sanity
# ---------------------------------------------------------------------------

def test_openapi_yaml_parses(openapi_spec):
    assert openapi_spec["openapi"].startswith("3.")


def test_openapi_has_required_top_level_sections(openapi_spec):
    for key in ("info", "paths", "components"):
        assert key in openapi_spec


def test_openapi_declares_all_nine_endpoints(openapi_spec):
    expected = {
        "/resumes", "/resumes/{resume_id}", "/jobs", "/jobs/{jd_id}",
        "/scoring-jobs", "/scoring-jobs/{job_id}", "/scoring-jobs/{job_id}/cancel",
        "/rank", "/health",
    }
    assert expected <= set(openapi_spec["paths"].keys())


def test_scoring_jobs_post_returns_202(openapi_spec):
    assert "202" in openapi_spec["paths"]["/scoring-jobs"]["post"]["responses"]


def test_rank_endpoint_is_synchronous_200(openapi_spec):
    assert "200" in openapi_spec["paths"]["/rank"]["post"]["responses"]


def test_json_schema_file_parses(schema_defs):
    expected = {
        "ComponentResult", "CandidateScore", "BiasReport", "NormalizedScore",
        "RankedCandidateView", "ScoringJobCreateRequest", "ScoringJobStatus", "ErrorResponse",
    }
    assert expected <= set(schema_defs.keys())


# ---------------------------------------------------------------------------
# Conformance against real Day 13-15 output
# ---------------------------------------------------------------------------

def test_day13_score_results_conform_to_candidate_score_schema(schema_defs):
    files = sorted(RESULTS_DIR.glob("*__vs__*.json"))
    assert len(files) > 0, "no Day 13 result files found"
    for f in files:
        data = json.loads(f.read_text())
        wrapped = {"resume_id": "x", "jd_id": "y", **data}
        v.validate(wrapped, {"$ref": "#/$defs/CandidateScore"}, schema_defs)


def test_day14_ranking_results_conform_to_ranked_candidate_view(schema_defs):
    files = sorted(RESULTS_DIR.glob("ranking__*.json"))
    assert len(files) > 0, "no Day 14 ranking result file found"
    for f in files:
        data = json.loads(f.read_text())
        for row in data["candidates"]:
            v.validate(row, {"$ref": "#/$defs/RankedCandidateView"}, schema_defs)


def test_day15_bias_report_conforms_after_key_remap(schema_defs):
    fairness_path = RESULTS_DIR / "fairness_report.json"
    assert fairness_path.exists()
    data = json.loads(fairness_path.read_text())
    bias = data["bias_report_resume_15"]
    bias = {**bias, "pii_fields_detected": bias.pop("fields_detected")}
    v.validate(bias, {"$ref": "#/$defs/BiasReport"}, schema_defs)


def test_day15_normalized_scores_conform_to_schema(schema_defs):
    fairness_path = RESULTS_DIR / "fairness_report.json"
    data = json.loads(fairness_path.read_text())
    for ns in data["normalized_batch"]:
        v.validate(ns, {"$ref": "#/$defs/NormalizedScore"}, schema_defs)


def test_validator_rejects_a_deliberately_broken_payload(schema_defs):
    broken = {"score": 50.0}  # missing every required field
    with pytest.raises(v.SchemaValidationError):
        v.validate(broken, {"$ref": "#/$defs/CandidateScore"}, schema_defs)


def test_validator_enforces_enum_constraints(schema_defs):
    bad_zone_row = {
        "rank": 1, "candidate": "x", "job": "y", "score": 50.0,
        "zone": "MAYBE",  # not a valid enum value
        "role_category": "tech", "strongest_factor": "skill_match", "flags": "-",
    }
    with pytest.raises(v.SchemaValidationError):
        v.validate(bad_zone_row, {"$ref": "#/$defs/RankedCandidateView"}, schema_defs)


def test_validator_enforces_score_range(schema_defs):
    out_of_range = {
        "name": "skill_match", "score": 150.0,  # >100, invalid
        "base_weight": 0.3, "effective_weight": 0.3, "contribution": 45.0, "available": True,
    }
    with pytest.raises(v.SchemaValidationError):
        v.validate(out_of_range, {"$ref": "#/$defs/ComponentResult"}, schema_defs)
