# Day 59 – API & Integration Planning

Zecpath – AI Job Portal | AI integration document

## Objective

Define how all AI modules integrate with backend services and external systems: identify the AI APIs, map backend → AI → database interactions, define request/response formats, design sync vs async processing, define error handling and retries, and plan authentication and security.

**How to read this.** Day 59 is a planning day, so most of it is design. Three kinds of statement are kept apart:

- **Checked against the code.** The API catalogue, error codes, schemas, access map and retry rules live in `parsers/integration_contract.py`, and `tests/test_integration_contract.py` fails if the code and this plan disagree.
- **Measured.** Timings and the batch comparison come from `run_day59_integration_demo.py` on this machine, compute only (no network, storage or speech-to-text).
- **Proposed.** Timeouts, size caps, token lifetimes and rate limits are starting points to tune. They are marked PROPOSED.

Nothing is deployed. There is no gateway, queue, job store, database or login server in this project. Two small services were added so that every API in the brief has real code behind it (section 1). Existing code was not changed.

## Decisions requested

| # | Decision | Why now |
|---|---|---|
| D1 | The AI layer is **stateless**: the backend reads inputs, calls the AI, and saves the results and the audit entry. The AI services never connect to a database. | Matches how the four Day 57 services already work; makes retries safe; keeps one writer for the audit log. It reverses the Day 16 idea that the ATS API stores resumes itself. |
| D2 | Batch scoring scores each candidate on its own pair, never on a shared corpus (already built that way). | Measured: a shared corpus changed one candidate's zone out of 16 (finding F1). |
| D3 | The resume-parsing API returns text, skills, experience, education and certifications, but **no name, email or phone**. The Day 2 `CandidateProfile` schema, which requires them, is not the output contract. | No engine uses them, Day 15 masks them, the audit log forbids them (F4). |
| D4 | Fix the Day 55 gaps: add a resource type for parsed resume fields, and a job store to the storage plan (G1, G2). Decide how tenant isolation reaches the service role (G3). | The access check run in section 2 fails on exactly these three. |
| D5 | Choose the gateway, queue and identity provider. Keep polling (not webhooks) for job results until then. | None exists; section 6 states what each must provide. |

## 1. The AI APIs

The brief lists five AI APIs. All five now have a service class behind the Day 57 `run(payload)` contract (never raises, always returns a success or error envelope). Two classes are new in Day 59: resume parsing had no service (only loose functions and a Day 1 stub in `parsers/resume_parser.py`), and batch scoring needed its own.

| Operation | Method and path | Mode | Implemented by | Scope | Proposed timeout | Status |
|---|---|---|---|---|---|---|
| `parse_resume` | `POST /v1/ai/resumes/parse` | async (202) | `ResumeParsingService` (new) | `ai:resume:parse` | 60 s | service |
| `score_ats` | `POST /v1/ai/ats/score` | sync (200) | `ATSService` | `ai:ats:score` | 2 s | service |
| `score_ats_batch` | `POST /v1/ai/ats/score-batch` | async (202) | `ATSBatchService` (new) | `ai:ats:score` | 120 s | service |
| `score_screening` | `POST /v1/ai/screening/score` | sync (200) | `ScreeningService` | `ai:screening:score` | 2 s | service |
| `score_interview` | `POST /v1/ai/interviews/score` | sync (200) | `InterviewIntelligenceService` | `ai:interview:score` | 2 s | service |
| `recommend_decision` | `POST /v1/ai/decisions/recommend` | sync (200) | `DecisionScoringService` | `ai:decision:recommend` | 2 s | service |
| `get_job` | `GET /v1/ai/jobs/{job_id}` | sync (200) | job store | `ai:jobs:read` | 2 s | planned |
| `cancel_job` | `POST /v1/ai/jobs/{job_id}/cancel` | sync (200) | job store | `ai:jobs:cancel` | 2 s | planned |
| `health` | `GET /v1/ai/health` | sync (200) | gateway | none | 1 s | planned |

