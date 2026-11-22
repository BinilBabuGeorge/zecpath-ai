# Zecpath AI: Developer Onboarding Guide

Zecpath: AI Job Portal | For developers joining the AI layer | Built 2026-11-20 (Day 62)

Read this first. It gets you from a clean machine to a first change in a day. The full reference is the **Technical Handbook** (`docs/day62_zecpath_ai_technical_handbook.md`); the picture is in the **System Architecture** (`docs/day62_system_architecture.md`).

## 1. What you are joining

A Python codebase of small, stateless AI services that score resumes, screening calls, interviews and machine tests and recommend a hiring decision for a person to act on. About 80 Python files and 1,643 test functions. Almost all logic is rule-based and deterministic, with reasoned (not calibrated) weights. Nothing is deployed; there is no gateway, database or queue here.

## 2. Your first day

| Step | Do this | Time |
|---|---|---|
| 1 | Read `README.md` and `docs/CODE_STANDARDS.md` | 20 min |
| 2 | Read handbook sections 1 and 2 (overview, architecture) | 30 min |
| 3 | Set up (section 3 below) and run the sample | 30 min |
| 4 | Read `utils/base_service.py` and `ats_engine/service.py` (170 lines in total) | 20 min |
| 5 | Run one day's demo and read its document, for example Day 56 (`run_day56_full_system_simulation.py`, `docs/day56_full_system_simulation.md`) | 40 min |
| 6 | Read the handbook's scoring section (5) and the glossary | 30 min |
| 7 | Pick a starter task (section 9) | rest of day |

## 3. Set up

Prerequisites: Python 3.11, Git.

```bash
git clone <your-repo-url>
cd zecpath-ai
python -m venv venv
venv\Scripts\activate            # macOS / Linux:  source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # macOS / Linux:  cp .env.example .env
```

Check it works:

```bash
python -c "from ats_engine.service import ATSService; print(ATSService().run({'resume_text': 'React, Node.js', 'job_description': 'Needs React and Node.js'}))"
pytest tests/test_ats_engine.py tests/test_scoring.py tests/test_service_contracts.py
pytest                      # the full suite; the Day 61 run was 2,017 passed, 6 skipped
```

If `pytest` is not available (some locked-down machines), `regression_runner.py` runs test modules without it; edit its module list at the bottom.

**Watch for these on a new machine**

- `requirements.txt` now lists scikit-learn, pdfplumber and python-docx (it did not before Day 62); if an import fails, reinstall.
- **Python 3.12 gives HR scores that differ by 0.1** from 3.11 at rounding boundaries (a float `sum()` change). The golden test handles both; do not "fix" a 0.1 difference.
- `venv/`, logs and real data are gitignored; do not commit them.

## 4. A tour of the repository

```
ats_engine/      services: ATS, batch ATS, resume parsing          start: service.py
screening_ai/    service: screening call scoring
interview_ai/    service: HR and technical interviews
scoring/         service: decision and recommendation
parsers/         every engine (resume, ATS, screening, HR, technical, machine test,
                 aggregation, recommendation, governance, integration, observability)
utils/           base_service, config, logger, perf (cache), warmup
api/, schemas/   OpenAPI and JSON Schemas (some are GENERATED; see section 7)
tests/           one test file per module; tests/golden/ holds golden outputs
docs/            one document per day; docs/diagrams/ holds the pictures
run_dayNN_*.py   one demo script per day; each writes logs/dayNN_*.log
```

To find a module, use the module reference in the handbook (section 3): it lists every file with what it does and the PRD phase it serves.

## 5. Ten ideas to hold in your head

1. **Call `run()`, never `process()`.** `run()` never raises and always returns an envelope with `status` of `success` or `error`.
2. **Services are stateless and never touch a database.** The backend saves results.
3. **Services never import each other.** Engines in `parsers/` are shared libraries.
4. **Every score shows its working:** components, weights, contributions, reasons.
5. **Missing is not zero.** A missing section redistributes weight; a missing round makes the result provisional.
6. **A rejection is only a recommendation.** Never write code that rejects automatically; `human_confirmation_required` must be true.
7. **No personal content in logs or audit entries** (text, answers, names, emails, transcripts). Log numbers and codes.
8. **Do not claim a capability that does not exist.** If a signal cannot be observed, say "not implemented" in the output, as the integrity report does.
9. **Weights are reasoned, not calibrated.** Say so when you change one.
10. **Change behaviour deliberately.** A test that fails after a scoring change is the system working; read why before touching the test.

## 6. Follow one request

`ATSService().run({"resume_text": ..., "job_description": ...})`

1. `BaseAIService.run` checks the payload is a dictionary and calls `process`.
2. `ATSService.process` reads the fields (`_get_text`, `_get_list`) and picks the mode: with a `job_description` it is the real engine (`scoring_mode: ats_engine`); with only `job_requirements` it is the **deprecated** keyword-coverage mode, which is **not comparable** with an engine score.
3. It normalises resume headings (a resume headed "Technical Skills" must not score as having none), fits TF-IDF on exactly this resume and job description, and calls `score_candidate`.
4. The result carries `ats_score`, `zone` and the four components; `to_json_safe` makes it JSON-safe.
5. Any bad input raised as `ServiceInputError` becomes an error envelope with `code` and `field`.

## 7. How work is done here

Each day's task produces the same set of things. Follow the pattern.

