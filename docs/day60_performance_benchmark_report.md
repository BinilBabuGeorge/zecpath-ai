# Day 60 – Performance Tuning & Scalability: Benchmarking Report

Zecpath – AI Job Portal | Performance benchmarking report

## Objective

Optimize the AI services for real-world usage and large-scale hiring operations: faster inference, lower API latency, batching for resume processing, lower memory use and caching, a horizontal scaling strategy, and a test under simulated load.

**Headline.** The services are faster, use far less memory in four of the five worker types, and start without a slow first request. **Every answer is unchanged:** the optimized code reproduces the pre-optimization output exactly (golden file generated from the old code, plus a SHA-256 fingerprint of every benchmark result, identical in all 9 recorded runs). The gains are real but modest, because earlier days (18 and 54) had already removed the big hotspots: ATS scoring is about 1.4 to 1.7 times faster, screening and HR scoring about 1.6 to 1.7 times, a repeated resume parse about 150 times, and a decision or interview worker uses 19 MB instead of 138 MB. This report also says where nothing was gained and why.

**How to read this.** Every number comes from `run_day60_benchmark.py`, one script run on the unchanged code ("before") and on the optimized code ("after"), three times each; the table shows the median. Compute only, one machine, one process: no network, storage, queue, speech-to-text or authentication. The sandbox that produced these numbers has **1 CPU** and is shared, so single runs vary by up to 30 %; the speed-ups are ratios of medians and are the thing to trust, not the absolute milliseconds (your machine will be slower). Run `python run_day60_performance_demo.py` to regenerate every table below from the recorded runs.

## 1. What was done, by brief item

| Brief item | What was done | Evidence |
|---|---|---|
| Optimize model inference time | Profiled first (section 2), then fixed what the profile showed: six TF-IDF transforms per resume became one; the fuzzy skill matcher only offers difflib terms that can pass its own length test and remembers answers; skill extraction is remembered by text; phrase patterns used by screening and interview scoring are compiled once | ATS 5.16 → 2.96 ms per resume (1.74×); screening 2.85 → 1.66 ms; HR interview 2.00 → 1.22 ms |
| Reduce API response latency | Warm-up at start-up moves a one-off 992 ms out of the first request; p95 tails fall with the average; logging and the service wrapper were measured and left alone | First request after start 1,235 → 3.8 ms; ATS p95 5.8 → 3.5 ms; PDF parse p95 77 → 26 ms |
| Implement batching for resume processing | Batch scoring keeps the Day 59 rule (each candidate scored on their own pair, so a batch equals single requests) and gains from remembered job-side work and one transform per resume; an optional process pool spreads large batches over cores; parse results are remembered by file content | 100 candidates 464 → 301 ms (1.54×); repeated PDF parse 21.6 → 0.14 ms |
| Optimize memory usage and caching | scikit-learn is loaded only when a matcher is built, so decision, interview and screening workers no longer carry it; every cache is bounded in entries and bytes | Decision, interview, screening worker 138 MB → 19 MB (–86 %); all Day 60 caches together capped at 9.5 MB |
| Design horizontal scaling strategy | Load balancing and microservice scaling designed from measurements and a checked simulation | `docs/day60_scalability_strategy.md` |
| Test the system under simulated load | Threads and processes measured; load-balancing policies and dedicated pools simulated; capacity planned | Section 6 |

**Tests:** 50 new in `tests/test_day60_performance.py`; the full suite passes (1,951 passed, 6 skipped; previous 1,901).

## 2. What the profile found (before any change)

Profiling came first, on the Day 59 code. Percentages are shares of the time of that operation.

| Operation | Where the time went | Action |
|---|---|---|
| ATS scoring (about 5 ms) | 54 % semantic similarity, almost all of it scikit-learn's fixed cost per `transform` call, six calls per resume; 19 % fitting the per-request vectorizer; 18 % skill extraction, 15 % of it the fuzzy fallback | Batch the six transforms into one; speed up and remember the fuzzy fallback; remember skill extraction. The per-pair fit stays: Day 59 chose per-pair scoring so a candidate's zone cannot depend on who else applied |
| DOCX parsing (about 10 ms) | 50 % opening the file, 43 % skill extraction (fuzzy) | Same skill fixes; result remembered by file content |
| PDF parsing (about 21 ms) | 87 % inside `pdfplumber` (third-party) | **Not changed**: a faster extractor would change the text, and so the scores. Remembered by file content for repeats |
| Screening scoring (about 3 ms) | 37 % fuzzy matching, plus pattern rebuilding | Same fuzzy fix; patterns compiled once |
| HR interview scoring (about 2 ms) | Phrase patterns rebuilt for every phrase on every answer (about 600 rebuilds per call) | Compiled once |
| First request in a fresh process | 1,235 ms against 5 ms for the second: one-off imports and pattern compilation done lazily inside the request | Warm-up at start-up |
| Memory of a worker | 138 MB for a process that only scores decisions, because importing the ATS zone logic pulled in scikit-learn, NumPy and SciPy | Import them only when a matcher is built |
| Logging | 0.0 to 0.2 ms per request with the project's real handlers | Measured, **left alone** (noise level) |
| Service wrapper (`run()`) | A decision request takes 0.07 ms in total, so the wrapper is negligible | Left alone |

