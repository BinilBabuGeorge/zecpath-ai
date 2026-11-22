# Day 63: Demo Dataset Creation

Zecpath: AI Job Portal | Demo dataset, end-to-end simulation environment and test candidate profiles | Built 2026-11-21

## Objective

Prepare realistic data to demonstrate full system functionality.

**Headline.** There is now a synthetic demo dataset of 6 job descriptions and 30 candidates, with resumes of varied quality as real DOCX and PDF files, what each candidate says and types in every round, and machine-test attempts and browser events. An end-to-end environment runs all 30 through the **real** engines (ATS, screening, HR interview, technical interview, machine test, integrity check, Hiring Fit Score, recommendation, recruiter report) with no errors. The system produced the outcome the author expected for **24 of 30** candidates; the other 6 are explained below, and several are real findings about the system.

**How to read this.** Everything is invented: no real person, employer or contact detail is in the data. The ATS results, screening outputs, interview scores and decisions are **not typed in**; they are produced by running this repository's engines on the dataset's inputs. The author's expected outcomes were written down **before** the run and are reported as design intent, not as truth.

## 1. What the brief asked, and what was built

| Brief item | What was done | Where |
|---|---|---|
| Create sample resumes (varied quality) | 30 resumes as DOCX (20) and PDF (10): excellent, good, average and poor (keyword-stuffed, minimal, no section headings, typos, a demographic header); plus the same text as .txt | `data/demo_dataset/resumes/`, `resumes_text/` |
| Create sample job descriptions | 6 job descriptions across 3 technical and 3 non-technical roles, written in the format the JD parser reads | `data/demo_dataset/jobs/` |
| Create sample candidate responses | Screening answers (7 per candidate), HR answers (6), technical answers (5, by domain and tier), machine-test attempts and browser events | `responses/`, `machine_test/`, `integrity/` |
| Simulate ATS results, screening outputs, interview responses | Produced by the real engines: ATS score and components, screening scores, HR and technical scores, machine-test reports | `simulated/ats_results.json`, `screening_outputs.json`, `interview_results.json`, `machine_test_results.json` |
| Prepare complete hiring pipeline data | One row per candidate with every round, the Hiring Fit Score, the recommendation, flags and a recruiter report each | `simulated/pipeline_results.csv` and `.json`, `simulated/reports/DC-*.md` |
| Ensure demo reflects real-world scenarios | 30 different scenarios (see section 3): career change, gap, job hopping, over-qualification, inflated claims, dropped call, noisy line, integrity flag, fairness probe, bad formatting | `candidates.json` |
| Deliverable: Demo dataset | `data/demo_dataset/` with a dataset card | `data/demo_dataset/README.md` |
| Deliverable: End-to-end simulation environment | `parsers/demo_environment.py` and `run_day63_demo_dataset.py` | section 5 |
| Deliverable: Test candidate profiles | 30 profiles with scenario, resume quality, expected outcome and the reason | section 3, `candidates.json` |

## 2. What is in the dataset

```
data/demo_dataset/
  README.md              dataset card
  manifest.json          counts and checksums of the text resumes
  candidates.json        30 candidate records (scenario, resume file, expected outcome and why)
  jobs/                  6 job descriptions + jobs.json
  resumes/               30 resumes (20 DOCX, 10 PDF), the real upload formats
  resumes_text/          the same 30 as plain text
  edge_files/            4 files the upload path must refuse (corrupt PDF, empty DOCX, legacy .doc, image)
  responses/             screening, HR and technical answers
  machine_test/          2 coding tasks and 32 attempts (code snapshots + execution results)
  integrity/             browser events (tab and focus changes)
  simulated/             RESULTS of running the real engines (written by the run)
```

### The six jobs

| Id | Title | Role type | Interview domain | Candidates |
|---|---|---|---|---|
| JOB-01 | Full Stack Developer (MERN) | technical | mern | 9 |
| JOB-02 | Java Backend Developer | technical | java | 4 |
| JOB-03 | DevOps Engineer | technical | devops | 3 |
| JOB-04 | Sales Executive (B2B SaaS) | non-technical | - | 5 |
| JOB-05 | UI/UX Designer | non-technical | - | 4 |
| JOB-06 | HR Recruiter (Talent Acquisition) | non-technical | - | 5 |

