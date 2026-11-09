"""
Day 59 tests: the integration plan is checked against the code it describes.

Each group answers one question a reviewer would ask:
  * Is every error code the code can emit covered by the error policy?            (test_error_codes_*)
  * Do the schemas accept what the services return, and reject what they reject?  (test_*_schema_*, test_gateway_*)
  * Is the plan's access map consistent with the Day 55 matrix?                   (test_access_*)
  * Do retries and idempotency behave as the plan says?                           (test_retry_*, test_idempotency_*)
  * Is the generated schema/OpenAPI file in the repo up to date?                  (test_generated_files_*)
  * Do the two new services keep the Day 57 contract?                             (test_resume_parsing_*, test_batch_*)
"""

import ast
import json
import logging
import random
import re
from datetime import date
from pathlib import Path

import pytest
import yaml

jsonschema = pytest.importorskip("jsonschema")

from ats_engine.batch_service import ATSBatchService
from ats_engine.resume_parsing_service import ResumeParsingService
from ats_engine.service import ATSService
from interview_ai.service import InterviewIntelligenceService
from parsers import integration_contract as ic
from parsers.access_control import AccessController, Action, Actor, Resource, ResourceType, Role
from scoring.service import DecisionScoringService
from screening_ai.service import ScreeningService

ROOT = Path(__file__).resolve().parent.parent
RESUME_DIR = ROOT / "data" / "raw_resumes"
JD = "Required Skills: React, Node.js, MongoDB\nWe need a MERN developer."
RESUME = "Summary: MERN developer.\nSkills: React, Node.js, MongoDB, Express\nExperience:\nDeveloper, Acme (Jan 2021 - Present)\nEducation:\nB.Tech in Computer Science, XYZ, 2020"

SERVICES = {
    "score_ats": ATSService(), "score_ats_batch": ATSBatchService(), "score_screening": ScreeningService(),
    "score_interview": InterviewIntelligenceService(), "recommend_decision": DecisionScoringService(),
}


# ---------------------------------------------------------------------------------------------------- catalogue
def test_operation_ids_paths_and_scopes_are_unique():
    assert len({o.op_id for o in ic.OPERATIONS}) == len(ic.OPERATIONS)
    assert len({(o.method, o.path) for o in ic.OPERATIONS}) == len(ic.OPERATIONS)
    scopes = [o.scope for o in ic.OPERATIONS if o.scope]
    assert all(re.fullmatch(r"ai:[a-z]+:[a-z]+", s) for s in scopes)


def test_every_listed_ai_api_exists_with_the_planned_mode():
    """The brief lists five AI APIs; resume processing is async and real-time interview scoring is sync."""
    expected = {"parse_resume": ic.Mode.ASYNC, "score_ats": ic.Mode.SYNC, "score_screening": ic.Mode.SYNC,
                "score_interview": ic.Mode.SYNC, "recommend_decision": ic.Mode.SYNC, "score_ats_batch": ic.Mode.ASYNC}
    for op_id, mode in expected.items():
        assert ic.OPERATION_BY_ID[op_id].mode == mode


def test_every_implementation_path_resolves_to_a_real_class_with_run():
    import importlib
    for op in ic.OPERATIONS:
        if not op.implementation:
            continue
        module, cls = op.implementation.rsplit(".", 1)
        klass = getattr(importlib.import_module(module), cls)
        assert callable(getattr(klass, "run"))


def test_every_schema_named_by_an_operation_exists():
    defs = ic.build_schemas()
    for op in ic.OPERATIONS:
        assert op.response_schema in defs
        if op.request_schema:
            assert op.request_schema in defs


def test_async_operations_require_idempotency_and_sync_ones_do_not_need_it():
    for op in ic.OPERATIONS:
        if op.mode == ic.Mode.ASYNC:
            assert op.idempotency == "required"
        assert op.timeout_s > 0 and op.max_body_bytes > 0


def test_every_store_touched_exists_in_the_storage_plan_or_is_declared_unmodelled():
    known = ic.known_store_ids()
    for op in ic.OPERATIONS:
        for t in op.touches:
            assert t.store in known, f"{op.op_id} touches unknown store {t.store}"


def test_every_operation_writes_an_audit_entry_when_it_touches_candidate_data():
    for op in ic.OPERATIONS:
        if op.touches:
            assert any(t.resource == ResourceType.AUDIT_LOG for t in op.touches), op.op_id


# ---------------------------------------------------------------------------------------------------- error policy
def _error_codes_raised_in(path: Path) -> set:
    """String literals passed as the first argument of ServiceInputError(...) / ResumeUploadError(...) in a source file."""
    codes = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) in ("ServiceInputError", "ResumeUploadError", "_error_response"):
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                codes.add(node.args[0].value)
    return codes


