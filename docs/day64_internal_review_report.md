# Day 64: Internal Review and System Walkthrough

Zecpath: AI Job Portal | Internal review report | Built 2026-11-23

## Objective

Evaluate the system internally and identify improvement areas.

**Headline.** The system is safe by construction and cheap to run, but it has accuracy gaps that can give a candidate a wrong result without any warning. The review found **28 improvements**: **6 at P0** (a candidate can get a wrong or unfair result), 14 at P1, 4 at P2 and 4 at P3. The most serious are that the same resume scores up to 17.4 points lower as a PDF than as a DOCX, that nonsense answers score 56.4 to 75.6 in the screening and HR rounds, and that a resume with no section headings is read as having no experience. None needs a redesign; the first 6 fit in about 15.0 working days.

**How to read this.** Every number is measured by a probe that runs on the real engines and the Day 63 demo dataset (`parsers/internal_review.py`); a test fails if this report and the probes disagree. Ratings, impact and effort are the author's judgement and are labelled so. **Reviewer feedback has not yet been collected: 0 entries are recorded.** Section 9 explains how to add it.

## 1. Scope and method

**Reviewed:** the AI layer in this repository (82 Python modules in the services, `parsers/` and `utils/`, including the Day 63 demo modules), end to end: ATS, screening, HR interview, technical interview, machine test and the decision, on 30 synthetic candidates.

**Not reviewed:** the backend, frontend, telephony, video, e-mail and payments (not in this repository); real speech; real candidates; legal compliance.

| Question | Probe | What it does |
|---|---|---|
| Does it work end to end? | Walkthrough | Traces five candidates through every stage with real outputs (section 2) |
| Is it accurate? | Expectation agreement, rank agreement, score spread, negative controls, file-format invariance, robustness to harmless edits, name swap | Section 4 |
| Is it usable? | Error-message audit, recruiter-report audit, API pitfalls | Section 5 |
| Is it fast? | Per-stage timings, resume reading by file type, ATS throughput, cold start | Section 6 |
| Is it maintainable? | Wall-clock reads, tests per module, CI, style-standard breaches, dependency pinning | Section 7 |

**A caution about the demo data.** The Day 63 expectations were written before the run, and the system met 24 of 30. Finding ACC-01 shows that the 10 PDF resumes in that dataset carry a wrapped-line penalty (a real system gap, but a confound when comparing the PDF and DOCX candidates). Day 63's results are kept as they were.

## 2. Walkthrough: ATS, Screening, HR, Technical, Decision

How to read each trace: the stages are the real engines run on the candidate's files; "Note" shows what a reviewer should notice. The candidates were chosen to show a clean path, a keyword-stuffed resume, an integrity flag, a formatting failure and a dropped call.

**DC-01: Aligned strong mid-level developer.** Expected selected; the system said **hold_review**.

| Stage | Input | Output | Note |
|---|---|---|---|
| ATS | DOCX resume, job 'Full Stack Developer (MERN)' | 62.0 -> shortlist | years parsed 4.7 |
| Screening | 7 turns, 7 categories answered | 93.7 | - |
| HR interview | 6 answers | 93.1 | - |
| Technical interview | tier intermediate, 5 answers | 77.0 | - |
| Machine test | 2 coding attempts | 97.0 (strong) | integrity clear |
| Decision | all round scores | hold_review, Hiring Fit 86.4, confidence 90.0 | The score (86.39%) would select this candidate, but selection is held for review because the aggregate score raised review flags: Rounds disagree strongly (machine_test 97 vs ats 62); an average hides |

**DC-04: Keyword-stuffed resume, shallow interviews.** Expected rejected / hold_review; the system said **rejected**.

| Stage | Input | Output | Note |
|---|---|---|---|
| ATS | DOCX resume, job 'Full Stack Developer (MERN)' | 58.1 -> shortlist | years parsed 1.8 |
| Screening | 8 turns, 7 categories answered | 85.1 | - |
| HR interview | 6 answers | 78.1 | - |
| Technical interview | tier basics, 5 answers | 27.0 | - |
| Machine test | 2 coding attempts | 3.0 (limited) | integrity clear |
| Decision | all round scores | rejected, Hiring Fit 38.9, confidence 66.8 | Hiring Fit 38.94% is below the hold threshold (50). |

**DC-09: Strong scores but repeated tab switching in the machine test.** Expected hold_review; the system said **hold_review**.