"Status: service" means the AI class exists and is tested. The HTTP gateway around every row is still planned.

**How this relates to the earlier specs.** The Day 16 (ATS), Day 32 (screening) and Day 44 (HR interview) OpenAPI files stay as the detailed contracts for session-style flows: a live call fed turn by turn (`/calls/{id}/turns`) and per-answer interview submission (`/hr-interviews/{id}/responses`). The gateway operations above take a whole payload and answer once. Ranking, aptitude, unified score and transcript scrubbing remain in their module specs; Day 59 does not re-specify them.

## 2. Backend → AI → database

One pattern for every operation. The backend authenticates the user and checks the Day 55 access rules for what they asked. It reads the input from its store, calls the AI gateway with a service token, receives the result, saves it, and appends an audit entry. The AI layer never touches a store (decision D1).

Every read and write was run through the real Day 55 `AccessController` as the service role, using the stores of the Day 55 storage plan.

| Operation | Reads | Writes | Check |
|---|---|---|---|
| `parse_resume` | resume (resume_store) | resume (resume_store); audit_log (audit_store) | gap: resume write (G1) |
| `score_ats` | resume (resume_store); job_store | score (report_store); audit_log (audit_store) | gap: job_store read (G2) |
| `score_ats_batch` | resume (resume_store); job_store | score (report_store); audit_log (audit_store) | gap: job_store read (G2) |
| `score_screening` | transcript (transcript_store) | score (report_store); audit_log (audit_store) | all allowed |
| `score_interview` | transcript (transcript_store) | score (report_store); audit_log (audit_store) | all allowed |
| `recommend_decision` | score (report_store) | decision (report_store); audit_log (audit_store) | all allowed |

17 of 20 touches are allowed. The three that are not are real findings, pinned exactly by a test:

- **G1.** The role matrix lets the service read a resume but not write one, and has no resource type for parsed fields. Either add a resource type (for example `parsed_profile`) or allow the service to write resumes.
- **G2.** Job descriptions are not a Day 55 resource type and the storage plan has no job store. A job description is a company document, not personal data, so this is a gap in the plan more than a risk.
- **G3.** Tenant isolation (rule R1) applies to recruiters and company admins only. A service-role request is not tenant-checked by the Day 55 code. A test pins this. The plan therefore (a) puts the tenant and the pseudonymous actor in the signed service token and (b) forbids a batch from mixing tenants, since the AI layer only ever sees the payload it was handed.

Also confirmed by test: the service role can never confirm a rejection (rule R6) and can append to, but never edit or delete, the audit log (rule R5). A recommendation of "rejected" always carries `human_confirmation_required: true` and `automated_action: "none"`.

## 3. Request and response formats

**Files.** `schemas/integration_api_schemas.json` (24 JSON Schemas, draft 2020-12) and `api/integration_openapi.yaml` (OpenAPI 3.1, 9 operations) are generated by the demo from `parsers/integration_contract.py`. Enum values and limits are read from the code (for example the decision outcomes, role types and technical domains), not typed a second time. A test fails if the files in the repo differ from what the code generates. Worked examples are in `data/integration/day59_example_payloads.json`.

**Responses** keep the Day 57 envelope: `service`, `model_version`, `api_version`, `status` (`success` or `error`), plus the operation's fields. Response schemas allow extra fields so a new field does not break clients, and a test fails if a real service returns a field the schema does not declare.

**Requests** are strict: unknown fields are refused. The gateway checks every request against its schema before the service sees it, and answers in the services' own error codes and field names. Eight deliberately bad requests were sent to both; the code agreed every time, and a 15-case test table checks the same.

The gateway is stricter than the services in three documented ways: `candidate_id` must look like a pseudonymous reference (letters, digits, `_`, `-`, up to 64 characters, so a name or an email cannot pass); unknown fields are refused; and `experience_years` is capped at 60.