def test_error_codes_emitted_by_the_code_are_all_in_the_policy():
    files = [ROOT / "utils/base_service.py", ROOT / "ats_engine/service.py", ROOT / "ats_engine/batch_service.py",
             ROOT / "ats_engine/resume_parsing_service.py", ROOT / "screening_ai/service.py", ROOT / "interview_ai/service.py",
             ROOT / "scoring/service.py", ROOT / "parsers/resume_extractor.py"]
    emitted = set().union(*(_error_codes_raised_in(f) for f in files))
    assert emitted, "the scan found no error codes; the test would pass for the wrong reason"
    assert emitted <= set(ic.ERROR_CODES), f"unmapped: {emitted - set(ic.ERROR_CODES)}"


def test_error_codes_documented_in_the_docstrings_match_the_policy():
    base = (ROOT / "utils/base_service.py").read_text(encoding="utf-8")
    documented = {c for c in re.search(r"Error codes: ([a-z_ |\n]+)", base).group(1).replace(" ", "").replace("\n", "").split("|") if c}
    assert len(documented) >= 7 and documented <= set(ic.ERROR_CODES)
    upload = (ROOT / "parsers/resume_extractor.py").read_text(encoding="utf-8")
    codes = {c for c in re.search(r"Codes: ([a-z_ |\n]+)", upload).group(1).replace(" ", "").replace("\n", "").split("|") if c}
    assert len(codes) == 4 and codes <= set(ic.ERROR_CODES)


def test_error_rules_are_internally_consistent():
    for code, rule in ic.ERROR_RULES.items():
        assert rule.code == code and 400 <= rule.http_status <= 599 and rule.max_retries >= 0 and rule.client_action
        if rule.max_retries:
            assert rule.http_status in (404, 429, 500, 503, 504), code    # only these may ever be retried
        if rule.http_status in (400, 401, 403, 413, 415, 422):
            assert rule.max_retries == 0, f"{code}: a client error must not be retried"


def test_unknown_code_is_not_retried_freely_and_does_not_leak():
    env = {"service": "x", "api_version": "1.0", "status": "error", "error": {"code": "some_new_code", "message": "secret detail", "field": None}}
    err = ic.to_gateway_error(env, "req-1")
    assert err.http_status == 500 and err.body["error"]["code"] == "internal_error" and "secret" not in json.dumps(err.body)


def test_gateway_error_carries_request_id_status_retry_advice_and_validates():
    env = ATSService().run({})
    assert env["status"] == "error"
    err = ic.to_gateway_error(env, "req-abc")
    assert err.http_status == 422 and err.body["request_id"] == "req-abc" and err.body["retryable"] is False
    assert ic.validate_response("ErrorResponse", err.body) == []
    limited = ic.to_gateway_error({"api_version": "1.0", "status": "error", "error": {"code": "rate_limited", "message": "m", "field": None}}, "r", 7)
    assert limited.http_status == 429 and limited.headers["Retry-After"] == "7" and limited.body["retryable"] is True


def test_to_gateway_error_rejects_a_success_envelope():
    with pytest.raises(ValueError):
        ic.to_gateway_error({"status": "success"}, "r")


# ---------------------------------------------------------------------------------------------------- real outputs vs schemas
def _call_all_services():
    """One success (and where useful an error) from every real service, keyed by the response schema it must satisfy."""
    out = []
    out.append(("ATSScoreResult", ATSService().run({"resume_text": RESUME, "job_description": JD})))
    out.append(("ATSScoreResult", ATSService().run({"resume_text": RESUME, "job_requirements": ["React", "Go"]})))
    out.append(("ATSBatchScoreResult", ATSBatchService().run({"job_description": JD, "candidates": [
        {"candidate_id": "A1", "resume_text": RESUME}, {"candidate_id": "A2", "resume_text": ""}]})))
    turns = [{"text": "I am a developer with 3 years of experience", "confidence": 0.9}]
    out.append(("ScreeningScoreResult", ScreeningService().run({"candidate_id": "C1", "turns": turns})))
    out.append(("ScreeningScoreResult", ScreeningService().run({"candidate_id": "C1"})))
    out.append(("InterviewScoreResult", InterviewIntelligenceService().run({"interview_type": "hr", "answers": ["I led a team of five on a React project."]})))
    out.append(("InterviewScoreResult", InterviewIntelligenceService().run({"interview_type": "hr"})))
    out.append(("InterviewScoreResult", InterviewIntelligenceService().run({"interview_type": "technical", "domain": "mern", "experience_years": 3, "answers": ["A closure keeps access to its outer scope."]})))
    out.append(("InterviewScoreResult", InterviewIntelligenceService().run({"interview_type": "technical", "domain": "java", "experience_years": 1})))
    out.append(("DecisionResult", DecisionScoringService().run({"candidate_id": "C1", "ats_score": 70, "hr_interview_score": 80})))
    out.append(("DecisionResult", DecisionScoringService().run({"candidate_id": "C1", "ats_score": 80, "screening_score": 80, "hr_interview_score": 80,
                                                                 "technical_score": 80, "machine_test_score": 80})))
    out.append(("DecisionResult", DecisionScoringService().run({"ats_score": 30, "ats_zone": "reject", "communication_score": 40, "behavior_score": 50})))
    return out