## 3. The 30 test candidate profiles

Candidates are called `DC-01` to `DC-30` and carry invented names. **Expected** is what the author thought the system should conclude, written before the first run; **why** says what the author was testing.

| Id | Name | Job | Scenario | Resume quality | File | Expected | Why |
|---|---|---|---|---|---|---|---|
| DC-01 | Priya Menon | MERN | Aligned strong mid-level developer | excellent | DOCX | selected | consistent, specific evidence in every round; the resume and the call agree |
| DC-02 | Arjun Verma | MERN | Senior tech lead, over the 3-6 year band | excellent | PDF | selected / hold_review | strong evidence; salary and seniority above the posted band justify a human look |
| DC-03 | Sneha Kulkarni | MERN | Fresher with good projects | good | DOCX | hold_review / rejected | relevant skills but too little experience for a 3-6 year role; a human should decide |
| DC-04 | Rahul Desai | MERN | Keyword-stuffed resume, shallow interviews | poor (keyword stuffing) | DOCX | rejected / hold_review | the resume lists everything; the interviews cannot back it up |
| DC-05 | Ishaan Qureshi | MERN | Career changer from manual QA | average | PDF | hold_review | real but partial match: the total years are high, relevant development years are about two |
| DC-06 | Divya Pillai | MERN | Strong Python backend developer, wrong stack | good | DOCX | hold_review / rejected | a strong engineer in a different stack; the ATS should not shortlist, a human may still see value |
| DC-07 | Karthik Subramanian | MERN | Inflater: says 5 years in the call, resume shows about 2.5 | average | DOCX | hold_review | the call and the resume disagree about experience; a human must resolve it |
| DC-08 | Anjali Bhatt | MERN | Technically strong but nervous speaker | good | PDF | selected / hold_review | strong skills; hesitant delivery should not sink an otherwise strong profile |
| DC-09 | Vikram Singh | MERN | Strong scores but repeated tab switching in the machine test | good | DOCX | hold_review | scores are strong, but the integrity tag blocks an automatic selection and asks for a human review |
| DC-10 | Nikhil Joshi | Java | Aligned strong Java developer | excellent | DOCX | selected | consistent, specific evidence in every round |
| DC-11 | Farhan Sheikh | Java | Right keywords, shallow depth | average | DOCX | hold_review / rejected | the resume matches the keywords; the interviews show limited depth |
| DC-12 | Lakshmi Iyer | Java | Strong developer with a 14-month career gap | good | PDF | selected / hold_review | the gap should not count against strong evidence; a human may want to ask about it |
| DC-13 | Tarun Mehta | Java | Good developer, resume without section headings | poor (formatting) | DOCX | hold_review / selected | a formatting problem on the resume should not hide a competent developer |
| DC-14 | Aditya Rao | DevOps | Aligned strong DevOps engineer | excellent | DOCX | selected | consistent, specific evidence in every round |
| DC-15 | Pooja Hegde | DevOps | Competent engineer whose tools the ATS vocabulary does not know | good | DOCX | hold_review / selected | a good fit whose strongest tools (Ansible, Helm, Prometheus) are not in the ATS vocabulary |
| DC-16 | Manoj Pandey | DevOps | System administrator moving to cloud | average | PDF | hold_review / rejected | strong Linux base; the cloud and infrastructure-as-code requirements are only partly met |
| DC-17 | Neha Kapoor | Sales | Aligned strong B2B SaaS seller | excellent | DOCX | selected | consistent, specific evidence in every round |
| DC-18 | Sameer Khan | Sales | Average, generic seller | average | PDF | hold_review / rejected | relevant basics, no evidence of B2B software selling or standout results |
| DC-19 | Riya Sharma | Sales | MBA fresher | good | DOCX | hold_review / rejected | promising fresher for a 2-4 year role; below the experience band |
| DC-20 | Ajay Thomas | Sales | Mismatch: HR executive applying for a sales role | good | DOCX | rejected / hold_review | no sales evidence; good communication does not replace the required skills |
| DC-21 | Gaurav Malik | Sales | Frequent job changes, confident talker | average | PDF | hold_review | relevant skills and a strong talker, but five roles in four years need a human conversation |
| DC-22 | Kavya Reddy | UX | Aligned strong product designer | excellent | DOCX | selected | consistent, specific evidence in every round |
| DC-23 | Dev Patel | UX | Thin resume, generic answers | poor (minimal) | DOCX | rejected / hold_review | the resume and the answers give little evidence of product design work |
| DC-24 | Shreya Banerjee | UX | Strong designer returning after a two-year break | good | PDF | selected / hold_review | the gap should not count against strong evidence; a human may want to ask about it |
| DC-25 | Omar Siddiqui | UX | Capable designer, careless resume (typos, no headings) | poor (typos) | DOCX | hold_review / selected | typos on a resume are a signal for a recruiter to read, not a reason to reject a designer outright |
| DC-26 | Sunita Rajan | HR | Aligned strong talent acquisition executive | excellent | DOCX | selected | consistent, specific evidence in every round |
| DC-27 | Amit Chawla | HR | Average recruiter, limited detail | average | PDF | hold_review / selected | meets the basics for a 1-3 year role without distinguishing evidence |
| DC-28 | Harish Bhandari | HR | Resume with a full demographic header (fairness check) | good | DOCX | selected / hold_review | personal details must not affect the result: compare with an identical resume without the header |
| DC-29 | Fatima Noor | HR | Strong recruiter, limited English and a noisy line | good | DOCX | hold_review / selected | weak speech recognition and limited English should lead to a human review, not a rejection |
| DC-30 | Jasmine D'Souza | HR | The call drops after three questions | good | PDF | hold_review | the call ended early, so the evidence is incomplete: hold for evidence, not a rejection |

