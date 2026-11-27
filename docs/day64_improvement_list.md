# Day 64: Improvement List

Zecpath: AI Job Portal | Prioritised improvements from the internal review | Built 2026-11-23

## How items are ranked

```
priority score = impact x confidence / effort
impact 1-5 | confidence 1-3 | effort in working days (one developer who knows the code)
P0  the system can give a candidate a wrong or unfair result (harm) and impact is 4 or 5
P1  score 3.0 or more     P2  1.5 or more     P3  below 1.5
GATE  must be done before any real candidate data is used, whatever the score
```

Impact, confidence and effort are the author's estimates. The formula makes the reasoning visible; it does not make it correct. A large item scores low because it is large, which is why three items are marked GATE. Every problem statement quotes a number measured by `parsers/internal_review.py`; `data/review/day64_improvement_list.json` and `.csv` hold the same list.

## The list

28 items: 6 P0, 14 P1, 4 P2, 4 P3.

| Id | Area | Improvement | Priority | Score | Impact | Conf. | Effort (days) |
|---|---|---|---|---|---|---|---|
| ACC-01 | accuracy | Wrapped lines of the Skills section are dropped | P0 | 7.5 | 5 | 3 | 2.0 |
| ACC-05 | accuracy | The raw ATS scale makes the round-disagreement rule fire for most candidates | P0 | 6.0 | 4 | 3 | 2.0 |
| ENG-02 | engineering | Engine code reads today's date | P0 | 6.0 | 4 | 3 | 2.0 |
| ACC-02 | accuracy | Nonsense answers earn a middling screening score | P0 | 5.0 | 5 | 3 | 3.0 |
| ACC-04 | accuracy | A resume without section headings is read as having no experience | P0 | 5.0 | 5 | 3 | 3.0 |
| ACC-03 | accuracy | Off-topic HR answers score 75 | P0 | 4.0 | 4 | 3 | 3.0 |
| ENG-01 | engineering | There is no automated test run on every push | P1 | 24.0 | 4 | 3 | 0.5 |
| ENG-04 | engineering | Line endings differ between machines | P1 | 24.0 | 2 | 3 | 0.25 |
| ACC-10 | accuracy | 'Six months' is read as six years | P1 | 18.0 | 3 | 3 | 0.5 |
| PERF-02 | performance | The first request pays an import cost | P1 | 12.0 | 2 | 3 | 0.5 |
| UX-04 | ux | A screening turn with no text is scored | P1 | 12.0 | 2 | 3 | 0.5 |
| ENG-03 | engineering | The code standard is not followed or enforced | P1 | 6.0 | 2 | 3 | 1.0 |
| UX-01 | ux | Answers are matched to questions by position | P1 | 6.0 | 4 | 3 | 2.0 |
| UX-03 | ux | Some error messages do not say what to do | P1 | 6.0 | 2 | 3 | 1.0 |
| ACC-07 | accuracy | Heading and bullet variants change the score | P1 | 4.5 | 3 | 3 | 2.0 |
| UX-02 | ux | Recruiter reports are long, and some lines are cut off | P1 | 4.5 | 3 | 3 | 2.0 |
| ACC-06 | accuracy | Skills the ATS does not know earn nothing | P1 | 4.0 | 4 | 3 | 3.0 |
| PERF-01 | performance | PDF reading is the slowest part of the cheap stages | P1 | 4.0 | 2 | 2 | 1.0 |
| ACC-09 | accuracy | The screening score barely separates candidates | P1 | 3.0 | 3 | 3 | 3.0 |
| ACC-11 | accuracy | The technical tier counts years of any kind | P1 | 3.0 | 3 | 2 | 2.0 |
| ACC-08 | accuracy | Technical interview scoring may under-reward DevOps answers | P2 | 2.7 | 4 | 2 | 3.0 |
| ACC-12 | accuracy | Nothing reads how long a candidate stays | P2 | 2.7 | 2 | 2 | 1.5 |
| GOV-02 | governance | No legal review of consent, retention or fairness | P2 GATE | 2.4 | 4 | 3 | 5.0 |
| ENG-05 | engineering | Some modules have no test file of their own | P2 | 2.0 | 2 | 2 | 2.0 |
| GOV-01 | governance | Tenant isolation, storage and the gateway are designs, not systems | P3 GATE | 1.2 | 4 | 3 | 10.0 |
| ACC-14 | accuracy | Machine tests exist only for Python | P3 | 0.9 | 3 | 3 | 10.0 |
| ENG-07 | engineering | No sandbox exists for running candidate code | P3 | 0.9 | 3 | 3 | 10.0 |
| ACC-13 | accuracy | Weights and thresholds are reasoned, not calibrated | P3 GATE | 0.8 | 5 | 3 | 20.0 |

