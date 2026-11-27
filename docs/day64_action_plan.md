# Day 64: Action Plan

Zecpath: AI Job Portal | Order of work after the internal review | Built 2026-11-23

## Assumptions

- **One developer** who knows the code does the work, in the order below. Effort is the author's estimate in working days.
- **Remaining internship time is not known to this plan** (tasks 65 to 70 are not described), so Wave 0 is sized to fit in a few days and the rest is written as a hand-over plan. The owner should move the wave boundaries to the time that exists.
- **Decisions come first.** Five items need an owner's decision (D1 to D6 in the report); they are named in the waves so they are not discovered halfway through.
- **Any change that alters scores needs a new golden file and a re-run of the demo dataset.** The Day 60 golden files exist to prove optimisations did not change answers; a deliberate behaviour change gets a new, labelled golden file, never a regenerated one.

## The plan in one line

Wave 0 makes changes safe, Wave 1 removes every way a candidate can get a wrong or unfair result, Wave 2 improves the scoring and the reports, and Wave 3 holds what needs data, policy or the backend. Total about 95.7 working days, of which Waves 0 and 1 are 20.2.

## Waves

### Wave 0: Quick wins (this week (each under a day))

**Goal.** Stop avoidable surprises and make every later change safer.

**Effort.** About 3.2 working days.

| Id | Item | Priority | Effort (days) | Depends on | Decision needed |
|---|---|---|---|---|---|
| ENG-01 | There is no automated test run on every push | P1 | 0.5 | - | - |
| ENG-04 | Line endings differ between machines | P1 | 0.25 | - | - |
| ACC-10 | 'Six months' is read as six years | P1 | 0.5 | - | - |
| UX-04 | A screening turn with no text is scored | P1 | 0.5 | - | - |
| UX-03 | Some error messages do not say what to do | P1 | 1.0 | - | - |
| PERF-02 | The first request pays an import cost | P1 | 0.5 | - | - |

**Exit criteria.** CI runs on 3.11 and 3.12; T9, T11 met; line endings stable.
### Wave 1: Correctness (weeks 1 to 4 (one developer))

**Goal.** Remove every way the system can give a candidate a wrong or unfair result.

**Effort.** About 17.0 working days.

| Id | Item | Priority | Effort (days) | Depends on | Decision needed |
|---|---|---|---|---|---|
| ACC-01 | Wrapped lines of the Skills section are dropped | P0 | 2.0 | - | - |
| ACC-02 | Nonsense answers earn a middling screening score | P0 | 3.0 | - | - |
| ACC-03 | Off-topic HR answers score 75 | P0 | 3.0 | - | - |
| ACC-04 | A resume without section headings is read as having no experience | P0 | 3.0 | - | - |
| ACC-05 | The raw ATS scale makes the round-disagreement rule fire for most candidates | P0 | 2.0 | - | Owner: change a default that alters results |
| UX-01 | Answers are matched to questions by position | P1 | 2.0 | - | - |
| ENG-02 | Engine code reads today's date | P0 | 2.0 | - | - |

**Exit criteria.** T1, T2, T3, T4, T6, T10 met on a fresh run of the review script; the demo dataset is re-run and its results re-read.
### Wave 2: Quality of scoring and reports (weeks 5 to 8 (one developer))

**Goal.** Better separation between candidates and reports a recruiter reads in a minute.

**Effort.** About 19.0 working days.

| Id | Item | Priority | Effort (days) | Depends on | Decision needed |
|---|---|---|---|---|---|
| ACC-06 | Skills the ATS does not know earn nothing | P1 | 3.0 | - | - |
| ACC-07 | Heading and bullet variants change the score | P1 | 2.0 | - | - |
| ACC-08 | Technical interview scoring may under-reward DevOps answers | P2 | 3.0 | - | - |
| ACC-09 | The screening score barely separates candidates | P1 | 3.0 | ACC-02 | - |
| ACC-11 | The technical tier counts years of any kind | P1 | 2.0 | - | - |
| UX-02 | Recruiter reports are long, and some lines are cut off | P1 | 2.0 | - | - |
| ENG-03 | The code standard is not followed or enforced | P1 | 1.0 | ENG-01 | Owner: enforce or relax the standard |
| ENG-05 | Some modules have no test file of their own | P2 | 2.0 | - | - |
| PERF-01 | PDF reading is the slowest part of the cheap stages | P1 | 1.0 | - | - |

**Exit criteria.** T5, T7, T8 met; style standard enforced in CI; coverage reported.
### Wave 3: Needs data, policy or the backend (after handover)

**Goal.** The items that cannot be finished inside this repository.

**Effort.** About 56.5 working days.