| Piece | Naming | Notes |
|---|---|---|
| Module | `parsers/<topic>.py` (or a service folder) | starts with a docstring: what it implements, input contract, output contract, and what it does **not** do |
| Tests | `tests/test_<module>.py` | one file per module; a normal case and an edge case per function |
| Demo | `run_dayNN_<topic>_demo.py` | reproduces the day's numbers; writes `logs/dayNN_*.log` and `data/results/*.json` |
| Document | `docs/dayNN_<topic>.md` | separates what is built, measured, proposed and not built |
| Regression | run the full suite before you finish | record the result in the day's document |

**Style** (`docs/CODE_STANDARDS.md`): PEP 8, `black` and `flake8` (maximum line length 100), type hints on signatures, `snake_case` names, `PascalCase` classes, `UPPER_SNAKE_CASE` constants, `get_logger(__name__)` instead of `print`, commit messages as `<area>: <short description>`.

## 8. Recipes

### 8.1 Add a new service
1. Create the folder with `__init__.py` and `service.py`.
2. Subclass `BaseAIService`, implement `process()`, return `self._base_response()` plus your fields.
3. Raise `ServiceInputError(code, message, field)` for bad input; use the typed helpers for fields.
4. Write `tests/test_<service>.py`, and add the service to the contract tests.
5. Add the operation to `parsers/integration_contract.py`, then run `python run_day59_integration_demo.py` to regenerate `schemas/integration_api_schemas.json` and `api/integration_openapi.yaml`. A test fails if those files differ from what the code generates.
6. Add the new modules to `parsers/documentation_index.py` (`MODULE_CATALOGUE`), or the Day 62 test fails.

### 8.2 Change a weight or threshold
1. Find the constant (the handbook's scoring section names the module; the numbers are read from the code).
2. Change it, and expect tests and the golden test to fail: they pin behaviour on purpose.
3. Decide whether the new answers are right. If yes, update the tests that pin the old values and say why in the day's document. **Never regenerate the golden files from changed code**: they were generated from the pre-optimisation code so that an optimisation can be proven not to change answers. A deliberate behaviour change needs a new, clearly labelled golden file.
4. Say in the document that the number is reasoned, not calibrated.
5. Re-run `python run_day62_handbook.py` so the handbook shows the new value.

### 8.3 Add a skill or a question
Skills: add to `parsers/skill_dictionary.py` (grouped by domain, with aliases), then run `tests/test_skill_extractor.py`. Questions: add to the relevant bank (`screening_question_bank`, `hr_interview_question_bank`, `technical_interview_question_bank`) with its category and expected key concepts, then run that bank's test file.

### 8.4 Debug a request
1. Reproduce with `Service().run(payload)` and read `status` and `error`.
2. `error.field` names the input at fault; `internal_error` means a bug: read `logs/zecpath_ai.log` for the full trace.
3. For a surprising score, look at the components, weights and warnings in the response before reading code.
4. Use `parsers/stability_checks.py` patterns to turn the failing input into a permanent edge-case test.

## 9. Pitfalls found the hard way

| Pitfall | What happens | Source |
|---|---|---|
| Interview answers are matched **in order** to the questions the service asks | a good answer to a different question scores 0. For a technical interview the first question is "tell me about your technical background", so an answer about React internals sent first scores 0. Send answers in the order the questions are asked | `interview_ai/service.py` |
| Extra answers beyond the question count | ignored, with a warning | `interview_ai/service.py` |
| Keyword-coverage mode of the ATS | looks like a score but is only the percentage of keywords found | `ats_engine/service.py` |
| Resume with unusual section headings | skills invisible; the readiness check tells a candidate when the system cannot read their resume | Day 57, Day 58 |
| A score of 0.0 from an engine | may mean "nothing to score", not a real zero; the aggregation reads the evidence and reports the round as missing | Day 51 |
| Technical roles with no machine test | never `selected` or `rejected` on partial evidence | Day 57 |
| `behavior_score` and `communication_score` keys | legacy: `behavior_score` is ignored with a warning, `communication_score` is an alias for `hr_interview_score` | `scoring/service.py` |
| Python 3.12 vs 3.11 | HR scores can differ by 0.1 | Day 60 |
| Missing install lines | fixed in Day 62 | `requirements.txt` |

## 10. Starter tasks

1. Run `run_day56_full_system_simulation.py` and read the "inconsistencies found" section of its document.
2. Add an edge-case test for an input you think could break an engine (see `tests/test_edge_case_sweep.py`).
3. Pick a limit from the handbook's section 11 and read its day's document to see how it was found.
4. Fix a documentation gap: if a module's docstring is missing a contract line, add it.

## 11. Rules of the road (checklist before you commit)

- [ ] Module docstring states what it implements, its input contract, its output contract and its limits
- [ ] Type hints; `black` and `flake8` clean
- [ ] No `print`; logging through `get_logger`
- [ ] No personal content in any log or audit entry
- [ ] No service imports another service
- [ ] A test file for the module, normal and edge cases
- [ ] Full test suite passes; result recorded in the day's document
- [ ] Any new weight or threshold labelled as reasoned or calibrated
- [ ] `parsers/documentation_index.py` updated for a new module; `python run_day62_handbook.py` re-run
- [ ] Commit message `<area>: <short description>`

## 12. Glossary

See the handbook, appendix A. The most-used words: *ATS*, *zone*, *round*, *Hiring Fit Score*, *provisional*, *envelope*, *stateless*, *golden file*, *human confirmation*.
