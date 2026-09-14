# Day 32 — Screening Call API Specification

Companion document to `api/screening_openapi.yaml` (the formal,
importable spec), following the exact same pattern as
`docs/day16_api_specification.md` for the ATS API. Every response
schema here is derived directly from real dataclasses already shipping
in Days 24–31 (`RawSTTResult` in `speech_to_text.py`, `TurnOutcome` in
`edge_case_handler.py`, `ScreeningReport` in
`screening_report_generator.py`) — not designed from scratch.

## Design decisions

**Why this is a separate spec from `api/openapi.yaml`, not an extension
of it.** The ATS API (Days 1–20) and the screening-call API (Days
22–31) are two different service boundaries handling two different
kinds of work — batch resume scoring vs. live, turn-by-turn voice
calls. Keeping them as separate files matches that real architectural
split rather than forcing one document to describe two different
interaction models.

**Why `/calls/{call_id}/turns` is synchronous, not job-based.** The ATS
API's `/scoring-jobs` is async because scoring a batch of resumes is
slow and has no real-time constraint. A live call is the opposite: each
turn needs an immediate response (what should the AI say next?) — there
is no batch to queue, and nothing to poll for.

**Why the request/response bodies are exactly `RawSTTResult` in and
`TurnOutcome` out.** Same discipline as the ATS API mirroring
`ATSScoreResult`: the API surface should match what the engine already
returns, not add a translation layer that could drift out of sync with
the real dataclasses.

**Why `text` accepts `null`.** Day 31's crash guard exists specifically
to handle malformed input gracefully rather than reject it outright —
the API contract reflects that by not validating `text` as
non-nullable. A malformed submission gets a `crash_guard_skip` action
back, not a `400`.

## Endpoints

### Calls
| Method | Path | Purpose |
|---|---|---|
| POST | `/calls` | Start a call. Defaults to Day 22's 7 categories if none given. Does not return question text — that's Day 22's `generate_screening_questions()`'s job, kept separate from flow-state tracking. |
| GET | `/calls/{call_id}` | Current state — status, current category, metadata. |

### Turns (sync)
| Method | Path | Purpose |
|---|---|---|
| POST | `/calls/{call_id}/turns` | Submit one turn. Body mirrors `RawSTTResult` (Day 24) exactly. Response mirrors `TurnOutcome` (Day 31) exactly — `action` tells the caller what the AI does next (retry, clarify, skip, end, or pass through to a normal Day 29 response). `409` if the call is already complete. |

### Reports
| Method | Path | Purpose |
|---|---|---|
| GET | `/calls/{call_id}/report` | The final report, once complete. Mirrors `ScreeningReport.to_dict()` (Day 28) exactly — this is the same object `run_screening_call()` (Day 32) produces. `409` if the call isn't finished yet. |

### System
| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness check. |

## What this spec deliberately does NOT claim

- **No real-time audio streaming contract.** `RawSTTResult` assumes
  transcription already happened — this API is downstream of whatever
  real STT service a production deployment would use. Day 24's STT
  layer is a documented mock; this spec doesn't pretend otherwise by
  inventing a streaming-audio endpoint that nothing in this project
  implements.
- **No multi-language support.** `expected_language` exists so the
  language-mismatch check has something to compare against, not because
  setting it to `"hi"` would make the pipeline understand Hindi. Every
  downstream module (Day 25's keyword lexicons, Day 27's sentiment
  lexicon) is English-only.
- **No authentication/authorization scheme.** Out of scope for what
  this project's engine layer provides; a real deployment would add
  this at the gateway level, same caveat the ATS API spec carries.
