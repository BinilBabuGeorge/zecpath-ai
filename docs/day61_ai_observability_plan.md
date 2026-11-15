# Day 61 – AI Monitoring & Observability Design: Observability Plan

Zecpath – AI Job Portal | AI observability plan

## Objective

Enable tracking, debugging and performance monitoring of the AI systems: a logging system (API logs, model outputs, errors), key metrics (response time, accuracy, failure rates), alerting rules, a dashboard structure (candidate processing stats, interview success rates) and audit logs for decisions.

**How to read this.** Day 61 is a design day, so the plan is kept apart from the evidence. **Built and run:** the structured logger and its privacy guard, the metrics registry, the observer that wraps a service call, the metric catalogue, 16 alert rules and an engine that evaluates them, the dashboard definitions and the code that computes their values, and a decision-audit recorder with replay. All of it was exercised on **real service output** (the sample resumes, answers and screening conversations). **Proposed:** every threshold, window, SLO, retention period and sampling rate. **Not built:** a log shipper, a metrics server, an alert manager, a pager, a dashboard tool: this project has none, so each output goes to a file. **Simulated:** the traffic used to test the alert rules is made by resampling real events; its arrival pattern, error background and every incident are invented, so a result such as "caught in 8 minutes" describes the rule on an invented incident, not a production guarantee.

**Headline.** Every one of the 10 injected incidents was caught by the rule meant to catch it, and the 3 simulated normal days (34,500 requests each) raised no alert. The logger refused personal content in every test and no input text reached the log (0 of 360 slices of real resumes, answers and transcripts were found in 478 log events). The audit work found one real gap in Day 55: its typed loggers record outputs but not the input that explains a decision, so two different decisions looked identical in the log (section 6).

## Decisions requested

| # | Decision | Why now |
|---|---|---|
| D1 | Log model outputs as **numbers and codes from a per-operation allowlist**, never "the whole response"; refuse anything else | Logs are an uncontrolled copy that is shipped, searched and kept for weeks; the audit log already forbids personal content, logs must too |
| D2 | Adopt the SLOs in section 3, counting **only server errors** against availability | A caller's bad request must not page the AI team (rule `A04` is a ticket, not a page) |
| D3 | Accept that accuracy is watched through **drift and recruiter overrides** until human ratings exist; record recruiter overrides (`ai_human_override_total`) and get the Day 58 F3 ratings | Ground truth arrives late or never; section 3 says what can and cannot be measured |
| D4 | Add the **decision-audit recorder** (inputs entry, result entry, request id, replay) to the backend | Day 55's entries cannot explain a decision on their own (finding F1) |
| D5 | Approve the alert severities: **pages only for four conditions** (fast availability burn, an automated rejection, no traffic, a missing audit entry); everything else is a ticket | Alert fatigue is the usual way monitoring dies |
| D6 | Choose the log shipper, metrics store, alert manager and dashboard tool; set retention | None exists; sections 2 and 8 say what each must do |
| D7 | Fairness monitoring (`A16`) stays **blocked** until Compliance approves a separately stored, consented demographic monitoring dataset | The platform deliberately does not collect protected attributes (Day 55); this alert cannot be built from the logs |

## 1. What exists after Day 61

| Piece | State | Where |
|---|---|---|
| Structured logger with allowlist and privacy guard | built, tested | `parsers/observability.py` |
| Metrics registry (counters, gauges, histograms, label cap, Prometheus text) | built, tested | `parsers/observability.py` |
| Observer that wraps any service's `run()` | built, tested | `parsers/observability.py` |
| JSON Schema of every log event (generated from the guard) | built, tested | `schemas/observability_log_schemas.json` |
| Metric catalogue, SLOs, drift measure, alert rules and engine, dashboard definitions | built, tested | `parsers/observability_plan.py` |
| Decision-audit recorder with replay and completeness check | built, tested | `parsers/decision_audit.py` |
| Log shipper, metrics server, alert manager, pager, dashboard tool | **not built** | decision D6 |
| Queue, gateway and recruiter-review metrics | **not built** (planned metrics) | Day 59 plan, section 3 |