## 3. Results

Median of three runs each; p50 per request, or the median per batch. "Caches OFF" is the optimized code run with `ZECPATH_CACHE=off`, so it shows only the gains that do not depend on any cache: **treat it as the conservative claim.**

| Workload | Before | After | Speed-up | Caches OFF | Speed-up |
|---|---|---|---|---|---|
| `ats_single_same_jd` (16 resumes, one job) | 5.155 ms | 2.963 ms | 1.74× | 3.703 ms | 1.39× |
| `ats_single_four_jds` (64 pairs) | 4.431 ms | 2.466 ms | 1.80× | 3.346 ms | 1.32× |
| `ats_batch_16` | 81.8 ms | 49.8 ms | 1.64× | 58.4 ms | 1.40× |
| `ats_batch_100` | 464.4 ms | 300.9 ms | 1.54× | 338.6 ms | 1.37× |
| `parse_docx` (first parse of each file) | 9.451 ms | 6.722 ms | 1.41× | 8.028 ms | 1.18× |
| `parse_pdf` (first parse of each file) | 21.245 ms | 16.104 ms | 1.32× | 20.255 ms | 1.05× |
| `parse_pdf_same_file_again` (retry or re-upload) | 21.626 ms | 0.144 ms | 150× | 19.685 ms | 1.10× |
| `screening_7_turns` | 2.848 ms | 1.664 ms | 1.71× | 2.199 ms | 1.30× |
| `interview_hr_4_answers` | 1.995 ms | 1.216 ms | 1.64× | 1.256 ms | 1.59× |
| `interview_technical_3_answers` | 0.042 ms | 0.039 ms | 1.08× | 0.040 ms | 1.05× |
| `decision` | 0.074 ms | 0.067 ms | 1.10× | 0.068 ms | 1.09× |

Tail latency (p95): ATS 5.78 → 3.48 ms; screening 4.12 → 1.74 ms; HR interview 2.92 → 1.33 ms; DOCX parse 27.5 → 23.8 ms; PDF parse 77.5 → 26.2 ms.

**Two workloads gain nothing, on purpose.** `interview_technical_3_answers` and `decision` already take under 0.1 ms; there is nothing worth the risk of changing. The PDF first-parse gain (1.05× without caches) is within noise, because 87 % of it is a third-party library.

**Cold start** (a fresh process, one ATS request):

| | Import | Warm-up | First request | Second request |
|---|---|---|---|---|
| Before | 21 ms | none | 1,235 ms | 6.7 ms |
| After | 12 ms | 992 ms at start-up | 3.8 ms | 3.1 ms |

Warm-up does not make the work disappear, it moves about a second from the first candidate's request (and from the tail latency of every freshly started or autoscaled worker) to start-up, where a worker can stay out of the load balancer until it finishes.

**Memory** (resident memory of a fresh process after serving only one kind of request; Linux `/proc`, so not available on Windows):

| Process that has served only | Before | After |
|---|---|---|
| Nothing (an idle Python) | 11.6 MB | 11.6 MB |
| Decision | 137.6 MB | **19.0 MB** |
| Interview | 137.9 MB | **19.5 MB** |
| Screening | 137.7 MB | **19.4 MB** |
| ATS scoring | 153.8 MB | 153.7 MB |
| Resume parsing (libraries loaded, no request) | 40.9 MB | 40.9 MB |

Memory per request is small and does not leak: a 100-candidate batch (73 KB of input) peaks at 1.8 MB of Python allocations and retains 0.05 MB afterwards. The ATS worker's 154 MB is scikit-learn, NumPy and SciPy and is not reducible without replacing them.

**Caches** on a 100-candidate batch (`run_day60_performance_demo.py`, section 6):

| Cache | Entries | Hit rate | Byte budget |
|---|---|---|---|
| `skill_extract_text` (skills found in a text) | 52 of 1,024 | 87 % | 7.6 MB |
| `skill_fuzzy` (closest dictionary term for a fragment) | 29 of 8,192 | 3 % | 1.9 MB |
| `resume_parse` (parse result by file content) | – | – | 15.3 MB budget; the demo batch parses no files |