## Acceptance targets

A target is a measurement the review script already makes. When it is met, the improvement is done; re-run `python run_day64_internal_review.py` to see the current value.

| Target | Improvement | Goal | Now | Needs | Unit | Met |
|---|---|---|---|---|---|---|
| T1 | ACC-01 | DOCX and PDF of the same resume differ by at most 0.5 point | 4 | <= 0 | candidates differing | open |
| T2 | ACC-02 | No screening negative control scores 40 or more | 3 | <= 0 | controls at 40 or more | open |
| T3 | ACC-03 | No HR negative control scores 40 or more | 1 | <= 0 | controls at 40 or more | open |
| T4 | ACC-05 | Round disagreement is flagged for fewer than half the candidates | 24 | < 15.0 | candidates flagged | open |
| T5 | ACC-06/07 | No harmless edit loses 3 or more points | 5 | <= 0 | edits losing points | open |
| T6 | UX-01 | Reordered technical answers keep their score | 35.0 | <= 0 | points of difference | open |
| T7 | UX-02 | No report has a cut-off summary line | 0 | <= 0 | reports affected | yes |
| T8 | UX-03 | Every error message says what is allowed and names a field | 0 | <= 0 | messages to fix | yes |
| T9 | ACC-10 | 'Six months' reads as 0.5 years | 0.5 | == 0.5 | years returned | yes |
| T10 | ENG-02 | Engine modules read the clock in at most one place | 9 | <= 1 | reads | open |
| T11 | ENG-01 | A CI workflow exists | 1 | == 1 | 1 = present | yes |

## Items in detail


### ACC-01: Wrapped lines of the Skills section are dropped

**P0** | area accuracy | impact 5 | confidence 3 | effort 2.0 days | score 7.5 | harm

**Problem.** The same resume as DOCX and as PDF differs by more than half a point for 4 of 30 candidates (DC-02, DC-04, DC-26, DC-30); the worst is DC-04 (-17.4 points, skill_match -50.0). A PDF wraps long lines, and only the first line of the 'Skills:' line is read. Every real PDF wraps. The Day 63 PDF candidates carry this penalty.

**Fix.** Treat the lines that follow a section heading, up to the next heading, as part of that section; join wrapped lines before skill extraction.

**Done when.** format_invariance: no candidate differs by more than 0.5 point between DOCX and PDF

**Roadmap link (Day 58).** C1


### ACC-05: The raw ATS scale makes the round-disagreement rule fire for most candidates

**P0** | area accuracy | impact 4 | confidence 3 | effort 2.0 days | score 6.0 | harm

**Problem.** 7 of 30 outcomes change when the ATS round is put on the common scale (ats_scale='zone_aligned'); 7 candidates move from hold_review to selected. By default the ATS scores here run from 24.4 to 72.6 while most interview scores are 80 or more, so the round-disagreement rule trips. The rule is flagged for 24 of 30 candidates on the raw scale and 10 on the common scale.

**Fix.** Make the common scale the default (ats_scale='zone_aligned'), then re-check the disagreement threshold on the demo set; record a new golden file for the change.

**Done when.** round_disagreement_flagged is below half of the candidates

**Decision needed.** Owner: change a default that alters results


### ENG-02: Engine code reads today's date

**P0** | area engineering | impact 4 | confidence 3 | effort 2.0 days | score 6.0 | harm

**Problem.** 9 reads of the wall clock in engine modules (ats_engine/resume_parsing_service.py:99 date.today(), ats_engine/resume_parsing_service.py:134 date.today(), parsers/audit_trail.py:116 datetime.now(), ...). The ATS experience score therefore changes with the day, which broke three Day 60 tests on 2026-11-22 and a fourth on 2026-11-26 (the first fix pinned the date in only three of the four tests that use the golden ATS outputs).

