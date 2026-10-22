# Day 52 — Final Recommendation AI

## What this day builds

The last step of the scoring pipeline. Day 51 combined five rounds into a
Hiring Fit Score; this engine turns that score, plus integrity (Day 49) and
behavioral (Day 48) risk factors, into one of three decision categories —
**Selected, Hold / Review, Rejected** — with a **confidence score** and a full
**explainable rule trace**. It is the engine behind PRD Phase 71 (final
selection recommendation with hiring-fit confidence).

Code: `parsers/final_recommendation_engine.py`.

## The decision this day had to make: "automated hiring outcomes"

The brief says *"Build decision-making AI for automated hiring outcomes."*
This design **automates the recommendation** and keeps one hard line on the
**outcome**, enforced in code, not only in this document:

| Outcome | May the system apply it without a person? |
|---|---|
| **Rejected** | **Never.** `DecisionPolicy` raises `ValueError` if you try to enable it. The candidate-facing notice for an unconfirmed rejection says "under review". A named human must confirm it |
| **Hold / Review** | No — a hold *is* a request for a person |
| **Selected** | Only if a policy explicitly enables auto-advance (default: **off**), confidence ≥ 75, no rule blocked it and no review reason exists. Even then it is a low-harm, reversible move to the next stage |

Every human confirmation or override is recorded with the reviewer's name;
an override requires a written note.

**Why:** a wrongly rejected candidate is the costly, hard-to-reverse error;
every weight and threshold here is reasoned, not calibrated (no labelled
hiring-outcome data exists); and employment is a category that regulators in
several places treat as high-risk or as subject to rules about solely
automated decisions (general awareness, not legal advice — real use needs
legal review and a bias audit first). Days 41 and 51 already took this stance;
Day 52 makes it enforceable. *If your mentor reads "automated" as "fully
automatic rejection", this is the point to raise with them.*

## Decision categories

| Category | Meaning | `hold_kind` (for Hold / Review) |
|---|---|---|
| **SELECTED** | Score clears 70, no rule blocks it | — |
| **HOLD_REVIEW** | A person should look before anything happens | `pending_evidence` — rounds still to complete |
| | | `mid_score` — fit is in the 50–70 review band |
| | | `selection_blocked` — the score says select, a rule says look first |
| | | `insufficient_evidence_to_reject` — score is low, but not enough evidence to recommend rejection |
| **REJECTED** | Score is below 50 with adequate confidence — a **recommendation**, human-confirmed | — |

`hold_kind` makes "why is this on hold?" answerable at a glance.

## Rule + score hybrid logic

1. **Score sets a base band** from the Hiring Fit Score, using the 70 / 50
   thresholds carried unchanged from Day 2 → Day 41 → Day 51 (pinned by a test).
2. **Rules then guard that band.** Rules only ever move an outcome toward
   human review, never toward rejection.

| Rule | Condition | Effect |
|---|---|---|
| **R1** Evidence complete | An applicable round is missing | Forces HOLD (`pending_evidence`) |
| **R2** Critical-round floors | A skill round is below 40 (`technical_interview`, `machine_test`; `hr_interview` for non-technical roles) | Blocks SELECTED |
| **R3** Integrity gate | Day 49 tag is MEDIUM or HIGH | Blocks SELECTED |
| **R4** Review flags | Day 51 raised borderline / round-disagreement / a round asked for review | Blocks SELECTED |
| **R5** Selection confidence | Confidence below 55 | Blocks SELECTED |
| **R6** Rejection confidence | Confidence below 50 | REJECTED → HOLD (`insufficient_evidence_to_reject`) |
| **R7** Rejection needs a person | Outcome is REJECTED | Recorded; never auto-applicable |

**Why R2 exists:** an average is compensatory — a candidate can score 95 on
everything except the core skill round and still average above 70. R2 is the
guard against "great overall, failed the thing the job is about" (demo
candidate D: Hiring Fit 77.0, technical round 35).

**Why R6 exists:** the cost of a wrong rejection is higher than the cost of
a wrong hold, so shaky evidence is never enough to recommend rejection.

## Confidence score (0–100)

A measure of how **robust the evidence behind the score band** is. It is
**not a probability of a good hire and not calibrated** — there is no outcome
data to calibrate it against. It tells a reviewer how much to trust the number.

| Component | Weight | Meaning |
|---|---|---|
| Margin | 35% | Distance from the nearest threshold (full credit at 15 points) |
| Coverage | 25% | Share of applicable weight that has evidence (Day 51) |
| Agreement | 20% | Spread between rounds the profile did not deliberately down-weight |
| Stability | 20% | Share of leave-one-out scenarios (Day 51 sensitivity) that keep the same band |

The weighted sum is multiplied by a **risk multiplier** (integrity: low ×0.95,
medium ×0.80, high ×0.60; behavior: low ×0.95, medium ×0.90). A score with a
missing round is **capped at 60**, so an incomplete candidate never reads as
"high confidence" (the demo exposed this: cand-C showed 80.8 / high while
waiting on a whole round).

## Risk factors