The combined byte ceiling of all three is 9.5 MB for the first two plus the parse cache's budget; a test pins the total at under 30 MB.

**Read the hit rates honestly.** The 100-candidate batch is built from 16 real resumes with a unique line added, so their skills sections repeat and flatter the 87 %. With genuinely distinct resumes the resume side will rarely hit; the job-description side hits for every candidate after the first. The fuzzy cache's 3 % shows it is not what makes the batch faster; the length filter, the batched transform and the compiled patterns are. This is why the caches-OFF column, not the headline column, is the number to quote.

## 4. How each change keeps the answers identical

| Change | Why it cannot change a result | How that was checked |
|---|---|---|
| One `transform` for six texts (`embed_many`) | Rows of a TF-IDF transform are independent of each other | Vectors compared array by array; all 64 sample scores compared |
| Fuzzy length window | difflib already discards any term whose length makes `real_quick_ratio` fall below the cutoff; the window applies the same expression first | 20,000 generated fragments (typos, noise, truncations): same answer as difflib's own call; each length 1–64 checked term by term |
| Memoised fuzzy match and skill extraction | Both are pure functions of their text; results are copies, so a caller cannot alter what the next caller sees | Mutation tests; golden skill hashes on the first call and on a repeat |
| Phrase patterns compiled once | Same pattern text, built once instead of per call | 240 generated answers through nine engines compared with the old output |
| Parse result cached by file bytes, type and date | Keyed by content, not name; errors never cached; each caller gets a deep copy and its own `candidate_id` | Tests: same path with different bytes; different date; a fixed file after an error |
| Lazy scikit-learn import | Only the import moves | A fresh-process test: decision, interview and screening do not load it; ATS does |
| Warm-up | Runs a tiny real request, then empties the caches | Test: no cache entries remain; later results equal the golden file |

**The strongest evidence** is `tests/golden/day60_golden_outputs.json`, generated by `tests/golden/make_day60_golden.py` run on the Day 59 code before any change: 64 ATS pairs, a 16-candidate batch, 20 parsed files, 20 skill extractions (twice), 240 answers through nine engines, and screening, interview and decision results. The optimized code must reproduce all of it, with the caches warm, cold and switched off. The existing 1,901 tests also pass unchanged.

## 5. What was not optimized, and why

| Item | Why not |
|---|---|
| PDF text extraction (87 % of a PDF parse) | It is a third-party library; another extractor changes the text and therefore skills, experience and scores |
| The per-request TF-IDF fit (19 % of ATS scoring) | Sharing one vocabulary across a batch would be faster but made one candidate in 16 change zone (Day 59, F1). A hand-written TF-IDF could remove it but risks differences in the last digits |
| Technical-interview and decision scoring | Already under 0.1 ms |
| Logging, `run()` overhead | Measured at noise level |
| Machine-test scoring | No service wiring exists yet (Day 57, O3) |

## 6. Load test

`run_day60_load_test.py` (results in `data/results/day60_load_test.json`). Three parts that prove different things.

**A. Threads (measured).** More threads add no throughput, because scoring is pure-Python CPU work and the interpreter lock lets one thread run at a time:

| Threads | Requests per second | p50 | p99 |
|---|---|---|---|
| 1 | 305 | 3.2 ms | 4.7 ms |
| 2 | 317 | 6.9 ms | 11.9 ms |
| 4 | 284 | 15.4 ms | 30.9 ms |
| 8 | 283 | 27.5 ms | 95.7 ms |

**B. Processes (measured, and limited).** Throughput was 284, 287 and 257 requests per second for 1, 2 and 4 worker processes. **This machine has 1 CPU, so processes cannot run in parallel here, and this result does not show or disprove scaling.** It does show that extra processes cost little when they cannot help (speed-ups of 1.01 and 0.90 against one process). On a multi-core machine the same script prints the real curve (`python run_day60_load_test.py`); that measurement is still to do, and the parallel batch code is tested for correctness here, not for speed.

**C. Simulation (a model, not a measurement).** Four workers at 60 % utilization with the benchmark's measured service times (312,394 requests over 10 simulated minutes: ATS scoring, HR scoring, screening, PDF parsing, 100-candidate batches). Latency of the **quick** requests (ATS, HR, screening):

