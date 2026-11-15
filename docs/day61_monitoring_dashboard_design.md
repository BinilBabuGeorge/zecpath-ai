# Day 61 – Monitoring Dashboard Design

Zecpath – AI Job Portal | Dashboard structure: candidate processing stats and interview success rates

## Principles

- **One dashboard per audience and question.** Engineers watch service health and drift; recruiters watch their pipeline; auditors watch the decision record. A panel is shown only to the roles listed on it (Day 55 roles apply).
- **Aggregates only.** Counts, rates and distributions; never a name, a transcript or a candidate reference. **Groups smaller than 5 are shown as "<5"** (proposed; use 10 for any view that compares groups), so a dashboard cannot single out one person.
- **Every panel names its metric and, where one exists, its alert rule.** A number worth showing is a number worth alerting on; a rule with no panel is invisible.
- **Process success is not candidate quality.** "Interview success rate" means the system completed the interview and could score it. It says nothing about whether a candidate is good, and no panel ranks people.
- **Honest about what is planned.** Panels that need the queue, recruiter review outcomes or human ratings are marked as planned; they are in the design so the data gets collected.

## Definitions of the two stats the brief names

| Stat | Definition |
|---|---|
| Candidate processing: funnel | distinct candidate references at each stage (scored, screened, interviewed, decided); counts only |
| Resumes parsed vs failed | parses by outcome: `parsed`, `no_text`, or a Day 59 error code (`empty_file`, `corrupt_file`, `unsupported_type`, `file_not_found`) |
| ATS zone mix | shortlist, review and reject results |
| Recommendations | selected, hold for review (with the hold kind) and rejected (each rejection needs a named person) |
| Human review required | share of recommendations that ask a person to look |
| Screening completion rate | `completed` / (`completed` + `incomplete` + `ended_early`), excluding conversations that never started |
| Interview scoring status | `scored` vs `not_started`, for HR and technical |
| Substantive answer rate | 1 minus (non-substantive answers / answers scored): the share of answers with enough content to score |

## The dashboards and their panels

### `service_health`: AI service health

Audience: engineer, admin. Refresh every 15 s.

| Panel | Title | Type | Query or definition | Unit | Alert rules | Privacy |
|---|---|---|---|---|---|---|
| `sh1` | Requests per second by operation | timeseries | `sum by (op) (rate(ai_requests_total[1m]))` | req/s | `A11` | aggregate |
| `sh2` | Error ratio by class | timeseries | `sum by (error_class) (rate(ai_requests_total{status='error'}[5m])) / sum(rate(ai_requests_total[5m]))` | ratio | `A01`, `A02`, `A04` | aggregate |
| `sh3` | Latency p50, p95, p99 by operation | timeseries | `histogram_quantile(0.95, sum by (op, le) (rate(ai_request_duration_seconds_bucket[5m])))` | ms | `A03` | aggregate |
| `sh4` | Error budget remaining (30 days) | stat | `1 - (server errors / requests) over 30 d, against the 99.9 % SLO` | % | `A01`, `A02` | aggregate |
| `sh5` | Top error codes | table | `topk(10, sum by (op, code) (increase(ai_errors_total[1h])))` | count | none | aggregate |
| `sh6` | Caches, warm-up and memory | table | `latest value per cache and tier` | ratio / MB | none | aggregate |

### `candidate_processing`: Candidate processing

Audience: recruiter, admin. Refresh every 60 s.

| Panel | Title | Type | Query or definition | Unit | Alert rules | Privacy |
|---|---|---|---|---|---|---|
| `cp1` | Candidate funnel today | funnel | `parsed -> scored -> shortlisted -> decision recommended -> human review required` | candidates | none | aggregate |
| `cp2` | Resumes parsed vs failed, by reason | bar | `sum by (outcome) (increase(ai_resume_parses_total[1d]))` | count | `A05` | aggregate_k5 |
| `cp3` | ATS zone mix | bar | `sum by (zone) (increase(ai_zone_total[1d]))` | count | `A07` | aggregate |
| `cp4` | Recommendations by outcome | bar | `sum by (decision, hold_kind) (increase(ai_decision_total[1d]))` | count | `A08`, `A09` | aggregate |
| `cp5` | Human review required | stat | `review required / decisions` | % | `A09` | aggregate |
| `cp6` | Processing time per stage (p50) | table | `p50 by op` | ms | none | aggregate |

### `interview_success`: Interview success rates

Audience: recruiter, admin. Refresh every 60 s.

| Panel | Title | Type | Query or definition | Unit | Alert rules | Privacy |
|---|---|---|---|---|---|---|
| `is1` | Screening calls by how they ended | bar | `sum by (call_status) (increase(ai_screening_calls_total[1d]))` | count | `A10` | aggregate |
| `is2` | Screening completion rate | stat | `completed / (completed + incomplete + ended_early)` | % | `A10` | aggregate |
| `is3` | Interview scoring status by type | bar | `sum by (interview_type, interview_status) (increase(ai_interviews_total[1d]))` | count | none | aggregate |
| `is4` | Substantive answer rate | stat | `1 - non_substantive_answers / answers_scored (from model_output logs)` | % | none | aggregate |
| `is5` | Score distribution by round | histogram | `histogram of hr_score, technical_score, screening_score (10 bins)` | score | `A06` | aggregate_k5 |