| Operation | Request (required fields) | Response (key fields) |
|---|---|---|
| `parse_resume` | `candidate_id`, `file_ref`, `file_type` (pdf/docx); optional `as_of_date` | cleaned text, sections, skills, experience (years, entries, gaps), education, certifications, warnings |
| `score_ats` | `job_description` (or deprecated `job_requirements`); `resume_text` | `ats_score` 0–100, `zone` (shortlist/review/reject), components, warnings |
| `score_ats_batch` | `job_description`, `candidates[]` (`candidate_id`, `resume_text`) | per-candidate outcome, `succeeded`, `failed`, `scoring_basis: per_pair` |
| `score_screening` | `candidate_id`, `turns[]` (`text`, `confidence`, `is_silent`) | `call_status`, `screening_score` (null when nothing to score), categories answered/missing |
| `score_interview` | `interview_type` (hr/technical); technical needs `experience_years` | `hr_score` or `technical_score`, `answers_scored`, `answers_ignored` |
| `recommend_decision` | any round score(s) 0–100; optional `ats_zone`, `role_type`, `experience_level` | `hiring_fit_score`, `decision` (selected/hold_review/rejected), `human_confirmation_required`, reasons |

**Two rules about meaning.** A missing score is absent, never zero (Day 57). `as_of_date` makes "Present" on a CV a fixed date, so a parse can be repeated exactly; without it the result depends on the day it ran.

**Size limits.** The service limits (200 items, 20,000 characters per answer, 200,000 per text) allow far larger requests than the proposed gateway caps: up to 153 MiB for a batch and 15 MiB for an interview against proposed caps of 10 MiB and 2 MiB. The cap is what really binds, and the gateway answers `too_large` (413). Real limits should come from real data (F3).

## 4. Sync versus async

**The rule.** An operation is synchronous when its work is bounded by the schema limits, finishes well inside the proposed 2 s timeout, and the caller needs the answer to continue. It is asynchronous when it reads a file or an external system, covers a batch, or is the start of a longer pipeline.

**Measured compute** (this machine, 30 runs each, p95 shown; one run, so do not read a ranking into differences of a few milliseconds):

| Operation | p50 | p95 |
|---|---|---|
| Resume parse, DOCX | 7.2 ms | 23.7 ms |
| Resume parse, PDF | 19.0 ms | 20.0 ms |
| ATS score, one resume | 3.9 ms | 4.1 ms |
| Screening score, 7 turns | 2.4 ms | 2.9 ms |
| HR interview score, 6 answers | 2.4 ms | 2.4 ms |
| Technical interview score, 6 answers | 0.06 ms | 0.09 ms |
| Decision | 0.06 ms | 0.08 ms |
| ATS batch, 16 resumes | 61.5 ms | 62.7 ms |

**Real-time interview scoring is sync.** Scoring takes a few milliseconds, far inside the 2 s timeout, and a live interview needs the follow-up decision before the next question. The per-answer path (Day 44 `/hr-interviews/{id}/responses`) is the live variant; `score_interview` scores a finished set of answers. The real latency of a live interview will be speech-to-text and the network, which are not built and not measured here.

**Resume processing is async, and the honest reason is not CPU.** One parse takes about 7–20 ms, which alone would not need a queue. It is asynchronous because it reads a file from storage, because applicants arrive in bursts that should not compete with interactive scoring, because it starts a pipeline (parse, then score, then rank, then notify), and because a scanned PDF will later need OCR, which is slow. Batch scoring is async for the same reasons: its cost grows with the number of applicants.

**Job lifecycle.** Unchanged from Day 16: `queued → running → completed | failed | cancelled`, terminal states never change, cancelling a finished job is a `conflict`. A job is created with `202`, a `job_id` and a `Retry-After`; the client polls `GET /v1/ai/jobs/{job_id}` (start at 1 s, back off to 5 s). Retries of a transient failure happen **inside** `running` (`attempts` rises up to `max_attempts`, PROPOSED 3); a job that runs out of attempts becomes `failed` with its error and goes to a dead-letter list for a person. The `JobStatus` schema enforces that a completed job has a result and no error, a failed job the reverse, and an unfinished one no result.

