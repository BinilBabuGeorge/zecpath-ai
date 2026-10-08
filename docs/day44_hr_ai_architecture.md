# Day 44 — HR AI Architecture Document

## What this day is

A documentation day, preparing the HR interview AI (Days 33–43) for
integration and maintenance by someone who didn't build it. Three
documents, matching the brief's three deliverables:

- This file — **architecture**.
- `api/hr_interview_openapi.yaml` — **API specification**.
- `day44_developer_integration_guide.md` — **developer handbook**
  (integration guide + troubleshooting).

## Environment note

Same constraint as Days 41–43: this build has the base project through
Day 34, plus Days 41–43's own additions. Days 35, 36, 38, 39, and 40
aren't present locally. Everything below about those days' internals
is documented from their own prior session output (docstrings, JSON
reports, earlier replies in this conversation), not re-read from live
source here. Marked inline wherever that distinction matters.

## System overview

The HR AI is three layers over a shared `InterviewSession` /
`AptitudeSession` state object, not a single monolithic engine:

```
                    ┌─────────────────────────┐
                    │  Day 33: Question Bank    │
                    │  InterviewSession          │
                    │  (sequences questions,     │
                    │   captures responses)      │
                    └──────────┬──────────────┘
                               │ response_text
              ┌────────────────┼────────────────┬──────────────┐
              ▼                ▼                 ▼              ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ ┌─────────────┐
    │ Day 34        │  │ Day 35        │  │ Day 36        │ │ Day 38      │
    │ Follow-up      │  │ Communication │  │ Confidence/   │ │ Aptitude    │
    │ (relevance tier│  │ skill scoring │  │ stress scoring│ │ (separate   │
    │  + probing     │  │               │  │               │ │  session)   │
    │  question)     │  │               │  │               │ │             │
    └───────┬───────┘  └───────┬───────┘  └───────┬───────┘ └──────┬──────┘
            │                   │                   │                │
            └───────────────────┴─────────┬─────────┘                │
                                           ▼                          │
                              ┌──────────────────────┐                │
                              │ Day 37: HR Scoring     │                │
                              │ (weighted combination  │                │
                              │  of relevance/comm/    │                │
                              │  confidence/consistency)│               │
                              └───────────┬───────────┘                │
                                           │                            │
                              ┌───────────▼────────────┐                │
                              │ Day 39: Summary          │◄──────────────┘
                              │ (strengths/weaknesses/   │
                              │  risk flags/narrative)   │
                              └───────────┬────────────┘
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    │                                              │
          ┌─────────▼─────────┐                        ┌──────────▼─────────┐
          │ ATS score (Day 13) │                        │ Screening score     │
          │ (separate pipeline)│                        │ (Day 26, separate   │
          │                    │                        │  pipeline)          │
          └─────────┬─────────┘                        └──────────┬─────────┘
                    │                                              │
                    └──────────────────┬───────────────────────────┘
                                        ▼
                          ┌──────────────────────────┐
                          │ Day 41: Unified Scoring    │
                          │ (cross-round weighted       │
                          │  hiring-fit percentage)      │
                          └──────────────────────────┘

          ┌──────────────────────────────────────────────────────┐
          │ Day 43: Transcript Demographic Scrubber                │
          │ (orthogonal utility -- call on any response_text        │
          │  before storage; not wired into the flow above yet)     │
          └──────────────────────────────────────────────────────┘
```

## Layer-by-layer

### Layer 1 — Session state (Day 33, verified)

`InterviewSession` (`hr_interview_question_bank.py`) is a minimal
linear container: given `ExperienceLevel` and `RoleType`, it generates
a fixed question set across 4 categories (`self_introduction`,
`career_journey`, `strengths_weaknesses`, `teamwork_culture_fit`), each
tagged with an `InterviewPhase`. It does one thing — sequence
questions and capture responses — and deliberately does not score,
decide follow-ups, or evaluate anything itself. Every other engine
reads from this session; none of them own it.