@pytest.mark.parametrize("schema,response", _call_all_services())
def test_real_service_output_satisfies_its_response_schema(schema, response):
    assert response["status"] == "success"
    assert ic.validate_response(schema, response) == []


@pytest.mark.parametrize("schema,response", _call_all_services())
def test_real_service_output_has_no_key_the_schema_does_not_declare(schema, response):
    """Responses are open (forward compatible), so drift is caught here instead: a new key must be added to the schema."""
    declared = ic.declared_keys(schema)
    if schema == "ATSBatchScoreResult":
        for item in response["results"]:
            assert set(item) <= {"candidate_id", "outcome"}
    assert set(response) <= declared, f"undeclared: {set(response) - declared}"


def test_every_real_error_envelope_validates_as_a_service_error():
    bad = [ATSService().run({}), ATSService().run({"job_description": 5}), ScreeningService().run({"turns": "x"}),
           InterviewIntelligenceService().run({"interview_type": "final"}), DecisionScoringService().run({}),
           DecisionScoringService().run({"ats_score": 101}), ATSService().run("not a dict")]
    for env in bad:
        assert env["status"] == "error" and env["error"]["code"] in ic.ERROR_CODES
        assert ic.validate_response("ServiceErrorEnvelope", env) == []


def test_schemas_are_valid_json_schema_and_the_openapi_document_is_valid():
    jsonschema.Draft202012Validator.check_schema(ic.schema_document())
    for name, sub in ic.build_schemas().items():
        jsonschema.Draft202012Validator.check_schema({"$defs": ic.build_schemas(), **sub})
    oa = ic.build_openapi()
    assert oa["openapi"] == "3.1.0"
    for path in oa["paths"].values():
        for item in path.values():
            assert item["operationId"] in ic.OPERATION_BY_ID and "responses" in item


def test_enums_in_the_schemas_come_from_the_code():
    from parsers.final_recommendation_engine import DecisionOutcome
    from parsers.hr_interview_question_bank import RoleType
    from parsers.technical_interview_question_bank import TechnicalDomain
    defs = ic.build_schemas()
    assert defs["DecisionResult"]["properties"]["decision"]["enum"] == [o.value for o in DecisionOutcome]
    assert defs["DecisionRequest"]["properties"]["role_type"]["enum"] == [r.value for r in RoleType]
    assert defs["InterviewScoreRequest"]["properties"]["domain"]["enum"] == [d.value for d in TechnicalDomain]
    assert defs["ErrorCode"]["enum"] == list(ic.ERROR_CODES)


# ---------------------------------------------------------------------------------------------------- gateway validation vs service
GOOD_REQUESTS = [
    ("score_ats", {"resume_text": RESUME, "job_description": JD}, ATSService()),
    ("score_ats", {"resume_text": "", "job_description": JD}, ATSService()),
    ("score_ats", {"resume_text": RESUME, "job_requirements": ["React"]}, ATSService()),
    ("score_screening", {"candidate_id": "C1"}, ScreeningService()),
    ("score_screening", {"candidate_id": "C1", "job_role": "MERN", "turns": [{"text": "hello", "confidence": 0.5, "is_silent": False}]}, ScreeningService()),
    ("score_interview", {"interview_type": "hr", "role_type": "technical", "experience_level": "fresher", "answers": ["I know React."]}, InterviewIntelligenceService()),
    ("score_interview", {"interview_type": "technical", "domain": "devops", "experience_years": 0, "answers": []}, InterviewIntelligenceService()),
    ("recommend_decision", {"candidate_id": "C1", "ats_score": 0}, DecisionScoringService()),
    ("recommend_decision", {"hr_interview_score": 100, "role_type": "non_technical", "experience_level": "fresher", "ats_zone": "review"}, DecisionScoringService()),
]


@pytest.mark.parametrize("op_id,body,service", GOOD_REQUESTS)
def test_gateway_accepts_what_the_service_accepts(op_id, body, service):
    assert ic.validate_request(op_id, body) is None
    assert service.run(body)["status"] == "success"


