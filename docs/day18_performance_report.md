# Day 18 — Optimization & Performance Tuning Report

## Method

Every number in this report was measured directly with `run_day18_benchmark.py`
in this environment — not estimated. "Before" numbers were captured by
`git stash`-ing the five fix commits, running the benchmark, then popping
the stash and re-running for "after". Each fix is also verified
behavior-identical via a golden-master comparison against the original
algorithm (see `tests/test_day18_performance.py`), and the entire
pre-existing 209-test suite from Days 9–17 passes unchanged (225 total
including this day's own 16 new tests) — see the Validation section.

## Results

| Benchmark | Before | After | Speedup |
|---|---|---|---|
| `normalize_for_embedding()`, full 20-doc corpus | 44.0ms/call | 1.5ms/call | **~30x** |
| `extract_skills()`, full 20-doc corpus | 80.8ms/call | 38–42ms/call | **~2x** |
| `score_candidate()`, all 64 resume×JD pairs | 956ms total | 241–267ms total | **~3.7x** |
| `parse_certifications()`, pathological line (1500 reps, ~72KB) | **3.61s** | 0.0001s | **~36,000x** |
| `extract_skills()`, noisy resume (3000 garbage fragments) | 539ms | 51–60ms | **~9–10x** |

Re-run twice to confirm stability — results vary by only a few
milliseconds run to run, well within normal measurement noise.

## What changed, and why (evidence, not guesswork)

### 1. `semantic_matcher.normalize_for_embedding()` — 143 passes → 1 pass
Ran one `re.sub()` per known synonym (143 of them) across every text —
O(143 × text length) per call, and this function runs on every resume and
every JD, every scoring call. Replaced with a single precompiled
alternation pattern (`_COMBINED_SYNONYM_PATTERN`), doing the same
longest-match-wins substitution in one O(text length) pass. This alone
accounted for the largest share of `score_candidate()`'s wall time.
**Verified identical output** on every real sample resume/JD via a
golden-master test against the original sequential algorithm.

### 2. `skill_extractor._find_exact_matches()` — N scans → 1 scan
Same shape of problem: one `re.finditer()` pass per synonym, with a
hand-rolled `bytearray` to prevent overlapping matches across passes.
Replaced with one combined pattern — `finditer()` on a single pattern
never produces overlapping matches by construction, so the manual
overlap-tracking became unnecessary. **Verified identical skill sets
detected** on every real sample resume via golden-master comparison.

### 3. `ats_scoring_engine.score_candidate()` — 3x redundant extraction → 1x
`jd_sections["skills"]` was independently re-parsed by `extract_skills()`
three separate times per call: once inside `infer_role_category()`, once
inside `_score_skill_match()`, and once more for `required_skill_names`.
`extract_skills()` includes an O(fragments × dictionary) `difflib` fuzzy
fallback, so this wasn't free work being repeated. Extracted once,
reused three times. Combined with fixes #1 and #2 (which `score_candidate`
also depends on), the full batch time dropped ~3.7x.

### 4. `education_parser.parse_certifications()` — catastrophic blowup → early exit
`CERTIFICATION_PATTERN` requires a literal `(` to match at all, but a line
with none was still handed to the regex engine, which burned real time
searching for a match that could never succeed — confirmed **quadratic**
growth in line length (1000 repetitions → 1.6s, 2000 → 6.4s; the
pathological benchmark case at 1500 repetitions reproduces a **3.6 second**
single `.match()` call). Added a one-line pre-check (`if "(" not in line:
continue`) that changes zero matching behavior for lines that could ever
match, verified against real certification lines still parsing correctly.

### 5. `skill_extractor._find_fuzzy_matches()` — unbounded fragment count
Two related issues: `list(_SYNONYM_LOOKUP.keys())` (~150+ entries) was
rebuilt on every single call instead of once at import time, and
`_candidate_fragments()` had no upper bound — a garbled/noisy resume
(bad PDF extraction, thousands of junk tokens) could generate thousands
of fragments, each compared via `difflib` against the full term list.
Fixed the list rebuild (module-level constant now), and capped fragment
count at 300 — 10x the largest fragment count seen in any real sample
resume (15–31), so it only engages on genuinely pathological input, never
a real resume.

## Stability: input validation

`extract_resume_sections(None)` and `extract_jd_sections(None)` (or any
non-string) used to crash 4+ calls deep inside `re.search()` with an
opaque `TypeError: expected string or bytes-like object, got 'NoneType'`.
Added an entry-point check that raises the same `TypeError` but
immediately, with a message pointing at the actual problem — useful today
for anyone calling this directly, and directly useful for Day 16's
planned API layer, which needs a clean signal to convert into a `400`
response rather than a bare stack trace.

## Validation

- **225 tests pass in the full project environment**, zero failures: the
  pre-existing 209 tests from Days 9–17 (unchanged) plus 16 new Day 18
  tests, confirmed this session via `_manual_regression_runner.py`
  (pytest itself isn't installable offline in this sandbox — no network
  access — so a small dependency-aware runner was used instead;
  behavior is identical to `pytest -v`, run it yourself for the
  authoritative timing/output).
- **The zipped deliverable's bundled regression** (`regression_runner.py`)
  is deliberately scoped to the 8 test modules that are self-contained
  with the files in this package — everything Day 18 actually touches
  (the 5 changed files) plus everything built directly on top of them
  (`ranking_engine`, `fairness_engine`): **159/159 passing**. The other
  6 pre-existing test modules (`test_jd_parser`, `test_section_classifier`,
  `test_resume_extractor`, `test_logger`, `test_ats_engine`,
  `test_scoring`) depend on data fixtures and modules outside this day's
  scope and aren't bundled here, but were verified passing in the full
  project directory as part of the 225 total.
- **Golden-master comparisons**: fixes #1 and #2 are verified to produce
  byte-identical/set-identical output to the original algorithms on every
  real sample resume and JD in the project, not just "doesn't crash."
- **Real before/after timing**, captured via `git stash`, not estimated
  or copied from assumption.

## What this does NOT cover (stated honestly)

- No load/concurrency testing — all numbers are single-process, single-
  request timings. A real production deployment (per Day 16's async job
  design) would need separate load testing under concurrent scoring jobs.
- Memory profiling was scoped to "does anything obviously leak or grow
  unboundedly" (checked: `fairness_engine`'s temporary `WEIGHT_PROFILES`
  key is removed via `try/finally` even on exception, confirmed in Day 15)
  — no formal memory profiler (e.g. `tracemalloc`) run this session.
  Worth a dedicated pass if resume volume grows significantly.
- `extract_skills()`'s remaining ~2x speedup (vs. `normalize_for_embedding`'s
  ~30x) is because its fuzzy-match path is inherently O(fragments ×
  dictionary terms) via `difflib` — the fixes here removed accidental
  overhead, not the fundamental algorithmic cost. A real further speedup
  would need a different fuzzy-matching approach (e.g. a BK-tree or
  precomputed trigram index) — noted as a candidate for a future
  performance pass, not attempted here since it's a larger design change
  than a tuning day should carry.
