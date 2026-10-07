# Day 43 — Fairness Review Notes

## Scope of this review

Three things were actually checked against live code: the question
banks (for protected-attribute-eliciting questions), the ATS fairness
module's coverage, and the codebase-wide presence of any bias-review
mechanism. One new capability was built to close a found gap. Findings
about Screening/HR-interview-specific modules not present in this
environment are marked as such, not asserted as verified.

## Finding 1 (PASS) — Question banks do not elicit protected attributes

Checked `hr_interview_question_bank.py` and `screening_question_bank.py`
directly for any question touching marital status, pregnancy, children,
religion, caste, age, disability, or nationality. **None found.** Every
question in both banks is scoped to role-relevant behavioral or factual
content (experience, teamwork, availability, skills). This is a clean
result worth stating plainly, not just a negative-findings list — the
question design itself was already built without the obvious compliance
risk of a US/India-style "don't ask this in an interview" question.

## Finding 2 (PASS, with scope) — ATS round has fairness tooling; ran since Day 15

Day 15's `fairness_engine.py` already does real, tested bias-risk work
for the ATS round: masks 12 categories of non-essential/protected
resume fields (name, email, phone, location, gender, DOB, age, marital
status, religion, nationality, parent/spouse name, photo) before
scoring, detects keyword stuffing as a separate integrity signal, and
reports a `BiasReport` with a risk level and specific notes — not just
a score. This is mature, real fairness infrastructure already in
place.

## Finding 3 (GAP) — Fairness review does not extend to Screening or HR interview rounds

`fairness_engine.py` wraps `ats_scoring_engine.score_candidate()`
specifically — there is no equivalent bias-review module for the
Screening round (Days 21–32) or the HR interview round (Days 33–42),
even though Day 41 now combines all three into one unified hiring
decision. A candidate's score could carry an unreviewed bias risk from
either of those two rounds while the final unified decision looks
fully fairness-reviewed, because only one of its three inputs actually
has been.

**Recommendation:** build a Screening/HR-interview equivalent of
`evaluate_bias_indicators()` — scoped to what those rounds actually
process (free-text transcripts, not structured resume fields). This
day builds the detection half of that (see Finding 4); a full
`BiasReport`-equivalent for those rounds, integrated into Day 41's
unified score, is future work.

## Finding 4 (GAP, addressed this day) — Free-text transcripts weren't scrubbed for volunteered demographic disclosures

Day 15's PII masking matches *labeled* resume fields
(`^Gender:\s*(.+)$` etc.) — it has no mechanism for free-form speech,
where a candidate might volunteer a protected attribute unprompted
while answering an ordinary question ("I'm a single mother returning
to work...", "being Muslim, I'd need Friday prayer time..."). Nothing
in the project previously scrubbed this before storage or scoring.

**Addressed this day:** `parsers/transcript_demographic_scrubber.py`
— first-person self-disclosure detection across six categories (age,
gender identity, religion, marital/family status, nationality,
disability), with the same `(masked_text, categories_detected)`
interface shape as Day 15's `mask_pii()`. Deliberately narrow pattern
scope (first-person phrasing only) so it doesn't false-flag a
candidate describing a past project, a colleague, or a team — verified
directly: 4 genuine disclosure examples all detected, 4 deliberately
similar-looking non-disclosures (a project "for a Catholic charity,"
a manager "married with two kids," an "accessibility project for
visually impaired users") all correctly left unflagged.

Stated honestly: this is pattern matching, not understanding — it will
miss indirect disclosures and is not a guarantee of zero demographic
signal in transcripts, the same caveat every heuristic classifier in
this project carries. It reduces a real, previously-unaddressed
exposure; it does not eliminate it.

## Deliverable status

This document is the **fairness review notes** deliverable. Findings
1–2 are clean/positive results. Finding 3 is an open gap with a
recommendation, not yet built (out of this day's scope — needs the
Screening/HR-interview source files, same constraint noted in Day 42).
Finding 4 is a gap that **was** closed this day, with working, tested
code.

## Verification

15 new tests (`tests/test_transcript_demographic_scrubber.py`),
covering 6 genuine-disclosure categories and 4 narrow-scope negative
cases (third-party mentions, project context) that must NOT trigger.
All passing. Full regression in this environment: 298 tests (283
previous + 15 new) passed clean with zero regressions.
