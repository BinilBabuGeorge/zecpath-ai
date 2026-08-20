# Day 17 — ATS Testing Report

## Objective

Validate ATS accuracy, reliability, and role adaptability by comparing the
AI pipeline's zone classification (Day 12 semantic matching → Day 13
scoring → Day 14 zone classification) against independently-judged manual
review, across tech roles, non-tech roles, fresher resumes, and senior
profiles.

## Methodology

12 resume/JD pairs were selected to cover all four required test
dimensions. For each pair, an `expected_zone` (SHORTLIST / REVIEW /
REJECT) was written by reading the resume and JD text directly and
reasoning about genuine fit — **before** running the AI, and without
looking at what the AI would produce. This mirrors the discipline already
established in this project's `generate_ground_truth.py` for the section
classifier: manual judgments written independently are what make an
accuracy comparison meaningful rather than circular.

One new fixture, `resume_16_senior_backend_lead.txt` (6.5 years, MERN
tech lead), was added — the existing dataset's most senior candidate
tops out around 4 years, which isn't enough to actually test "senior
profiles" as the brief requires.

The AI was then run unmodified against all 12 pairs, and its zone
classification was compared to the manual-review zone. See
`data/ground_truth_ats/day17_manual_review.json` for every judgment and
its reasoning, and `run_day17_testing.py` for the comparison harness.

## Result: 41.7% agreement (5/12)

This is the headline number, and it is not a good one. Full breakdown:

| Zone | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| SHORTLIST | 1 | 1 | 3 | 0.500 | 0.250 | 0.333 |
| REVIEW | 3 | 6 | 1 | 0.333 | 0.750 | 0.462 |
| REJECT | 1 | 0 | 3 | 1.000 | 0.250 | 0.400 |

**By category:** non-tech 60.0% (3/5), tech 28.6% (2/7).
**By experience level:** fresher 100% (1/1), mid 44.4% (4/9), **senior 0% (0/2)**.

The system is not randomly wrong — it is **systematically biased toward
REVIEW**. 9 of 12 predictions landed in REVIEW (6 of those incorrectly),
while REVIEW only belongs there 3 times per manual judgment. In effect,
the current thresholds turn the shortlist/reject decision into "REVIEW,
unless the score is unusually high or unusually low" — which defeats
much of the point of automated zoning.

## Two root causes, not twelve isolated bugs

Reading all 7 mismatches together, they collapse into two systemic issues
rather than a dozen unrelated ones:

**1. SHORTLIST threshold is miscalibrated for tech roles.**
Every genuinely strong tech-role match in this test scored in the
50–55 range (resume_01 vs jd_01: 50.3; resume_16 senior vs jd_03: 53.1;
resume_16 senior vs jd_01: 49.5) — all landed in REVIEW because the
SHORTLIST cutoff is 55. That cutoff was calibrated during Day 15 against
a **different, informal 6-candidate sample** dominated by a strong
business-role match (61.3). Tech-role scores apparently have a lower
practical ceiling under the current weight profile, and a single global
threshold doesn't account for that — Day 15 built exactly the tool for
this (`normalize_scores_batch()`) but zone classification doesn't use
it.

**2. REVIEW's floor (25) doesn't gate on skill relevance.**
Every genuine mismatch in this test (wrong tech stack, wrong business
function) still scored 25–35 and landed in REVIEW instead of REJECT —
because `experience` and `education` components award credit for
*years* and *degree level* independent of whether those years/degree are
in a relevant field. resume_11 (Python/Django backend dev) scored 34.9
against a MERN JD specifically because `experience` contributed 14.1
points despite zero stack overlap — its own explanation says so:
*"Strongest contributor: experience (47.0/100, contributing 14.1
points)"* for a candidate whose skill_match should have been the
overriding signal.

## What worked

- **Fresher handling (1/1):** the one fresher case correctly landed in
  REVIEW, not an automatic REJECT for lacking experience nor an automatic
  SHORTLIST for having the right skills — arguably the hardest of the
  three-way calls, and it landed right.
- **Direct strong matches score decisively:** resume_03 (sales) vs
  jd_02 scored 61.3 and correctly shortlisted — when a candidate is an
  unambiguous fit, the system gets it right.
- **Clear accounting mismatch correctly rejected:** resume_09 vs
  jd_02_sales_executive — zero relevant skills, correctly landed in
  REJECT, the one true-negative in this test.

## Limitations of this test itself

- 12 pairs is a real but small sample — the *pattern* (systematic bias
  toward REVIEW, threshold miscalibration) is well-supported by 7
  consistent mismatches, but the exact percentages will move with a
  larger test set.
- All ground truth was authored by one reviewer (this session). A
  production testing process should have multiple independent reviewers
  and measure inter-rater agreement before trusting the "expected" label
  itself.
- This test only exercises `classify_zone()`'s three-way call, not the
  underlying `overall_score` accuracy directly (e.g. via correlation to
  a numeric human rating) — that's a reasonable follow-up test design.

See `docs/day17_improvement_backlog.md` for concrete next steps derived
from these findings.