## 4. How the inputs were made

- **Resumes** are rendered from each persona's facts in one of six layouts: standard, keyword-stuffed (the skill list repeated), minimal, no section headings (also used for the typo resume), and a header with gender, birth date, religion and a father's name (a fairness probe). Dates are set so the years the **resume parser** reads match the years the persona is meant to have. They are written to DOCX (python-docx) and to PDF by a small dependency-free writer, then read back by the real upload path.
- **Screening answers** follow the order the system asks (introduction, education, experience, skills, location, salary, notice period). A "vague" candidate dodges first and gives the plain answer when asked again. The inflater says 5 years in the call and shows about 2.5 on the resume. The dropped call answers 3 of 7 questions. The noisy-line candidate has speech-recognition confidence 0.58.
- **HR answers** (6) are built from the persona's own facts in six styles: excellent, good, average, weak, nervous and limited English.
- **Technical answers** use the question the real bank asks for the candidate's domain and tier (basics, intermediate, advanced) in three qualities. The tier is **derived by the real question bank from the years the resume parser finds**, so a resume the parser misreads gets the wrong questions (finding F3).
- **Machine tests**: two small Python tasks (top-N words, merge intervals). Each attempt is a set of code snapshots in one of five qualities (strong, partial, slow, overfit, broken). The recorded pass or fail of each case is the result of **really executing** that code when the dataset is built; runtimes are fixed multiples of a reference so the dataset is identical on every machine. The scoring engine itself never runs candidate code.
- **Integrity**: DC-09 has ten tab and window-focus events during the machine test; everyone else has none.
- **Clock**: "today" is frozen at 2026-11-21, so the results do not change with the day the script is run.

## 5. The end-to-end simulation environment

```
python run_day63_demo_dataset.py        # about 10 seconds
```

| Stage | What runs |
|---|---|
| 1 Build | `parsers/demo_dataset_builder.py` writes every input file |
| 2 Check | `verify_dataset()` checks the dataset is consistent; the 4 edge files go through the real upload path and are refused with a named error |
| 3 Run | `parsers/demo_environment.py` takes each candidate from the resume file through ATS, screening, HR, technical, machine test with integrity, Hiring Fit, recommendation and report. The semantic matcher is fitted per resume and job pair, exactly as the ATS service does |
| 4 Write | ATS, screening, interview, machine-test and pipeline results, one recruiter report per candidate, and a summary |
| 5 Findings | `probe_findings()` computes what the run shows about the system |

It builds on the Day 56 simulation (`parsers/pipeline_simulation.py`) and adds what that simulation lacked: a machine-test round and an integrity check, so technical candidates reach a real decision instead of "provisional, waiting for the machine test".

## 6. Results of the run

30 candidates, no errors, no automated rejection, the whole run takes a few seconds.

