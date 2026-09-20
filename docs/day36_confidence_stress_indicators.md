# Day 36 — Confidence & Stress Indicators

## What this day adds

Day 27 already built hesitation detection, sentiment analysis, and
uncertainty-marker detection — but scoped to the **screening call**
phase (Days 22–32), consuming `StructuredAnswer` objects and reusing
Day 26's contradiction findings. Neither exists in the HR-interview
phase (Days 33–35), which works with `InterviewSession` /
`InterviewQuestionState` and plain response text — the same gap Day 35
filled for communication skill, and Day 34 filled for follow-up logic.
This day is the HR-interview-phase counterpart for confidence and
stress specifically.

## Reuse, not reimplementation

- `detect_hesitation()`, `analyze_sentiment()`, and
  `detect_uncertainty()` are imported **directly** from Day 27's
  `confidence_sentiment_engine`, unchanged. All three already take
  plain `text: str` with nothing screening-specific in their logic —
  they were only ever *called* from a screening-scoped pipeline, not
  *built* for one. Stronger reuse case than Day 34/35's, where the
  reused functions were generic but still needed a new caller; here
  they apply with zero adaptation.
- `assess_grammar()` is imported from Day 35's
  `communication_skill_engine` for its `repeated_word_pairs` field —
  built there to catch a grammar error, reused here because
  consecutive word repetition ("I I want to...") is also a classic
  verbal disfluency marker. Same function, two legitimate uses.

## Scope, stated honestly up front

- **"Long pauses" are not computed.** Day 24's STT layer is a
  documented mock with no real audio pipeline — pause timing requires
  audio. Every result reports `long_pauses_detected: None` with a
  note, the same "not computed" pattern Day 27 used for
  words-per-minute pace.
- **"Stress indicators" are a linguistic proxy, not a physiological
  measurement.** Real stress detection would use vocal pitch, skin
  response, or similar biometric signals — none available. What this
  module measures: hesitation rate, uncertainty density, disfluent
  repetition, and negative/mixed sentiment combined into a 0–100
  score — a reasonable, explainable stand-in, named as such.
- **"Contradiction patterns" for behavioral answers ≠ Day 26's
  check.** Day 26 compares literal factual claims for logical
  inconsistency — behavioral answers have no factual payload to
  cross-check. Instead this module: (1) flags single answers with
  strongly mixed sentiment (multiple positive AND multiple negative
  words), and (2) flags large sentiment swings between consecutive
  answers as *possible* inconsistency. Both are labeled `possible_`,
  not asserted as confirmed contradictions — real semantic entailment
  checking is out of scope for a rule-based project.

## Normalizing to reduce bias

Every component score is independently clamped to 0–100 before
combining, and the behavioral confidence score's penalties are each
capped (hesitation, uncertainty, repeated words, mixed sentiment)
so no single heuristic can sink the whole score alone — the same
discipline as Days 34/35.

**Known limitation, carried from Day 27, not re-solved here:** filler
and disfluency detection on text alone is weaker than on audio, and a
candidate answering in a second language may show more hesitation
markers and repeated words for reasons unrelated to confidence or
stress. Flagged, not corrected for — no rule-based text fix exists
for that gap.

## Components

| Component | What it measures | Reused from |
|---|---|---|
| Filler-word hesitation | filler count, rate per 100 words | Day 27 |
| Uncertainty markers | hedge phrase density | Day 27 |
| Repeated words | consecutive word repetition (disfluency) | Day 35's grammar checker |
| Long pauses | — | not computed (no audio) |
| Sentiment | positive/negative/neutral, score | Day 27 |
| Mixed-sentiment flag | strong positive + negative in one answer | new |
| Cross-answer swings | large sentiment deltas between answers | new |
| Stress score | weighted combination of the above | new |
| Behavioral confidence score | 100 minus capped penalties, plus sentiment adjustment | new |

## Deliverables

- `parsers/confidence_stress_engine.py` — the confidence analyzer
  module + sentiment scoring reuse + behavioral signal logic, at
  per-answer and per-session (`InterviewSession`) granularity.
- This document — behavioral signal logic documentation.
- `run_day36_confidence_stress_demo.py` +
  `data/results/day36_confidence_stress_report.json` — sample output
  across a calm answer, a hesitant/stressed answer, and a deliberate
  large sentiment swing, with two built-in sanity checks.

## Verification

18 new tests (`tests/test_confidence_stress_engine.py`) covering
hesitation-pattern detection, mixed-sentiment and cross-answer swing
flags, stress scoring, per-answer confidence scoring, and the
session-level aggregate. `pytest` itself isn't installable in this
build environment (no network access), so these ran via the same
assert-based Python runner used for Day 35 — functionally equivalent,
stated plainly. Full project regression (261 tests, including Day
27/33/34/35's own suites that this module imports from) passed clean
with zero regressions.

## Not done here (left for a future day)

- Wiring any confidence/stress field into `interview_ai/service.py` —
  no such placeholder currently exists there (only
  `communication_score` and `technical_score` do); this is new
  standalone capability, not yet plugged into the service layer.
- Real semantic contradiction detection for behavioral answers —
  would need an NLP entailment model, not available in this project.
- Any audio-based pause/pitch detection — would need a real STT/audio
  pipeline, which Day 24 explicitly documents as out of scope (mocked).