# (operation, body, the code the SERVICE gives). The gateway must refuse each of these AND name the same code and field.
BAD_REQUESTS = [
    ("score_ats", {"resume_text": RESUME}, "missing_field", "job_description"),
    ("score_ats", {"resume_text": RESUME, "job_description": "   "}, "invalid_input", "job_description"),
    ("score_ats", {"resume_text": 5, "job_description": JD}, "invalid_input", "resume_text"),
    ("score_ats", {"resume_text": "x" * (200_000 + 1), "job_description": JD}, "too_large", "resume_text"),
    ("score_screening", {"candidate_id": "C1", "turns": [{"text": "hi", "confidence": 2}]}, "invalid_input", "turns[0].confidence"),
    ("score_screening", {"candidate_id": "C1", "turns": "nope"}, "invalid_input", "turns"),
    ("score_interview", {"interview_type": "final"}, "unsupported_value", "interview_type"),
    ("score_interview", {"interview_type": "technical", "domain": "mern"}, "missing_field", "experience_years"),
    ("score_interview", {"interview_type": "technical", "domain": "cobol", "experience_years": 2}, "unsupported_value", "domain"),
    ("score_interview", {"interview_type": "hr", "answers": [5]}, "invalid_input", "answers[0]"),
    ("recommend_decision", {}, "missing_field", "ats_score"),
    ("recommend_decision", {"ats_score": 101}, "invalid_score", "ats_score"),
    ("recommend_decision", {"ats_score": "high"}, "invalid_score", "ats_score"),
    ("recommend_decision", {"ats_score": 50, "ats_zone": "maybe"}, "unsupported_value", "ats_zone"),
    ("recommend_decision", {"ats_score": 50, "role_type": "chef"}, "unsupported_value", "role_type"),
]


@pytest.mark.parametrize("op_id,body,code,field", BAD_REQUESTS)
def test_gateway_and_service_refuse_the_same_bad_request_with_the_same_code(op_id, body, code, field):
    service_env = SERVICES[op_id].run(body)
    assert service_env["status"] == "error", "the service accepted a request the table says is bad"
    gateway_env = ic.validate_request(op_id, body)
    assert gateway_env is not None, "the gateway accepted a request the service refuses"
    assert service_env["error"]["code"] == code
    assert gateway_env["error"]["code"] == code
    assert gateway_env["error"]["field"] == field


def test_gateway_rejects_a_non_object_body():
    assert ic.validate_request("score_ats", ["not", "an", "object"])["error"]["code"] == "invalid_payload"


def test_gateway_is_deliberately_stricter_about_candidate_ids_and_unknown_keys():
    """Documented difference: the services take any text as candidate_id; the gateway only accepts a pseudonymous reference."""
    for bad_id in ("jane.doe@example.com", "Jane Doe", "x" * 65, ""):
        assert ic.validate_request("score_screening", {"candidate_id": bad_id}) is not None
    assert ic.validate_request("score_screening", {"candidate_id": "cref_0123456789abcdef0123"}) is None
    assert ic.validate_request("score_ats", {"job_description": JD, "unexpected": 1}) is not None


def test_a_pseudonym_from_day_55_passes_the_candidate_id_pattern():
    from parsers.data_governance import pseudonymise
    ref = pseudonymise("jane.doe@example.com", b"k" * 32)
    assert re.fullmatch(ic.CANDIDATE_ID_PATTERN, ref)


def test_worst_case_request_sizes_exceed_the_proposed_body_caps_so_the_caps_are_what_binds():
    """Finding F3: the service limits (200 items x 20,000 chars) allow far more than the proposed gateway caps."""
    for op in ic.OPERATIONS:
        if op.request_schema in ("ATSBatchScoreRequest", "ScreeningScoreRequest", "InterviewScoreRequest"):
            assert ic.worst_case_bytes(op.request_schema) > op.max_body_bytes


# ---------------------------------------------------------------------------------------------------- jobs
def test_job_state_machine_is_the_day_16_machine():
    assert ic.JOB_STATES == ("queued", "running", "completed", "failed", "cancelled")
    assert ic.can_transition("queued", "running") and ic.can_transition("queued", "cancelled")
    assert ic.can_transition("running", "completed") and ic.can_transition("running", "failed") and ic.can_transition("running", "cancelled")
    for terminal in ("completed", "failed", "cancelled"):
        assert not any(ic.can_transition(terminal, s) for s in ic.JOB_STATES)
    assert not ic.can_transition("queued", "completed")
    doc = (ROOT / "docs" / "day16_integration_flow.md").read_text(encoding="utf-8")
    for state in ic.JOB_STATES:
        assert f"[{state}]" in doc


def _job(status, result=None, error=None):
    return {"job_id": "job_abcdef1234", "operation": "parse_resume", "status": status, "attempts": 1, "max_attempts": 3,
            "created_at": "2026-11-07T09:00:00Z", "started_at": None, "completed_at": None, "result": result, "error": error}