## 2. Logging system

Details are in `docs/day61_logging_structure.md`. In short: one JSON line per event, three kinds (`api_request`, `model_output`, `error`) plus the separate Day 55 audit log, all sharing a `request_id`. The logger **allowlists** fields; a forbidden key, an unlisted field, a string over 64 characters or a non-finite number is refused, counted in `ai_log_dropped_total` and never written. Logging can never break a request: a failing sink or a policy violation is caught and counted. The observer wraps a service and changes nothing in its answer (tested).

**Evidence.** 478 events from real runs (239 `api_request`, 229 `model_output`, 10 `error`); 0 of 360 thirty-character slices of 120 real input texts found in the logs; 478 of 478 events valid against the generated schema; 3 of 3 deliberate violations refused. Cost: 2.457 ms per ATS request without the observer and 2.595 ms with it in the latest run (0.138 ms added; across runs it varied from about 0.03 to 0.33 ms, so 1 to 10 % of a 3 ms request, which is noise-level on a shared machine).

## 3. Key metrics

Grouped as the brief asks. `prototype` metrics are emitted today by the observer; `planned` ones need the queue, the gateway, recruiter review outcomes or human ratings, none of which exist yet.

| Metric | Type | Labels | Category | What it tells you | Status |
|---|---|---|---|---|---|
| `ai_requests_total` | counter | op, status, error_class | volume | AI API requests by operation, outcome and error class | prototype |
| `ai_errors_total` | counter | op, code | failure | AI API errors by operation and error code | prototype |
| `ai_request_duration_seconds` | histogram | op | response time | Compute time of one AI call | prototype |
| `ai_score_value` | histogram | op, score | accuracy | Distribution of produced scores (drift input) | prototype |
| `ai_zone_total` | counter | zone | accuracy | ATS results by zone (drift input) | prototype |
| `ai_decision_total` | counter | decision, hold_kind | quality | Hiring recommendations by outcome | prototype |
| `ai_human_review_required_total` | counter | op | quality | Results asking a person to review | prototype |
| `ai_screening_calls_total` | counter | call_status | quality | Screening conversations by how they ended | prototype |
| `ai_interviews_total` | counter | interview_type, interview_status | quality | Interview scoring requests by type and status | prototype |
| `ai_resume_parses_total` | counter | file_type, outcome | failure | Resume parses by file type and outcome | prototype |
| `ai_invariant_violations_total` | counter | invariant | audit | Rules that must never be broken | prototype |
| `ai_log_dropped_total` | counter | reason | failure | Log events refused or lost, by reason | prototype |
| `ai_gateway_request_duration_seconds` | histogram | op | response time | End-to-end latency seen at the gateway, including queueing and network | planned |
| `ai_job_queue_wait_seconds` | histogram | op | response time | Time from job submission to the start of work | planned |
| `ai_job_queue_oldest_age_seconds` | gauge | op | saturation | Age of the oldest waiting job (autoscaling and alert signal) | planned |
| `ai_jobs_total` | counter | op, state | failure | Jobs by final state (completed, failed, cancelled) | planned |
| `ai_job_attempts_total` | counter | op | failure | Job attempts, so retries and dead-lettered jobs are visible | planned |
| `ai_worker_resident_memory_bytes` | gauge | tier | saturation | Resident memory per worker (Day 60: 19 MB to 154 MB by profile) | planned |
| `ai_cache_hit_ratio` | gauge | cache | saturation | Hit rate of each Day 60 cache (utils.perf.all_cache_stats) | planned |
| `ai_human_override_total` | counter | recommended, final | accuracy | Recruiter changes to the AI recommendation (the online accuracy proxy) | planned |
| `ai_agreement_with_human_ratio` | gauge | op | accuracy | Agreement with human ratings on a labelled sample (needs the Day 58 F3 ratings) | planned |
| `ai_decision_audit_missing_total` | counter | op | audit | Decisions with no matching audit entry (must stay zero) | planned |
| `ai_audit_chain_verified` | gauge | none | audit | 1 when the latest audit-chain verification passed, 0 when it failed | planned |