### `model_quality`: Model quality and drift

Audience: engineer, admin. Refresh every 300 s.

| Panel | Title | Type | Query or definition | Unit | Alert rules | Privacy |
|---|---|---|---|---|---|---|
| `mq1` | ATS score distribution vs baseline | histogram | `current 6 h histogram next to the baseline` | score | `A06` | aggregate |
| `mq2` | PSI over time | timeseries | `psi(baseline, 6 h window) every 30 min` | PSI | `A06`, `A07` | aggregate |
| `mq3` | Agreement with human ratings | stat | `latest evaluation run` | % | none | aggregate |
| `mq4` | Recruiter override rate | timeseries | `overrides / recommendations` | % | `A15` | aggregate |

### `audit_compliance`: Decision audit and compliance

Audience: auditor, admin. Refresh every 300 s.

| Panel | Title | Type | Query or definition | Unit | Alert rules | Privacy |
|---|---|---|---|---|---|---|
| `ac1` | Audit entries by event type | bar | `count by event_type from the audit log` | count | none | aggregate |
| `ac2` | Decisions without an audit entry | stat | `decisions logged - decisions audited (must be 0)` | count | `A12` | aggregate |
| `ac3` | Audit chain verification | stat | `result of AuditLog.verify() against the external anchor` | pass/fail | `A12` | aggregate |
| `ac4` | Rejections awaiting human confirmation | stat | `rejected recommendations without a final_decision entry` | count | `A08` | aggregate |
| `ac5` | Invariant violations | stat | `sum(increase(ai_invariant_violations_total[7d])) (must be 0)` | count | `A08` | aggregate |
| `ac6` | Log events refused by the privacy guard | stat | `increase(ai_log_dropped_total{reason='policy_violation'}[7d])` | count | `A13` | aggregate |

## Mock-up, with real sample values

`data/observability/day61_dashboard_mockup.png` draws six of the panels from values **computed by the dashboard code from the logged events** of real service runs on the 16 sample resumes, the sample answers and a set of generated screening conversations. It is a layout mock-up on sample data, not production data.

Values behind it:

| Operation | Requests | p50 | p95 | p99 |
|---|---|---|---|---|
| `parse_resume` | 22 | 9.863 ms | 23.658 ms | 75.46 ms |
| `recommend_decision` | 42 | 0.073 ms | 0.097 ms | 0.213 ms |
| `score_ats` | 67 | 3.532 ms | 4.383 ms | 4.562 ms |
| `score_interview` | 67 | 0.523 ms | 1.031 ms | 1.068 ms |
| `score_screening` | 41 | 1.336 ms | 1.455 ms | 3.995 ms |

- **Candidate processing:** distinct candidates by stage {'scored': 16, 'screened': 40, 'interviewed': 65, 'decided': 40}; resumes by outcome {'file_not_found': '<5', 'unsupported_value': '<5', 'parsed': 20} (groups under 5 suppressed); ATS zones {'shortlist': 10, 'reject': 47, 'review': 7}; recommendations {'hold_review': 35, 'rejected': 5}; human review required 67.5%; 5 rejections recommended (each needs a named person).
- **Interview success:** screening calls {'incomplete': 12, 'completed': 28}, completion rate 70%; interviews {'hr/scored': 40, 'technical/scored': 25}; substantive answer rate 84.2%.
- **Model quality:** ATS PSI against its own baseline 0.0 (a distribution compared with itself, so zero by construction).

Machine-readable layout: `data/observability/day61_dashboards.json` (generated from the same definitions, and checked by a test).

## How the panel values are produced

`build_dashboard_data()` in `parsers/observability_plan.py` takes the log events and returns the numbers above; its output is checked against the events (request count, error ratio, histogram totals), small groups are suppressed, and a test confirms no `cref_` reference appears in the output. The **queries** in the tables are written in a Prometheus style to show how a metrics store would answer the same question; they were **not run against a real Prometheus**, because none exists here.

## Access (Day 55 roles)

| Dashboard | Who sees it |
|---|---|
| `service_health` | engineer, admin |
| `candidate_processing` | recruiter (own company's data only), admin |
| `interview_success` | recruiter (own company's data only), admin |
| `model_quality` | engineer, admin |
| `audit_compliance` | auditor, admin |

A recruiter's views are limited to their own company. The Day 55 access rules enforce that for recruiters; they do **not** enforce it for the service role (Day 59, finding G3), so the dashboard backend must apply the tenant filter itself.

## Limits

No dashboard tool exists to draw these; the mock-up is a picture. Panels marked planned need data nobody collects yet. Refresh rates and the suppression threshold are proposals. Tests: 66 new in `tests/test_observability.py` (the logger guard, observer, metrics, drift, every alert rule, simulated incidents, dashboards, decision-audit replay, generated files and these documents); full suite 2,017 passed, 6 skipped (previous 1,951).