def test_job_status_schema_enforces_result_and_error_by_status():
    ok = ResumeParsingService(resolver=lambda ref: str(next(RESUME_DIR.glob("docx/resume_01*.docx")))).run(
        {"candidate_id": "C1", "file_ref": "x.docx", "file_type": "docx", "as_of_date": "2026-11-01"})
    assert ic.validate_response("JobStatus", _job("completed", result=ok)) == []
    assert ic.validate_response("JobStatus", _job("failed", error={"code": "corrupt_file", "message": "m", "field": None})) == []
    assert ic.validate_response("JobStatus", _job("running")) == []
    assert ic.validate_response("JobStatus", _job("completed")) != []                         # completed needs a result
    assert ic.validate_response("JobStatus", _job("failed", result=ok)) != []                 # failed has no result
    assert ic.validate_response("JobStatus", _job("running", result=ok)) != []                # unfinished has no result
    assert ic.validate_response("JobStatus", _job("exploded")) != []


# ---------------------------------------------------------------------------------------------------- retry and backoff
def test_backoff_is_full_jitter_bounded_and_capped():
    p = ic.RetryPolicy(base_delay_s=0.5, max_delay_s=30.0)
    assert ic.backoff_delay(1, p, rng=lambda: 1.0) == 0.5
    assert ic.backoff_delay(3, p, rng=lambda: 1.0) == 2.0
    assert ic.backoff_delay(20, p, rng=lambda: 1.0) == 30.0                       # the cap
    assert ic.backoff_delay(4, p, rng=lambda: 0.0) == 0.0                          # full jitter can be zero
    rng = random.Random(7)
    for n in range(1, 12):
        assert 0 <= ic.backoff_delay(n, p, rng=rng.random) <= min(30.0, 0.5 * 2 ** (n - 1))
    with pytest.raises(ValueError):
        ic.backoff_delay(0, p)


def _ok():
    return {"status": "success"}


def _err(code):
    return {"status": "error", "error": {"code": code, "message": "m", "field": None}}


def test_retry_succeeds_after_transient_failures_and_records_the_waits():
    calls, slept = [], []

    def flaky(attempt):
        calls.append(attempt)
        if attempt < 3:
            raise ic.TransportError("service_unavailable")
        return _ok()

    out = ic.call_with_retry(flaky, sleep=slept.append, rng=lambda: 1.0)
    assert out.envelope["status"] == "success" and out.attempts == 3 and out.gave_up is None
    assert slept == [0.5, 1.0] == out.delays


@pytest.mark.parametrize("code", [c for c, r in ic.ERROR_RULES.items() if r.max_retries == 0])
def test_retry_never_retries_a_code_the_policy_forbids(code):
    slept = []
    out = ic.call_with_retry(lambda a: _err(code), sleep=slept.append)
    assert out.attempts == 1 and slept == [] and out.gave_up == "not_retryable"


def test_retry_honours_each_codes_own_limit_and_the_global_limit():
    out = ic.call_with_retry(lambda a: _err("internal_error"), sleep=lambda s: None, rng=lambda: 0.0)
    assert out.attempts == 2 and out.gave_up == "retries_exhausted"                  # internal_error: one retry
    out = ic.call_with_retry(lambda a: _err("file_not_found"), sleep=lambda s: None, rng=lambda: 0.0)
    assert out.attempts == 3                                                         # two retries
    out = ic.call_with_retry(lambda a: _err("rate_limited"), ic.RetryPolicy(max_retries=2), sleep=lambda s: None, rng=lambda: 0.0)
    assert out.attempts == 3                                                         # policy caps the code's 5 at 2


def test_retry_follows_retry_after_as_a_minimum_wait_and_the_wait_budget():
    slept = []

    def limited(attempt):
        if attempt == 1:
            raise ic.TransportError("rate_limited", retry_after_seconds=9)
        return _ok()

    out = ic.call_with_retry(limited, sleep=slept.append, rng=lambda: 0.0)
    assert slept == [9] and out.envelope["status"] == "success"
    out = ic.call_with_retry(lambda a: (_ for _ in ()).throw(ic.TransportError("rate_limited", 25)), ic.RetryPolicy(total_wait_budget_s=20), sleep=lambda s: None)
    assert out.gave_up == "wait_budget_exhausted" and out.attempts == 1


def test_retrying_a_deterministic_service_gives_the_same_answer():
    """Why retries and replays are safe (Day 57): same request, same response."""
    body = {"resume_text": RESUME, "job_description": JD}
    first = ATSService().run(body)
    out = ic.call_with_retry(lambda a: ATSService().run(body))
    assert out.envelope == first
    d = {"ats_score": 70, "hr_interview_score": 80, "candidate_id": "C1"}
    assert DecisionScoringService().run(d) == DecisionScoringService().run(d)


# ---------------------------------------------------------------------------------------------------- idempotency
def test_canonical_hash_ignores_key_order_and_spacing_but_not_content_or_operation():
    a = ic.canonical_request_hash("score_ats", {"a": 1, "b": [1, 2]})
    assert a == ic.canonical_request_hash("score_ats", {"b": [1, 2], "a": 1})
    assert a != ic.canonical_request_hash("score_ats", {"a": 1, "b": [2, 1]})
    assert a != ic.canonical_request_hash("score_screening", {"a": 1, "b": [1, 2]})