| Design | p50 | p95 | p99 |
|---|---|---|---|
| One mixed pool, round robin | 3.3 ms | 273 ms | 453 ms |
| One mixed pool, random | 4.5 ms | 281 ms | 467 ms |
| One mixed pool, least connections | 2.2 ms | 21.6 ms | 145 ms |
| One mixed pool, shared queue | 2.2 ms | 17.3 ms | 64 ms |
| **Dedicated pools** (2 workers for quick requests, 2 for parsing and batches) | **2.1 ms** | **4.8 ms** | **6.4 ms** |

The simulator is trusted because it reproduces queueing theory: an M/M/1 queue matched the textbook mean wait within 6 %, and an M/M/2 queue at 60 % utilization within 1 % (0.557 s simulated against 0.563 s theoretical). What the model leaves out: network, start-up, failures, real arrival patterns.

**D. Capacity arithmetic.** One application's compute (parse a PDF, ATS score, screening, HR interview, technical interview, decision) is about **22 ms**. Busiest hour assumed to carry 15 % of the day; target utilization 60 %; one spare worker:

| Volume | Busiest hour | Workers at target | With one spare |
|---|---|---|---|
| 10,000 applications a day | 0.4 per second | 1 | 2 |
| 100,000 a day | 4.2 per second | 1 | 2 |
| 1,000,000 a day | 41.7 per second | 2 | 3 |
| 10,000,000 a day | 416.7 per second | 16 | 17 |

The surprise worth stating: **raw scoring compute is not the scaling problem at any realistic size.** The real reasons to scale are isolation of slow work from quick work (section 6C), redundancy, absorbing bursts, and the parts not modelled here (speech-to-text, telephony, storage), which will cost far more than the 22 ms.

## 7. Honest limits

- One machine, one sandbox with **1 CPU**, shared and noisy; medians of three runs, ratios more reliable than milliseconds. Your timings will differ, and the machine you run on matters (the demo on your laptop was about 1.5 to 2 times slower in Day 59).
- **Process-pool speed-up is untested on real cores**; only its correctness (identical results, safe fallback) is tested.
- Cache hit rates depend on traffic: job-side work is shared by every candidate of a job, resume-side work is not. Real hit rates need real traffic; the caches-OFF column is the safe number.
- Memory figures use Linux `/proc` and are `n/a` on Windows; Python-allocation figures (tracemalloc) work everywhere.
- The simulation and capacity plan are models with stated assumptions (15 % busiest hour, 60 % target utilization), not forecasts.
- Not covered: network, disk, queue, database, speech-to-text, telephony, authentication; anything that happens under real production traffic.
- **A finding about Python versions, not caused by Day 60.** Python 3.12 made `sum()` on floats more exact. The HR scorer averages with `sum()`, and for some inputs the average lands exactly on a rounding boundary: (88.2 + 25.9 + 66.8 + 92.9) / 4 is 68.45 with the new `sum()` and 68.44999999999999 with the old one, so the same interview scores 68.5 on Python 3.12 and 68.4 on Python 3.11 or earlier. The untouched Day 59 code does this too (checked by running it both ways). In the 20-case HR sample, 2 cases moved by 0.1. That is why there are two golden files, both generated from the old code (`day60_golden_outputs.json` for Python 3.12 and later, `day60_golden_outputs_py311sum.json` for earlier), and the tests use the one matching the Python in use; one test emulates the old `sum()` on any Python. A fix for the project itself (for example `math.fsum`) would make scores identical on every Python version, but it changes scores on older Pythons, so it is a decision, not a Day 60 change.
- Existing modules changed (all behaviour-preserving, all verified above): `parsers/skill_extractor.py`, `parsers/semantic_matcher.py`, six engines that compile phrase patterns once, `ats_engine/batch_service.py`, `ats_engine/resume_parsing_service.py`. New: `utils/perf.py`, `utils/warmup.py`, `ats_engine/parallel.py`, `parsers/scaling_model.py`.

## 8. Files and how to rerun

New: `utils/perf.py`, `utils/warmup.py`, `ats_engine/parallel.py`, `parsers/scaling_model.py`, `run_day60_benchmark.py`, `run_day60_load_test.py`, `run_day60_performance_demo.py`, `tests/test_day60_performance.py`, `tests/golden/make_day60_golden.py`, `tests/golden/day60_golden_outputs.json`, `docs/day60_performance_benchmark_report.md`, `docs/day60_scalability_strategy.md`, recorded runs in `data/results/day60_runs/`, and `data/results/day60_benchmark_summary.json`, `data/results/day60_load_test.json`, logs.

```
python run_day60_performance_demo.py                       # tables above, from the recorded runs
python run_day60_benchmark.py --label after --out data/results/my_run.json     # measure on your machine
python run_day60_load_test.py                              # threads, processes, simulation, capacity
python -m pytest tests/test_day60_performance.py -v        # 50 tests
```
