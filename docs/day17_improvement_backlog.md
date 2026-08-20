# Day 17 — Improvement Backlog

Every item below traces to a specific mismatch found in
`docs/day17_testing_report.md` — nothing here is speculative housekeeping.

## P0 — Fix before this system makes real shortlisting decisions

### 1. Recalibrate zone thresholds per role category, or normalize before zoning
**Evidence:** 3 of 3 SHORTLIST-expected tech-role mismatches scored 49.5–53.1,
all just under the global SHORTLIST cutoff of 55. The cutoff was calibrated
against a different, business-role-heavy sample in Day 15.
**Fix direction:** Day 15 already built `normalize_scores_batch()` for
exactly this cross-category comparability problem — `classify_zone()`
should run on normalized/percentile scores within a role category, or
`DEFAULT_THRESHOLDS` should become per-`role_category` (mirroring how
`WEIGHT_PROFILES` already varies by category). Either fixes all 3
SHORTLIST-recall misses in this test in one change.
**Owner note:** this is a one-file change (`ranking_engine.py`) but needs
a larger, better-labeled test set than these 12 pairs to calibrate
correctly — don't hand-tune to just these 3 cases.

### 2. Gate REVIEW/SHORTLIST on a skill-relevance floor
**Evidence:** resume_11 (Python/Django, zero MERN skills) scored 34.9 and
landed in REVIEW; resume_05 (HR) scored 27.6 against a sales JD and
landed in REVIEW; resume_08 (marketer) scored 25.4 against a BD JD and
landed in REVIEW. All three are clean-mismatch REJECTs by manual
judgment — `experience`/`education` credit for years/degree-level
independent of field relevance is propping up scores that should be low.
**Fix direction:** either (a) a hard floor — a resume with skill_match
below some threshold (e.g. 20/100) cannot classify above REJECT
regardless of other components, or (b) couple `experience_relevance`'s
scoring more tightly to skill overlap so irrelevant years earn less
credit. (a) is the smaller, safer change; (b) is more correct but
touches Day 10's scoring logic and needs its own test pass.

## P1 — Real gap, but not urgent

### 3. Senior/overqualified candidates are being under-shortlisted (0/2 in this test)
**Evidence:** resume_16 (6.5y) scored *lower* against jd_01 (49.5) than
resume_01 (3y) did against the same JD (50.3), despite having strictly
more of every required skill. Worth confirming `experience_relevance`
doesn't cap or taper credit for years above a JD's stated upper bound —
if it does, that's a real "penalizes seniority" bug, not just a
threshold issue like #1.
**Fix direction:** add a targeted test to `test_experience_relevance.py`
(not written today) that checks score behavior for years well above a
JD's upper bound — confirm it's flat or still-increasing, not
decreasing.

### 4. Larger, multi-reviewer ground truth set
**Evidence:** this test's conclusions rest on 12 pairs judged by one
reviewer. The *pattern* (systematic REVIEW bias) is well-supported by 7
consistent mismatches, but exact precision/recall numbers will shift
with more data, and a single reviewer's judgment isn't itself validated.
**Fix direction:** expand to 30–50 pairs across more roles, have a second
person independently judge a subset, measure inter-rater agreement
before trusting "expected_zone" as ground truth going forward.

## P2 — Worth doing, not blocking

### 5. Test `overall_score` correlation directly, not just the 3-way zone call
**Evidence:** none yet — this is a testing-methodology gap noted in the
report's limitations, not a finding from this run.
**Fix direction:** have reviewers assign a 0–100 fit score (not just a
zone) for a subset of pairs, measure correlation with `overall_score`
directly. Would catch miscalibration *within* a zone that the 3-way test
can't see.

### 6. Re-run this exact test after #1 and #2 land, before closing this backlog item
Once the threshold recalibration and skill-relevance gate are in, rerun
`run_day17_testing.py` against the same 12 pairs (plus ideally the
expanded set from #4) and confirm the two root causes are actually
resolved, not just symptom-patched. Regression risk: fixing #2 could
shift some currently-correct REVIEW classifications (e.g.
resume_12_partial_mern_match, resume_10_customer_support, both
currently correct) — watch those specifically when retesting.