def test_idempotency_new_replay_conflict_and_in_progress():
    store = ic.IdempotencyStore()
    body = {"job_description": JD, "candidates": []}
    assert store.begin("t1", "k1", "score_ats_batch", body) == ("new", None)
    assert store.begin("t1", "k1", "score_ats_batch", body) == ("in_progress", None)
    store.complete("t1", "k1", {"job_id": "job_abcdef1234"})
    state, stored = store.begin("t1", "k1", "score_ats_batch", dict(reversed(list(body.items()))))
    assert state == "replay" and stored == {"job_id": "job_abcdef1234"}
    assert store.begin("t1", "k1", "score_ats_batch", {"job_description": "other", "candidates": []})[0] == "conflict"
    assert store.begin("t2", "k1", "score_ats_batch", {"x": 1})[0] == "new"          # keys are per tenant
    for bad in ("", "k" * 129):
        with pytest.raises(ValueError):
            store.begin("t1", bad, "score_ats_batch", body)


def test_idempotency_replay_is_a_copy_not_a_shared_object():
    store = ic.IdempotencyStore()
    store.begin("t", "k", "op", {})
    store.complete("t", "k", {"x": [1]})
    _, first = store.begin("t", "k", "op", {})
    first["x"].append(2)
    assert store.begin("t", "k", "op", {})[1] == {"x": [1]}


# ---------------------------------------------------------------------------------------------------- access (Day 55)
def test_access_check_finds_exactly_the_documented_gaps():
    gaps = {c.key for c in ic.check_data_access() if c.allowed is not True}
    assert gaps == set(ic.KNOWN_GAPS), "the plan and the Day 55 matrix disagree in a new way (or a gap was fixed): update KNOWN_GAPS and the document"


def test_every_modelled_touch_other_than_the_known_gaps_is_allowed_for_the_service_role():
    for c in ic.check_data_access():
        if c.key not in ic.KNOWN_GAPS:
            assert c.allowed is True, (c.key, c.rule_id)


def test_the_service_role_can_never_confirm_a_rejection_or_edit_the_audit_log():
    ctl = AccessController()
    svc = Actor("ai", Role.SERVICE)
    assert not ctl.decide(svc, Action.CONFIRM_REJECTION, Resource(ResourceType.DECISION, "cref_x", "co")).allowed
    assert not ctl.decide(svc, Action.DELETE, Resource(ResourceType.AUDIT_LOG)).allowed
    assert ctl.decide(svc, Action.WRITE, Resource(ResourceType.AUDIT_LOG)).allowed


def test_finding_G3_tenant_isolation_is_not_enforced_for_the_service_role():
    """Finding G3: rule R1 applies to recruiter/company_admin only, so a service-role request is not tenant-checked by Day 55's code.
    The plan therefore puts the tenant in the signed token and forbids cross-tenant batches. If this test fails, R1 changed: update the plan."""
    ctl = AccessController()
    svc = Actor("ai", Role.SERVICE, company_id="co_A")
    assert ctl.decide(svc, Action.READ, Resource(ResourceType.RESUME, "cref_x", "co_B")).allowed
    rec = Actor("r", Role.RECRUITER, company_id="co_A")
    assert not ctl.decide(rec, Action.READ, Resource(ResourceType.RESUME, "cref_x", "co_B")).allowed


# ---------------------------------------------------------------------------------------------------- logging (no personal data)
MARK = "ZZ-SECRET-MARKER-ZZ"


def test_no_service_logs_the_text_it_was_given(caplog):
    caplog.set_level(logging.DEBUG)
    ATSService().run({"resume_text": f"Skills: React {MARK}", "job_description": f"Required Skills: React {MARK}"})
    ATSBatchService().run({"job_description": JD, "candidates": [{"candidate_id": "A1", "resume_text": f"React {MARK}"}]})
    ScreeningService().run({"candidate_id": "C1", "turns": [{"text": f"I am {MARK}", "confidence": 0.9}]})
    InterviewIntelligenceService().run({"interview_type": "hr", "answers": [f"I am {MARK}"]})
    InterviewIntelligenceService().run({"interview_type": "technical", "domain": "mern", "experience_years": 2, "answers": [f"{MARK}"]})
    DecisionScoringService().run({"candidate_id": "C1", "ats_score": 50})
    assert caplog.records, "nothing was logged, so this test proves nothing"
    assert MARK not in caplog.text


def test_error_messages_do_not_echo_the_text_that_caused_them():
    env = ATSService().run({"resume_text": [MARK], "job_description": JD})
    assert env["status"] == "error" and MARK not in json.dumps(env)


# ---------------------------------------------------------------------------------------------------- resume parsing service
def _docx(name="resume_01_mern_developer"):
    return str(RESUME_DIR / "docx" / f"{name}.docx")


def _svc(path=None):
    return ResumeParsingService(resolver=lambda ref: path or _docx())


