# Day 28 — AI Screening Report Generator

## Scope, stated honestly up front

This module does **not** generate any new text with an LLM. Every
bullet in a report's strengths/risks/missing-data sections is produced
by a fixed template filled in from a real, already-computed number or
fact from Day 25/26/27 — never freely generated prose. This is a
deliberate design choice, not a limitation: a recruiter-facing report
that claims to summarize an AI evaluation should say only what the
evaluation actually found, in the evaluation's own numbers, not a
paraphrase an LLM invented that could drift from what was actually
measured.

**Nothing is recomputed.** This module's entire job is aggregation and
formatting of outputs that already exist.

## Pipeline position

```
understand_answer()              (Day 25) → StructuredAnswer, per turn
score_screening_call()           (Day 26) → ScreeningScoreResult
build_communication_profile()    (Day 27) → CommunicationProfile
                                        │
                                        ▼
generate_screening_report()      (Day 28, this module)
                                        │
                                        ▼
ScreeningReport  →  .to_dict() / .to_json()  (machine-readable)
                 →  .to_markdown()            (recruiter-readable, exportable)
```

## Section-by-section logic

| Section | Source | Logic |
|---|---|---|
| **Key Answers** | Day 25 (`raw_text`) + Day 26 (`weighted_total`) | One row per turn, joined by `turn_id`; long answers truncated to 160 chars with `...` |
| **Strengths** | Day 26 scores + Day 27 breakdown | Templated bullets for questions ≥80/100, zero hesitation/uncertainty, positive sentiment (>5, matching Day 27's own label boundary), zero contradictions |
| **Risks** | Day 26 scores + Day 27 breakdown + Day 26 findings | Templated bullets for questions <50/100 (excluding MISSING, to avoid double-reporting the same gap as both a risk and a missing-data item), Day 26's `consistency_findings` surfaced verbatim, elevated hesitation/uncertainty (>10/100 words), negative sentiment (<−5) |
| **Missing Data** | Day 25 quality + notes | Every `MISSING`-quality turn, plus every turn carrying a "could not extract" / "not found" note from Day 25/26 |
| **Highlights** | Day 25 entities | Every non-`None` salary/availability mention found (not just the first), deduplicated union of all skills mentioned across the call |

All thresholds (`80`, `50`, `10`/100 words, `±5`) are named constants
at the top of the module — reasonable defaults in the same spirit as
Day 26's weight profiles and Day 27's scoring formula, not tuned
against real hiring outcomes this project doesn't have data for.

### Why a MISSING answer isn't also flagged as a "weak answer" risk

A silent/missing turn already appears in Missing Data. Also listing it
under Risks as "weak answer (score 10/100)" would report the exact
same gap twice under two different framings — the risk-builder
explicitly excludes `MISSING`-quality turns from the weak-answer check
for this reason, verified by a dedicated test.

## Demo run

Six answers from one candidate — deliberately mixing a mediocre
introduction, an hesitant answer that conflicts with it, a clean
skills answer, an unparseable-salary answer, a clean availability
answer, and one silent (missing) answer — run via
`run_day28_screening_report_demo.py`:

- **Total Screening Score: 70.7** / **Communication Strength Score: 78.6**
- 4 strengths correctly identified (experience, skills, availability
  scores ≥80; positive sentiment)
- 2 risks correctly identified (weak introduction score; the reused
  Day 26 experience-years conflict)
- 2 missing-data items correctly identified (unparseable salary;
  silent education answer)
- Highlights correctly pulled availability (`immediate: True`) and 3
  deduplicated skills (Node.js, React.js, Docker); salary correctly
  reports "not stated / not extractable" since Day 25 couldn't parse
  an amount from "a good package"

This run produces the actual deliverable files, not just log output:
`data/reports/sample_screening_report_CAND-2026-0142.md` (recruiter-
readable) and the matching `.json` (machine-readable).

## Deliverables (per the Day 28 brief)

- **AI screening report builder** — `generate_screening_report()`.
- **Recruiter-ready report format** — `ScreeningReport.to_markdown()`,
  producing a clean Markdown document with a scores header, a key-
  answers table, and the four narrative sections.
- **Sample screening reports** — the actual generated `.md` and
  `.json` files from the demo run, included as real artifacts, not
  just described.

## Testing

22 tests in `tests/test_screening_report_generator.py`: every section
builder (key answers, strengths, risks, missing data, highlights)
independently, the MISSING-vs-weak-answer double-counting guard, both
export formats (`.to_dict()`/`.to_json()` validity, `.to_markdown()`
section presence and graceful empty-section rendering), and score/
metadata pass-through. 132 tests pass project-wide across the
pytest-independent test modules (Days 1–28) — zero regressions from
this change.

## Honest limitations carried forward

- No generative text — reports are template-filled from real numbers
  only. A recruiter wanting free-form narrative summary would need an
  LLM layer on top of this, explicitly out of scope here.
- All thresholds are fixed defaults, not calibrated against real
  hiring outcomes.
- Highlights present *every* stated value for salary/availability
  without resolving conflicts between them — Day 26's consistency
  findings (surfaced separately in Risks) are the place a recruiter
  would see that two answers disagreed; Highlights intentionally shows
  the raw facts rather than picking a "winner" between them.
- Every limitation inherited from Day 25/26/27 (text-only disfluency
  detection, salary-unit gap, rule-based-not-ML scoring) still applies
  here, since this module surfaces those same numbers rather than
  changing them.
