# Day 53 — Hiring Intelligence Report Generator

## What this day builds

Days 13–52 produce a great deal of structured data: ATS components,
screening scores, HR and technical results, a machine-test report, behavioral
and integrity signals, an aggregate score (Day 51) and a recommendation
(Day 52). A recruiter cannot read any of it in under a minute. This module is
the final translation layer: it assembles **one recruiter-facing report**
covering the brief's five insight areas and four highlights.

| Brief asks for | Where it appears in the report |
|---|---|
| ATS summary | Round section "ATS resume match" (components, matched / missing skills) |
| Screening results | "Screening call" (per-category scores) + optional "Screening highlights" (confirmed skills, salary expectation, availability, missing data) |
| HR insights | "HR interview" (relevance, communication, confidence, consistency) + optional Day 39 culture-fit note |
| Technical performance | "Technical interview" (per-skill scores, answer depth) and "Machine test" (per-task, per-metric) |
| Behavioral flags | "Behavioral flags" section |
| Strengths / Weaknesses | Two tables, each row with source, score and evidence |
| Risk indicators | Severity-ranked table (high / medium / low / info) |
| Final recommendation | Recommendation block with outcome, fit, confidence, reasons and next steps |

Code: `parsers/hiring_report_generator.py`.

## Read, never recompute

The recommendation, hiring fit, confidence, rule trace, risk factors and
review reasons are **read** from Day 52's `CandidateDecision` and Day 51's
`CrossRoundCandidateScore`. This module never re-decides anything. If the two
objects do not belong together (different candidate, or a hiring fit that does
not match) it **raises `ValueError`** rather than print a report whose pieces
disagree. Day 31's `ScreeningReport` and Day 39's `InterviewSummaryReport` are
optional extras: when supplied, their highlights and strengths / weaknesses
are used instead of being re-derived.

## Text generation, stated honestly

Like Day 39, "AI-generated" here means **template-based sentences chosen by
score band** — deterministic and rule-based. There is **no language model**
anywhere in this project and this day does not add one. The report says so in
its "About this report" section.

The consequence is a useful property: **every statement has a number behind
it.** Each strength, weakness and risk indicator carries its source round, the
metric, the score and a short evidence string.

## Strengths, weaknesses and risk indicators

**Strength** = a score of **75 or more**; **weakness** = a score **below 50**
(reasoned thresholds, not validated with recruiters). At most three of each per
source round, most extreme first, so the report stays digestible. Markdown and
HTML tables show the top 8 of each with a "N more, see the JSON export" note;
the JSON keeps every item. The executive summary picks its top three with
**breadth first** — the best item from each round before a second item from the
same round — so one chatty round cannot fill the whole summary.