def test_resume_parsing_returns_the_structured_fields_and_validates():
    out = _svc().run({"candidate_id": "cref_1", "file_ref": "r.docx", "file_type": "docx", "as_of_date": "2026-11-01"})
    assert out["status"] == "success" and ic.validate_response("ParseResumeResult", out) == []
    assert out["has_text"] and set(out["detected_sections"]) >= {"Skills", "Experience", "Education"}
    assert any(s["name"] == "React" or s["name"] == "Node.js" for s in out["skills"])
    assert out["education"][0]["degree"] == "B.Tech" and out["certifications"]
    assert set(out) <= ic.declared_keys("ParseResumeResult")


def test_resume_parsing_does_not_return_name_or_contact_fields():
    out = _svc().run({"candidate_id": "cref_1", "file_ref": "r.docx", "file_type": "docx", "as_of_date": "2026-11-01"})
    for forbidden in ("name", "email", "phone", "contact", "address", "date_of_birth"):
        assert forbidden not in out, forbidden
    for item in out["education"] + out["certifications"] + out["experience"]["entries"]:
        assert not {"email", "phone", "contact", "address"} & set(item)


def test_resume_parsing_is_repeatable_once_the_present_date_is_pinned():
    body = {"candidate_id": "cref_1", "file_ref": "r.docx", "file_type": "docx", "as_of_date": "2026-11-01"}
    assert _svc().run(body) == _svc().run(body)
    later = _svc().run({**body, "as_of_date": "2027-11-01"})
    assert later["experience"]["total_years"] > _svc().run(body)["experience"]["total_years"]      # "Present" really moves


def test_resume_parsing_pdf_works_too():
    pdf = str(RESUME_DIR / "pdf" / "resume_01_mern_developer.pdf")
    out = _svc(pdf).run({"candidate_id": "cref_1", "file_ref": "r.pdf", "file_type": "pdf", "as_of_date": "2026-11-01"})
    assert out["status"] == "success" and out["has_text"] and ic.validate_response("ParseResumeResult", out) == []


@pytest.mark.parametrize("ref", ["../../etc/passwd", "/etc/passwd", "a/../../outside.pdf"])
def test_resume_parsing_refuses_paths_outside_the_store(ref):
    out = ResumeParsingService().run({"candidate_id": "c1", "file_ref": ref, "file_type": "pdf"})
    assert out["status"] == "error" and out["error"]["code"] == "invalid_input" and out["error"]["field"] == "file_ref"


def test_resume_parsing_upload_error_codes_reach_the_caller(tmp_path):
    empty = tmp_path / "empty.docx"
    empty.write_bytes(b"")
    corrupt = tmp_path / "bad.pdf"
    corrupt.write_bytes(b"this is not a pdf")
    cases = [(str(empty), "docx", "empty_file"), (str(corrupt), "pdf", "corrupt_file"), (str(tmp_path / "nope.pdf"), "pdf", "file_not_found")]
    for path, ftype, code in cases:
        out = ResumeParsingService(resolver=lambda ref, p=path: p).run({"candidate_id": "c1", "file_ref": "x", "file_type": ftype})
        assert out["status"] == "error" and out["error"]["code"] == code, out
        assert ic.validate_response("ServiceErrorEnvelope", out) == []


def test_resume_parsing_input_validation():
    base = {"candidate_id": "c1", "file_ref": "r.docx", "file_type": "docx"}
    cases = [({k: v for k, v in base.items() if k != "file_type"}, "missing_field"), ({**base, "file_type": "txt"}, "unsupported_value"),
             ({**base, "candidate_id": 5}, "invalid_input"), ({**base, "as_of_date": "yesterday"}, "invalid_input"),
             ({**base, "file_ref": "x" * 600}, "too_large"), ({**base, "file_type": "pdf"}, "invalid_input")]
    for body, code in cases:
        out = _svc().run(body)
        assert out["status"] == "error" and out["error"]["code"] == code, (body, out)


def test_gateway_validates_the_resume_parsing_request():
    ok = {"candidate_id": "cref_1", "file_ref": "tenant1/r.docx", "file_type": "docx", "as_of_date": "2026-11-01"}
    assert ic.validate_request("parse_resume", ok) is None
    expect = [({k: v for k, v in ok.items() if k != "file_type"}, "missing_field", "file_type"),
              ({**ok, "file_type": "txt"}, "unsupported_value", "file_type"), ({**ok, "as_of_date": "yesterday"}, "invalid_input", "as_of_date"),
              ({**ok, "file_ref": "x" * 600}, "too_large", "file_ref"), ({**ok, "candidate_id": "a@b.com"}, "invalid_input", "candidate_id")]
    for body, code, field in expect:
        err = ic.validate_request("parse_resume", body)
        assert err and err["error"]["code"] == code and err["error"]["field"] == field, (body, err)


