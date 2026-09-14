# Day 32 — Screening AI Evaluation Report

Three simulated candidates, run through the complete, real, assembled
pipeline (`run_screening_call()`, Days 22–31) via
`run_day32_end_to_end_demo.py`. All turns are hand-written example
text, not real candidate speech — same honesty stance as every prior
demo in this project. What follows is a genuine evaluation of the
system's output on these three runs, not a rehearsed narrative.

## Results

| Candidate | Role | Total Score | Communication Score | Categories Answered | Strengths | Risks |
|---|---|---|---|---|---|---|
| **Strong** | MERN Stack Developer | **89.9** | 100.0 | 7/7 | 7 | 0 |
| **Mixed** | QA Tester | **69.4** | 100.0 | 7/7 | 5 | 2 |
| **Weak** | Sales Executive | **23.2** | 78.6 | 4/7 | 1 | 5 |

The system produces a clean, discriminative spread across candidate
quality — this is the headline finding: it correctly separates a
strong candidate from a mediocre one from a weak one, using nothing but
the rule-based logic built across Days 25–28.

## Strong candidate — clean, substantial answers throughout

Every one of 7 categories answered with a complete, on-topic,
substantial response. Result: 7 strengths, 0 risks, 89.9/100. This is
the system behaving exactly as intended on well-formed input — not an
interesting result by itself, but the necessary baseline the other two
runs are measured against.

## Mixed candidate — two answers deliberately hit known, already-documented gaps

This candidate's call was designed to test something specific: what
happens when a mostly-solid candidate gives two short, correct-but-
unusually-phrased answers?

- **"B.Sc IT"** for education — scored `vague`. Day 25's education
  keyword list recognizes `"b\.?tech"` but not "B.Sc," "M.Sc," "B.Com,"
  or other common degree abbreviations. **This is a new gap found
  during this evaluation**, not previously documented — noted in
  `docs/day32_handover.md` as a concrete next step, not fixed here (Day
  32 is a finalization/integration day, not a new bug-fixing round —
  see Day 30 for that methodology if this gap is prioritized later).
- **"Chennai"** for location — scored `vague`. This is Day 30's
  already-known, already-documented gap (bare place names have no
  digit/keyword/confident-word signal without a location gazetteer).
  Seeing it reproduce exactly as documented, in a fresh end-to-end run
  three days of work later, is itself a small piece of validation that
  the documentation is accurate.

Both answers correctly triggered Day 29's fallback-question logic (the
candidate was asked a simplified restatement), and both were still too
short to pass the second time, correctly resulting in a `polite_skip`
for those two categories rather than an infinite retry loop. Final
score: 69.4/100 — meaningfully lower than the strong candidate, but not
catastrophically low, which is the right outcome: two short answers
amid five solid ones should read as "worth a second look," not "reject."

## Weak candidate — genuine hedging, and a real system behavior worth knowing about

This candidate hedges or goes off-topic on nearly every answer
("I guess I have done some work before," "not sure," "maybe a few
things," "depends"). Result: only **4 of 7 categories were even
reached** before the simulated turns ran out, because each vague answer
consumes an extra turn for Day 29's fallback question.

**This is a genuine, worth-knowing system property, not a demo
artifact:** a call with a consistently unclear candidate will
organically run longer (more fallback/retry turns per question) and,
if the call has a fixed turn/time budget, may not reach every planned
question at all. A real deployment should account for this — either by
giving calls a generous turn budget, or by treating "candidate never
reached several questions due to repeated vagueness" as itself a
meaningful, reportable signal (which Day 28's Missing Data section
already surfaces, correctly attributing it to "the call ended before
this question was reached" rather than miscategorizing it as a
technical failure).

Final score: 23.2/100, correctly reflecting a candidate who could not
give a clear, on-topic answer to almost anything asked — appropriately
the lowest of the three.

## What this evaluation validates

1. **Discriminative power** — three genuinely different candidate
   qualities produced three clearly different, sensibly-ordered scores.
2. **Known limitations reproduce accurately** — the "Chennai" gap
   documented in Day 30 showed up exactly as expected in a completely
   independent, later test.
3. **A new limitation was found**, honestly reported rather than
   hidden — the degree-abbreviation gap.
4. **A real, non-obvious system behavior was surfaced** — vague
   answers extend call length and can reduce category coverage, a
   property worth designing around in production, not something this
   evaluation manufactured artificially.
5. **The Day 28 report-generator fix works as intended** — every
   missing-data entry in all three reports carries an accurate,
   specific reason, not just a generic "no answer" line.

## Sample reports

Full recruiter-facing and machine-readable reports for all three
candidates: `data/reports/day32_sample_report_CAND-{STRONG,MIXED,WEAK}-01.{md,json}`.
Full run log: `logs/day32_end_to_end_demo.log`. Comparison summary:
`data/results/day32_evaluation_summary.json`.
