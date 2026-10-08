"""
Day 44 tests -- structural validation of api/hr_interview_openapi.yaml.
A spec file can't be "run" the way code can, but it can still be
checked for real: valid YAML, every $ref resolves, every schema this
day claims is "verified against live source" actually matches the
live dataclass it claims to mirror.
"""

import re
import yaml

SPEC_PATH = "api/hr_interview_openapi.yaml"


def _load_spec():
    with open(SPEC_PATH) as f:
        text = f.read()
    return text, yaml.safe_load(text)


# ---------------------------------------------------------------------------
# Structural validity
# ---------------------------------------------------------------------------

def test_spec_is_valid_yaml():
    _, spec = _load_spec()
    assert spec["openapi"] == "3.0.3"
    assert "info" in spec and "paths" in spec and "components" in spec


def test_spec_has_expected_tags():
    _, spec = _load_spec()
    tag_names = {t["name"] for t in spec["tags"]}
    assert {"HR Interviews", "Scoring", "Aptitude", "Reports", "Unified", "Compliance", "System"}.issubset(tag_names)


def test_spec_has_health_endpoint():
    _, spec = _load_spec()
    assert "/health" in spec["paths"]


def test_every_ref_resolves():
    text, spec = _load_spec()
    schema_names = set(spec["components"]["schemas"].keys())
    param_names = set(spec["components"]["parameters"].keys())
    response_names = set(spec["components"]["responses"].keys())

    refs = re.findall(r"\$ref: '#/components/(schemas|parameters|responses)/([A-Za-z0-9_]+)'", text)
    assert refs, "Expected at least one $ref in the spec"

    pools = {"schemas": schema_names, "parameters": param_names, "responses": response_names}
    broken = [(kind, name) for kind, name in refs if name not in pools[kind]]
    assert broken == [], f"Broken refs found: {broken}"


def test_every_defined_schema_is_referenced():
    text, spec = _load_spec()
    schema_names = set(spec["components"]["schemas"].keys())
    refs = re.findall(r"\$ref: '#/components/schemas/([A-Za-z0-9_]+)'", text)
    referenced = set(refs)
    unused = schema_names - referenced
    assert unused == set(), f"Schemas defined but never referenced (likely dead weight): {unused}"


def test_error_response_matches_established_convention():
    # Must match the exact shape api/openapi.yaml and
    # api/screening_openapi.yaml already use -- same contract across
    # all three service boundaries.
    _, spec = _load_spec()
    err = spec["components"]["schemas"]["ErrorResponse"]
    props = err["properties"]["error"]["properties"]
    assert set(err["properties"]["error"]["required"]) == {"code", "message", "request_id"}
    assert "code" in props and "message" in props and "request_id" in props


# ---------------------------------------------------------------------------
# Every endpoint path has at least one documented success + error response
# ---------------------------------------------------------------------------

def test_every_operation_has_a_2xx_response():
    _, spec = _load_spec()
    for path, methods in spec["paths"].items():
        for method, operation in methods.items():
            responses = operation.get("responses", {})
            has_2xx = any(code.startswith("2") for code in responses)
            assert has_2xx, f"{method.upper()} {path} has no 2xx response defined"


# ---------------------------------------------------------------------------
# Honesty check -- schemas this file itself labels "reconstructed, not
# re-verified" must actually say so, and the ones it claims are
# verified must NOT carry that disclaimer by mistake.
# ---------------------------------------------------------------------------

_RECONSTRUCTED_SCHEMAS = {
    "AnswerScoreBreakdown", "HRInterviewScoreReport", "InterviewSummaryReport",
    "AptitudeSession", "AptitudeAnswerEvaluation", "AptitudeProfile",
}
_VERIFIED_SCHEMAS = {
    "InterviewQuestionState", "HRInterviewSession", "FollowUpDecision",
    "UnifiedCandidateScore", "ComponentContribution", "ScrubResult",
}


def test_reconstructed_schemas_are_labeled_as_such():
    _, spec = _load_spec()
    schemas = spec["components"]["schemas"]
    for name in _RECONSTRUCTED_SCHEMAS:
        description = schemas[name].get("description", "")
        assert "not re-verified" in description, f"{name} is reconstructed but doesn't say so in its description"


def test_verified_schemas_are_not_mislabeled_as_reconstructed():
    _, spec = _load_spec()
    schemas = spec["components"]["schemas"]
    for name in _VERIFIED_SCHEMAS:
        description = schemas[name].get("description", "")
        assert "not re-verified" not in description, f"{name} is verified against live source but its description wrongly hedges"


# ---------------------------------------------------------------------------
# Verified schemas actually match live dataclasses -- the thing the
# "verified" label is claiming
# ---------------------------------------------------------------------------

def test_interview_question_state_schema_matches_live_dataclass():
    from parsers.hr_interview_question_bank import InterviewQuestionState
    _, spec = _load_spec()
    schema_props = set(spec["components"]["schemas"]["InterviewQuestionState"]["properties"].keys())
    live_fields = set(InterviewQuestionState.__dataclass_fields__.keys())
    assert live_fields.issubset(schema_props), f"Live fields missing from spec: {live_fields - schema_props}"


def test_follow_up_decision_schema_matches_live_dataclass():
    from parsers.hr_followup_engine import FollowUpDecision
    _, spec = _load_spec()
    schema_props = set(spec["components"]["schemas"]["FollowUpDecision"]["properties"].keys())
    live_fields = set(FollowUpDecision.__dataclass_fields__.keys())
    assert live_fields.issubset(schema_props), f"Live fields missing from spec: {live_fields - schema_props}"


def test_unified_candidate_score_schema_matches_live_dataclass():
    from parsers.unified_scoring_engine import UnifiedCandidateScore
    _, spec = _load_spec()
    schema_props = set(spec["components"]["schemas"]["UnifiedCandidateScore"]["properties"].keys())
    live_fields = set(UnifiedCandidateScore.__dataclass_fields__.keys())
    assert live_fields.issubset(schema_props), f"Live fields missing from spec: {live_fields - schema_props}"


def test_component_contribution_schema_matches_live_dataclass():
    from parsers.unified_scoring_engine import ComponentContribution
    _, spec = _load_spec()
    schema_props = set(spec["components"]["schemas"]["ComponentContribution"]["properties"].keys())
    live_fields = set(ComponentContribution.__dataclass_fields__.keys())
    assert live_fields.issubset(schema_props), f"Live fields missing from spec: {live_fields - schema_props}"