| Source | Findings built from |
|---|---|
| ATS | Each available component; the skill component names matched and missing skills |
| Screening | Average score per question category |
| HR | The three averages (or Day 39's strengths / weaknesses when supplied) |
| Technical | Each skill in the skill breakdown; "answer depth" when a **majority** of answers were shallow |
| Machine test | Each assessed metric of each task |

Risk-indicator severity is a fixed mapping, not a judgement call:

| Indicator | Severity |
|---|---|
| Integrity tag HIGH / MEDIUM / LOW | high / medium / low |
| Missing evidence (provisional score) | medium |
| Strong round disagreement | medium |
| Machine test passes visible but fails hidden cases | medium |
| Low confidence in the recommendation | medium |
| Borderline score; screening / HR consistency findings; sandbox-relevant API; late submission; design proxy scoring | low |
| **Behavioral timing signals** | **low at most** (weak evidence) |
| Ignored evidence after deadline; ignored not-applicable score | info |

An invariant, tested: **every strength scores ≥ 75 and every weakness < 50.**
The first version of the depth finding broke it (exactly 50% shallow produced a
"weakness" scoring 50); it now needs a strict majority.

## Recruiter-friendly format

1. **Confidentiality banner** — "CONFIDENTIAL — RECRUITER USE ONLY".
2. **Executive summary** (six lines): outcome and fit, why, strongest areas,
   main concerns, evidence coverage, next step.
3. Recommendation table, reasons, suggested next steps.
4. Strengths, Weaknesses, Risk indicators, Behavioral flags.
5. Round-by-round results, then screening highlights.
6. How the Hiring Fit was calculated — profile, weights, contributions,
   leave-one-out sensitivity — and the decision rule trace.
7. About this report — limitations, not-implemented items, caveats.

Design rules: **missing evidence is "not yet available", never a zero**;
the outcome is shown as a **text label** as well as a colour; the report
states what it cannot tell you; a rejection is described as *a recommendation
that needs a person's confirmation*, and the candidate sees only "under review"
until then.

## Full candidate AI profile report (JSON schema 1.0)

`candidate` · `recommendation` (outcome, hold kind, fit, confidence, coverage,
reasons, next steps, `automated_action: "none"`) · `executive_summary` ·
`strengths` · `weaknesses` · `risk_indicators` · `rounds` · `behavioral_flags` ·
`score_breakdown` · `screening_highlights` · `rule_trace` · `about` ·
`confidentiality` · `report_id` · `generated_at` · `schema_version`.

`report_id` is `HIR-` plus a **content fingerprint** (hash of the report
excluding the timestamp): the same inputs give the same id, any change gives a
different one. It is an identifier, **not a digital signature**.

## Export-ready formats

One internal document model is rendered to three formats, so they cannot
drift apart (a test checks the same key facts appear in all three):

| Format | Notes |
|---|---|
| **JSON** | Stable, versioned, complete |
| **Markdown** | Escapes `\ ` * _ [ ] < > \|` — underscores show as `\_` in raw text and render normally |
| **HTML** | Self-contained: no scripts, no external resources, an A4 print stylesheet. **Print it to PDF from any browser** |

`export_report(report, directory, formats)` writes the files, named from the
fingerprint — **never from candidate-supplied text**, so an id like
`../../evil` cannot escape the folder. **All candidate-derived text is escaped**
for the target format (tested with `<script>` and `<img onerror>` payloads).

`to_preview_dict()` returns only the basic outcome and score, shaped for the
PRD's pay-to-unlock model (Phases 23 / 48 / 73 / 100). **Enforcing that access,
and payment, are not built.**

## Privacy and fairness

- The report holds **scores and short evidence only** — no transcripts and no
  raw answers (a test plants a secret string in a screening answer and checks
  it never appears in any export). No demographic fields exist in its model.
- **Verbal hesitation is displayed but labelled "NOT used"** — it penalises
  nervous and non-native speakers (Day 52's fairness choice).
- Behavioral timing is capped at LOW severity and never changes a
  recommendation by itself (Day 49's rule).
- It is recruiter-only; Day 52's candidate notices are the candidate-facing text.

## Integration

| Integration point | Status |
|---|---|
| Day 52 `CandidateDecision` and Day 51 `CrossRoundCandidateScore` | **Consumed** (consistency-checked) |
| Day 13 ATS, Day 26 screening, Day 37 HR, Day 47 technical, Day 50 machine test | **Consumed** (tested on the real classes) |
| Day 48 behavioral and Day 49 integrity reports | **Consumed** |
| Day 31 `ScreeningReport` and Day 39 `InterviewSummaryReport` | **Optional**, tested on the real classes |
| Native PDF, delivery, storage, access control | Not built |

## Demo results

Technical role; round results are hand-built stand-ins from the real result
classes, and the report logic is real. Each report is exported in all three
formats (12 files).

| Candidate | Report ID | Outcome | Fit | Confidence | Strengths / weaknesses / risks |
|---|---|---|---|---|---|
| A. Strong, clean | `HIR-41ad3f5e51b3` | SELECTED | 88.7 | 95.7 | 13 / 0 / 0 |
| B. Strong, integrity MEDIUM, timing spikes | `HIR-c93d7c9b34dc` | HOLD (selection blocked) | 85.9 | 68.5 | 9 / 3 / 4 |
| C. Weak across the board | `HIR-2a8a21c9dd45` | REJECTION RECOMMENDED | 34.15 | 96.7 | 0 / 14 / 0 |
| D. Machine test not taken | `HIR-cd47623266dd` | HOLD (pending) | 78.14 | 60.0 | 7 / 0 / 1 |

## Known limits

- The format has **not been tested with real recruiters**; thresholds, severity
  mapping and wording are reasoned.
- **No native PDF** — print the HTML export.
- **Access control and payment** for the preview/full split are not built.
- **No bias audit** of the recommendations by group.
- The report inherits every upstream limit — the machine-test round rests on a
  sandbox that has not been built.
- The HTML was checked in a limited renderer and by tests; it has not been
  eyeballed across browsers.