| Factor | Source | Effect |
|---|---|---|
| **Integrity** | Day 49 tag / report (the more severe of the two wins) | MEDIUM/HIGH blocks SELECTED and lowers confidence; LOW is informational |
| **Behavior** | Day 48: 2+ response-time spikes, pacing-consistency score below 50 | **Lowers confidence only** — never changes the category by itself |
| **Verbal hesitation** | Day 48 | **Shown but deliberately not used** |

Hesitation is not used because it penalises nervous and non-native speakers —
a fairness risk Day 48 itself named. Behavior only lowers confidence because
Day 49 established that behavioral signals can corroborate but never accuse.

**Property, tested exhaustively:** across 7 score levels × 5 integrity tags ×
3 spike counts × 2 pacing levels, no combination of risk factors turns a
non-rejected candidate into a rejected one, or a non-selected one into a
selected one.

## Explainable outputs

Every decision carries:

- the **score band** (what the score alone says) next to the **final outcome**
- the **ordered rule trace** — all seven rules, fired or not, with the effect
  (a rule that did not fire shows no detail, so it cannot contradict itself)
- plain-language **reasons**, the **confidence breakdown** and the **risk factors**
- **what would change this** — concrete conditions (e.g. "+10.0 points with no flags would select")
- `explain()` and `to_summary_text()` renderings

**Candidate-facing notices** are separate from recruiter detail: they never
contain scores, risk factors, confidence or the word "integrity" (tested).
Until a human confirms a rejection, the candidate sees only "under review".

## Candidate decision output format (schema 1.0)

`CandidateDecision.to_dict()` returns stable, plain-string fields:

| Field | Content |
|---|---|
| `schema_version` | `"1.0"` |
| `candidate_id`, `role_type`, `experience_level` | Identity and profile |
| `outcome`, `hold_kind`, `score_band` | `selected` / `hold_review` / `rejected`; why held; what the score alone says |
| `hiring_fit_percentage` | Day 51 score (`null` when nothing is scored) |
| `confidence` | Score, band, the four components, risk multiplier, note |
| `risk_factors`, `rule_trace`, `reasons`, `what_would_change` | The explanation |
| `automation_eligible`, `requires_human_confirmation`, `automated_action` | Always `"none"` — the engine itself never acts |
| `evidence_coverage`, `not_implemented`, `caveats` | Honesty fields |

`FinalizedDecision.audit_record()` returns `candidate_id`, `engine_outcome`,
`final_outcome`, `decided_by` (`human:<id>` or `policy:auto_advance`),
`overridden`, `note`.

## Integration

| Integration point | Status |
|---|---|
| Day 51 `CrossRoundCandidateScore` (fit, coverage, sensitivity, flags, integrity tag) | **Consumed** |
| Day 49 `IntegrityReport` | **Consumed** (flags shown in the risk factor); tested on a real report |
| Day 48 `BehavioralInsightReport` | **Consumed** (tested on a real tracker report) |
| Day 50 machine-test review reasons | **Flow through Day 51 into R4** |
| PRD Phase 71 (recommendation + confidence) | **Built** |
| PRD Phase 72 (selection / rejection communication) | Notice text only; **sending is not built**, and rejection notices are withheld until a human confirms |
| API / database / queue | Not wired |

## Demo results

Technical role; per-round inputs are synthetic stand-ins, the decision logic
is real (the integrity input is a real Day 49 report).

| Candidate | Fit | Score band | Outcome | Confidence | Why |
|---|---|---|---|---|---|
| A. Strong, clean | 85.1 | selected | **SELECTED** | 96.0 | Auto-advance eligible when the policy is on |
| B. Fresher, weak resume | 83.42 | selected | **SELECTED** | 95.7 | Fresher profile applied |
| C. No machine test yet | 80.0 | — | HOLD (`pending_evidence`) | 60.0 | Capped while incomplete |
| D. Core technical round 35 | 77.0 | selected | HOLD (`selection_blocked`) | 60.2 | R2 and R4 |
| E. All rounds ≈ 71 | 71.3 | selected | HOLD (`selection_blocked`) | 67.5 | R4 borderline |
| F. Weak everywhere | 30.0 | rejected | **REJECTED** | 100.0 | R7: human must confirm; candidate sees "under review" |
| G. Strong, integrity MEDIUM | 86.6 | selected | HOLD (`selection_blocked`) | 79.1 (98.9 without the tag) | R3; score unchanged |
| H. Strong, timing spikes | 86.6 | selected | **SELECTED** | 89.0 | Behavior lowered confidence only |
| I. Weak, scattered, integrity MEDIUM | 46.0 | rejected | HOLD (`insufficient_evidence_to_reject`) | 42.6 | R6 |
| J. Middle scorer | 60.0 | hold | HOLD (`mid_score`) | 88.3 | — |

With auto-advance **on**: A is eligible; G (integrity) and F (rejection) are
refused, and `DecisionPolicy(auto_apply={REJECTED: True})` cannot even be
constructed.

## Known limits

- Thresholds, floors, multipliers and confidence weights are reasoned, not calibrated.
- **No bias audit** of the decisions by group has been done — a prerequisite for any automation.
- Confidence is a robustness measure, not a probability.
- Notices are text only; delivery, audit storage and an appeals workflow are not built.
- Not reviewed against employment or automated-decision regulation.
- The decision inherits every upstream limit — the machine-test round still
  rests on a sandbox that has not been built.
