# Day 40 — HR Interview Test Report

## What this day is

The capstone validation for the entire HR-interview pipeline built
across Days 33–39. This is a **test day, not a feature day** — no new
scoring signal is introduced. Four deliberately different candidate
personas were run through the full pipeline (question bank → follow-up
logic → communication → confidence/stress → HR scoring → aptitude →
summary generation), each checked against a hand-written **manual
expectation** — what a competent human interviewer would likely
conclude — written *before* running the pipeline, so the comparison is
real rather than after-the-fact rationalization.

**Manual expectations are a sanity-check baseline, stated honestly**:
there is no human-rated dataset in this project (the same caveat as
every prior scoring day). These are single reasoned sentences, not
statistically validated ground truth.

## The four personas

| Persona | Probes for |
|---|---|
| Confident | Baseline — clean, concrete, well-structured answers |
| Hesitant | Whether the pipeline conflates delivery style with content quality |
| Inexperienced | Whether "weak content" gets correctly kept separate from "risky/inconsistent" |
| Overqualified | Whether candid, nuanced self-disclosure gets mis-flagged as contradiction |

## Results summary

| Persona | Combined Score | Band | Risk Flags | Matched manual expectation? |
|---|---|---|---|---|
| Confident | 77.8 | Good | 0 | Yes |
| Hesitant | 51.6 | Moderate | 1 (weak aptitude) | Partially — see Finding 1 |
| Inexperienced | 55.6 | Moderate | 1 (weak aptitude) | Yes — critically, no false "risky" flag |
| Overqualified | 74.9 | Good | 0 | Partially — see Finding 3 |

**Top-line accuracy: 4/4 personas landed in a directionally sensible
performance band**, and — importantly — the Inexperienced persona was
correctly *not* flagged as inconsistent or risky, confirming the
pipeline does distinguish "weak" from "risky" as designed. The
partial-match cases below are not band-level failures; they're
finer-grained precision limits inside otherwise-reasonable scores.

## Finding 1 — Relevance scoring is sensitive to marker phrasing, not just content substance

The Hesitant persona described real experience and a real teamwork
example, but 3 of 4 answers were classified `thin` rather than
`confident` by Day 34's relevance classifier. The cause: the classifier
requires one of a fixed set of concrete-example marker phrases ("for
example", "for instance", "once,", etc.) — a genuine, coherent personal
narrative told *without* one of those stock phrases (e.g., "So, um, I
started as an intern, and then... I became a full-time developer")
gets the same `thin` tag as an actually vague answer. Relevance
(70.0) and confidence (60.0) *did* separate as hoped — the pipeline
does not fully collapse content and delivery into one number — but
relevance is lower than the content itself probably warrants, because
of phrasing style rather than genuine thinness.

## Finding 2 — A "strength" label on delivery calm can read as more positive than warranted when content is weak

The Inexperienced persona's confidence score was a full 100.0 —
correct, since Day 36's confidence signal measures calm, hedge-free
delivery, and this persona's plain, matter-of-fact answers genuinely
contain no hesitation markers. But Day 39's summary generator then
surfaces this as a headline **Strength**, sitting in the same report
as a candidate whose actual content was uniformly thin (relevance
60.0). Each component is behaving exactly as documented — but the
recruiter-facing summary doesn't yet contextualize a delivery-based
strength against weak content in the same report, which could read
more positively than warranted to someone skimming just the
strengths section.

## Finding 3 — The mixed-sentiment detector missed a genuine nuanced disclosure

The Overqualified persona's most interesting answer ("I once had to
hold back frustration... but I coached them through it patiently")
registered as flatly **neutral** (sentiment score 0.0), with zero
positive or negative hits — a real, notable nuance went completely
undetected. Two specific, evidenced causes:

1. **Threshold too strict**: Day 36's mixed-sentiment flag requires at
   least 2 positive AND 2 negative word hits in one answer. A subtle,
   realistic self-disclosure typically has exactly one clear cue on
   each side, which falls below the threshold.
2. **Exact word-form matching**: the sentiment lexicon matched
   "frustrated" (in a different answer) but not "frustration" or
   "impatient" — morphological variants of listed words are silently
   missed, a direct consequence of the project's stated pattern-match
   (not stemmed/lemmatized) approach.

Net effect: no false positive occurred (the system didn't invent a
contradiction), but a real, worth-surfacing nuance was silently missed
— a false negative on the "detect something notable" goal.

## Accuracy evaluation

- **Band-level accuracy**: 4/4 (100%) — every persona's overall
  performance band matched the direction a human reviewer would expect.
- **Critical negative-check accuracy**: 1/1 — the Inexperienced persona
  was correctly not penalized as "risky," the specific failure mode
  this persona was designed to catch.
- **Fine-grained precision**: 2 of 4 personas surfaced a real, specific
  scoring limitation (Findings 1 and 3) even though their top-line
  scores were still directionally reasonable. Both are precision
  issues inside a working system, not band-level errors.

## Improvement recommendations

1. **Broaden concrete-example detection** (Day 34) beyond a fixed
   phrase list — or, more honestly, keep the list but document plainly
   in recruiter-facing output that "thin" can mean "no example marker
   phrase used," not only "no real example given," so a human reviewer
   knows to read the actual transcript before trusting the tag.
2. **Have Day 39's summary generator cross-check strengths against
   content signals** — e.g., don't surface "strong confidence" as an
   unqualified headline strength when relevance is simultaneously
   below the weak threshold; note the pairing explicitly instead
   ("calm delivery, but content was limited").
3. **Loosen or reconsider the mixed-sentiment threshold** (Day 36) —
   a 1-and-1 threshold (with a smaller bonus/flag weight than the
   current 2-and-2 case) would catch more realistic nuanced
   disclosures without over-triggering on noise. Separately, expanding
   the sentiment lexicon with a small set of common morphological
   variants (frustrated/frustration/frustrating,
   impatient/impatience) would close the exact-match gap found here.

None of these are implemented in this day's deliverable — per the
brief, Day 40 is the test and report, not the fix.

## Deliverables

- `parsers/hr_interview_simulation.py` — the four persona definitions
  and the simulation runner (the "simulate multiple interview
  sessions" + "test different candidate types" tasks, as real,
  runnable, tested code).
- `run_day40_hr_interview_simulation.py` +
  `data/results/day40_hr_interview_test_report.json` — the executed
  comparison, with all four personas' AI output and manual
  expectations side by side.
- This document — the HR interview test report, accuracy evaluation,
  and improvement recommendations.

## Verification

11 new tests (`tests/test_hr_interview_simulation.py`), covering
persona definitions, end-to-end simulation runs, and the specific
directional claims each persona was designed to probe (Confident
scores well with no flags; Inexperienced isn't flagged inconsistent;
Hesitant's relevance and confidence scores differ). `pytest` itself
isn't installable in this build environment (no network access), so
these ran via the same assert-based Python runner used since Day 35.
Full project regression (324 tests, including every engine from Days
33–39 that this simulation exercises) passed clean with zero
regressions.
