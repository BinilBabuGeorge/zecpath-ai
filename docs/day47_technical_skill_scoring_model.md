# Day 47 — Technical Skill Scoring Model

## What this day adds

Day 46 explicitly deferred this: "Scoring technical answers is
explicitly out of scope for this design day... left for a future day
the way Day 33 left HR scoring for Day 37." This is that day: a real
scoring engine for the 27 tiered technical questions Day 46 built,
evaluating the four parameters the brief names — accuracy, depth,
logical reasoning, real-world applicability — against hand-mapped
per-question rubrics.

## Accuracy, stated honestly

This project has no fact-checking model and no live knowledge base —
"accuracy of answer" means coverage of a **hand-mapped set of key
concepts** a correct answer to that specific question would mention
(e.g., for "state vs props in React": that props come from the
parent, are read-only, and state changes trigger re-renders), matched
by keyword/phrase presence. This is the exact same deterministic,
non-ML approach Day 38 used for logical-reasoning puzzles ("ideal
answer elements"), applied here to real technical content instead of
logic puzzles. It **cannot** verify a correct answer phrased in
unexpected terminology, and it **cannot** catch a confidently wrong
answer that happens to use the right keywords.

## Reuse

`assess_real_world_applicability()` imports `has_concrete_example()`
directly from Day 34's (Day 42-broadened) `hr_followup_engine`,
unchanged. Detecting concrete, specific, experience-grounded language
is exactly what "real-world applicability" means, and Day 34/42
already built and tested that detector. `assess_logical_reasoning()`
reuses the **pattern** Day 38 established (a curated causal/
conditional connector list, scored by density) — not its code, since
`aptitude_logic_engine.py` isn't present in this build environment
(same constraint noted on every day since 41).

## A real bug found and fixed via this day's own balance check

Reusing `has_concrete_example()` against technical prose (rather than
HR behavioral answers, its original domain) immediately surfaced a
real false-positive: its "when i" and "then i" markers were checked as
**plain substrings**, with no word boundary. That means "when **i**t
changes", "when **i**s the deadline", and "then **i**t fails" — all
extremely ordinary technical phrasing — silently matched as if the
candidate had said "when I..." or "then I...", a first-person
recollection marker. This was mostly invisible for HR behavioral
answers (where "when it"/"then it" rarely come up) but fires
constantly in technical explanations, which is exactly the content
this day now runs it over.

**Found, verified, and fixed as part of this day's work** — not a
separate optimization day, because it directly undermined this day's
own "real-world applicability" signal (it was close to a near-
universal false positive for any technical answer using ordinary
phrasing). Fixed narrowly: "when i" and "then i" moved to a small,
separate word-boundary-regex check (`\bwhen i\b`, `\bthen i\b`); every
other marker is left on the simple substring check that already works
correctly for it — the same surgical-fix discipline Day 42 established
rather than a blanket rewrite.

Verified directly:
- `"when it changes"`, `"when is the deadline"`, `"then it fails"` →
  now correctly `False`.
- `"when I was debugging, I found the issue"`, `"then I realized the
  cause"` → still correctly `True`.
- Day 34's own 23 tests and Day 42's own 9 tests, both of which depend
  heavily on this function, pass completely unaffected.

## Normalizing across difficulty levels (the brief's explicit task)

- **Accuracy** is a coverage **ratio** (matched concepts / total
  concepts for that question), not a raw count — a basics question
  with 3 concepts and an advanced question with 4 both land on the
  same 0–100 scale.
- **Depth** uses tier-scaled word-count expectations (basics needs
  ~20 words for full credit; advanced needs ~50), not one fixed
  threshold — an appropriately terse basics answer isn't penalized for
  not being as long as an advanced system-design answer, and a
  padded-but-shallow advanced answer doesn't get undeserved credit
  just for length.
- **Rubric size itself scales with tier** (3 concepts for basics, 4
  for advanced) — part of the normalization design, not just the
  word-count scaling.

This is the mechanism behind "normalize scores across difficulty
levels" — not a separate rescaling step bolted on afterward.

## Scoring formula

`overall_technical_score` = 40% accuracy + 20% depth + 20% logical
reasoning + 20% real-world applicability. Reasoned, not data-
calibrated — same caveat as every scoring day since 34. Classified
into shallow (<40) / moderate (40–69) / deep (≥70) — the brief's
explicit "detect shallow vs deep answers" task.

## Deliverables

- **Technical scoring engine** —
  `parsers/technical_skill_scoring_engine.py`.
- **Skill-wise scoring breakdown** —
  `build_technical_evaluation_report()` aggregates by Day 46's
  `skill_tags` (e.g. `react`, `jvm`, `architecture`), not just by
  domain.
- **Technical evaluation report format** —
  `TechnicalAnswerEvaluation.to_dict()` /
  `TechnicalEvaluationReport.to_dict()`, fully explainable: every
  score traces to matched/missing concepts, word counts vs targets,
  and specific connector hits.

## Verification

18 new tests (`tests/test_technical_skill_scoring_engine.py`),
covering rubric coverage completeness, the accuracy/depth/reasoning/
real-world components individually, the discovered-and-fixed false
positive explicitly (as its own named test), classification bands,
full-answer evaluation, and the session-level skill-wise aggregate.
`pytest` isn't installable in this build environment (no network
access), so these ran via the same assert-based Python runner used
since Day 35. Full project regression (357 tests, 339 previous + 18
new) passed clean with zero regressions — explicitly re-verified that
Day 34's and Day 42's own suites, both of which depend on the function
this day modified, are completely unaffected.

Demo run (Java, advanced tier): a deep, grounded conceptual answer
scored 74.4 (deep), a correct-but-textbook conceptual answer scored
43.2 (moderate), and a shallow non-answer to the scenario question
scored 10.4 (shallow) — three different classifications from three
deliberately different answers, not one band reused throughout. One
genuine precision note surfaced by the demo itself: the "deep" answer
said "in my last **project**", which doesn't match the marker list's
"in my last **job**" / "in my previous role" phrasing, so it scored
`real_world=30` despite real narrative content — a live illustration
of the stated "misses unusual phrasing" limitation, not a bug, left
as-is rather than quietly special-cased to make the demo look better.

## Not done here (left for a future day)

- Wiring this into Day 41's unified scoring engine as a fourth round
  alongside ATS/Screening/HR.
- A fairness/bias review for this scoring engine, matching Day 43's
  review of the other rounds.
- Expanding rubric phrase coverage based on real transcript review —
  the "in my last project" gap above is exactly the kind of precision
  issue that only shows up with real usage data, which doesn't exist
  yet for this track.
