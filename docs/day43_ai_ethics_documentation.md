# Day 43 — AI Ethics Documentation

## What this day is

An ethics and compliance review, not a feature day. Three deliverables
were requested — ethics documentation, fairness review notes, and a
compliance readiness report — split across three documents (this one,
`day43_fairness_review_notes.md`, `day43_compliance_readiness_report.md`)
to match. One piece of real code was also built where a genuine,
previously-unaddressed gap was found: a free-text demographic-
disclosure scrubber for screening and HR interview transcripts (Day
15's PII masking only covers labeled resume fields).

## Environment note

Same constraint as Days 41–42: this build has the base project through
Day 34, plus Days 41 and 42's own additions. Days 35, 36, 39, and 40
aren't present locally — audited and documented here based on what's
directly accessible, with findings about those rounds stated as
**inferred from their documented scope** (their own docstrings and
reports from earlier sessions), not re-verified against live code in
this environment.

## Consent requirements

### What's collected today

- **Resume text** (ATS round, Days 1–20) — parsed for skills,
  experience, education; Day 15 masks labeled PII fields before
  scoring.
- **Screening call transcripts** (Days 21–32) — speech-to-text output,
  stored via `CallSession` (`transcript_schema.py`).
- **HR interview transcripts** (Days 33–42) — response text per
  question, held in `InterviewSession`.

### Finding: no consent-capture mechanism exists anywhere in this codebase

Checked explicitly — no field, flag, timestamp, or check related to
candidate consent appears anywhere in the project (`grep` for
consent-related terms across every `.py` file returned nothing
relevant). Resume parsing, call transcription, and interview scoring
all proceed unconditionally on whatever text arrives; nothing records
whether the candidate agreed to be evaluated this way, agreed to be
recorded, or agreed to automated scoring specifically.

**This is a real gap, not a style note.** A production hiring system
built on this project would need, at minimum:
- A recorded consent event before resume parsing begins.
- A separate recorded consent event before call recording/transcription
  begins (distinct from resume consent — recording a person's voice is
  a different and often more regulated act than parsing a document
  they submitted).
- A recorded consent event, or at least a disclosure, that responses
  are evaluated by automated scoring (relevant under regulations like
  GDPR Article 22 and similar automated-decision-making provisions,
  and increasingly under local equivalents).

**Recommendation:** add a `consent_record` concept to intake — a
timestamp plus which consent (resume/recording/automated-scoring) was
given — checked before each corresponding processing step runs. Not
built in this day's deliverable: it requires schema and workflow
decisions (where intake happens, what the consent UI looks like) that
are infrastructure choices outside a parsing-and-scoring project, not
something to guess at.

## Explainability — consolidated, not newly built

Every scoring round already produces an explanation. This is a
genuine strength of the project as built, worth stating plainly rather
than treated as a gap needing new work:

| Round | Explainability mechanism | Source |
|---|---|---|
| ATS | `ATSScoreResult.components` + `.explanation` | Day 13 |
| Screening | `ScreeningScoreResult` breakdown | Day 26 |
| HR interview | Per-answer `component_breakdown` + `to_summary_text()` | Day 37, Day 39 (documented; not re-verified in this environment) |
| Unified | `UnifiedCandidateScore.contributions` (per-round, per-weight) | Day 41 |

No round produces a bare number with no reasoning attached — every
score a candidate or recruiter would see can be traced to the specific
inputs that produced it. Verified directly for ATS and Unified (code
present); taken from documented scope for Screening and HR interview
(code not present in this environment).

## Not done here

- Building the actual consent-capture mechanism (needs infrastructure
  decisions, see above).
- Re-verifying Screening/HR-interview explainability against live code
  (files not present in this environment — see environment note).
