# Day 61 – Logging Structure

Zecpath – AI Job Portal | Structured logging for API logs, model outputs and errors

## Principles

1. **Logs are an uncontrolled copy.** They are shipped, indexed, searched by engineers and kept for weeks. They must never hold what the audit log is forbidden to hold: resume text, answers, transcripts, names, contact details.
2. **Allowlist, not denylist.** A field is logged only if it is on a list; everything else is refused. Model outputs are chosen field by field from a per-operation list, never "log the response".
3. **Numbers and codes, not content.** A request's text is logged as a SIZE (`input_chars`); a response's list becomes a COUNT; a reason sentence never leaves the process.
4. **One id ties it together.** `request_id` is on every event of a call and on the audit entries.
5. **Logging never breaks a request.** A failing sink or a refused event is caught and counted (`ai_log_dropped_total`); the caller still gets the service's answer unchanged.
6. **Machine first.** One JSON object per line, sorted keys, UTC timestamps, a schema version, and a JSON Schema (`schemas/observability_log_schemas.json`) generated from the same constants as the guard, so the two cannot drift.

## The streams

| Event | Extra fields | Written when |
|---|---|---|
| `api_request` | `duration_ms`, `error_class`, `error_code`, `http_status`, `input_chars`, `mode`, `retry_attempt`, `status`, `warnings` | every call, success or error |
| `model_output` | `outputs` | every successful call |
| `error` | `duration_ms`, `error_class`, `error_code`, `exception_type`, `field`, `http_status`, `retryable` | every failed call, never sampled |

The Day 55 **audit log** is a fourth record, kept apart: append-only, hash-chained, long-lived, written by the backend, readable by auditors. It is not a log event and is not shipped with the operational logs (see `docs/day61_ai_observability_plan.md`, section 6).

### Envelope (on every event)

| Field | Meaning |
|---|---|
| `api_version` | API contract version |
| `candidate_ref` | pseudonymous candidate reference (`cref_...`), never a name or an email |
| `event` | `api_request`, `model_output` or `error` |
| `level` | INFO or ERROR |
| `model_version` | scoring model version that produced the result |
| `op_id` | which operation (`score_ats`, ...) |
| `request_id` | one id per call; the same on every event of the call and on the audit entries |
| `schema_version` | log format version (so readers can evolve) |
| `service` | service name |
| `tenant_ref` | pseudonymous tenant (company) reference |
| `tier` | sync or async |
| `ts` | UTC time, ISO 8601, milliseconds |

### Fields per event

| Event | Field | Meaning |
|---|---|---|
| `api_request` | `status` | success or error |
| `api_request` | `http_status` | status the gateway would send |
| `api_request` | `error_code` | Day 59 error code, or null |
| `api_request` | `error_class` | none, client or server |
| `api_request` | `duration_ms` | compute time of the call |
| `api_request` | `input_chars` | total characters of text in the request: a SIZE, never the text |
| `api_request` | `warnings` | number of warnings in the response |
| `api_request` | `mode` | sync or async |
| `api_request` | `retry_attempt` | which attempt this was |
| `model_output` | `outputs` | the allowlisted numbers and codes of the response (next table); lists appear as `<name>_count` |
| `error` | `error_code` | Day 59 error code |
| `error` | `error_class` | client or server |
| `error` | `http_status` | status |
| `error` | `field` | the field the caller got wrong (a name, short) |
| `error` | `retryable` | whether the Day 59 policy allows a retry |
| `error` | `exception_type` | type of an unexpected exception (never its message) |
| `error` | `duration_ms` | time spent before failing |

### What a `model_output` may contain, by operation

| Operation | Allowlisted response fields (lists logged as a count) |
|---|---|
| `parse_resume` | `file_type`, `has_text`, `line_count`, `detected_sections`, `skills`, `education`, `certifications`, `warnings` |
| `score_ats` | `scoring_mode`, `ats_score`, `zone`, `role_category`, `warnings` |
| `score_ats_batch` | `scoring_basis`, `total`, `succeeded`, `failed`, `warnings` |
| `score_screening` | `call_status`, `screening_score`, `categories_answered`, `categories_missing`, `turns_used`, `warnings` |
| `score_interview` | `interview_type`, `interview_status`, `tier`, `hr_score`, `technical_score`, `communication_score`, `relevance_score`, `confidence_score`, `answers_scored`, `answers_ignored`, `non_substantive_answers`, `warnings` |
| `recommend_decision` | `hiring_fit_score`, `decision`, `hold_kind`, `confidence`, `provisional`, `missing_rounds`, `human_review_required`, `human_confirmation_required`, `automation_eligible`, `automated_action`, `human_review_reasons`, `warnings` |

For `parse_resume` two numbers from the nested experience (`experience_total_years`, `experience_total_months`) are also allowed. Everything not listed stays inside the process: the cleaned resume text, the skill names, the reason sentences, the transcript.

## What is refused

The logger drops an event, counts it under `policy_violation`, and raises alert rule `A13` when any of these appears:

