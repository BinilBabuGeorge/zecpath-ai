# Day 64: Reviewer Session Kit

Zecpath: AI Job Portal | How to collect mentor and reviewer feedback | Built 2026-11-23

Day 64 asks for feedback from mentors and reviewers. This kit makes a 45-minute session easy to run and its feedback easy to record. **No feedback is included in the review report until it is recorded here.**

## Before the session (10 minutes)

```
venv\Scripts\activate
python run_day63_demo_dataset.py
python run_day64_internal_review.py
```

Open `docs/day64_internal_review_report.md` (sections 2 to 6), `data/demo_dataset/simulated/pipeline_results.csv` and the reports of DC-01, DC-04, DC-09, DC-13 and DC-30.

## Agenda (45 minutes)

| Min | Item | What to show | Ask the reviewer |
|---|---|---|---|
| 0-5 | What the system is | Handbook section 1 and the candidate-journey diagram (`docs/diagrams/day62_candidate_workflow.png`) | Is anything in the scope missing? |
| 5-10 | ATS | DC-01 resume and its ATS components; then DC-13 (no headings) and the PDF example in the report, 4.6 | Would a recruiter score this resume the same way? |
| 10-17 | Screening | DC-01 answers, then the negative controls (report 4.5) | Is it acceptable that gibberish scores about 56? |
| 17-24 | HR interview | DC-01 answers and the off-topic control | Should relevance dominate? What would you check? |
| 24-31 | Technical interview and machine test | DC-04 (stuffed resume) and DC-09 (integrity) | Are the questions and the code checks fair for the role? |
| 31-38 | Decision | DC-01 recruiter report and its rule trace; DC-30 (dropped call) | Would you have decided differently? Is the report readable in a minute? |
| 38-45 | Priorities | The top of the improvement list and the six decisions | What would you fix first? What is missing? |

## Questions to ask at every stage

1. What did you expect to see that is missing?
2. What surprised you?
3. Where could this give a candidate a wrong result?
4. What would you change first?
5. What would stop you using this on real candidates?

## Rating scale (ask for one number per area)

| Score | Meaning |
|---|---|
| 1 | Not usable |
| 2 | Needs major work |
| 3 | Usable with known gaps |
| 4 | Good, small fixes |
| 5 | Ready |

Areas: ATS, Screening, HR interview, Technical interview, Machine test, Decision, Recruiter report, API and errors, Documentation. The author's own scores are in report section 3; compare them with the reviewer's.

## Feedback form (copy per reviewer)

```
Reviewer:                 Role: mentor / reviewer / recruiter / developer      Date:
Ratings (1-5):  ATS __  Screening __  HR __  Technical __  Machine test __  Decision __  Report __  API __  Docs __

Comment 1   Stage:        Kind: accuracy / ux / performance / engineering / governance
            Observed:
            Severity (1-5):           Suggestion:
Comment 2   ...
```

## Recording the feedback

Add one object per comment to `entries` in `data/review/feedback_log.json`:

```
{
  "reviewer": "initials",
  "role": "mentor",
  "date": "2026-11-24",
  "stage": "Screening",
  "kind": "accuracy",
  "comment": "what they observed, in their words",
  "severity": 4,
  "suggestion": "what they would change (optional)"
}
```

Then run `python run_day64_internal_review.py`. Each entry becomes a triage item `FB-001`, `FB-002`, ... in `docs/day64_improvement_list.md` (impact = severity, confidence 2, effort 2 days until triaged), and the report states how many entries it was built from.

## After the session

- Triage each FB item: merge it with an existing item, re-score it, or reject it with a reason.
- Update the action plan if a comment moves a wave.
- Record the reviewer's ratings next to the author's scores in the report.