| Stage | Input | Output | Note |
|---|---|---|---|
| ATS | DOCX resume, job 'Full Stack Developer (MERN)' | 57.2 -> shortlist | years parsed 4.2 |
| Screening | 7 turns, 7 categories answered | 93.4 | - |
| HR interview | 6 answers | 89.1 | - |
| Technical interview | tier intermediate, 5 answers | 77.0 | - |
| Machine test | 2 coding attempts | 97.0 (strong) | integrity medium |
| Decision | all round scores | hold_review, Hiring Fit 85.1, confidence 70.9 | The score (85.08%) would select this candidate, but selection is held for review because the interview integrity tag is MEDIUM; the aggregate score raised review flags: Rounds disagree strongly (machi |

**DC-13: Good developer, resume without section headings.** Expected hold_review / selected; the system said **hold_review**.

| Stage | Input | Output | Note |
|---|---|---|---|
| ATS | DOCX resume, job 'Java Backend Developer' | 1.0 -> reject | years parsed 0.0 |
| Screening | 7 turns, 7 categories answered | 93.4 | - |
| HR interview | 6 answers | 89.0 | - |
| Technical interview | tier basics, 5 answers | 33.7 | - |
| Machine test | 2 coding attempts | 69.6 (moderate) | integrity clear |
| Decision | all round scores | hold_review, Hiring Fit 60.4, confidence 73.1 | Hiring Fit 60.41% is in the review band (50-70). |

**DC-30: The call drops after three questions.** Expected hold_review; the system said **hold_review**.

| Stage | Input | Output | Note |
|---|---|---|---|
| ATS | PDF resume, job 'HR Recruiter (Talent Acquisition)' | 57.1 -> shortlist | years parsed 3.2 |
| Screening | 3 turns, 3 categories answered | 43.6 | - |
| HR interview | 6 answers | 89.0 | - |
| Decision | all round scores | hold_review, Hiring Fit 74.2, confidence 55.2 | The score (74.22%) would select this candidate, but selection is held for review because the aggregate score raised review flags: Rounds disagree strongly (hr_interview 89 vs screening 43.6); an avera |

**What a reviewer should check at each stage**

| Stage | Look at | Ask |
|---|---|---|
| ATS | the four components, the zone and the years parsed | Does the score match how a recruiter would read this resume? Are skills missing because of wrapping or vocabulary? |
| Screening | answered categories, re-asks, the claimed years against the resume | Would a recruiter agree with the score? Could a weak answer be scored well? |
| HR interview | relevance, communication, confidence, consistency | Does the relevance score fall when the answer ignores the question? |
| Technical interview | the tier and the question set | Is the tier right for this person's real experience? |
| Machine test | task scores, flags, integrity tag | Do the flags match what you see in the code? |
| Decision | the outcome, confidence, reasons and rule flags | Is the 'hold' justified? Would you have chosen differently? |

## 3. Scorecard (author's judgement, 1 to 5)

| Area | Score | Why | Evidence |
|---|---|---|---|
| ATS (resume scoring) | 3 | Sound structure and explainable components, and it ignores personal details; but wrapped skill lines, unknown skills and heading variants cost real points (ACC-01, 04, 06, 07). | accuracy.format_invariance, robustness |
| Screening call | 2 | Good conversation flow and safe handling of dropped calls; but nonsense scores about 56 and real answers barely differ (ACC-02, 09, 10). | accuracy.negative_controls, score_spread |
| HR interview | 2 | Fair on fluent, relevant answers; off-topic answers score 75 (ACC-03). | accuracy.negative_controls |
| Technical interview | 3 | Separates candidates well (spread wide, strongest rank agreement with the final score) and rejects nonsense; order-dependence and domain balance need work (UX-01, ACC-08, ACC-11). | accuracy.negative_controls, rank_agreement |
| Machine test | 4 | Clear design, never runs candidate code, flags over-fitting and integrity; Python only (ACC-14). | walkthrough |
| Decision and aggregation | 3 | Safe by construction (no automated rejection, rules move toward review) but the disagreement rule is over-sensitive on the raw scale (ACC-05). | accuracy.round_disagreement_flagged |
| Governance and security | 3 | Rules, audit and consent logic are built and tested; nothing enforces them yet and a legal review is missing (GOV-01, 02). | carried from Days 55, 59 |
| Observability | 3 | A complete design and prototype; no shipper, store or alert manager. | Day 61 |
| Documentation | 4 | Handbook, architecture, onboarding and one document per day; generated numbers are tested. | Days 62, 63 |
| Tests and delivery | 3 | About 2,059 tests and golden files; but no CI, wall-clock dependence, and a style standard that is not enforced (ENG-01 to 05). | engineering |
| Performance | 4 | Scoring is cheap (a few milliseconds per stage); only first-request cost and PDF reading stand out (PERF-01, 02). | performance_measured |

## 4. Accuracy gaps

### 4.1 Did the system agree with the author?

24 of 30 demo candidates reached the expected outcome (written before the run; missed: DC-01, DC-10, DC-14, DC-21, DC-22, DC-26). Five of the six misses come from one cause: the raw ATS scale disagrees with 90-point interview scores (ACC-05).

### 4.2 Does each round rank candidates the way the final score does?

Spearman rank correlation between each round and the final Hiring Fit (1.0 = same order):

| Round | Rank agreement |
|---|---|
| ats | 0.63 |
| screening | 0.32 |
| hr | 0.63 |
| technical | 0.88 |
| machine_test | 0.9 |

The technical round and machine test carry 60 % of the weight for technical roles, so their high agreement is partly built in. The weakest is the screening round (0.32): it adds little to the order.

### 4.3 How far apart does each round put candidates?

| Round | n | Min | Max | Mean | Std |
|---|---|---|---|---|---|
| ats | 28 | 24.4 | 72.6 | 51.4 | 10.4 |
| screening | 29 | 85.1 | 95.0 | 92.1 | 2.5 |
| hr | 30 | 78.1 | 93.1 | 88.1 | 4.3 |
| technical | 16 | 11.9 | 77.0 | 48.7 | 23.2 |
| machine_test | 16 | 3.0 | 97.0 | 70.0 | 29.6 |
| hiring_fit | 30 | 38.9 | 86.4 | 72.9 | 13.3 |

Screening scores of completed calls span only 85.1 to 95.0.

### 4.4 ATS zone against final outcome

| ATS zone | Final outcomes |
|---|---|
| shortlist | hold_review 12, rejected 2, selected 3 |
| review | hold_review 10 |
| reject | hold_review 3 |

### 4.5 Negative controls: does nonsense ever score well?

| Input | Score | Expected |
|---|---|---|
| ATS: unrelated resume (a designer against the MERN job) | 20.3 | low is right |
| ATS: one-line resume | 0.1 | low is right |
| Screening: gibberish x7 | 56.4 | should be low |
| Screening: 'I do not know' x7 | 56.4 | should be low |
| Screening: off-topic x7 | 60.7 | should be low |
| HR: gibberish x6 | 33.9 | should be low |
| HR: 'Yes.' x6 | 33.8 | should be low |
| HR: off-topic x6 | 75.6 | should be low |
| Technical: gibberish x5 | 7.7 | should be low |
| Technical: 'I do not know' x5 | 8.9 | should be low |
| Technical: off-topic x5 | 12.9 | should be low |
| Machine test: broken code | 3.0 | should be low |

**Scores of 50 or more for nonsense: hr_off_topic, screening_dont_know, screening_gibberish, screening_off_topic.** A screening or HR score is only meaningful if an answer with no content cannot earn a middling one (ACC-02, ACC-03).

### 4.6 Is the score the same for the same resume in a different file type?

The same 30 resume texts, written once as DOCX and once as PDF and read back by the real upload path: **4 candidates differ by more than half a point** (DC-02, DC-04, DC-26, DC-30). The worst is DC-04 (58.1 as DOCX, 40.7 as PDF); the component responsible is skill_match. A PDF wraps long lines, as every real PDF does, and only the first line of the 'Skills:' line is read (ACC-01).

### 4.7 Do harmless edits change the score?

89 edits across 5 resumes (skill spellings, headings, formatting, dates, section order). Largest loss -33.9 points, largest gain 10.5. Edits that lose 3 or more points:

| Edit | Resume | Change | Years read |
|---|---|---|---|
| heading: Skills -> Technical Skills | DC-01 | -33.9 | 4.7 -> 4.7 |
| heading: Skills -> Core Competencies | DC-01 | -33.9 | 4.7 -> 4.7 |
| skill spelling: SFDC / cold-calling | DC-17 | -6.8 | 3.2 -> 3.2 |
| formatting: bullets '-' -> '*' | DC-22 | -6.3 | 4.1 -> 4.1 |
| skill spelling: Postgres / SpringBoot / RESTful | DC-01 | -4.6 | 4.7 -> 4.7 |

Date formats, case, blank lines and section order did not lose points; heading and bullet variants and unknown skill spellings did (ACC-06, ACC-07).

### 4.8 Fairness probes

Name swap: **0.0** points at most across 8 swaps. Demographic header (DC-28): 59.3 against 59.3. These probes cover the ATS round only; the interview rounds receive text that the transcript scrubber has already cleaned, and no bias audit on real data exists (GOV-02).

### 4.9 The decision rules

The round-disagreement rule is flagged for **24 of 30** candidates on the raw ATS scale and 10 on the common scale; 7 outcomes change between the two (ACC-05). A flag that fires for most candidates stops carrying information.

## 5. UX issues

This repository has no user interface; its surfaces are the API, its error messages and the recruiter report. The recruiter dashboard belongs to the frontend.

### 5.1 Error messages

25 malformed requests were sent to the five services. 21 were rejected with an error; 4 were answered 'not started' with no score (ScreeningService: empty payload; ScreeningService: no turns; ScreeningService: turn without text; InterviewIntelligenceService: empty payload); 0 was scored (). Messages that do not say what is accepted: 0. Errors that name no field: 0 () (UX-03, UX-04).

### 5.2 Recruiter reports

30 reports, 1019.0 to 1394.0 words (mean 1190.7); **30 are over 1,000 words**. 0 have a cut-off or unbalanced line in the summary, and 1042 escaped underscores (raw rule codes such as machine\_test) appear (UX-02).

### 5.3 API behaviour that surprises a caller

| Behaviour | Measured |
|---|---|
| Technical answers are matched to questions by position | the same five answers score 77.0 in order and 42.0 reordered |
| Screening turns are matched by position | reversed turns leave 3 categories missing and score 48.9 |
| A duration in months is read as years | 'six months' returns 0.5 |

## 6. Performance issues

Measured on one shared machine; compare stages with each other, not with another computer.

| Stage | n | Mean ms | Median ms | p95 ms | Max ms |
|---|---|---|---|---|---|
| upload | 30 | 9.5 | 8.1 | 16.8 | 18.2 |
| ats | 30 | 2.1 | 1.9 | 3.0 | 6.8 |
| screening | 30 | 1.9 | 1.7 | 4.7 | 6.6 |
| hr_interview | 30 | 3.1 | 2.9 | 4.7 | 5.3 |
| technical_interview | 16 | 0.2 | 0.2 | 0.4 | 0.4 |
| aggregation | 30 | 0.1 | 0.1 | 0.1 | 0.1 |
| decision | 30 | 0.0 | 0.0 | 0.1 | 0.1 |
| report | 30 | 0.4 | 0.3 | 0.6 | 4.0 |
| machine test, final aggregation and report | 30 | 38.0 | 13.9 | 75.8 | 693.0 |
| whole candidate | 30 | 55.4 | 29.7 | 93.7 | 713.8 |

- Resume reading: DOCX 5.8 ms, PDF 16.1 ms on average.
- ATS scoring: 90 resume-and-job pairs in 0.24 s on one process (377.4 a second).
- Cold start: the first ATS call in a fresh process takes 867 ms.
- **No performance bottleneck.** The stage with the largest mean (machine test, final aggregation and report) is dominated by one first-call import cost; its median is 13.9 ms. The Day 60 results (about 22 ms of compute per application, scaling by replicas) still describe the system (PERF-01, PERF-02).

## 7. Engineering and process

| Check | Result |
|---|---|
| Automated test run on every push | Yes |
| Engine reads of the wall clock | 9: ats_engine/resume_parsing_service.py:99 date.today(), ats_engine/resume_parsing_service.py:134 date.today(), parsers/audit_trail.py:116 datetime.now(), parsers/behavioral_signal_engine.py:129 time.monotonic(), ... |
| Lines over 100 characters (the written standard) | 3301 in 78 of 82 modules |
| print() calls in engine modules | 12 |
| Modules without a test file of their own name | 27 of 82 (some are covered by another file) |
| Dependencies pinned | 11 of 11 |
| Modules with a docstring | 82 of 82 |
| .gitattributes present | Yes |

Three Day 60 golden tests failed on 2026-11-22, and a fourth on 2026-11-26, although no code had changed: the ATS experience score counts years to 'Present', which means the day the test runs (ENG-02). A CI run on two Python versions would also have caught an f-string that fails only before Python 3.12 (ENG-01).

## 8. What works well

- No rejection is ever automatic: all 30 demo decisions finished with a person required for any rejection.
- Personal details do not move the ATS score: swapping names between candidates changes it by at most 0.0 points (8 swaps), and the demographic header changes it by 0.0.
- The technical interview and the machine test reject nonsense: gibberish, 'I do not know' and off-topic answers score 7.7, 8.9 and 12.9; broken code scores 3.0.
- 21 of 25 malformed requests get a named error rather than a crash, and 4 more are answered 'not started' with no score.
- Scoring is cheap: one ATS pair takes about 2.6 ms on a single process (377.4 pairs a second).
- A dropped call, a noisy line and a missing round are held for evidence, not rejected (DC-30: hold_review).
- An integrity tag stops an automatic selection; a missing round makes the result provisional.

## 9. Reviewer feedback

**0 entries recorded.** Day 64 asks for feedback from mentors and reviewers; it cannot be generated, so this report does not contain any. `docs/day64_review_session_kit.md` has a 45-minute agenda, the commands to show each stage, a feedback form and the format to record it in. Add each comment to `data/review/feedback_log.json`, run `python run_day64_internal_review.py`, and each becomes a triage item (FB-001, ...) in the improvement list and is counted here.

## 10. Prioritised summary

The full list is `docs/day64_improvement_list.md`; the order of work is `docs/day64_action_plan.md`.

| Id | Improvement | Priority | Score | Effort (days) |
|---|---|---|---|---|
| ACC-01 | Wrapped lines of the Skills section are dropped | P0 | 7.5 | 2.0 |
| ACC-02 | Nonsense answers earn a middling screening score | P0 | 5.0 | 3.0 |
| ACC-03 | Off-topic HR answers score 75 | P0 | 4.0 | 3.0 |
| ACC-04 | A resume without section headings is read as having no experience | P0 | 5.0 | 3.0 |
| ACC-05 | The raw ATS scale makes the round-disagreement rule fire for most candidates | P0 | 6.0 | 2.0 |
| ENG-02 | Engine code reads today's date | P0 | 6.0 | 2.0 |
| ACC-06 | Skills the ATS does not know earn nothing | P1 | 4.0 | 3.0 |
| ACC-07 | Heading and bullet variants change the score | P1 | 4.5 | 2.0 |
| ACC-09 | The screening score barely separates candidates | P1 | 3.0 | 3.0 |
| ACC-10 | 'Six months' is read as six years | P1 | 18.0 | 0.5 |
| ACC-11 | The technical tier counts years of any kind | P1 | 3.0 | 2.0 |
| UX-01 | Answers are matched to questions by position | P1 | 6.0 | 2.0 |

**Decisions requested**

| No. | Decision | Why |
|---|---|---|
| D1 | Make the common ATS scale the default (ACC-05)? | It changes outcomes: 7 of the 30 demo candidates move from hold to selected. It needs a new golden file and an owner's approval. |
| D2 | When an answer has no relevant content, score it low or mark it 'needs review' (ACC-02, 03)? | Both stop nonsense scoring well; 'needs review' keeps the human in the loop for a noisy line. |
| D3 | Adopt CI on every push (ENG-01)? | It would have caught two of this week's problems. |
| D4 | Enforce the 100-character standard or relax it (ENG-03)? | The code breaches it in most modules. |
| D5 | Is job-hopping a recruiter judgement or a system flag (ACC-12)? | A policy choice with fairness implications. |
| D6 | Who owns the labelled outcomes needed for calibration (ACC-13)? | Without them no weight can be defended. |

**Acceptance targets today:** 4 of 11 met. Re-run `python run_day64_internal_review.py` after each fix to see them change.

## 11. Limits of this review

- **Probes find what data can show.** They cannot say whether a weight is right: no labelled outcomes exist.
- **The demo dataset is synthetic and small** (30 candidates); the negative controls and edits are a handful of cases, not a test set.
- **Impact, confidence and effort are estimates** by the author. Effort is in working days for one developer who knows the code.
- **No second person has reviewed this report**, and no reviewer feedback is in it yet.
- **Timings are from one machine.** Trust the ranking of stages, not the milliseconds.
- **UX is judged from the API and the report only.** Nothing was tested with a recruiter.
