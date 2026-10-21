# Day 51 — Cross-Round Aggregation Engine

## What this day adds

Day 41's `unified_scoring_engine` combined three rounds: ATS, screening and
HR interview. Since then the project built two more — the technical
interview (Day 47) and the machine test (Day 50) — so there are now **five**
round outputs and nothing that combines them. This engine does, and produces
the PRD's **Hiring Fit Score (%)** (Phases 70–71).

It is **additive**: Day 41 is untouched. Two things are carried over so the
two engines stay consistent, and both are tested:

- The **70 / 50 recommendation thresholds** are pinned to Day 41's constants
  (a test fails if they drift).
- For a **non-technical, experienced** candidate the result **reproduces Day
  41's three-round score exactly** (75.35 vs 75.35 in the demo).

For technical roles the weights are deliberately different — see below.

Code: `parsers/cross_round_aggregation_engine.py`.

## Aggregation flow

```
 ATS  Screening  HR  Technical  Machine test        (earlier engines' own result objects)
  │      │       │      │           │
  └──────┴───────┴──────┴───────────┘
                  │  round_from_* adapters: read the EVIDENCE, not just the number
                  v
         RoundResult (score 0-100 | missing)
                  │
                  v   role weight profile  ->  experience adjustment  ->  renormalise
        applicable / not applicable / missing  ->  redistribute over scored rounds
                  │
                  v
   Hiring Fit % + coverage + contributions + sensitivity + flags
                  │
                  v   recommendation (advice) + human-review rules
         CrossRoundCandidateScore   ──>  rank_candidates (complete candidates, one role type)
```

## Inputs: evidence, not numbers

Several earlier engines return `0.0` when a round had nothing to score — Day
47 with no scoreable answers, Day 37 with no answered questions, Day 26 with
no answers. Treating that as a real zero would silently punish a candidate
who simply has not done the round. The adapters check each result's evidence
and report such a round as **missing**:

| Adapter | Source object | Counted as missing when |
|---|---|---|
| `round_from_ats` | `ATSScoreResult` | no component is `available` |
| `round_from_screening` | `ScreeningScoreResult` | `question_scores` is empty |
| `round_from_hr` | `HRInterviewScoreReport` | `num_questions_answered` is 0 |
| `round_from_technical` | `TechnicalEvaluationReport` | `answer_evaluations` is empty |
| `round_from_machine_test` | `MachineTestReport` | `tasks` is empty |

A genuine score of 0 is still a score: a real zero and a missing round are
different things, and a test pins that. Scores on other scales are converted
by `normalize_score` (0–1, 0–10, 0–100); out-of-range, NaN or non-numeric
input is **rejected, not clamped**.

## Weightage system per role

| Round | Technical role | Non-technical role |
|---|---|---|
| ATS | 0.10 | 0.25 |
| Screening | 0.10 | 0.15 |
| HR interview | 0.20 | 0.60 |
| Technical interview | 0.30 | — (not applicable) |
| Machine test | 0.30 | — (not applicable) |

- **Technical roles** put 60% on the two rounds that test real skill. By the
  time a candidate reaches them, the ATS keyword match has already done its
  filtering job and discriminates weakly (range restriction).
- **Non-technical roles** are exactly Day 41's profile, so continuity holds.
- Custom weights can be supplied; they are validated (all five rounds, none
  negative, sum to 1) and used exactly as given.

**Not applicable ≠ missing.** A round the role does not use has weight 0 and
is `NOT_APPLICABLE`. A round the role needs that has no evidence yet is
`MISSING`. A score supplied for a not-applicable round is ignored and flagged.

## Hiring Fit Score (%)

```
effective_weight(r) = adjusted_weight(r) / sum(adjusted_weight of SCORED rounds)
hiring_fit          = sum( score(r) × effective_weight(r) )      over scored rounds
```

Worked example (technical role, experienced, demo candidate A):

```
0.10×82 + 0.10×78 + 0.20×80 + 0.30×85 + 0.30×92
=  8.2  +  7.8   +  16.0   +  25.5   +  27.6   =  85.1%
```

## Normalizing across candidate profiles

"Normalize" is easy to over-claim, so here is exactly what is and is not done.

1. **Scale** — every round is validated and converted to 0–100.
2. **Experience profile** — a fresher has little work history, so the ATS
   round (resume/experience match) scores them low for reasons unrelated to
   ability. For freshers, ATS weight ×0.5 and the two skill-test rounds
   ×1.15, then weights are renormalised to 1. Every score lists this
   adjustment. Demo candidate B (weak resume, strong skills) scores **83.42**
   under the fresher profile and **80.5** under the experienced one.
3. **Applicability** — rounds a role does not use are removed, not scored as
   zero.
4. **Comparability** — a score built from 3 of 5 rounds is not comparable
   with one built from all 5, so incomplete candidates are marked
   *provisional* and excluded from ranking (below).

