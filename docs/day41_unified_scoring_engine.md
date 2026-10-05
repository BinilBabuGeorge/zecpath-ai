# Day 41 — Unified Scoring Engine

## What this day adds

`scoring/service.py`'s `DecisionScoringService` has been a Day 2
skeleton since before any of the underlying engines existed — a flat
weighted sum over five **guessed** field names (`ats_score`,
`screening_score`, `communication_score`, `technical_score`,
`behavior_score`) that only ever ran against a hand-typed demo dict,
never a real computed score. This day is the first time genuine
computed scores from all three rounds the project actually built —
ATS (Days 9–20's `ats_scoring_engine`), Screening (Day 26's
`screening_scoring_engine`), and HR interview (Day 37's
`hr_interview_scoring_engine`) — are combined for real, replacing Day
2's guessed field set with the three genuine round outputs that exist
now, plus the configurable, role-aware weighting the brief asks for.

## Reuse, not reimplementation

This module takes each round's own result object and reads its
headline score — `ATSScoreResult.overall_score`,
`ScreeningScoreResult.total_score`,
`HRInterviewScoreReport.overall_hr_score` — rather than recomputing
any of the resume parsing, question scoring, or interview evaluation
those numbers already represent. The missing-round weight
redistribution reuses the **pattern** Day 13's `ats_scoring_engine`
already established internally for its own four components (missing
data gets its weight redistributed proportionally across what *is*
available, flagged rather than silently zeroed) — applied here one
level up, across whole rounds instead of within one round.

## Two role taxonomies exist in this project, stated honestly

Day 13's ATS engine already has its own role-based weighting
(`tech`/`business`/`creative`/`default`, for weighting skill-match vs
experience vs education *within* the ATS score), and Day 33's HR
interview engine uses a separate `RoleType.TECHNICAL` /
`RoleType.NON_TECHNICAL` axis. This day's role-based adjustment is
**cross-round** (how much to weight the whole ATS round vs the whole
HR interview round), a different question from either existing
system, so it reuses HR's simpler two-value `RoleType` directly rather
than inventing a third taxonomy or forcing ATS's four-category one to
answer a question it wasn't built for. Reconciling the two taxonomies
into one is explicitly out of scope — named rather than silently
ignored.

## Hiring-fit percentage and decision thresholds

The 0–100 `hiring_fit_percentage` and the selected/hold/rejected
thresholds (≥70 / ≥50 / below) are carried over **unchanged** from Day
2's original `DecisionScoringService` stub — the project's own
first-ever stated thresholds. Changing them now, with still no labeled
hiring-outcome data in this project, would just be swapping one
unvalidated number for another; reusing the original numbers is the
more honest choice than guessing new ones.

## Role-based cross-round weights

Reasoned, not data-calibrated (the same caveat stated on every scoring
day since 34):

| Role | ATS | Screening | HR Interview |
|---|---|---|---|
| Technical | 40% | 15% | 45% |
| Non-technical | 25% | 15% | 60% |

Technical roles weight the ATS round (skills/experience match) and the
HR interview round roughly evenly. Non-technical roles weight the HR
interview round — where communication and interpersonal signal
actually show up — more heavily than the keyword-driven ATS round.

## Deliverables

- `parsers/unified_scoring_engine.py` — the cross-round scoring system
  (`RoundWeights`, missing-round redistribution), the hiring-fit
  calculator (`compute_unified_score`), and the unified candidate
  score object (`UnifiedCandidateScore`, with both `to_dict()` and a
  readable `to_summary_text()`).
- `run_day41_unified_scoring_demo.py` +
  `data/results/day41_unified_scoring_report.json` — three sample
  candidates (full/all-rounds, missing-round, and weak), each role
  type, with three built-in sanity checks.

## Verification environment note, stated honestly

This build ran in a fresh container that only has the base project
through Day 34 available locally (the Days 35–40 modules built in
earlier sessions aren't present here — they were delivered to you as
separate zips and merged into *your* project, not mine). Verification
below reflects what's actually importable and runnable in *this*
environment: 274 tests across the Day-34-and-earlier suite passed
clean with zero regressions (the same long-standing `pytest`-not-
installed limitation applies to 17 files that use pytest-only
features and couldn't even be collected here, as in every prior day).
**Run the full suite on your machine, where Days 35–40 are already
merged in, for the true current total** — expected to be your last
confirmed 819 plus these 18 new tests.

## Verification (this environment)

18 new tests (`tests/test_unified_scoring_engine.py`), covering weight
validation, missing-round redistribution (including the proportional-
ratio check), decision-band thresholds, role-based weight differences,
custom weight overrides, and output format. All 18 passed via the same
assert-based Python runner used since Day 35 (`pytest` itself isn't
installable here, no network access).

## Not done here (left for a future day)

- Wiring this into `scoring/service.py`'s `DecisionScoringService`
  itself — this day builds the real computation; swapping it into the
  Day 2 stub's `process()` method is a small follow-up, not done here
  to keep this day's deliverable focused and testable on its own.
- Reconciling ATS's four-category role taxonomy with HR's two-category
  one into a single shared vocabulary.
- Calibrating weights or thresholds against real hiring outcomes — no
  labeled data exists in this project.
