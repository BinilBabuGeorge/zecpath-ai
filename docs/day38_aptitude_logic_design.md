# Day 38 — Aptitude Logic Design

## What this day is

The foundation for a genuinely new phase of this project — cognitive
and situational evaluation — distinct from both the factual screening
phase (Days 22–32) and the behavioral HR-interview phase (Days
33–37). Screening asks *what* a candidate has done; HR-interview asks
*how* they communicate; this phase asks *how they think* — logical
reasoning puzzles and workplace situational-judgment scenarios, each
with a hand-mapped "ideal answer structure" to score against.

Same design-day discipline as Day 33: real, tested, runnable code, not
a diagram. A question bank, a session structure, and — since scoring
is inseparable from what "ideal answer structure" even means — a
scoring model, all in one day, because this brief bundles design and
scoring tasks together where Days 33/34/35 spread an equivalent scope
across three.

## Reuse, not reimplementation

- **"Detect problem-solving clarity"** is conceptually the same thing
  Day 35 already built for behavioral answers — concrete grounding,
  clarity connectors, vagueness. Rather than re-deriving a second
  clarity heuristic, this day imports Day 35's `assess_clarity()`
  directly, unchanged.
- **The session shape** (a linear sequence of question states,
  captured one response at a time) follows Day 33's pattern — but the
  *pattern* is reused, not the code. Aptitude questions are fixed
  logic puzzles/scenarios with hand-mapped ideal elements, structurally
  nothing like Day 33's role-varied behavioral question generator, so
  a new, small `AptitudeSession` is built rather than stretching
  `InterviewSession` to fit a domain it wasn't designed for.

## Ideal answer structures, stated honestly

"Mapping an ideal answer structure" here means a hand-written list of
the **key reasoning elements** a strong answer would touch on (e.g.,
for the classic fox/chicken/grain puzzle: taking the chicken across
first, leaving fox+grain safely together, then bringing the chicken
back) — matched by keyword/phrase presence, the same deterministic,
non-ML approach every classifier in this project uses.

**This is not a formal logical-proof checker or a semantic answer
grader** — it cannot tell a correct answer phrased unusually from a
wrong one that happens to use the right words. Named here rather than
implied by "scoring model."

## Scoring model

- `logical_reasoning_score` combines: (1) how many of the ideal
  answer's key elements were matched (70 of 100 points — the actual
  reasoning content), and (2) density of logical/causal connectors
  ("because", "therefore", "if... then") — a weaker but real signal of
  step-by-step reasoning (up to 30 points, capped).
- `clarity_score` reuses Day 35's `assess_clarity()` unchanged.
- `overall_aptitude_score` = 60% reasoning + 40% clarity — reasoned,
  not data-calibrated (no labeled data exists in this project, the
  same caveat as every prior scoring day). Weights are named constants
  for easy adjustment.

## Question bank (6 questions, hand-written)

| ID | Type | Scenario |
|---|---|---|
| apt-lr01 | Logical reasoning | Mislabeled fruit boxes |
| apt-lr02 | Logical reasoning | Fox/chicken/grain river crossing |
| apt-lr03 | Logical reasoning | Syllogism (Zorgs/Blips/Trons) |
| apt-sj01 | Situational judgment | Teammate missing deadlines |
| apt-sj02 | Situational judgment | Disagreeing with a manager's instruction |
| apt-sj03 | Situational judgment | Two urgent tasks, same deadline |

Each has 3–4 hand-mapped ideal answer elements with explainable
matched/missing output per answer.

## Deliverables

- `parsers/aptitude_logic_engine.py` — the aptitude AI design (question
  bank + session), logical reasoning scoring model, and scenario
  evaluation framework (`AptitudeProfile` aggregate).
- This document — question design and scoring documentation.
- `run_day38_aptitude_logic_demo.py` +
  `data/results/day38_aptitude_logic_report.json` — sample output
  across strong, partial, and weak/vague answers for both question
  types, with two built-in sanity checks.

## Verification

17 new tests (`tests/test_aptitude_logic_engine.py`), covering the
question bank's structure, element matching, connector scoring,
session sequencing, and the profile aggregate. `pytest` itself isn't
installable in this build environment (no network access), so these
ran via the same assert-based Python runner used since Day 35. Full
project regression (295 tests, including Day 35's `assess_clarity()`
that this module imports from) passed clean with zero regressions.

Demo run: a strong logical-reasoning answer scored 78.0 against a
weak/vague one at 8.0; a strong situational-judgment answer scored
69.5 against a weak/vague one at 8.0 — both gaps asserted by the
demo's own sanity checks, not just claimed.

## Not done here (left for a future day)

- Wiring an aptitude score into `interview_ai/service.py` or a
  combined candidate score alongside Day 37's HR score — no such
  integration point currently exists.
- A true semantic answer grader — would need an NLP entailment/
  similarity model to recognize a correctly-reasoned answer phrased in
  unexpected words, not available in this project.
- Adaptive difficulty or a larger question pool — 6 hand-written
  questions demonstrate the framework; scaling the bank is straight-
  forward but was not the ask here.