`AptitudeSession` (`aptitude_logic_engine.py`, Day 38, not re-verified
this environment) follows the same shape for a separate, fixed
6-question logic/situational-judgment bank — a parallel session type,
not a phase of the main one.

### Layer 2 — Per-answer signal engines (Days 34–36, 38)

Four engines each read one `response_text` and produce one signal,
independently:

- **Day 34** (`hr_followup_engine.py`, verified) — classifies answer
  quality (missing/vague/thin/confident) via `assess_behavioral_answer()`
  and, separately, decides whether/how to follow up via
  `decide_follow_up()`. The quality classification is also reused
  directly by Day 37 as the "relevance" signal.
- **Day 35** (`communication_skill_engine.py`, not re-verified) —
  fluency, grammar, vocabulary, clarity, structure, each with its own
  heuristic, combined into one `communication_score`.
- **Day 36** (`confidence_stress_engine.py`, not re-verified) —
  reuses Day 27's hesitation/sentiment/uncertainty detectors (built
  for the Screening round, generic enough to reapply here), plus new
  cross-answer consistency checks.
- **Day 38** (`aptitude_logic_engine.py`, not re-verified) — a
  completely separate question type and session; reuses Day 35's
  clarity check for its own "problem-solving clarity" component.

These four never call each other. They're combined one level up.

### Layer 3 — Combination (Days 37, 39, 41)

- **Day 37** (`hr_interview_scoring_engine.py`, not re-verified) —
  the first combination point: takes relevance (reused from 34),
  communication (35), confidence (36), and a consistency penalty
  (derived from 36's cross-answer signals), applies a role-reasoned
  weight profile, produces one `overall_hr_score` with a full
  per-answer breakdown.
- **Day 39** (`interview_summary_generator.py`, not re-verified) —
  the recruiter-facing translation of Day 37's (and optionally Day
  38's) output into strengths/weaknesses/risk flags/narrative. Adds no
  new scoring signal — pure classification and template text over
  what Day 37/38 already computed.
- **Day 41** (`unified_scoring_engine.py`, verified) — the second,
  higher combination point: takes Day 37's `overall_hr_score` alongside
  the *separate* ATS (Day 13) and Screening (Day 26) pipelines'
  headline scores, applies cross-round weighting, produces one
  `hiring_fit_percentage` and decision.

### Orthogonal: compliance (Day 43, verified)

`transcript_demographic_scrubber.py` doesn't sit in the data-flow
diagram above because it isn't wired into it yet — it's a standalone
callable meant to run on raw `response_text` before any of Layer 2's
engines see it, or before storage. See the developer guide for how to
call it, and `day43_fairness_review_notes.md` for why it exists.

## Data formats

Every engine communicates via Python dataclasses (not a shared schema
language) — `to_dict()` methods exist on the report-level classes
(`HRInterviewScoreReport`, `InterviewSummaryReport`,
`UnifiedCandidateScore`, `AptitudeProfile`) specifically to make JSON
serialization at a future API boundary straightforward, which is
exactly what `api/hr_interview_openapi.yaml`'s schemas mirror. There is
no database or persistence layer in this project today — every session
lives only as long as the Python process holding it.

## Scoring logic summary

| Score | Inputs | Where |
|---|---|---|
| Per-answer relevance | keyword/phrase match against ideal-structure markers | Day 34 |
| Per-answer communication | fluency + grammar + vocabulary + clarity + structure | Day 35 |
| Per-answer confidence | hesitation + sentiment + uncertainty | Day 36 |
| `overall_hr_score` | weighted(relevance, communication, confidence) − consistency penalty | Day 37 |
| `overall_aptitude_score` | reasoning-element coverage + clarity (reused from 35) | Day 38 |
| `combined_overall_score` | 70% HR + 30% aptitude (when aptitude present) | Day 39 |
| `hiring_fit_percentage` | role-weighted(ATS, Screening, HR), redistributed if a round is missing | Day 41 |

Every weight at every layer is a reasoned, documented, non-data-
calibrated default — stated plainly on each originating day and not
repeated in full here; see each day's own doc for its specific
reasoning.
