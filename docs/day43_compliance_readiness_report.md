# Day 43 — Compliance Readiness Report

## Purpose

An honest readiness assessment, not a certification. This checks what
the codebase actually does today against what a compliant hiring-AI
system would need, and names the gaps plainly rather than asserting
readiness that isn't backed by code.

## Data retention — NOT READY

Searched the entire codebase for any retention, expiry, TTL, or
deletion logic. **None found.** `CallSession` (`transcript_schema.py`)
and `InterviewSession` (`hr_interview_question_bank.py`) both store
candidate data — transcripts, responses, derived scores — with no
field, job, or policy governing how long that data is kept or when/how
it's deleted.

This matters concretely: most data-protection regimes (GDPR and
similar frameworks elsewhere) require that personal data be kept no
longer than necessary for the purpose it was collected for, with a
defined retention period and a deletion mechanism. Right now, nothing
in this project would stop a rejected candidate's full interview
transcript, with every score and risk flag Day 39/40 generate, from
being retained indefinitely with no review.

**Recommendation:** define a retention window (e.g., N days
post-decision, configurable per deployment/jurisdiction) and a
deletion job or TTL mechanism enforcing it. Not built this day — this
needs a decision about storage infrastructure (what database, what
scheduling mechanism) this project doesn't currently specify, and
guessing at that would be inventing infrastructure rather than
documenting a real gap.

## Consent — NOT READY

Covered in full in `day43_ai_ethics_documentation.md`. Summary: zero
consent-capture mechanism exists anywhere in the codebase. Not ready.

## Bias/fairness review — PARTIALLY READY

Covered in full in `day43_fairness_review_notes.md`. Summary: the ATS
round (Day 15) has real, tested fairness tooling. The Screening and
HR-interview rounds do not have an equivalent — though this day closes
part of that gap for free-text demographic disclosures specifically
(`transcript_demographic_scrubber.py`). Partially ready: one of three
rounds fully covered, one gap addressed this day, one gap still open.

## Explainability — READY

Covered in full in `day43_ai_ethics_documentation.md`. Every round
(ATS, Screening, HR interview, Unified) produces a traceable
explanation for its score, not a bare number. This is a genuine
strength to carry into any compliance conversation — automated-
decision-making regulations generally expect a meaningful explanation
to be available to the affected person, and this project already has
one at every stage.

## Question design — READY

Covered in `day43_fairness_review_notes.md` Finding 1. Neither question
bank elicits protected-attribute information. Clean.

## Demographic-signal exposure in resume data — READY

Day 15's labeled-field PII masking is mature, tested, and in place for
the ATS round.

## Demographic-signal exposure in transcript data — IMPROVED, NOT FULLY READY

Day 15's masking didn't reach free-text transcripts at all before
today. This day adds detection and masking for first-person
self-disclosures across six protected-attribute categories, verified
against both genuine disclosures and deliberately similar-looking
non-disclosures. This is a real improvement, not a complete solution —
pattern matching will miss indirect disclosures, and the scrubber
isn't yet wired into the actual `CallSession`/`InterviewSession`
storage path (it exists as a callable module; integrating it into the
intake pipeline is a follow-up, consistent with every other "built but
not yet wired in" note across Days 35–42).

## Summary table

| Area | Status |
|---|---|
| Data retention | Not ready |
| Consent capture | Not ready |
| Bias/fairness review (ATS) | Ready |
| Bias/fairness review (Screening/HR) | Not ready |
| Explainability | Ready |
| Question design | Ready |
| Resume PII exposure | Ready |
| Transcript demographic exposure | Improved, not fully ready |

**Overall: not compliance-ready for a production deployment today.**
Two of eight areas are genuinely solid (explainability, question
design), two more are solid for one round each (resume PII,
fairness review on ATS), one was meaningfully improved this day
(transcript demographic exposure), and two remain open with no code
written yet (retention, consent) because they require infrastructure
decisions outside this project's current scope to resolve responsibly.

## Deliverables

This document is the **compliance readiness report**. See
`day43_ai_ethics_documentation.md` for the consent/explainability
detail and `day43_fairness_review_notes.md` for the full fairness
audit this summary draws from.
