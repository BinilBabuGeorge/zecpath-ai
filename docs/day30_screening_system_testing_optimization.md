# Day 30 — Screening System Testing & Optimization

## What this day actually is

Days 22–29 built the screening-call AI pipeline (question bank →
conversation flow → answer understanding → scoring → communication
signals → reporting). Day 30 is the validation milestone for that
whole phase — same role Day 20 played for the ATS phase (Days 1–20):
build a human-judged ground truth, run the real engine against it,
find and fix genuine defects, and report before/after numbers honestly.

**Everything below is measured, not asserted.** The bug was found by
actually running realistic short answers through the shipped engine
and observing wrong output — not by inspecting code and guessing at
what might be wrong.

## The bug, found by testing

Feeding a batch of realistic short screening answers through Day 25's
`understand_answer()` surfaced a real, high-impact defect:

| Text | Category | Result *before* Day 30 |
|---|---|---|
| "5 years" | experience | **vague** ❌ |
| "Two years" | experience | **vague** ❌ |
| "Immediately" | notice_period | **vague** ❌ |
| "Ten lakhs" | salary | **vague** ❌ |
| "B.Tech CSE" | education | **vague** ❌ |
| "Thirty days" | notice_period | **vague** ❌ |
| "Docker" | skills | **vague** ❌ |
| "8" | salary | **vague** ❌ |

**Root cause:** `_is_vague()` flagged *any* 1–2 word answer as vague
unless it was a bare "yes"/"no" — with no regard for whether the short
answer actually carried real, concrete content. A real screening call
produces exactly this kind of short factual answer constantly; the
original heuristic was rejecting good answers purely for their length.

## The fix

A short answer is now only treated as vague if it **also** carries no
recognizable concrete content: no digit, no number-word, no
category-keyword signal (reusing the same `category_scores` the intent
classifier already computes — no new classification work, just
checking a value that was already being thrown away), and none of a
narrow, genuinely unambiguous word set (`immediately`/`immediate`/`asap`).

### A real overcorrection this testing caught before shipping

An earlier draft of the fix also treated `remote`/`hybrid`/`onsite` as
universally confident short answers. Building the ground-truth test
set (case `c19`, "Remote" asked as a `notice_period` answer) caught
that this was wrong: those words don't correspond to any of Day 22's
7 canonical categories as a genuinely correct answer to any of them —
accepting them everywhere would have let wrong-category short answers
through as false acceptances. That word set was narrowed to only
`immediately`/`immediate`/`asap` before this fix was finalized —
verified by `test_remote_alone_still_vague_not_overcorrected` and its
`hybrid`/`onsite` counterparts.

## Results — before/after on a 20-case human-judged ground truth

`data/ground_truth_screening/day30_manual_review.json` — 20 cases
spanning all 7 categories and all 4 quality types, each independently
human-labeled with what a recruiter reading the answer would conclude.

| | Before | After |
|---|---|---|
| **Accuracy** | 11/20 (55.0%) | **19/20 (95.0%)** |
| **False rejections** (human says OK, engine disagreed) | 9 | **1** |

The one remaining false rejection — **"Bengaluru" as a bare location
answer** — is an honestly-documented, unfixed limitation: a bare place
name has no digit, number-word, category-keyword hit, or confident-word
match, so nothing distinguishes it from a random short non-answer
without a location gazetteer this project doesn't have. Fixing it
properly would mean either building/importing a places list (real
scope, not attempted here) or loosening the short-answer rule further
in a way that would likely reintroduce false acceptances elsewhere —
a genuine trade-off, stated rather than silently resolved.

## Downstream impact — this wasn't just a label change

Re-scoring the fixed cases through Day 26 shows what the bug actually
cost candidates in the final screening score:

| Case | Old score | New score | Change |
|---|---|---|---|
| "5 years" | 28.8 | 55.0 | +26.2 |
| "Two years" | 28.8 | 55.0 | +26.2 |
| "Immediately" | 28.8 | 100.0 | **+71.2** |
| "Ten lakhs" | 28.8 | 100.0 | **+71.2** |
| "B.Tech CSE" | 27.8 | 100.0 | **+72.2** |
| "Thirty days" | 28.8 | 55.0 | +26.2 |
| "Docker" | 27.8 | 100.0 | **+72.2** |
| "8" | 28.8 | 55.0 | +26.2 |
| "Bengaluru" (unfixed) | 27.8 | 27.8 | +0.0 |

Candidates giving completely correct, complete answers were being
scored 27–29 out of 100 on those questions — now they correctly score
55–100, depending on whether the answer was thin (triggering a
follow-up) or substantial.

## Cross-day consequence — Day 29's conversation flow, unchanged, behaves better

No code in `conversation_flow_engine.py` changed for Day 30. Its
behavior improved anyway, purely because its upstream input (Day 25's
classification) got more accurate — a clean illustration of why fixing
root causes upstream matters more than patching each symptom
separately. Concretely: every one of the 8 truly-fixed cases now
triggers `ask_follow_up` (a single, non-penalizing probe for a thin
answer) on the **first attempt**, instead of `ask_fallback` (a
retry-consuming response to what the engine used to think was a failed
answer). "Bengaluru" — still misclassified — correctly still triggers
`ask_fallback`, unchanged, since nothing about its classification
improved.

## Deliverables (per the Day 30 brief)

- **Screening system test report** — this document plus
  `data/results/day30_screening_system_test_report.json` (full
  case-by-case before/after data, scoring deltas, and conversation-flow
  impact).
- **Improved AI models** — the `parsers/answer_intent_engine.py`
  `_is_vague()` fix (these are rule-based classifiers throughout this
  project, not trained ML models — same terminology caveat as every
  prior day).
- **Optimized conversation logic** — Day 29's demonstrated behavioral
  improvement, achieved with zero changes to Day 29's own code.

## Testing

21 tests in `tests/test_day30_false_rejection_fix.py`: every genuinely
fixed case, every hedge that must still correctly read as vague, the
caught-and-reverted overcorrection (`remote`/`hybrid`/`onsite`), the
one honestly-documented remaining gap (`Bengaluru`), and sanity checks
confirming off-topic/missing/substantial-answer detection are
unaffected. 178 tests pass project-wide across the pytest-independent
test modules (Days 1–30) — zero regressions from this change, despite
it touching a core function every downstream day (26–29) depends on.

## A methodology note: a bug found in this testing script itself

Building this report's before/after comparison initially produced an
incorrect result for case `c09` ("No notice period"): the reconstructed
"old" logic used in this script forgot to apply the same
`notice_period` → `availability` category-name alias the real
`understand_answer()` applies, causing a false "off_topic" reading that
never actually existed in the shipped code. This was caught by
cross-checking against the real engine's actual historical behavior
before finalizing the numbers above — the corrected comparison script
is what `run_day30_screening_system_test.py` contains. Reported here
in the interest of the same testing rigor this whole day is about: a
test harness's own bugs need catching too, not just the code under test.

## Honest limitations carried forward

- "Bengaluru"-style bare place names remain a known, unfixed false
  rejection — needs a location gazetteer this project doesn't have.
- The concrete-content signals (digit, broad number-word list,
  confident-word list) are still a fixed, reasonable-but-arbitrary set,
  not exhaustive — an answer using a number word or format not in
  these lists could still be misflagged.
- This fix only addresses the specific false-rejection pattern found in
  this testing round; a more thorough audit of `classify_intent()`'s
  category keyword lists (Day 25) was out of this day's scope.