| Id | Item | Priority | Effort (days) | Depends on | Decision needed |
|---|---|---|---|---|---|
| ACC-12 | Nothing reads how long a candidate stays | P2 | 1.5 | - | Owner: is job-hopping a recruiter judgement or a system flag? |
| ACC-13 | Weights and thresholds are reasoned, not calibrated | P3 | 20.0 | - | - |
| ACC-14 | Machine tests exist only for Python | P3 | 10.0 | ENG-07 | - |
| ENG-07 | No sandbox exists for running candidate code | P3 | 10.0 | - | - |
| GOV-01 | Tenant isolation, storage and the gateway are designs, not systems | P3 | 10.0 | - | - |
| GOV-02 | No legal review of consent, retention or fairness | P2 | 5.0 | - | Owner: who commissions it |

**Exit criteria.** Decisions recorded (job-hopping policy, who owns calibration data, who commissions the legal review).

## How progress is tracked

1. Fix one item. Its acceptance line in the improvement list says when it is done.
2. Run `python run_day64_internal_review.py`. The acceptance targets (T1 to T11) show the current value of each measurement; 4 of 11 are met today.
3. Run `python run_day63_demo_dataset.py` and read which candidates moved. Update `data/demo_dataset/simulated/` by committing the new run.
4. Run the full test suite. A scoring change is expected to fail tests that pin the old behaviour; read why before editing a test.

## Risks

| Risk | Why it matters | What reduces it |
|---|---|---|
| Fixing one gap hides another | Scores interact: raising the ATS skill match changes who is shortlisted and how the disagreement rule fires. | Re-run the review and demo scripts after each change; change one thing at a time. |
| A fix changes results for real candidates | No real candidates are scored yet, but the weights will be used later. | Keep the change behind the golden-file process; record why each number changed. |
| Work finishes but is not seen | The probes only show what the data can show. | Hold the reviewer session in the kit and merge its feedback. |
| Estimates are wrong | Effort figures are one author's guesses. | Re-estimate after Wave 0; the first few items calibrate the rest. |

## Order of work, item by item

| Order | Wave | Id | Item | Priority |
|---|---|---|---|---|
| 1 | Wave 0 | ENG-01 | There is no automated test run on every push | P1 |
| 2 | Wave 0 | ENG-04 | Line endings differ between machines | P1 |
| 3 | Wave 0 | ACC-10 | 'Six months' is read as six years | P1 |
| 4 | Wave 0 | UX-04 | A screening turn with no text is scored | P1 |
| 5 | Wave 0 | UX-03 | Some error messages do not say what to do | P1 |
| 6 | Wave 0 | PERF-02 | The first request pays an import cost | P1 |
| 7 | Wave 1 | ACC-01 | Wrapped lines of the Skills section are dropped | P0 |
| 8 | Wave 1 | ACC-02 | Nonsense answers earn a middling screening score | P0 |
| 9 | Wave 1 | ACC-03 | Off-topic HR answers score 75 | P0 |
| 10 | Wave 1 | ACC-04 | A resume without section headings is read as having no experience | P0 |
| 11 | Wave 1 | ACC-05 | The raw ATS scale makes the round-disagreement rule fire for most candidates | P0 |
| 12 | Wave 1 | UX-01 | Answers are matched to questions by position | P1 |
| 13 | Wave 1 | ENG-02 | Engine code reads today's date | P0 |
| 14 | Wave 2 | ACC-06 | Skills the ATS does not know earn nothing | P1 |
| 15 | Wave 2 | ACC-07 | Heading and bullet variants change the score | P1 |
| 16 | Wave 2 | ACC-08 | Technical interview scoring may under-reward DevOps answers | P2 |
| 17 | Wave 2 | ACC-09 | The screening score barely separates candidates | P1 |
| 18 | Wave 2 | ACC-11 | The technical tier counts years of any kind | P1 |
| 19 | Wave 2 | UX-02 | Recruiter reports are long, and some lines are cut off | P1 |
| 20 | Wave 2 | ENG-03 | The code standard is not followed or enforced | P1 |
| 21 | Wave 2 | ENG-05 | Some modules have no test file of their own | P2 |
| 22 | Wave 2 | PERF-01 | PDF reading is the slowest part of the cheap stages | P1 |
| 23 | Wave 3 | ACC-12 | Nothing reads how long a candidate stays | P2 |
| 24 | Wave 3 | ACC-13 | Weights and thresholds are reasoned, not calibrated | P3 |
| 25 | Wave 3 | ACC-14 | Machine tests exist only for Python | P3 |
| 26 | Wave 3 | ENG-07 | No sandbox exists for running candidate code | P3 |
| 27 | Wave 3 | GOV-01 | Tenant isolation, storage and the gateway are designs, not systems | P3 |
| 28 | Wave 3 | GOV-02 | No legal review of consent, retention or fairness | P2 |