**Fix.** Pass an as_of date through every API that needs one, defaulting to the date only at the outermost call; add a test that runs the engines under two different dates.

**Done when.** engine modules read the clock only in one function


### ACC-02: Nonsense answers earn a middling screening score

**P0** | area accuracy | impact 5 | confidence 3 | effort 3.0 days | score 5.0 | harm

**Problem.** Seven answers of 'asdf qwer zxcv' score 56.4; 'I do not know' scores 56.4; seven off-topic sentences score 60.7. The engine counts a turn as an answer to the question asked even when it contains nothing relevant.

**Fix.** Gate each answer on content: require the expected kind of value or at least one topic term; otherwise mark the turn 'needs review' and leave it out of the score.

**Done when.** negative_controls: every screening control scores below 40, or the call is marked incomplete


### ACC-04: A resume without section headings is read as having no experience

**P0** | area accuracy | impact 5 | confidence 3 | effort 3.0 days | score 5.0 | harm

**Problem.** DC-13 (3.5 years on the resume) parses to 0.0 years and an ATS score of 1.0 (reject); DC-25 (3.0 years on the resume) parses to 0.0 years and an ATS score of 1.1 (reject). DC-13 is then asked the 'basics' technical questions.

**Fix.** When the text is long but no section is found, infer sections from dates and job-title patterns; if that fails, send the resume to review instead of scoring it.

**Done when.** robustness: a headingless resume keeps its years and scores within 10 points of the same resume with headings

**Roadmap link (Day 58).** C1


### ACC-03: Off-topic HR answers score 75

**P0** | area accuracy | impact 4 | confidence 3 | effort 3.0 days | score 4.0 | harm

**Problem.** Six sentences about pizza and cricket score 75.6 on the HR round (relevance is held near 60, confidence 100 because nothing hesitates); gibberish scores 33.9 and 'Yes.' scores 33.8.

**Fix.** Remove the relevance floor; add an off-topic check against the question; do not award confidence to an answer with no content.

**Done when.** negative_controls: every HR control scores below 40


### ENG-01: There is no automated test run on every push

**P1** | area engineering | impact 4 | confidence 3 | effort 0.5 days | score 24.0

**Problem.** A workflow exists. Two problems this week would have been caught by one: an f-string that only fails before Python 3.12, and three golden tests that failed because the calendar moved.

**Fix.** Add a GitHub Actions workflow that runs pytest on Python 3.11 and 3.12 for every push.

**Done when.** a push runs the suite on both versions


### ENG-04: Line endings differ between machines

**P1** | area engineering | impact 2 | confidence 3 | effort 0.25 days | score 24.0

**Problem.** Day 64 measured 0 .gitattributes files and 7 files listed as modified for line endings only. Fixed on Day 65: .gitattributes exists (* text=auto) and the dataset test compares files without regard to line endings.

**Fix.** Add `* text=auto` and normalise once.

**Done when.** git status shows no changes that are line endings only


### ACC-10: 'Six months' is read as six years

**P1** | area accuracy | impact 3 | confidence 3 | effort 0.5 days | score 18.0 | harm

**Problem.** extract_experience_years('I have six months of internship experience') returns 0.5.

**Fix.** Read the unit that follows the number: months divide by 12.

**Done when.** the function returns 0.5


### PERF-02: The first request pays an import cost

**P1** | area performance | impact 2 | confidence 3 | effort 0.5 days | score 12.0

**Problem.** The first ATS call in a fresh process takes 867 ms; the first candidate's machine-test and report stage takes 693.0 ms against a median of about 20 ms.

**Fix.** Add the machine-test, aggregation and report modules to utils.warmup.warm_up().

**Done when.** first-candidate stage within 3 times the median


### UX-04: A screening turn with no text is scored

**P1** | area ux | impact 2 | confidence 3 | effort 0.5 days | score 12.0

**Problem.** Day 64 measured 1 of 25 malformed requests accepted and scored (a turn with no text scored 13.6). Fixed on Day 65: it is now read as silence and the call returns no score.

**Fix.** Reject a turn with no text with a named field.

**Done when.** accepted_and_scored is empty


### ENG-03: The code standard is not followed or enforced

**P1** | area engineering | impact 2 | confidence 3 | effort 1.0 days | score 6.0

