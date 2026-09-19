# Day 35 — Communication Skill Evaluation

## What this day adds

`interview_ai/service.py` has carried a `communication_score: 0` TODO
placeholder since Day 2's original architecture. Day 27 already built
a real communication-signal engine — but it's scoped to the
**screening call** phase (Days 22–32): it consumes `StructuredAnswer`
objects and reuses Day 26's contradiction findings, neither of which
exist in the HR-interview phase (Days 33–34), which works with
`InterviewSession` / `InterviewQuestionState` and plain response text.
This day is the HR-interview-phase counterpart, covering the five
things the brief asks for that Day 27 never built: fluency, grammar,
vocabulary, clarity, and answer structure.

## Reuse, not reimplementation

- `detect_hesitation()` is imported directly from Day 27's
  `confidence_sentiment_engine` for "detect filler words" — it's
  already a generic transcript-text filler counter with nothing
  screening-specific in it, the same reuse discipline Day 34 applied
  to Day 29's `detect_repeated_answer()`.
- `has_concrete_example()` and `is_vague_behavioral_answer()` are
  imported directly from Day 34's `hr_followup_engine` for the
  "clarity of explanation" signal. Concreteness and hedging are
  exactly what clarity means for a spoken explanation, and Day 34
  already built both detectors for this exact answer population.

## Scope, stated honestly up front

- **Grammar checking is a small, curated pattern list** (subject-verb
  agreement, double negatives, a few irregular mistakes) plus
  repeated-word detection — not a real parser or trained model. No POS
  tagger or dependency parser is available in this project.
- **Capitalization and terminal punctuation are deliberately excluded**
  from grammar scoring. Day 24's STT layer is a documented mock, and
  even a real ASR transcript commonly comes back lowercase and
  unpunctuated — scoring a candidate down for a transcription-layer
  property rather than a communication-skill property would be exactly
  the kind of hidden unfairness Day 15's fairness engine exists to
  catch elsewhere.
- **Fluency and structure depend on sentence segmentation on
  punctuation.** If the upstream transcript has no punctuation, every
  answer degrades to "one long sentence" — flagged via
  `sentence_boundary_confidence`, not hidden or penalized as if it were
  a real run-on.
- **Vocabulary uses root type-token ratio** (unique words / √total
  words), not raw TTR — see normalization below.

## Normalizing to reduce bias (the brief's explicit last task)

1. **Length bias** — root TTR instead of raw TTR, so a longer, fuller
   answer isn't mechanically scored as "less varied" than a short one
   that happens to avoid repeating itself.
2. **Short-answer noise** — filler-word rate per 100 words is
   statistically noisy on very short answers (one filler in 6 words
   swamps the score the same way it would in 200 words). Below 12
   words, the filler penalty is halved and the answer is flagged
   `sample_size_reliability: "low"` rather than scored with false
   precision.
3. **Component clamping** — each of the five component scores is
   independently capped to 0–100 before averaging, so one
   false-triggered heuristic can't drag the composite below what the
   other four components independently support.
4. **Equal weighting** — all five components are weighted identically
   (20% each). No labeled data exists in this project to justify
   weighting one skill above another; an arbitrary weighting would be
   a hidden bias of its own.

**Known limitation, stated honestly:** none of this corrects for a
non-native English speaker naturally producing shorter sentences, a
smaller working vocabulary in a second language, or a more literal
explanation style — this module's heuristics would still under-score
that. This is a genuine fairness gap in a rule-based English-text
approach, named here rather than left implicit.

## Components

| Component | What it measures | Reused from |
|---|---|---|
| Fluency | sentence continuity, run-ons, fragments, connectors | new |
| Grammar | curated error patterns, repeated words | new |
| Vocabulary | root type-token ratio | new |
| Clarity | concrete grounding, clarity connectors, vagueness | Day 34 detectors |
| Structure | sequencing connectors, sentence count | new |
| Filler words | hesitation rate | Day 27 detector |

`communication_score` = average of the five component scores, minus a
capped filler penalty (halved for short answers), clamped to 0–100.

## Deliverables

- `parsers/communication_skill_engine.py` — the communication scoring
  model (fluency/grammar/vocabulary/clarity/structure/filler → 0–100
  score), at both per-answer and per-session (`InterviewSession`)
  granularity.
- This document — scoring formula documentation.
- `run_day35_communication_skill_demo.py` + `data/results/day35_communication_skill_report.json`
  — sample communication score outputs across a strong, a weak, and
  two ordinary answers, with a built-in sanity check that the strong
  answer outscores the weak one.

## Verification

19 new tests (`tests/test_communication_skill_engine.py`), covering
each component in isolation, the composite scoring/reliability
behavior, and the session-level aggregate. `pytest` itself isn't
installable in this build environment (no network access), so these
were run via a small Python runner that executes each assert-based
test function directly — functionally equivalent, but stated plainly
rather than implying the pytest CLI was used. Full project regression
(every test file runnable without `pytest` in this environment,
including Day 27/33/34's own suites, which this module imports from)
passed clean with zero regressions; test files that require pytest
itself could not be independently re-verified here for the same
reason.

## Not done here (left for a future day, same as every prior day)

- Wiring `communication_score` into `interview_ai/service.py` itself —
  same stated-but-deferred pattern Day 27 used for the screening-side
  placeholder.
- Any real grammar/fluency model — would need a labeled dataset or an
  external NLP library, neither of which exists in this project yet.