**Response time.** Latency is a histogram per operation, so p50, p95 and p99 come from the buckets (checked: the histogram's ATS p95 was 4.889 ms against an exact 4.383 ms). These are **compute** times inside the service; the gateway and queue add their own (planned metrics). 

**Failure rates.** Errors are counted by operation and by Day 59 code and split into **client** (the caller's request was bad) and **server** (our fault). Only server errors count against availability.

**Accuracy, honestly.** Accuracy cannot be read off live traffic, because the right answer for "was this candidate a good hire" arrives months later or never. The plan uses three layers instead:

| Layer | What it shows | State |
|---|---|---|
| Offline accuracy | Agreement with human ratings on a labelled sample (`ai_agreement_with_human_ratio`) | planned: needs the Day 58 F3 ratings |
| Online proxy | How often recruiters change the AI recommendation (`ai_human_override_total`) | planned: needs review outcomes recorded |
| Drift | Whether the distribution of scores and zones moved from the baseline (Population Stability Index, rule `A06` and `A07`) | **built and tested** |

A drift alert does not say the model is wrong; it says the inputs or the model changed and someone must look before trusting new scores. Under 0.1 is stable, 0.1 to 0.25 moderate, over 0.25 major (a common convention, not a law).

**Service level objectives (proposed).**

| Objective | Target | Counts as bad | Basis |
|---|---|---|---|
| Sync availability | 99.9 % over 30 days | a SERVER error (`internal_error`, `timeout`, `service_unavailable`) | A candidate's bad file is not an outage, so client errors do not count |
| Sync latency | 95 % under 50 ms of compute | a call slower than 50 ms inside the service | Day 60 measured ATS p95 3-6 ms; the gateway adds its own budget |
| Async start delay | 95 % start within 30 s | a job that waits longer than 30 s | Day 60 autoscaling target (needs the queue, which is not built) |

## 4. Alerting rules

| Rule | Name | Severity | Condition | Window / wait | Evaluable |
|---|---|---|---|---|---|
| `A01` | availability fast burn | page | Server errors are using the 30-day error budget 14 times too fast, on both the last hour and the last 5 minutes | 5 min / 0 min | yes |
| `A02` | availability slow burn | ticket | A slow leak of server errors: 6 times the sustainable rate over 6 hours and 30 minutes | 30 min / 0 min | yes |
| `A03` | latency p95 regression | ticket | p95 compute time of an operation above its SLO threshold, or above 5 times its own baseline (and over 5 ms), measured over 5 minutes, for 10 minutes running | 5 min / 10 min | yes |
| `A04` | client error spike | ticket | More than a quarter of requests were refused as invalid: an upstream caller is sending bad requests (not an outage) | 15 min / 5 min | yes |
| `A05` | resume parse failure ratio | ticket | More than one resume in ten could not be read (empty, corrupt, unsupported or missing file) | 60 min / 0 min | yes |
| `A06` | ats score drift | ticket | The distribution of ATS scores over 6 hours differs from the baseline (PSI above 0.25) | 360 min / 0 min | yes |
| `A07` | zone mix shift | ticket | The share of ATS shortlist results moved by more than 15 points from the baseline | 360 min / 0 min | yes |
| `A08` | automated rejection invariant | page | A rejection was recommended without human confirmation required, or with an automated action: a rule of the system was broken | 5 min / 0 min | yes |
| `A09` | human review rate band | ticket | The share of decisions asking for human review left its expected band | 24 h / 0 min | yes |
| `A10` | screening call failure surge | ticket | More than half of screening conversations ended early or incomplete | 60 min / 10 min | yes |
| `A11` | no traffic | page | No API requests at all for 15 minutes on a tier that normally has traffic (a silent failure looks like a quiet system) | 15 min / 0 min | yes |
| `A12` | decision audit gap | page | A decision was produced and no audit entry exists for it | 15 min / 0 min | yes |
| `A13` | log policy violation | ticket | The logger refused an event because it contained a forbidden field or free text: code is trying to log personal content | 60 min / 0 min | yes |
| `A14` | job queue oldest age | ticket | The oldest waiting job is older than 30 seconds at the busiest hour (the Day 60 autoscaling signal) | 5 min / 5 min | no: needs the job queue (Day 59 gateway and queue are not built) |
| `A15` | human override rate | ticket | Recruiters change the AI recommendation much more often than before (the online accuracy proxy) | 168 h / 0 min | no: needs recruiter review outcomes recorded (ai_human_override_total) |
| `A16` | selection rate gap | ticket | Selection rates differ between groups beyond an agreed limit (Day 58 F6) | 720 h / 0 min | no: needs consented, separately stored demographic data; the platform deliberately does not collect it (Day 55); cannot be built from the logs |

**Design rules.** A rule has a window (what it looks at), a wait (how long the condition must hold before it fires), a minimum number of events (so a quiet hour cannot raise a ratio alarm) and an owner with a first step. Pages are reserved for things that need a person now; the rest become tickets. **Availability uses two windows** (a fast burn on 1 hour and 5 minutes pages; a slow burn on 6 hours and 30 minutes opens a ticket), the standard way to catch both a sudden outage and a slow leak without noise.

**Owners and first steps.**

| Rule | Owner | First step (runbook) |
|---|---|---|
| `A01` | on-call engineer | Open the gateway and worker dashboards; check the last deploy and warm-up status; roll back if a deploy preceded it. |
| `A02` | service owner | Group errors by code and operation; look for one failing dependency or one worker. |
| `A03` | service owner | Compare with the last benchmark (run_day60_benchmark.py); check cache hit rates, cold workers, input sizes. |
| `A04` | integration owner | Group by error code and field; tell the calling team; do NOT page the AI team. |
| `A05` | service owner | Look at the error-code mix: unsupported_type means an upload form problem, corrupt_file a storage or extractor problem. |
| `A06` | model owner | Check for a new job-description template, a changed upload source, or a config change; compare with the evaluation set before trusting new scores. |
| `A07` | model owner | Same as A06; a shift in who is shortlisted is the visible symptom of drift. |
| `A08` | on-call engineer + compliance | Stop the automated path for that tenant; this must never happen (Day 52, Day 55 R6); capture the request id and open an incident. |
| `A09` | model owner | Too many: a rule or an upstream score changed. Too few: a review rule may have stopped firing. |
| `A10` | service owner | Check speech-to-text and telephony health first (silent calls); then the conversation flow. |
| `A11` | on-call engineer | Check the load balancer and gateway; a healthy-looking service with no requests is usually an upstream outage. |
| `A12` | on-call engineer + compliance | Compliance issue: find the request id, write the missing entry from the log, and fix the recorder. |
| `A13` | service owner | Find the call site from the request id; the event was NOT written, but the bug must be fixed. |
| `A14` | service owner | Scale out the async tier; check for a stuck consumer. |
| `A15` | model owner | Review a sample of the overridden cases with the model owner. |
| `A16` | model owner + compliance | Fairness review; see the bias-monitoring plan. |

**Evidence: do they fire when they should, and stay quiet when they should not?** Traffic was built by resampling **real** events (real durations and outputs), with a 2 % background of client errors and 0.05 % server errors, replayed minute by minute through the rules.

- **Normal traffic, 3 simulated days:** 34,579, 34,564, 34,650 requests; **false positives: none** in any day.
- **Incidents:**

| Injected incident (invented, on resampled real events) | Rule that should fire | Fired | Minutes to first alert | Unexpected alerts |
|---|---|---|---|---|
| latency_regression (ATS 15x slower for 30 min) | `A03` | `A03` | 11.0 | none |
| server_error_burst (15% server errors for 10 min) | `A01` | `A01` | 8.0 | none |
| client_error_spike (50% bad requests for 30 min) | `A04` | `A04` | 12.0 | none |
| score_drift (ATS scores +18 points from hour 4) | `A06` | `A06` | 61.0 | none |
| outage (no traffic for 20 min) | `A11` | `A11` | 14.0 | none |
| automated_rejection (rule broken for 10 min) | `A08` | `A08` | 1.0 | none |
| silent_call_surge (80% of calls end early for 4 h) | `A10` | `A10` | 41.0 | none |
| resume_parse_failures (40% unreadable for 4 h) | `A05` | `A05` | 16.0 | none |
| audit_gap (a decision without an audit entry) | `A12` | `A12` | 1.0 | none |
| log_policy_violation (logger refused an event) | `A13` | `A13` | 1.0 | none |

The delays are the rule working as designed: a rule that waits 10 minutes before firing cannot report sooner than 10 minutes. The drift alert needs hours of data by design (6-hour window). The client-error spike raised a ticket and **no page** (also tested). **Read the zero false positives with care:** the simulated normal traffic is stationary (no daily cycle, no deploys, no peaks), so real traffic will be noisier and every threshold needs tuning in the first weeks, with alerts running in report-only mode before they page anyone.

## 5. Dashboard structure

Details in `docs/day61_monitoring_dashboard_design.md`. Five dashboards, 27 panels, each tied to a metric and, where one exists, to an alert rule:

| Dashboard | Audience | Answers |
|---|---|---|
| `service_health` | engineer, admin | AI service health |
| `candidate_processing` | recruiter, admin | Candidate processing |
| `interview_success` | recruiter, admin | Interview success rates |
| `model_quality` | engineer, admin | Model quality and drift |
| `audit_compliance` | auditor, admin | Decision audit and compliance |

The two the brief names are `candidate_processing` (funnel, parse outcomes, ATS zones, recommendations, human-review share) and `interview_success` (how screening calls ended, completion rate, scoring status, share of answers that carried enough content to score). Every breakdown is aggregate; groups under 5 are shown as "<5".

## 6. Audit logs for decisions

**What Day 55 already provides.** A hash-chained, append-only audit log that refuses personal content, with typed entries for scores (`log_score`, `log_hiring_fit`), decisions (`log_decision`), final decisions and access, a rule that a rejection is never final without a named human (R6), and tamper detection on reload.

**What Day 61 found missing.** The audit question is "why was this candidate recommended for rejection or held, and can you show it?". Two decisions were run through the Day 55 typed loggers with the **same scores and different ATS zones** (shortlist and reject): the outcomes were `selected` and `hold_review` with hold kind `selection_blocked`, yet the score entries were **identical** (true). The decision entry records that a review-flag rule fired but not **which flag** (the ATS zone), so nobody can say why from the log alone (finding F1; reproduced in `tests/test_observability.py`).

**What Day 61 adds** (using only the existing log, so the chain, the forbidden-key guard and the human-rejection rule still apply):

| Entry | Holds | Never holds |
|---|---|---|
| `decision_inputs_recorded` | the request id, the round scores, ATS zone, role type, experience level, model and API versions | resume text, answers, names |
| `recommendation_recorded` | outcome, hold kind, hiring-fit score, confidence, review and confirmation flags, automated action, missing rounds, a **digest** of the reason sentences and their count, versions | the reason sentences themselves |
| `decision_confirmed` / `decision_overridden` / `decision_deferred` | the named human (`human:<id>`), the engine's outcome, the final outcome, whether it was overridden, whether a note exists | the note text |

**Four controls built on it:**

1. **Replay.** Re-run the decision service on the logged inputs and compare with the logged result. It works because scoring is deterministic (Day 57). Result on the real run: **38 of 38** recorded decisions replayed to the identical result. A recorded result that does not follow from its inputs is reported as a difference (tested with a forged result); a model version change is reported as a version change, not tampering.
2. **Completeness.** Decisions in the model-output log with no recommendation entry are found: the check found exactly the 2 decisions deliberately left out. Rule `A12` pages on any.
3. **Human confirmation.** A recommended rejection is pending until a named person records a decision: 1 of 5 rejections were still waiting in the demo. The recorder refuses to record a rejection that is automated or does not require confirmation, and the observer counts any such response as an invariant violation (rule `A08`, a page).
4. **Tamper evidence.** One edited entry in an exported log was detected on reload: true.

**Link to the logs.** The same `request_id` appears on the API log line, the model-output line and the audit entries, so an engineer can go from a complaint to the call to the decision.

**Privacy.** Candidates appear only as pseudonymous references. Erasure works by deleting the reference-to-person mapping (Day 55), not by editing the log. Retention for the audit log follows the Day 55 retention plan; retention for the operational logs is proposed in `docs/day61_logging_structure.md`.

## 7. Findings

| ID | Finding | Evidence | Effect |
|---|---|---|---|
| F1 | Day 55 audit entries cannot tell two different decisions apart: the ATS zone that changed the outcome is not recorded | Same scores, zone shortlist vs reject: different outcome, identical score entries | New inputs entry and replay (section 6) |
| F2 | A percentile alert whose window is as long as its wait cannot filter a short blip: a p95 stays high for as long as slow events remain in the window | A 4-minute slow spell fired the first version of `A03` | `A03` uses a 5-minute window with a 10-minute wait; a test pins window < wait for latency rules |
| F3 | A cold worker's first request (1 to 2 seconds, Day 60) poisons monitoring baselines and raised false alerts in the simulation | The first simulated pool contained one cold outlier | Baselines are built from warmed workers; warm-up before baselining |
| F4 | Accuracy cannot be monitored live; only drift and recruiter overrides can | Section 3 | Decision D3 |
| F5 | The fairness alert cannot be built from logs and should not be | Day 55 forbids storing protected attributes | `A16` blocked (D7) |
| F6 | One bad caller can look like an outage unless client and server errors are separated | 50 % bad requests raised a ticket and no page | Error class on every event |
| F7 | A label that varies per candidate would create millions of metric series | Test: 10 values, cap 3, 7 folded into one overflow series | Label cap of 200 series per metric |
| F8 | An absolute latency threshold taken from the SLO can sit 16 times above normal (ATS: 50 ms against a 3 ms median), so a large slowdown that stays under it goes unnoticed | The first simulation run did NOT detect ATS getting 15 times slower (3 ms to 45 ms) | `A03` also fires above 5 times the operation's own baseline (and over 5 ms); a test covers it |

## 8. Evidence and honest limits

- **Tests:** 66 new in `tests/test_observability.py` (the logger guard, observer, metrics, drift, every alert rule, simulated incidents, dashboards, decision-audit replay, generated files and these documents); full suite 2,017 passed, 6 skipped (previous 1,951).
- **Real vs invented:** all service outputs, durations, scores and log events are real; traffic volume, arrival pattern, background errors and every incident are invented. The 10 incidents are one example each, not a catalogue of everything that goes wrong.
- **Thresholds are proposals.** None has met real traffic. Expect to retune in shadow mode (alerts reported, not paged) for the first weeks.
- **Metrics queries and dashboards are design text.** The panel queries are written in a Prometheus style but were not run against a Prometheus server; the panel VALUES were computed from the events by tested code.
- **Not covered:** a real log pipeline, storage cost and retention enforcement, access control on the dashboards (Day 55 roles apply), alert delivery, on-call process, the queue and gateway metrics, recruiter-override data, human ratings, demographic monitoring.
- **The audit log's external anchor** (Day 55) is still only a plan; without it a person who can rewrite the whole log and recompute every hash would not be detected.

## 9. Files

New: `parsers/observability.py`, `parsers/observability_plan.py`, `parsers/decision_audit.py`, `run_day61_observability_demo.py`, `tests/test_observability.py`, `schemas/observability_log_schemas.json` (generated), these three documents, and under `data/observability/`: sample events, metrics sample, dashboards, alert rules, metric catalogue, dashboard mock-up and sample data. No existing module or test was changed.