**Problem.** 3301 lines over 100 characters in 78 of 82 modules, and 12 print() calls in engine modules, although docs/CODE_STANDARDS.md says otherwise.

**Fix.** Either enforce the standard (flake8 and black in CI, fix the print calls) or change it to a limit the code already meets.

**Done when.** CI runs flake8 with the chosen limit and passes

**Decision needed.** Owner: enforce or relax the standard

**Depends on.** ENG-01


### UX-01: Answers are matched to questions by position

**P1** | area ux | impact 4 | confidence 3 | effort 2.0 days | score 6.0

**Problem.** The same five technical answers score 77.0 in the order asked and 42.0 when sent in a different order; screening turns sent in reverse leave 3 categories missing and score 48.9.

**Fix.** Accept a question id with each answer and match by id; keep position as a fallback with a warning.

**Done when.** reordering answers that carry ids does not change the score


### UX-03: Some error messages do not say what to do

**P1** | area ux | impact 2 | confidence 3 | effort 1.0 days | score 6.0

**Problem.** Of 25 malformed requests, 21 get an error; 0 messages do not say what is allowed or what to send, and 0 name no field ().

**Fix.** Give every message the field, what was received and what is accepted.

**Done when.** error_not_actionable and error_without_field are empty


### ACC-07: Heading and bullet variants change the score

**P1** | area accuracy | impact 3 | confidence 3 | effort 2.0 days | score 4.5

**Problem.** Harmless edits that lose 3 or more points: heading: Skills -> Technical Skills on DC-01 (-33.9); heading: Skills -> Core Competencies on DC-01 (-33.9); formatting: bullets '-' -> '*' on DC-22 (-6.3).

**Fix.** Accept common heading synonyms (Technical Skills, Core Competencies) inline and on their own line; accept '*' and '•' bullets.

**Done when.** robustness: no heading or bullet variant loses 3 or more points


### UX-02: Recruiter reports are long, and some lines are cut off

**P1** | area ux | impact 3 | confidence 3 | effort 2.0 days | score 4.5

**Problem.** All 30 reports run from 1019.0 to 1394.0 words (mean 1190.7); 0 have a cut-off or unbalanced line in the summary; 1042 escaped underscores show raw rule codes such as machine\_test.

**Fix.** Put a one-page summary first; cut text at sentence ends; show plain-language rule names; render underscores properly.

**Done when.** reports_with_cut_off_summary_lines is 0 and the summary fits one page


### ACC-06: Skills the ATS does not know earn nothing

**P1** | area accuracy | impact 4 | confidence 3 | effort 3.0 days | score 4.0

**Problem.** DC-15 (Ansible, Helm, Prometheus, Grafana) gets a skill-match of 50.0 and ATS 39.0 (review) while DC-14 (Terraform, Jenkins, AWS) gets 100.0 and 72.6; their technical interviews score 56.0 and 56.0. Spelling variants lose points: SFDC / cold-calling (-6.8); Postgres / SpringBoot / RESTful (-4.6).