### Recommendations

| Outcome | Candidates |
|---|---|
| hold_review | 25 |
| selected | 3 |
| rejected | 2 |

### ATS zones

| Zone | Candidates |
|---|---|
| shortlist | 17 |
| review | 10 |
| reject | 3 |

### Did the system reach the outcome the author expected?

**24 of 30** candidates ended inside the expected set.

| Job | Candidates | Expected outcome met |
|---|---|---|
| Full Stack Developer (MERN) | 9 | 8 |
| Java Backend Developer | 4 | 3 |
| DevOps Engineer | 3 | 2 |
| Sales Executive (B2B SaaS) | 5 | 4 |
| UI/UX Designer | 4 | 3 |
| HR Recruiter (Talent Acquisition) | 5 | 4 |

### Every candidate, every round

ATS and the other columns are 0 to 100. `-` means the round does not apply to the role.

| Id | Job | ATS / zone | Screening | HR | Technical | Machine test | Integrity | Hiring Fit | Outcome | Expected | Met |
|---|---|---|---|---|---|---|---|---|---|---|---|
| DC-01 | MERN | 62.0 shortlist | 93.7 | 93.1 | 77.0 | 97.0 | clear | 86.4 | hold_review | selected | **NO** |
| DC-02 | MERN | 48.6 shortlist | 93.4 | 93.1 | 65.7 | 97.0 | clear | 81.6 | hold_review | selected / hold_review | yes |
| DC-03 | MERN | 37.0 review | 90.0 | 86.4 | 47.3 | 54.4 | clear | 60.8 | hold_review | hold_review / rejected | yes |
| DC-04 | MERN | 58.1 shortlist | 85.1 | 78.1 | 27.0 | 3.0 | clear | 38.9 | rejected | rejected / hold_review | yes |
| DC-05 | MERN | 43.8 review | 95.0 | 89.3 | 20.5 | 69.6 | clear | 58.8 | hold_review | hold_review | yes |
| DC-06 | MERN | 45.3 review | 93.4 | 89.0 | 20.5 | 97.0 | clear | 66.9 | hold_review | hold_review / rejected | yes |
| DC-07 | MERN | 52.4 shortlist | 93.4 | 89.0 | 28.6 | 54.4 | clear | 57.3 | hold_review | hold_review | yes |
| DC-08 | MERN | 55.5 shortlist | 95.0 | 84.2 | 77.0 | 97.0 | clear | 84.1 | hold_review | selected / hold_review | yes |
| DC-09 | MERN | 57.2 shortlist | 93.4 | 89.1 | 77.0 | 97.0 | medium | 85.1 | hold_review | hold_review | yes |
| DC-10 | Java | 61.9 shortlist | 93.7 | 93.0 | 75.7 | 97.0 | clear | 86.0 | hold_review | selected | **NO** |
| DC-11 | Java | 49.6 shortlist | 90.0 | 82.3 | 11.9 | 25.4 | clear | 41.6 | rejected | hold_review / rejected | yes |
| DC-12 | Java | 53.6 shortlist | 93.4 | 89.1 | 75.7 | 69.6 | clear | 76.1 | hold_review | selected / hold_review | yes |
| DC-13 | Java | 1.0 reject | 93.4 | 89.0 | 33.7 | 69.6 | clear | 60.4 | hold_review | hold_review / selected | yes |
| DC-14 | DevOps | 72.6 shortlist | 93.7 | 92.7 | 56.0 | 97.0 | clear | 81.1 | hold_review | selected | **NO** |
| DC-15 | DevOps | 39.0 review | 90.9 | 89.0 | 56.0 | 69.6 | clear | 68.5 | hold_review | hold_review / selected | yes |
| DC-16 | DevOps | 38.8 review | 90.0 | 82.4 | 30.3 | 25.4 | clear | 46.1 | hold_review | hold_review / rejected | yes |
| DC-17 | Sales | 58.1 shortlist | 91.2 | 93.0 | - | - | - | 84.0 | selected | selected | yes |
| DC-18 | Sales | 54.2 review | 95.0 | 82.3 | - | - | - | 77.2 | hold_review | hold_review / rejected | yes |
| DC-19 | Sales | 44.5 review | 90.0 | 86.2 | - | - | - | 80.9 | hold_review | hold_review / rejected | yes |
| DC-20 | Sales | 24.4 reject | 95.0 | 89.2 | - | - | - | 73.9 | hold_review | rejected / hold_review | yes |
| DC-21 | Sales | 57.9 shortlist | 92.5 | 92.1 | - | - | - | 83.6 | selected | hold_review | **NO** |
| DC-22 | UX | 57.8 shortlist | 91.7 | 92.8 | - | - | - | 83.9 | hold_review | selected | **NO** |
| DC-23 | UX | 28.7 review | 85.1 | 78.1 | - | - | - | 66.8 | hold_review | rejected / hold_review | yes |
| DC-24 | UX | 52.7 review | 92.5 | 89.1 | - | - | - | 80.5 | hold_review | selected / hold_review | yes |
| DC-25 | UX | 1.1 reject | 90.0 | 89.1 | - | - | - | 76.7 | hold_review | hold_review / selected | yes |
| DC-26 | HR | 56.3 shortlist | 92.1 | 92.8 | - | - | - | 83.6 | hold_review | selected | **NO** |
| DC-27 | HR | 58.6 shortlist | 95.0 | 82.3 | - | - | - | 78.3 | hold_review | hold_review / selected | yes |
| DC-28 | HR | 59.3 shortlist | 92.1 | 91.9 | - | - | - | 83.8 | selected | selected / hold_review | yes |
| DC-29 | HR | 54.6 review | 90.0 | 86.0 | - | - | - | 78.8 | hold_review | hold_review / selected | yes |
| DC-30 | HR | 57.1 shortlist | 43.6 | 89.0 | - | - | - | 74.2 | hold_review | hold_review | yes |

