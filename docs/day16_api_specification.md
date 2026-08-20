# Day 16 — ATS API Specification

Companion document to `api/openapi.yaml` (the formal, importable spec).
This covers the same nine endpoints in prose, plus the design decisions
behind them. Every response schema here is derived directly from the
real dataclasses already shipping in Days 13–15
(`ATSScoreResult`/`ComponentResult` in `ats_scoring_engine.py`,
`RankedCandidate` in `ranking_engine.py`, `BiasReport`/`NormalizedScore`
in `fairness_engine.py`) — not designed from scratch.

## Design decisions

**Why resumes and JDs are separate resources from scoring.** A resume or
JD is uploaded once and can be scored against many JDs/resumes over
time. Splitting ingestion from scoring avoids re-uploading the same
resume text for every job it's considered for.

**Why scoring is async and ranking is not.** Scoring requires fitting or
reusing a TF-IDF semantic matcher across the resume+JD corpus (Day 12)
and running the 4-component engine per candidate — for any real batch
size this is too slow for a synchronous request. Ranking (Day 14) and
score normalization (Day 15) are cheap, deterministic operations on
scores a scoring job already produced, so `/rank` stays synchronous —
no reason to make a caller poll for something that returns in
milliseconds.

**Why `/rank` takes a `scoring_job_id`, not raw scores.** Keeps the
client from having to reconstruct `ComponentResult` objects by hand —
it references a completed job, the API pulls the results server-side.

## Endpoints

### Resumes
| Method | Path | Purpose |
|---|---|---|
| POST | `/resumes` | Upload a resume (multipart). `.txt` supported today; `.pdf/.doc/.docx` accepted by the contract but **not yet extracted** — the current parsing layer only works on plain text, so those return `status=pending_extraction`. This is a real, stated gap, not an oversight. |
| GET | `/resumes/{resume_id}` | Fetch stored record + parsed sections once `status=ready`. |

### Job Descriptions
| Method | Path | Purpose |
|---|---|---|
| POST | `/jobs` | Create a JD from raw text. `role_category` is optional — auto-inferred via `infer_role_category()` if omitted. |
| GET | `/jobs/{jd_id}` | Fetch a stored JD. |

### Scoring (async)
| Method | Path | Purpose |
|---|---|---|
| POST | `/scoring-jobs` | Submit a batch of `resume_ids` against one `jd_id`. `options.use_fairness` runs Day 15's normalize→mask→bias-report pipeline; `options.use_fairness_weights` additionally dampens `skill_match`'s weight. Returns `202` with `status=queued` immediately. |
| GET | `/scoring-jobs/{job_id}` | Poll for status. `results` (array of `CandidateScore`) is populated once `status=completed`. |
| POST | `/scoring-jobs/{job_id}/cancel` | Cancel a queued/running job. `409` if already terminal. |

### Ranking (sync)
| Method | Path | Purpose |
|---|---|---|
| POST | `/rank` | Rank + shortlist a completed scoring job's results. Optional `thresholds` override `ranking_engine.DEFAULT_THRESHOLDS`; optional `normalize=true` also runs `normalize_scores_batch()` and adds `normalized_score`/`percentile` to each row. |

### System
| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness check. |

## Response shape reference

`CandidateScore` (one resume's result within a scoring job):
```json
{
  "resume_id": "r_01", "jd_id": "jd_01",
  "overall_score": 50.5, "role_category": "tech",
  "components": [
    { "name": "skill_match", "score": 80.0, "base_weight": 0.35,
      "effective_weight": 0.35, "contribution": 28.0, "available": true,
      "details": { "matched_skills": ["React.js", "Node.js"], "missing_skills": ["Kubernetes"] } }
  ],
  "explanation": "Role category: 'tech'. Strongest contributor: skill_match ...",
  "missing_data_notes": [],
  "bias_report": null
}
```

`RankedCandidateView` (one row within a `/rank` response):
```json
{ "rank": 1, "candidate": "resume_03_sales_executive", "job": "jd_02_sales_executive",
  "score": 61.3, "zone": "SHORTLIST", "role_category": "business",
  "strongest_factor": "skill_match", "flags": "-" }
```

Both are taken verbatim from real Day 13/14 output, not invented.

## Error & logging standards

**Error envelope** — every non-2xx response uses the same shape:
```json
{ "error": { "code": "VALIDATION_ERROR", "message": "resume_ids must contain at least one id",
             "details": {}, "request_id": "req_8f2a1c" } }
```
- `code` is a stable, machine-readable string (`RESUME_NOT_FOUND`,
  `VALIDATION_ERROR`, `JOB_NOT_COMPLETED`, …) — clients branch on this,
  never on `message` text.
- `message` is for humans/logs, not client logic — wording can change
  without breaking callers.
- `request_id` correlates the error to structured logs (see below) —
  this is what a recruiter-facing support flow actually needs when
  something goes wrong.

**HTTP status mapping**: `400` validation, `404` not found, `409`
conflict (e.g. cancelling a completed job), `413` payload too large,
`500` unexpected server error. Async job *failures* are not HTTP
errors — a scoring job that fails still returns `200` from
`GET /scoring-jobs/{id}` with `status=failed` and an `error` string;
the HTTP layer succeeded, the job did not.

**Logging standard**: structured (JSON) logs, one line per event, with
at minimum `timestamp`, `level`, `request_id`, `event`, and event-specific
fields. Every request gets a `request_id` at ingress (generated if not
supplied via an `X-Request-Id` header) and it's threaded through to every
log line and error response for that request/job — this is what makes
"why did this candidate's score look wrong" answerable after the fact
without re-running anything. Log levels: `INFO` for job lifecycle
transitions (queued→running→completed), `WARNING` for missing-data /
bias-flag conditions surfaced to the caller, `ERROR` for job failures,
with the underlying exception attached.

## Known gaps (stated honestly)

- PDF/DOC/DOCX text extraction is specified but not implemented — only
  plain text works today.
- No authentication/authorization scheme is defined yet — out of scope
  for this design pass, needed before any real deployment.
- No rate limiting or pagination defined for list-shaped responses —
  fine for the current sample-data scale, will need addressing once
  `resume_ids` batches or job history grow large.