def test_resume_parsing_a_readable_file_with_no_text_is_a_warning_not_a_crash(tmp_path):
    from docx import Document
    blank = tmp_path / "blank.docx"
    Document().save(blank)
    out = ResumeParsingService(resolver=lambda ref: str(blank)).run({"candidate_id": "c1", "file_ref": "b.docx", "file_type": "docx"})
    assert out["status"] == "success" and out["has_text"] is False and out["skills"] == [] and out["warnings"]


# ---------------------------------------------------------------------------------------------------- batch service
CANDS = [{"candidate_id": f"A{i}", "resume_text": t} for i, t in enumerate([RESUME, "Skills: Excel\nExperience:\nClerk, X (2019 - 2021)", "", RESUME + " Docker"])]


def test_batch_result_equals_single_request_result_for_every_candidate():
    """The consistency rule: a candidate's score and zone do not depend on who else was in the batch."""
    batch = ATSBatchService().run({"job_description": JD, "candidates": CANDS})
    assert batch["status"] == "success" and batch["total"] == 4 and batch["scoring_basis"] == "per_pair"
    for item, cand in zip(batch["results"], CANDS):
        assert item["outcome"] == ATSService().run({"resume_text": cand["resume_text"], "job_description": JD})


def test_batch_result_does_not_change_with_batch_order_or_company():
    forward = ATSBatchService().run({"job_description": JD, "candidates": CANDS})
    backward = ATSBatchService().run({"job_description": JD, "candidates": list(reversed(CANDS))})
    assert {r["candidate_id"]: r["outcome"] for r in forward["results"]} == {r["candidate_id"]: r["outcome"] for r in backward["results"]}


def test_batch_one_bad_item_does_not_fail_the_batch():
    cands = [{"candidate_id": "A1", "resume_text": RESUME}, {"candidate_id": "A2", "resume_text": 12345}]
    out = ATSBatchService().run({"job_description": JD, "candidates": cands})
    assert out["status"] == "success" and out["succeeded"] == 1 and out["failed"] == 1
    assert out["results"][1]["outcome"]["status"] == "error" and ic.validate_response("ATSBatchScoreResult", out) == []


@pytest.mark.parametrize("body,code", [
    ({"job_description": JD}, "missing_field"), ({"job_description": JD, "candidates": []}, "invalid_input"),
    ({"job_description": JD, "candidates": ["x"]}, "invalid_input"),
    ({"job_description": JD, "candidates": [{"resume_text": "x"}]}, "missing_field"),
    ({"job_description": JD, "candidates": [{"candidate_id": "A", "resume_text": "x"}, {"candidate_id": "A", "resume_text": "y"}]}, "invalid_input"),
    ({"job_description": " ", "candidates": [{"candidate_id": "A", "resume_text": "x"}]}, "invalid_input"),
    ({"job_description": JD, "candidates": [{"candidate_id": "A", "resume_text": "x"}] * 201}, "too_large"),
])
def test_batch_refuses_unusable_requests_with_the_shared_codes(body, code):
    out = ATSBatchService().run(body)
    assert out["status"] == "error" and out["error"]["code"] == code


# ---------------------------------------------------------------------------------------------------- generated files and docs
def test_generated_files_in_the_repo_match_the_code():
    schema_file = ROOT / "schemas" / "integration_api_schemas.json"
    assert json.loads(schema_file.read_text(encoding="utf-8")) == json.loads(json.dumps(ic.schema_document())), "run run_day59_integration_demo.py to regenerate"
    api_file = ROOT / "api" / "integration_openapi.yaml"
    assert yaml.safe_load(api_file.read_text(encoding="utf-8")) == json.loads(json.dumps(ic.build_openapi()))


def test_the_integration_document_mentions_every_operation_path_and_error_code():
    doc = (ROOT / "docs" / "day59_ai_integration_document.md").read_text(encoding="utf-8")
    for op in ic.OPERATIONS:
        assert op.path_with_prefix in doc, op.path_with_prefix
    for code in ic.ERROR_CODES:
        assert f"`{code}`" in doc, code
    for gap in ("G1", "G2", "G3"):
        assert gap in doc


def test_the_mapping_diagram_mentions_every_operation_and_store():
    text = (ROOT / "docs" / "day59_api_mapping_diagram.md").read_text(encoding="utf-8")
    for op in ic.OPERATIONS:
        assert op.path_with_prefix in text or op.op_id in text, op.op_id
    for store in ic.known_store_ids():
        assert store in text, store


def test_existing_api_specs_are_untouched():
    """Day 59 adds a gateway view; it does not rewrite the Day 16/32/44 module specs."""
    for name in ("openapi.yaml", "screening_openapi.yaml", "hr_interview_openapi.yaml"):
        spec = yaml.safe_load((ROOT / "api" / name).read_text(encoding="utf-8"))
        assert spec["openapi"].startswith("3.0") and spec["paths"]