**Fix.** Add the common aliases at once (a day's work), then widen the 72-skill vocabulary by domain with a review of each addition.

**Done when.** robustness: no skill-spelling variant loses 3 or more points; DC-15's skill match rises


### PERF-01: PDF reading is the slowest part of the cheap stages

**P1** | area performance | impact 2 | confidence 2 | effort 1.0 days | score 4.0

**Problem.** Resume reading takes 16.1 ms for a PDF and 5.8 ms for a DOCX (measured here); scoring one ATS pair takes about 2.6 ms.

**Fix.** Cache extracted text by file hash (the parse cache from Day 60 already exists) and read pages in one pass.

**Done when.** a repeated PDF read takes under 5 ms


### ACC-09: The screening score barely separates candidates

**P1** | area accuracy | impact 3 | confidence 3 | effort 3.0 days | score 3.0

**Problem.** Across the 29 candidates whose call completed, screening scores range only from 85.1 to 95.0; a candidate who answered vaguely and was re-asked scores close to one who answered well. Its rank agreement with the final Hiring Fit is 0.32, against 0.88 for the technical round.

**Fix.** Give a re-asked answer less credit than a first answer; score completeness and specificity, not only presence.

**Done when.** score spread among completed calls is at least 25 points

**Depends on.** ACC-02


### ACC-11: The technical tier counts years of any kind

**P1** | area accuracy | impact 3 | confidence 2 | effort 2.0 days | score 3.0

**Problem.** DC-05 has two development years after four in QA and is asked the 'advanced' questions, because the tier comes from total years.

**Fix.** Derive the tier from years in relevant roles (the experience-relevance module already scores relevance).

**Done when.** DC-05 receives the intermediate tier


### ACC-08: Technical interview scoring may under-reward DevOps answers

**P2** | area accuracy | impact 4 | confidence 2 | effort 3.0 days | score 2.7

**Problem.** Candidates whose answers were all written at the 'strong' level score on the technical round: devops 56.0 (n=2), java 75.7 (n=2), mern 74.2 (n=4); the key-concept lists differ by domain, so equal-quality answers do not score alike.

**Fix.** Review the key-concept lists of each domain and tier with a subject expert; add a test that equal-quality answers across domains score within 10 points.

**Done when.** strong answers in every domain score within 10 points of each other

**Roadmap link (Day 58).** F2


### ACC-12: Nothing reads how long a candidate stays

**P2** | area accuracy | impact 2 | confidence 2 | effort 1.5 days | score 2.7

**Problem.** DC-21 has five employers in four years and is selected (Hiring Fit 83.6), like a candidate with a stable history.

**Fix.** Add an informational flag (never a score) for several short tenures, shown to the recruiter; decide the policy first.

**Done when.** a flag appears for DC-21 and is not used in the score

**Decision needed.** Owner: is job-hopping a recruiter judgement or a system flag?


### GOV-02: No legal review of consent, retention or fairness

**P2** | area governance | impact 4 | confidence 3 | effort 5.0 days | score 2.4 | GATE before real use

**Problem.** Retention periods and consent rules are proposed defaults; no bias audit exists on real data.

**Fix.** Commission a legal review and a bias audit before real use.

**Done when.** a written review exists

**Roadmap link (Day 58).** F6, S4

**Decision needed.** Owner: who commissions it


### ENG-05: Some modules have no test file of their own

**P2** | area engineering | impact 2 | confidence 2 | effort 2.0 days | score 2.0

**Problem.** 27 of 82 modules have no test file named after them (some are covered by another file, for example the batch and parsing services).

**Fix.** Measure coverage with pytest-cov and add tests where a module is not exercised.

**Done when.** a coverage report is produced in CI


### GOV-01: Tenant isolation, storage and the gateway are designs, not systems

**P3** | area governance | impact 4 | confidence 3 | effort 10.0 days | score 1.2 | GATE before real use

**Problem.** Carried forward from Days 55 and 59: gaps G1 to G3 (role matrix, job store, tenant isolation for the service role), no gateway, queue or job store.

**Fix.** Build or choose the gateway and job store; fix G1 to G3 before any real data enters.

**Done when.** an authenticated request reaches a service through the gateway

**Roadmap link (Day 58).** F1, F4, F7


### ACC-14: Machine tests exist only for Python

**P3** | area accuracy | impact 3 | confidence 3 | effort 10.0 days | score 0.9

**Problem.** JavaScript and Java candidates are given Python tasks; static code analysis reads Python only.

**Fix.** Add task variants and a runner per language in a real sandbox.

**Done when.** a JavaScript task is scored for a MERN candidate

**Roadmap link (Day 58).** S2

**Depends on.** ENG-07


### ENG-07: No sandbox exists for running candidate code

**P3** | area engineering | impact 3 | confidence 3 | effort 10.0 days | score 0.9

**Problem.** The machine-test engine never runs code (by design); real results need a runner.

**Fix.** Design a container or microVM runner with no network and hard limits before any code runs.

**Done when.** a sandbox design is reviewed

**Roadmap link (Day 58).** S2


### ACC-13: Weights and thresholds are reasoned, not calibrated

**P3** | area accuracy | impact 5 | confidence 3 | effort 20.0 days | score 0.8 | GATE before real use

**Problem.** No labelled hiring outcomes exist, so no weight, cutoff or confidence figure can be checked against reality; 12 labelled ATS pairs are the only human ratings.

**Fix.** Start recording recruiter decisions and outcomes; run the evaluation harness on them before changing any weight.

**Done when.** at least 200 labelled candidates and a calibration report

**Roadmap link (Day 58).** F2, F3

