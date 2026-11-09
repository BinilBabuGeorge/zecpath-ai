# Day 59 – API Mapping Diagram

Companion to `docs/day59_ai_integration_document.md`. The same picture is drawn four ways: who talks to whom, how an asynchronous resume job runs, how a real-time interview score runs, and where each AI API fits in the hiring pipeline. A rendered image of the first is at `data/integration/day59_api_mapping.png`.

The AI layer is stateless. The backend reads the input, calls the AI, saves the result and writes the audit entry.

## 1. Architecture: who calls what

```mermaid
flowchart LR
    subgraph Clients
      RD[Recruiter dashboard]
      CP[Candidate portal]
      AD[Admin panel]
    end
    subgraph Backend
      AU[Auth: user token<br/>Day 55 access rules]
      Q[Job queue]
      WR[Saves results<br/>writes audit entry]
    end
    subgraph Gateway["AI gateway /v1/ai (planned)"]
      GW[Service token + scope<br/>schema check<br/>rate limit<br/>request id and error mapping]
    end
    subgraph AI["AI services (stateless, run() contract)"]
      P["POST /v1/ai/resumes/parse (async)<br/>ResumeParsingService"]
      A["POST /v1/ai/ats/score (sync)<br/>ATSService"]
      AB["POST /v1/ai/ats/score-batch (async)<br/>ATSBatchService"]
      S["POST /v1/ai/screening/score (sync)<br/>ScreeningService"]
      I["POST /v1/ai/interviews/score (sync)<br/>InterviewIntelligenceService"]
      D["POST /v1/ai/decisions/recommend (sync)<br/>DecisionScoringService"]
      J["GET /v1/ai/jobs/{job_id}<br/>POST /v1/ai/jobs/{job_id}/cancel<br/>GET /v1/ai/health"]
    end
    subgraph Stores["Data stores (Day 55 storage plan)"]
      RS[(resume_store)]
      TS[(transcript_store)]
      REP[(report_store)]
      JS[(job_store: not in plan, G2)]
      AUD[(audit_store)]
      ID[(identity_map)]
    end
    Clients -->|HTTPS + user token| AU
    AU --> Q
    AU -->|mTLS + service token| GW
    Q --> GW
    GW --> P & A & AB & S & I & D & J
    WR --- RS & TS & REP & JS & AUD
    ID -. never sent to the AI layer .- AU
```

## 2. Asynchronous: resume processing

```mermaid
sequenceDiagram
    participant B as Backend
    participant G as AI gateway
    participant W as Worker (ResumeParsingService)
    participant R as resume_store
    B->>G: POST /v1/ai/resumes/parse + Idempotency-Key
    G->>G: token scope ai:resume:parse, schema check
    G-->>B: 202 {job_id, status: queued}
    G->>W: run job (attempt 1)
    W->>R: read file by file_ref (inside the store only)
    W->>W: extract text, skills, experience, education
    alt success
      W-->>G: result
      G->>G: job completed
    else transient failure (timeout, 503)
      W-->>G: retry inside "running" with backoff, up to max_attempts
    else bad file (empty_file, corrupt_file, unsupported_type)
      W-->>G: job failed, no retry
    end
    loop poll, 1 s then back off to 5 s
      B->>G: GET /v1/ai/jobs/{job_id}
      G-->>B: status
    end
    B->>R: save parsed fields (needs G1 fixed)
    B->>B: append audit entry
```

## 3. Synchronous: real-time interview scoring

```mermaid
sequenceDiagram
    participant B as Backend
    participant G as AI gateway
    participant S as InterviewIntelligenceService
    participant T as transcript_store
    participant RP as report_store
    B->>T: read the candidate's answers
    B->>G: POST /v1/ai/interviews/score (service token)
    G->>G: scope ai:interview:score, schema check, body cap
    G->>S: run(payload)
    S-->>G: envelope (a few milliseconds)
    alt success
      G-->>B: 200 scores
      B->>RP: save score
      B->>B: append audit entry (ids and scores, no text)
    else error
      G-->>B: HTTP status from the error policy + request_id + retryable
      Note over B: retry only 429, 503, 504 (and one retry of internal_error)
    end
```

## 4. Where each API sits in the hiring pipeline

```mermaid
flowchart LR
    U[Resume upload] --> P[parse_resume<br/>/v1/ai/resumes/parse]
    P --> A[score_ats<br/>/v1/ai/ats/score]
    P --> AB[score_ats_batch<br/>/v1/ai/ats/score-batch]
    A --> SC[score_screening<br/>/v1/ai/screening/score]
    AB --> SC
    SC --> HR[score_interview hr<br/>/v1/ai/interviews/score]
    HR --> TE[score_interview technical<br/>/v1/ai/interviews/score]
    TE --> DE[recommend_decision<br/>/v1/ai/decisions/recommend]
    DE --> H{{A person confirms<br/>any rejection}}
```

The machine-test round has its own engine but no service wiring yet (Day 57, open item O3), so it has no API in this plan.

## 5. Job states (Day 16, unchanged)

```mermaid
stateDiagram-v2
    [*] --> queued
    queued --> running
    queued --> cancelled
    running --> completed
    running --> failed
    running --> cancelled
    completed --> [*]
    failed --> [*]
    cancelled --> [*]
```

## 6. Operation to data map

Each row was checked against the Day 55 access rules for the service role.

| Operation | Reads | Writes | Check |
|---|---|---|---|
| `parse_resume` | resume_store | resume_store, audit_store | gap G1: the service cannot write a resume |
| `score_ats` | resume_store, job_store | report_store, audit_store | gap G2: no job store in the plan |
| `score_ats_batch` | resume_store, job_store | report_store, audit_store | gap G2 |
| `score_screening` | transcript_store | report_store, audit_store | allowed |
| `score_interview` | transcript_store | report_store, audit_store | allowed |
| `recommend_decision` | report_store | report_store, audit_store | allowed |

Not used by any AI operation: `recording_store` (no recordings exist yet) and `identity_map` (identity never goes to the AI layer).