The round-disagreement check ignores any round the profile deliberately
down-weighted. Without that, a fresher's thin resume would trigger a
mandatory review — a second penalty that undoes the adjustment. (The demo
exposed this; it is fixed and tested both ways.)

**Not done:** cohort-relative normalization (z-scores or percentiles against
other candidates). It needs real cohort data this project does not have, and
it would make one candidate's score depend on who else applied.

## Missing rounds and provisional scores

| State | Hiring fit | Recommendation | Rankable |
|---|---|---|---|
| All applicable rounds scored | Computed | selected / hold / rejected | Yes |
| Any applicable round missing | Computed over scored rounds, marked **provisional**, with `coverage` shown | **incomplete** | No |
| No round scored | `None` (never 0) | incomplete | No |

## Recommendation and human-review rules

Thresholds are Day 2's, carried through Day 41: **≥ 70 selected, ≥ 50 hold,
below rejected.** The recommendation is advice. `automated_decision` is
always `"none"`.

Human review is required when any of these hold:

| Trigger | Why |
|---|---|
| Recommendation is **rejected** | A rejection is never automatic |
| Score within 3 points of a threshold | A small change in any round flips the outcome |
| Day 49 integrity tag is **MEDIUM or HIGH** | The session should be looked at; the number is **not** changed |
| A round itself asked for review | E.g. Day 50's keyword-scored system-design task |
| Rounds disagree by ≥ 35 points | An average hides that (demo candidate D: 73.3, but technical is 40) |

The integrity tag is read from the parameter and from each round, the most
severe wins, and exactly **one** consolidated review line is produced (the
machine-test adapter drops Day 50's own integrity line to avoid duplicating it).

## Transparency of scoring

Every score object carries:

- the **weight profile id** (e.g. `technical/fresher/v1`) and every **adjustment** applied
- per round: status, score, **base weight → adjusted weight → effective weight → points contributed**
- the **formula** as text and a plain-language `explain()`
- **leave-one-out sensitivity**: the fit if each round were excluded, so a reader sees which round the result leans on (and `explain()` says when none does)
- **flags** and review reasons, `coverage`, a `not_implemented` list and `caveats`

Contributions add up to the headline number; effective weights always sum to 1.

## Ranking

`rank_candidates` ranks **complete** candidates, **within one role type**
(mixed role types raise an error — fit scores for different jobs are not
comparable). Fresher and experienced candidates for the same role *are*
ranked together, because their weights are already profile-adjusted. Ties
share a rank. Incomplete candidates are listed separately with the reason.
Rows carry the review flag and integrity tag, so a flagged candidate at rank 1
is visible as such. Ranking is a sorting aid, not a decision.

## Integration plan

| Integration point | Status |
|---|---|
| Day 41 thresholds and non-technical weights | **Reused, pinned by tests** |
| Days 26, 37, 47, ATS result objects | **Adapters built, tested on the real classes** |
| Day 50 `MachineTestReport` (review reasons + Day 49 tag) | **Adapter built, tested on a real report** |
| Day 49 integrity tag | **Passed through; adds review, never changes the score** |
| Day 33 `RoleType` / `ExperienceLevel` taxonomy | **Reused** |
| `scoring/service.py` and the API layer | Not wired — scores come from result objects handed in |
| Stored per-job custom weights | Not built |

## Demo results

Technical role; per-round scores for A–G are synthetic stand-ins, the
aggregation is real. Candidate H uses real result objects.

| Candidate | Fit | Recommendation | Review | Why |
|---|---|---|---|---|
| A. Strong everywhere | 85.1 | selected | no | — |
| B. Fresher, weak resume, strong skills | 83.42 | selected | no | 80.5 under the experienced profile |
| C. No machine test yet | 80.0 | **incomplete** | no | Provisional, coverage 70%, not ranked |
| D. Technical round 40, others ≥ 85 | 73.3 | selected | **yes** | Rounds disagree by 52 |
| E. All rounds ≈ 71 | 71.3 | selected | **yes** | Borderline |
| F. Weak across the board | 40.0 | rejected | **yes** | Rejection always reviewed |
| G. Strong, integrity tag HIGH | 86.6 | selected | **yes** | Same score as without the tag |
| H. Real objects; HR and technical reported 0.0 with no answers | 89.5 | **incomplete** | yes | Zeros treated as missing; machine-test integrity tag MEDIUM |
| Non-technical role | 75.35 | — | — | Equals Day 41's 75.35 |

## Known limits

- Weights, the fresher multipliers and the 70/50 thresholds are reasoned,
  not calibrated; no labelled hiring-outcome data exists.
- No fairness analysis of the **aggregate** score by group has been done. The
  ATS and keyword-based rounds in particular could carry bias that the
  aggregate inherits.
- The aggregate is only as trustworthy as its weakest round — the machine
  test, for example, still rests on a sandbox that has not been built.
- Not wired to a database, API or the `scoring/service.py` skeleton.
- Two role types only; the finer ATS role categories (tech / business /
  creative) are a separate taxonomy, still unreconciled (Day 41's note).
