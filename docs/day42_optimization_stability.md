# Day 42 — Optimization & Stability

## What this day is

A reliability pass, not a feature day. Day 40's HR interview
simulation found three real, evidenced issues and explicitly deferred
fixing them ("Day 40 is the test and report, not the fix"). This day
is where that debt gets paid down — one issue fixed and verified for
real, two blocked on missing source files, stated honestly rather than
guessed at.

## Environment constraint, stated honestly up front

This build ran in the same reset container noted on Day 41: only the
base project through Day 34 (plus Day 41's own addition) is present
locally. Days 35, 36, and 39's files — `communication_skill_engine.py`,
`confidence_stress_engine.py`, `interview_summary_generator.py` — are
**not available in this environment**. They were delivered to you as
separate zips in earlier sessions and merged into *your* project, not
mine.

This directly limits what Day 42 could responsibly do:

- **Finding 1** (relevance scoring sensitive to marker phrasing) lives
  in `hr_followup_engine.py` (Day 34), which **is** present here — so
  it's fixed and verified for real below.
- **Finding 2** (a delivery-based "strength" can read as more positive
  than warranted) lives in `interview_summary_generator.py` (Day 39) —
  **not present here**. Not fixed this round.
- **Finding 3** (mixed-sentiment detector missed a genuine nuanced
  disclosure) lives in `confidence_stress_engine.py` (Day 36) — **not
  present here**. Not fixed this round.

Rather than reconstruct those two files from memory and risk shipping
a patch that silently drifts from what's actually on your machine,
**please send me `parsers/confidence_stress_engine.py` and
`parsers/interview_summary_generator.py` (or a fresh project zip)** so
Findings 2 and 3 can be fixed against your real code in a follow-up,
the same way Day 41 was.

## Fix 1 — Concrete-example detector broadened (Finding 1, resolved)

### The bug, reproduced exactly

Day 40's Hesitant persona produced this real, substantively-okay
answer:

> "So, um, I started as an intern, and then, uh, I think I became a
> full-time developer after that, and, um, I have been growing since
> then I think."

`has_concrete_example()` returned `False` for it, and
`assess_behavioral_answer()` tagged it `THIN` — the same tag a
genuinely vague, content-free answer gets — purely because the
sentence used ordinary storytelling language instead of a stock phrase
like "for example." Reproduced and confirmed before writing any fix.

### The fix

Two new, still-deterministic signals, added to `has_concrete_example()`
without touching the `VAGUE` path at all:

1. **Narrative transition language** — phrases that signal a real
   sequence of events being recounted ("started as", "then I", "after
   that", "eventually", "ended up"...), regardless of whether a formal
   example marker is also present.
2. **A specific quantity tied to a concrete unit** ("three years", "a
   couple of teammates") — generic, padded answers almost never
   include a specific number; real accounts often do. This reuses Day
   16's word-number vocabulary (`transcript_schema`'s `_WORD_NUMBERS`
   and `_APPROXIMATE_WORD_NUMBERS`) rather than maintaining a second,
   separately-drifting spelled-out-number list — so "three years" is
   recognized the same way "3 years" already was.

### Verified, not just claimed

Both exact sentences from Day 40's finding now classify `CONFIDENT`.
Three regression guards confirm the fix didn't over-correct:

- Genuinely vague hedge answers ("nothing comes to mind") are still
  tagged `VAGUE` — unaffected, since this fix never touches that path.
- Generic padding with no narrative, no quantity, and no marker phrase
  is still tagged `THIN`.
- `transcript_schema`'s own documented "a"/"an" exclusion still holds
  ("quite a while" does not false-match as a quantity).

9 new tests (`tests/test_day42_optimization_stability.py`). All
existing Day 34 tests (23 of them) still pass unchanged — this was an
addition to what counts as concrete, not a change to what counts as
vague or missing.

## "Enhance processing speed" — evaluated, no change made

No profiling data or reported bottleneck exists anywhere in this
project. This is a rule-based, regex/keyword-driven pipeline over
short text answers — not a workload where a speedup is likely to
matter, and inventing a change to claim a "speed improvement" without
a measured problem to point at would be exactly the kind of
unsubstantiated claim this project has consistently avoided elsewhere.
Stated honestly as "nothing found worth changing" rather than
manufactured.

## "Improve transcript cleanup" — a real risk found, no change made

`speech_to_text.py`'s `clean_transcript()` (Day 23/24, screening-call
pathway) strips filler words and collapses whitespace. One tempting
"cleanup" idea was considered and explicitly **rejected**: collapsing
immediate word repeats ("I I was") at the transcript-cleaning layer.
That would actively **destroy** the disfluency signal Day 35's grammar
checker and Day 36's stress scoring both depend on downstream — those
engines detect repeated words as a deliberate signal, not noise to
remove. Confirmed this pathway is separate from the HR-interview
flow (every HR session in Days 35–41 was tested with raw,
filler-intact text, never through this cleaner), so there's no actual
conflict today — but making that change anyway, without being able to
verify every consumer of `clean_transcript()`'s output in this reset
environment, would be shipping a risky, unverified edit. Not done,
stated as a reasoned "no" rather than silently skipped.

## Deliverables

- **Stable HR interview AI** — `parsers/hr_followup_engine.py`'s
  relevance classifier, fixed and verified (Finding 1).
- **Optimization report** — this document: one real fix, two
  explicitly blocked items with a clear path to resolve them, and two
  "evaluated, no change" findings with reasoning, not silence.
- **Refined scoring engine** — the broadened `has_concrete_example()`,
  the actual refinement, backed by tests.

## Verification

9 new tests, all passing via the same assert-based Python runner used
since Day 35 (`pytest` isn't installable in this environment, no
network access). Full regression in this environment: 283 tests (274
previous + 9 new) passed clean with zero regressions — this reflects
only the Day-34-and-earlier-plus-Day-41 codebase available locally;
run the full suite on your machine for the true current total.

## Next steps

Send `parsers/confidence_stress_engine.py` and
`parsers/interview_summary_generator.py` (or a fresh zip) to close out
Findings 2 and 3 with the same real-fix-and-verify treatment this one
got.