### The 6 misses, explained

The expectations were **not edited** after seeing the results. Each miss is a point where the system and the author disagree:

| Id | Expected | System said | Flag | Reason (from the decision engine) |
|---|---|---|---|---|
| DC-01 | selected | hold_review | ROUND_DISAGREEMENT | The score (86.39%) would select this candidate, but selection is held for review because the aggregate score raised review flags: Rounds disagree stro... |
| DC-10 | selected | hold_review | ROUND_DISAGREEMENT | The score (85.97%) would select this candidate, but selection is held for review because the aggregate score raised review flags: Rounds disagree stro... |
| DC-14 | selected | hold_review | ROUND_DISAGREEMENT | The score (81.07%) would select this candidate, but selection is held for review because the aggregate score raised review flags: Rounds disagree stro... |
| DC-21 | hold_review | selected | none | Hiring Fit 83.61% clears the selection threshold (70) with no rule blocking it. |
| DC-22 | selected | hold_review | ROUND_DISAGREEMENT | The score (83.89%) would select this candidate, but selection is held for review because the aggregate score raised review flags: Rounds disagree stro... |
| DC-26 | selected | hold_review | ROUND_DISAGREEMENT | The score (83.57%) would select this candidate, but selection is held for review because the aggregate score raised review flags: Rounds disagree stro... |

4 of the 6 (DC-01, DC-10, DC-22, DC-26) are held by the round-disagreement rule because the ATS round, on its raw scale, disagrees with interview scores of 90 or more; that is finding F1, and each would be selected on the common ATS scale. DC-14 is held for a different disagreement: machine_test 97 vs technical_interview 56. DC-21 is finding F6: the system selects a candidate the author expected to be held.

## 7. What the demo shows about the system (findings)

These ten statements are computed from the run by `probe_findings()`; none is typed in advance.

