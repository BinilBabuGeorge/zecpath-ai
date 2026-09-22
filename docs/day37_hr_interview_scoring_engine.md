# Day 37 — HR Interview Scoring Engine

## What this day adds

Days 34–36 built three independent signal engines for the
HR-interview phase — follow-up/answer-quality classification (34),
communication skill (35), and confidence/stress (36) — but nothing
that combined them into the one structured, explainable HR score an
actual hiring decision needs. This day is that combination layer.

## Reuse, not reimplementation — all four scoring parameters map onto existing work

| Scoring parameter | Reused from |
|---|---|
| Answer relevance | Day 34's `assess_behavioral_answer()` (MISSING/VAGUE/THIN/CONFIDENT) |
| Communication score | Day 35's `evaluate_answer_communication()` |
| Confidence score | Day 36's `evaluate_answer_confidence()` |
| Consistency | Day 36's cross-answer sentiment-swing / mixed-sentiment flags |

Nothing here re-derives a signal that already exists — this module's
only new code is the weighting, combination, and normalization logic,
which is exactly what the brief asks for and none of Days 34–36 built.

## Answer relevance, stated honestly

Day 34's four-tier classifier is an answer-**quality** signal, not a
semantic relevance-to-the-question checker — this project has no NLP
model to verify an answer actually addresses what was asked versus
just being long and concrete about something else. Mapping quality
tiers to a relevance score (CONFIDENT=100, THIN=60, VAGUE=30,
MISSING=0) is a reasoned proxy, not a direct measurement — named here
rather than implied by the field name alone.

## Weightage system

Unlike Days 34–36's equal-weighting default (used because those
components were of equal, unknown reliability), this day's four
parameters differ in what they actually verify — so the default
weights are **reasoned**, not equal, and fully configurable via
`WeightConfig`:

- **Relevance: 35%** — the most direct measure of whether the
  candidate actually answered the question.
- **Communication: 25%** — a real, independently useful skill signal.
- **Confidence: 25%** — useful, but Day 36 itself flags this as more
  heuristic (text-only, no audio).
- **Consistency: 15%** — weighted lowest because Day 36 explicitly
  labels its own contradiction signals `possible_`, not confirmed.

This is a reasoned default, **not calibrated against labeled hiring
outcomes** — no such data exists in this project. Fully configurable
for anyone who disagrees with the reasoning.

## Normalizing across different interview lengths (the brief's explicit last task)

- Relevance/communication/confidence are combined as **per-answer
  averages**, not sums, so a 4-question and a 10-question interview
  land on the same 0–100 scale.
- The consistency penalty is computed from an **issue rate** (swing
  flags + mixed-sentiment answers, divided by the number of
  answers/pairs), not a raw count. Day 36's own aggregate capped the
  raw swing count, which would under-penalize a long interview with
  the same *proportion* of issues as a short one, just because the cap
  saturates at a lower rate. Rate-based normalization fixes that at
  this aggregation layer without changing Day 36's module.

Verified directly in the test suite: a 2-question and a 4-question
session with the same answer quality repeated land within 5 points of
each other.

## Explainable scoring breakdown

Every number in the final report traces to a named component — no
opaque combined score. `to_summary_text()` produces a human-readable
report showing per-question relevance/communication/confidence plus
the consistency penalty and its findings; `to_dict()` gives the same
structure as JSON for programmatic use.

## Deliverables

- `parsers/hr_interview_scoring_engine.py` — the HR interview scoring
  engine + weight configuration system (`WeightConfig`, fully
  adjustable and validated to sum to 1.0).
- `HRInterviewScoreReport.to_summary_text()` — the candidate HR score
  report format.
- This document — scoring parameter and weightage documentation.
- `run_day37_hr_scoring_demo.py` +
  `data/results/day37_hr_scoring_report.json` — sample output scored
  twice (default weights, then a relevance-heavy configuration) on the
  same session, demonstrating the weight system actually changes the
  result.

## Verification

17 new tests (`tests/test_hr_interview_scoring_engine.py`) covering
weight validation, per-answer scoring, rate-based consistency, length
normalization, and full-report generation. `pytest` itself isn't
installable in this build environment (no network access), so these
ran via the same assert-based Python runner used for Days 35–36.
Full project regression (278 tests, including Day 27/34/35/36's own
suites that this module imports from) passed clean with zero
regressions.

## Not done here (left for a future day)

- Wiring `overall_hr_score` into `interview_ai/service.py` or
  `scoring/service.py` — no such combined-score placeholder currently
  exists in either service; this is new standalone capability.
- Calibrating the default weights against real hiring outcomes — no
  labeled data exists in this project.
- A true semantic relevance checker (does the answer actually address
  the question asked) — would need an NLP entailment/similarity model,
  not available here.