- a key from the forbidden list (the same list the Day 55 audit log uses): `address`, `age`, `answer`, `answer_text`, `answers`, `audio`, `caste`, `date_of_birth`, `disability`, `dob`, `email`, `ethnicity`, `first_name`, `full_name`, `gender`, `last_name`, `marital_status`, `name`, `nationality`, `phone`, `photo`, `race`, `raw_text`, `recording`, `religion`, `response`, `response_text`, `resume_text`, `text`, `transcript`, `transcript_text`, `video`;
- a field that is not on the allowlist for that event;
- a string longer than 64 characters (long strings are free text);
- a value that is not a number, boolean, null, short code or a flat mapping of those (nesting is limited to two levels);
- a number that is not finite.

## Real examples

An `api_request` for a successful ATS call (the resume and job description are NOT in it, only the size):

```json
{"api_version": "1.0", "candidate_ref": "cref_7b3bae96d8caeac7fae7", "duration_ms": 3.797, "error_class": "none", "error_code": null, "event": "api_request", "http_status": 200, "input_chars": 1555, "level": "INFO", "mode": "sync", "model_version": "v0.1.0", "op_id": "score_ats", "request_id": "req-000021", "schema_version": "1.0", "service": "ats_ai_service", "status": "success", "tier": "sync", "ts": "2025-11-05T00:00:40.000+00:00", "warnings": 0}
```

Its `model_output`, with the allowlisted numbers and codes:

```json
{"api_version": "1.0", "candidate_ref": "cref_7b3bae96d8caeac7fae7", "event": "model_output", "level": "INFO", "model_version": "v0.1.0", "op_id": "score_ats", "outputs": {"ats_score": 50.2, "role_category": "tech", "scoring_mode": "ats_engine", "warnings_count": 0, "zone": "shortlist"}, "request_id": "req-000021", "schema_version": "1.0", "service": "ats_ai_service", "tier": "sync", "ts": "2025-11-05T00:00:41.000+00:00"}
```

An `error` for a request that left out the job description (the field NAME is logged, not its content):

```json
{"api_version": "1.0", "duration_ms": 0.017, "error_class": "client", "error_code": "missing_field", "event": "error", "field": "job_description", "http_status": 422, "level": "ERROR", "model_version": "v0.1.0", "op_id": "score_ats", "request_id": "req-000230", "retryable": false, "schema_version": "1.0", "service": "ats_ai_service", "tier": "sync", "ts": "2025-11-05T00:07:39.000+00:00"}
```

## Levels, sampling, retention (all proposed)

| Event | Level | Sampling | Retention |
|---|---|---|---|
| `error` | ERROR | never sampled | 90 days |
| `api_request` | INFO | keep all; sample 1 in 10 only if volume demands it (Day 60: logging costs under 0.2 ms per call) | 30 days |
| `model_output` | INFO | same as `api_request` | 30 days |
| audit entries | n/a | never | the Day 55 retention plan |

Sampling is deterministic (every N-th event) and never applies to errors. Because `model_output` events feed the drift rules (`A06`, `A07`), do not sample them below what the minimum-event limits of those rules need.

## How to follow one request

Take the `request_id` from a complaint or an alert. Find the `api_request` line (status, error class, duration), the `error` line if there is one (code, field, whether a retry was allowed), the `model_output` line (what the system produced, as numbers and codes), and for a decision the two audit entries and any human review that share the id. `parsers/decision_audit.py` can then **replay** the decision from the audit inputs to confirm the logged result follows from them.

## How it plugs in

```python
observer = ServiceObserver({"score_ats": ATSService(), "recommend_decision": DecisionScoringService()}, StructuredLogger(sink))
response = observer.call("score_ats", payload, candidate_ref=ref, request_id=request_id)   # the same answer the service would give
```

The existing text logging in `utils/logger.py` (console and rotating file, no personal data, Day 59 tested) stays for developers; the structured stream is for operations and is what the shipper reads.

## Evidence

- 478 events from the real services on the sample data; **0 of 360** thirty-character slices of 120 real input texts (resumes, answers, transcripts, job descriptions) were found in the logs.
- 478 of 478 events valid against the generated schema.
- The guard refused a forbidden key, an unlisted field and an over-long string, and counted them.
- Observer overhead: 0.138 ms per ATS call in the latest run (about 0.03 to 0.33 ms across runs).
- Tests: 66 new in `tests/test_observability.py` (the logger guard, observer, metrics, drift, every alert rule, simulated incidents, dashboards, decision-audit replay, generated files and these documents); full suite 2,017 passed, 6 skipped (previous 1,951).

## Limits

There is no log shipper, search index or retention job; the sink is a function (the demo writes a file). Retention and sampling numbers are proposals. The privacy test checks for 30-character slices of the inputs; it proves no text was copied, not that no personal fact could be inferred from numbers such as a score and a timestamp. Candidate references are pseudonyms, and linking them back to a person needs the identity map, which logs never see.