Webhooks stay deferred, as in Day 16. When added, they use `HMAC-SHA256 over '<timestamp>.<body>' with a per-tenant secret; reject if the timestamp is more than 5 minutes old`, and the same job resource.

## 5. Error handling and retries

Every error code the code can emit is in one table, and a test scans the source for `ServiceInputError`, `ResumeUploadError` and error-envelope codes and fails if any is missing here. The gateway adds `request_id`, `retryable` and, for 429/503, `Retry-After`. An unknown code becomes a generic `internal_error` (500) with no detail, so nothing internal leaks.

| Code | HTTP | Retries | Source |
|---|---|---|---|
| `invalid_payload` | 400 | 0 | service |
| `invalid_input` | 422 | 0 | service |
| `missing_field` | 422 | 0 | service |
| `invalid_score` | 422 | 0 | service |
| `too_large` | 413 | 0 | service |
| `unsupported_value` | 422 | 0 | service |
| `internal_error` | 500 | 1 | service |
| `unsupported_type` | 415 | 0 | resume upload |
| `file_not_found` | 404 | 2 | resume upload |
| `empty_file` | 422 | 0 | resume upload |
| `corrupt_file` | 422 | 0 | resume upload |
| `unauthenticated` | 401 | 0 | gateway (planned) |
| `forbidden` | 403 | 0 | gateway (planned) |
| `not_found` | 404 | 0 | gateway (planned) |
| `conflict` | 409 | 0 | gateway (planned) |
| `idempotency_conflict` | 409 | 0 | gateway (planned) |
| `rate_limited` | 429 | 5 | gateway (planned) |
| `service_unavailable` | 503 | 5 | gateway (planned) |
| `timeout` | 504 | 3 | gateway (planned) |

**What is retried and why.** Client errors (400, 401, 403, 413, 415, 422) are never retried: the same request fails the same way. Only 429, 503 and 504 are retried freely. `internal_error` gets one retry, because Day 57 showed scoring is deterministic, so a second failure is a bug, not bad luck. `file_not_found` gets two, in case the upload has not replicated yet.

**How.** Exponential backoff with full jitter (PROPOSED: 0.5 s doubling to a 30 s cap, at most 4 retries, 20 s of waiting in total), honouring `Retry-After` as a minimum. Full jitter stops many callers that failed together from returning together. A simulation of four failure patterns behaved as designed (two 503s then success: 3 attempts, waits of 0.5 s and 1.0 s; four timeouts: gave up after 3 waits; a bad input: no retry; one rate limit: waited the 3 s the server asked for).

**Why retries are safe.** Scoring is deterministic, and a test shows the same request gives the same response. For job creation the `Idempotency-Key` header is required: the same key with the same body returns the stored job, the same key with a different body is `idempotency_conflict`, and keys are per tenant (PROPOSED 24 h lifetime). The batch rule (D2) matters here too: a re-run batch gives the same scores.

**Partial failure.** One bad resume in a batch does not fail the batch; its entry carries the ordinary error envelope and `failed` counts it.

## 6. Authentication and security

Authentication is **not built** (Day 55 says so). This is the plan.

