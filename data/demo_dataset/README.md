# Zecpath demo dataset (Day 63)

**Synthetic data only.** Every name, employer, institute, e-mail address (`@example.com`) and phone number (`+91-90000-...`) is invented. Any match with a real person or company is a coincidence. No real candidate data is, or should ever be, stored here.

## What it is

A small, realistic set of hiring data for demonstrating the whole Zecpath AI layer: **6 job descriptions** and **30 candidates** (`DC-01` to `DC-30`) with resumes of varied quality, what each said and typed in every round, machine-test attempts and browser events. `simulated/` holds the results of running the **real engines** on this data.

## Layout

| Path | Contents |
|---|---|
| `jobs/` | 6 job descriptions (`JOB-01` to `JOB-06`) and `jobs.json` |
| `resumes/` | 30 resumes as DOCX (20) and PDF (10), the formats the upload path accepts |
| `resumes_text/` | the same resumes as plain text |
| `edge_files/` | 4 files the upload path must refuse (corrupt PDF, empty DOCX, legacy `.doc`, image) |
| `candidates.json` | one record per candidate: scenario, job, resume file, the author's **expected outcome** and why |
| `responses/` | `screening_responses.json`, `hr_responses.json`, `technical_responses.json` |
| `machine_test/` | `tasks.json` (2 coding tasks) and `submissions.json` (32 attempts: code snapshots and execution results) |
| `integrity/` | `browser_events.json` (tab and focus changes) |
| `simulated/` | **outputs**: `ats_results.json`, `screening_outputs.json`, `interview_results.json`, `machine_test_results.json`, `pipeline_results.csv` / `.json`, `summary.json`, `reports/DC-*.md` |
| `manifest.json` | counts and SHA-256 of the text resumes |

## Run it

```
python run_day63_demo_dataset.py        # rebuilds the inputs, runs all 30 candidates, rewrites simulated/
python -m pytest tests/test_demo_dataset.py -q
```

Using one candidate from Python:

```python
from parsers import demo_environment as env
ds = env.load_dataset()
run = env.run_candidate(ds, ds["candidates"][0], env.date(2026, 11, 21))
print(run.outcome, run.score.hiring_fit_percentage)
```

## Things to know

- **Inputs vs outputs.** Everything outside `simulated/` is input written by `parsers/demo_dataset_builder.py`. Nothing in the inputs is a score. `simulated/` is produced by the engines and is overwritten by every run.
- **Expected outcomes are the author's design intent**, written before the first run. They are not human judgement and are never edited after seeing results.
- **The clock is frozen** at the as-of date in `candidates.json` (2026-11-21), so results do not change with the day you run it.
- **Reproducible.** Rebuilding gives byte-identical JSON, text resumes and PDFs (DOCX files differ in internal timestamps only).
- **Not a benchmark.** 30 candidates cannot measure accuracy. Use it to demonstrate and to test behaviour.

Full description, results and findings: `docs/day63_demo_dataset.md`.
