# Day 26 — Screening Scoring Engine

## Scope, stated honestly up front

Scoring here is rule-based and explainable — deterministic formulas
over Day 25's `StructuredAnswer` output — not a trained scoring model.
Same reasoning as every prior day: no labeled "good answer" training
data exists in this project, so a claimed ML scorer would be a
fabricated capability. What IS real: a genuine, independently-tested,
four-parameter scoring formula (Clarity, Relevance, Completeness,
Consistency) with every component visible in the output, not collapsed
into an opaque single number.

## Pipeline position

```
audio → STTProvider.transcribe()   (Day 24)
      → clean_transcript()          (Day 24)
      → understand_answer()         (Day 25) → StructuredAnswer
      → score_screening_call()      (Day 26, this module)
      → ScreeningScoreResult
```

## The four scoring parameters

| Parameter | What it measures | How it's computed |
|---|---|---|
| **Clarity** | How well-formed the answer was, independent of topic | Day 25's intent-classification confidence; hedged/missing answers score low by definition |
| **Relevance** | How much of the content was actually on-topic | Expected category's score as a % share of everything the answer scored on — not flat pass/fail |
| **Completeness** | Whether a concrete value was actually delivered | For experience/salary/availability: was a value extracted? For introduction/skills/education/location: was a substantive answer given? |
| **Consistency** | Whether this answer agrees with the candidate's other answers | **Cannot** be judged from one answer alone — see below |

### Why Consistency is a genuinely two-pass design, not an oversight

A single answer can't be checked for consistency against itself.
`score_answer()` scores Clarity/Relevance/Completeness immediately and
defaults Consistency to a neutral 100 with an honest note
("not yet cross-checked"). The real check only runs in
`score_screening_call()`, once every answer from the call is available
to compare against each other — at which point:

- **Experience years** mentioned in *any* answer (not just
  "experience"-category ones) are collected and compared. A gap over 1
  year is flagged and penalizes every conflicting turn to 40.
- **Salary figures** are only directly compared when the units match
  (lakhs vs. lakhs, or k/month vs. k/month) — differing units are
  flagged as "cannot verify without guessing a conversion" and are
  **not** penalized, the same "don't guess" stance Day 25's
  `extract_salary_expectation()` already takes. Same-unit figures that
  differ by more than 60% are flagged as worth a follow-up (a
  current-vs-expected range is normal and not flagged).
- **Availability**: stating "immediate" in one answer and a specific
  non-zero notice period in another is a direct contradiction and is
  penalized.

Once cross-checked, every question's `weighted_total` is recomputed —
questions with nothing comparable to check against get their note
corrected to "no comparable field to cross-check against" rather than
leaving the pre-check "not yet cross-checked" wording in place, which
would otherwise misleadingly imply a check that never actually ran.

## Category weighting

Reuses the same reasoning as Day 13's `WEIGHT_PROFILES`: a question
asking for a fact should weight completeness higher; a question asking
for description should weight clarity higher.

| Profile | Categories | clarity | relevance | completeness | consistency |
|---|---|---|---|---|---|
| structured | experience, salary, availability | 0.15 | 0.30 | 0.40 | 0.15 |
| open_ended | introduction, skills, education, location | 0.35 | 0.35 | 0.20 | 0.10 |
| default | (fallback, unused categories) | 0.25 | 0.25 | 0.25 | 0.25 |

## Demo run

Nine sample answers from one candidate, run via
`run_day26_screening_scoring_demo.py`, deliberately including a real
experience-years conflict (t000: "three years" vs. t004: "eight
years") so the consistency check has something genuine to catch:

- Both conflicting turns correctly penalized to consistency=40, with
  the specific values named in the note.
- t007 ("a good package, it's negotiable") correctly scores partial
  completeness (40) — on-topic but nothing extractable, per Day 25's
  documented salary-unit gap.
- t008 (silent) correctly scores 0 across clarity/relevance/completeness.
- **Total screening score: 81.0** — full breakdown in
  `data/results/day26_screening_scoring_report.json`.

## Deliverables (per the Day 26 brief)

- **Screening scoring engine** — `score_screening_call()`, the
  aggregate pipeline entry point.
- **Per-question score breakdown** — `QuestionScore` /
  `score_answer()`, with every one of the four components independently
  visible, scored, and annotated.
- **Final screening score object** — `ScreeningScoreResult`, holding
  the aggregate `total_score`, every `QuestionScore`, and the list of
  consistency findings surfaced across the whole call.

## Testing

19 tests in `tests/test_screening_scoring_engine.py`: every quality
bucket (missing/vague/off-topic/ok) across every component, the
structured-vs-open_ended weight-profile distinction, the neutral
consistency default, and every consistency-check branch (agreement,
conflict, same-unit spread, different-unit non-penalty, availability
contradiction). 84 tests pass project-wide across the pytest-independent
test modules (Days 1–26) — zero regressions from this change.

## Honest limitations carried forward

- Rule-based, not ML — there is no learned notion of "a good answer";
  scoring reflects the four defined formulas only.
- Consistency checks only compare fields Day 25 successfully extracted
  — a genuine contradiction phrased in a way Day 25's extractors miss
  won't be caught, same inherited limitation as Day 25's own gaps.
- Salary consistency across different units is explicitly left
  unverified rather than guessing a lakhs↔thousands-per-month
  conversion — a documented gap, not a silent miss.
- The 1-year experience tolerance and 60% salary-spread threshold are
  fixed, reasonable-but-arbitrary constants, not calibrated against any
  real hiring data this project doesn't have.