- **Two layers.** Users (recruiter, candidate, admin) authenticate to the backend with a short-lived token (PROPOSED 15 minutes); the backend maps it to a Day 55 `Actor` and checks the access rules. The backend calls the AI gateway with its own short-lived service token (PROPOSED 5 minutes, client-credentials over mTLS). The AI layer never sees a user session.
- **Scopes.** Each operation needs exactly one scope (the table in section 1). A token without it gets `forbidden`. The token also carries the tenant, the pseudonymous actor reference and the request id, so the AI side can log and audit without any personal data (G3).
- **No personal data in logs or errors.** Verified by test: texts containing a marker string were sent to every service and the marker never appears in the logs or in error messages. Services log lengths, counts and the pseudonymous candidate reference only. The gateway must do the same: log ids, sizes, codes and timings, never bodies. The parse result's `cleaned_text` is marked as containing personal data in its schema.
- **Pseudonymous identifiers only.** `candidate_id` on the wire is the Day 55 `cref_…` reference. The services call the field `candidate_id`; the governance code calls it `candidate_ref` (F2). The wire name stays, the schema pattern enforces the format.
- **Input handling.** Schema check at the gateway (defence in depth), body-size caps, and the resume file is only ever opened through a store key that must resolve inside the resume store (`../` and absolute paths are refused, tested).
- **Transport and storage.** TLS 1.2+ everywhere and encryption at rest with per-tenant keys, as the Day 55 storage plan already requires.
- **Rate limits** (PROPOSED, to tune after a load test): per service credential and per tenant, with `429` and `Retry-After`. Measured compute allows far more than any sensible limit, so the limit protects fairness between tenants, not the CPU.
- **Audit.** Every call appends one audit entry (ids, scores, versions, outcome; never text), which the Day 55 log already enforces.
- **Not browser-facing.** The AI gateway is internal, so it has no CORS surface.
- **Health** is the only unauthenticated endpoint and returns no personal data.

## 7. Findings

| ID | Finding | Evidence | Effect |
|---|---|---|---|
| F1 | A shared corpus makes a candidate's score depend on who else applied | 16 resumes: score differences up to 0.30 points, and 1 of 16 changed zone (shortlist alone, review in the batch); per pair costs about 1.7× the time | Batch is per pair (D2); it equals the single result, tested |
| F2 | The same field is `candidate_id` in the services and `candidate_ref` in the governance code | source | Wire name kept; value must be the pseudonym |
| F3 | Schema limits allow requests far larger than any sensible cap | up to 153 MiB (batch), 15 MiB (interview) | Gateway caps are the real limit; set from real data |
| F4 | The Day 2 `CandidateProfile` schema requires name and email; no code produces them (`extract_fields` is a stub that returns empty values) | `schemas/resume_schema.json`, `parsers/resume_parser.py` | Parsing API returns none (D3) |
| F5 | The Day 16 spec has the ATS API store resumes and jobs; the Day 57 services are stateless | specs vs code | Reconciled by D1 |
| G1–G3 | The Day 55 access rules do not cover parsed resume data, job descriptions, or tenant checks for the service role | section 2 | D4 |

## 8. Evidence and honest limits

- **Tests:** 123 new tests in `tests/test_integration_contract.py`; full suite 1,901 passed, 6 skipped (previous 1,778). They check the plan against the code: every error code the source can emit is in the policy; every real service response validates against its schema and declares all its keys; the gateway and service refuse the same bad requests with the same code and field; the access check finds exactly the documented gaps; retry, backoff and idempotency behave as stated; the generated files match the code; the two new services keep the Day 57 contract.
- **Real data:** 20 of 20 sample resumes (10 DOCX, 10 PDF) parsed and validated; 16 of 16 ATS responses validated; the batch equals the single-request results; the screening, HR, technical and decision responses validated.
- **Not covered:** nothing here has run over a network. Timings exclude speech-to-text, storage, queue and authentication, which will dominate real latency. Timeouts, size caps, token lifetimes, retry numbers and rate limits are proposals. The access check covers the Day 55 matrix as written, which is itself "a reasoned starting point", not a signed-off policy.
- **Open:** D1–D5; the gateway, queue, job store and identity provider are not chosen; OCR for scanned resumes; whether live speech scoring needs a streaming API rather than polling (not designed).

## 9. Files

New: `ats_engine/resume_parsing_service.py`, `ats_engine/batch_service.py`, `parsers/integration_contract.py`, `run_day59_integration_demo.py`, `tests/test_integration_contract.py`, `schemas/integration_api_schemas.json` and `api/integration_openapi.yaml` (generated), this document, `docs/day59_api_mapping_diagram.md`, and outputs under `data/integration/`, `data/results/day59_integration_report.json` and `logs/day59_integration_run.log`. Changed: `requirements.txt` only (adds `jsonschema` and `PyYAML` (needed by the new tests) and `matplotlib` (the diagram image)). No existing module or test was changed.