| # | Finding | What the run shows |
|---|---|---|
| F1 | The raw ATS scale blocks strong candidates from 'selected' | 7 of 30 outcomes change when the ATS round is put on the common scale (ats_scale='zone_aligned'); 7 candidates move from hold_review to selected. By default the ATS scores here run from 24.4 to 72.6 while most interview scores are 80 or more, so the round-disagreement rule trips. |
| F2 | The screening score barely discriminates | Across the 29 candidates whose call completed, screening scores range only from 85.1 to 95.0; a candidate who answered vaguely and was re-asked scores close to one who answered well. |
| F3 | A resume without section headings is read as having no experience | DC-13 (3.5 years on the resume) parses to 0.0 years and an ATS score of 1.0 (reject); DC-25 (3.0 years on the resume) parses to 0.0 years and an ATS score of 1.1 (reject). DC-13 is then asked the 'basics' technical questions. |
| F4 | Personal details in a resume do not move the ATS score (fairness probe) | DC-28's resume with gender, birth date, religion and father's name scores 59.3 against 59.3 for the same resume without that header (difference 0.00). |
| F5 | Later rounds catch what a keyword-stuffed resume hides | DC-04's stuffed resume reaches the 'shortlist' zone (ATS 58.1); the technical interview (27.0) and machine test (3.0) bring the final outcome to rejected. |
| F6 | Nothing in the scoring looks at how long a candidate stays | DC-21 has five employers in four years and is selected (Hiring Fit 83.6), like a candidate with a stable history. |
| F7 | Skills outside the ATS vocabulary earn no credit | DC-15 (Ansible, Helm, Prometheus, Grafana) gets a skill-match of 50.0 and ATS 39.0 (review) while DC-14 (Terraform, Jenkins, AWS) gets 100.0 and 72.6; their technical interviews score 56.0 and 56.0. |
| F8 | An integrity tag stops an automatic selection | DC-09's Hiring Fit is 85.1 (selection threshold 70) but 10 browser events give the tag 'medium', so the outcome is hold_review. |
| F9 | A dropped call is held for evidence, not rejected | DC-30's call ended after 3 of 7 questions (screening 43.6); the outcome is hold_review. |
| F10 | 'Six months' is read as six years in a screening answer | extract_experience_years('I have six months of internship experience') returns 6.0. The dataset's fresher candidates therefore say '0.5 years' instead. |

## 8. Using the dataset in a demonstration

A ten-minute walk through, with the files to open:

1. **A clean pass.** `DC-17` (sales) or `DC-01` (MERN): open the resume, the screening answers and `simulated/reports/DC-17.md`. Note that every round agrees.
2. **Keywords are not enough.** `DC-04`: the resume lists 38 technologies and reaches the shortlist; the technical interview and machine test bring the outcome to rejected (which still needs a person to confirm).
3. **Integrity.** `DC-09`: strong scores, ten tab events, outcome held for review.
4. **Fairness.** `DC-28`: the same ATS score with and without the demographic header.
5. **Formatting hurts.** `DC-13` or `DC-25`: a competent person whose resume has no section headings scores about 1 out of 100.
6. **A dropped call is not a rejection.** `DC-30`.
7. **Uploading a bad file.** the four files in `edge_files/`.
8. **Where the system is weak.** Run `ats_scale="zone_aligned"` on `DC-01` (finding F1) or open `DC-21` (finding F6).

## 9. Honest limits

- **Synthetic, scripted data.** Answers are assembled from templates and the persona's facts. They are plain on purpose; they test a scoring layer, not how people really speak, and every 'strong' answer sounds alike.
- **The expected outcomes are the author's intent**, not human judgement. No recruiter reviewed these candidates.
- **Small and uneven.** 30 candidates, 3 to 9 per job, one fairness probe, one integrity case. It is a demonstration set, not a benchmark, and cannot support claims about accuracy.
- **Machine-test code is ours.** The code in each attempt was written by us, so the results show how the engine treats five kinds of code, not how real candidates code. Only Python tasks exist, so JavaScript or Java candidates are given Python tasks.
- **Questions the system cannot cover.** There is no real speech, video, voice, calendar or e-mail in the dataset; those parts of the PRD are not in this repository.
- **Dependence on the engines as they are today.** The run, the findings and the numbers in this document describe today's weights. A test fails if the committed results differ from a fresh run.

## 10. Files

| File | What it is |
|---|---|
| `data/demo_dataset/**` | The dataset and its simulated results |
| `parsers/demo_dataset_content.py` | The 6 jobs and 30 personas (who they are, what the author expects) |
| `parsers/demo_dataset_answers.py` | Answer templates, technical answer banks and machine-test code |
| `parsers/demo_dataset_builder.py` | Writes the inputs (resumes, answers, attempts, events) |
| `parsers/demo_environment.py` | Runs the dataset through the real engines; writes the results; computes the findings |
| `run_day63_demo_dataset.py` | Build, check, run and print |
| `tests/test_demo_dataset.py` | 21 tests |
| `data/results/day63_demo_report.json`, `logs/day63_demo_run.log` | Record of the run |
