# Day 60 – Scalability Strategy

Zecpath – AI Job Portal | Horizontal scaling strategy: load balancing, microservice scaling, autoscaling and capacity

## Objective

Design how the AI services scale horizontally for large-scale hiring operations: load balancing, microservice scaling, and how the design was tested under simulated load.

**How to read this.** Three kinds of statement are kept apart. **Measured:** from `run_day60_benchmark.py` and `run_day60_load_test.py` (details in `docs/day60_performance_benchmark_report.md`). **Modelled:** from the simulator in `parsers/scaling_model.py`, checked against queueing theory, using the measured service times. **Proposed:** targets, thresholds and stages that are starting points to tune. Nothing described here is deployed: there is no load balancer, queue, autoscaler or cluster in this project. The sandbox that measured the numbers has 1 CPU, so real multi-core scaling is **not yet measured** (section 8).

## Decisions requested

| # | Decision | Why now |
|---|---|---|
| D1 | Deploy in two tiers first: a **sync tier** (ATS, screening, interview, decision) and an **async tier** (resume parsing, batch scoring), each its own pool | Modelled: it cuts the p99 of quick requests from 64–453 ms to 6 ms at the same total worker count |
| D2 | A worker reports itself ready only after `warm_up()`; no exceptions | Measured: the first request on a cold worker takes 1,235 ms against 4 ms |
| D3 | One worker process per core; scale by adding processes and replicas, not threads | Measured: eight threads gave no more throughput than one |
| D4 | Choose the load balancer, the job queue and the autoscaler platform | None exists; section 7 says what each must provide |
| D5 | Approve the proposed targets in section 6 (SLOs, utilization, queue-age limits) | Autoscaling needs numbers to act on |

## 1. What the measurements say about scaling

- **Scoring is cheap.** One application's compute (parse a PDF, ATS, screening, HR, technical, decision) is about 22 ms. One core can do roughly 45 applications a second, about 3.9 million a day at full load. At a sensible 60 % target utilization with a busy hour carrying 15 % of the day, 1,000,000 applications a day needs 2 workers.
- **So scale is about shape, not size.** The reasons to scale out are redundancy (a worker will die), isolating slow work from quick work, absorbing bursts, and the parts not modelled here (speech-to-text, telephony, storage) which will cost far more than the scoring.
- **Python threads do not help.** Scoring is pure-Python CPU work; eight threads gave 283 requests per second against 305 for one, with latency rising in proportion. Use processes.
- **The AI layer is stateless** (Day 59, decision D1). Any worker can serve any request, so horizontal scaling needs no session affinity and no shared database. The only shared state is the idempotency store for job creation.
- **Per-process memory matters more than per-request memory.** A 100-candidate batch peaks at 1.8 MB of Python memory (about 18 KB per candidate) and keeps almost none of it; a worker costs 154 MB if it scores resumes (scikit-learn, NumPy, SciPy), 41 MB if it parses files, 19 MB if it only scores decisions, interviews or screening.

## 2. Load balancing

**Where load balancing happens.** In front of the sync tier: a layer-7 (HTTP) balancer between the AI gateway and its workers. For the async tier there is no balancer, but a queue with competing consumers: a worker takes the next job when it is free.

**Simulation** (a model, not a measurement): 4 workers, 60 % utilization, the benchmark's measured service times, 312,394 requests over 10 simulated minutes. Latency of the quick requests (ATS, HR, screening):

| Design | p50 | p95 | p99 |
|---|---|---|---|
| Mixed pool, round robin | 3.3 ms | 273 ms | 453 ms |
| Mixed pool, random | 4.5 ms | 281 ms | 467 ms |
| Mixed pool, least connections | 2.2 ms | 21.6 ms | 145 ms |
| Mixed pool, shared queue | 2.2 ms | 17.3 ms | 64 ms |
| Dedicated pools (2 for quick, 2 for slow) | 2.1 ms | 4.8 ms | 6.4 ms |

**What it shows.** Blind policies (round robin, random) send a 3 ms request to a worker that is in the middle of a 300 ms batch, and the 3 ms request waits. Policies that look at load (least connections) or use one shared queue do much better. **Separating the slow work from the quick work does best of all**, because a quick request then never waits behind a slow one.

**Recommendation.**

| Tier | Policy | Why |
|---|---|---|
| Sync | Least outstanding requests (least connections) across identical workers | Needs no queue, and adapts when some requests are slower |
| Async | One shared queue, competing consumers, one job at a time per worker | Best measured result among mixed designs; jobs are retried and visible (`queued → running → completed`) |
| Both | Health check on a readiness endpoint that turns green only after `warm_up()`; remove an unhealthy worker; drain in-flight requests before stopping one | A cold or dying worker must never receive traffic |

**Not needed now:** sticky sessions (stateless), consistent hashing by job description (it would improve cache hits for batches, but the caches are small and the gain is unmeasured; revisit if profiling in production shows the job-side cache missing).

**Timeouts and retries** follow Day 59: 2 s timeout for sync operations, and only `429`, `503`, `504` (and one retry of `internal_error`) are retried, with exponential backoff and full jitter, so that a struggling tier is not hit by synchronized retries.

## 3. Microservice scaling

**Split by cost profile, in stages, only when the metrics justify the next stage.**

| Stage | Layout | When |
|---|---|---|
| 0 | One process serves everything (today) | Development, demos |
| 1 | **Two pools**: sync tier and async tier (D1) | First deployment |
| 2 | Split by profile: (a) decision + interview + screening, (b) ATS scoring, (c) resume parsing, (d) batch scoring | When the dashboard shows one profile limiting another, or memory per node becomes the cost |
| 3 | Per-tenant or per-region pools | Only for contractual isolation or data residency |

**The profiles** (measured):

| Service | Latency | Memory per worker | Scale on |
|---|---|---|---|
| Decision, interview, screening scoring | 0.04–1.7 ms | 19 MB | requests per second, CPU |
| ATS single scoring | 3 ms | 154 MB | requests per second, CPU |
| Resume parsing (async) | 7–16 ms, PDF-heavy | 41 MB plus the parsing libraries | queue depth and age |
| Batch scoring (async) | 3 ms per candidate, so 300 ms per 100 | 154 MB | queue depth and age |

**Why split.** Failure isolation (a bad PDF can exhaust a parsing worker without touching interview scoring); different latency goals; the memory profile (the 19 MB services no longer carry scikit-learn after the Day 60 change, so many can share a node); and independent deployment. **The cost** is more moving parts to run and monitor, which is why Stage 1 comes first and Stage 2 needs evidence.

**Inside the async tier**, large batches can use the process pool in `ats_engine/parallel.py` (results identical to sequential, safe fallback, workers reused and warmed), but across hosts the simpler way is more queue consumers. Keep the pool for single-host use; it is correct but its speed-up is not yet measured (section 8).

## 4. Caching and memory at scale

- **Caches are per process and bounded**: skill-extraction results (7.6 MB), fuzzy matches (1.9 MB), parse results by file content (15.3 MB). Together they have a hard ceiling under 26 MB per worker, however long it runs; each cache reports hits, misses and evictions (`utils.perf.all_cache_stats()`) and all can be turned off with `ZECPATH_CACHE=off`.
- **No shared (distributed) cache for scoring.** A scoring request costs 3 ms; a network round trip to a shared cache costs about as much, so it would not pay. Revisit only for something that costs far more, such as parsing a PDF.
- **The one shared store is the idempotency store** from Day 59 (key, request fingerprint, stored response, about 24 hours): this must be a shared cache with a time limit, because a retry may land on a different worker.
- **Memory arithmetic** for planning: a node with 4 cores running one ATS worker per core needs about 0.6 GB for the workers plus headroom; 19 MB services are almost free by comparison. With the `spawn` start method used by the pool and by Windows, workers do not share memory, so each pays its own import cost; warm them once at start.

## 5. Autoscaling

| Tier | Scale-out signal (proposed) | Scale-in | Notes |
|---|---|---|---|
| Sync | Average CPU over 60 % for 2 minutes, or p95 latency over target for 2 minutes | CPU under 30 % for 10 minutes, one worker at a time | Never fewer than 2 replicas |
| Async | Oldest queued job older than 30 s, or queue depth above 2 × the number of workers | Queue empty for 10 minutes | A worker takes one job at a time |

**Sizing rule:** `workers = ceil(arrival rate × service time / 0.6)`, plus one spare (`parsers.scaling_model.workers_needed`). **Start-up time** is about 1 s (warm-up), so scale-out is quick; a worker is added to the pool only when ready. **Protect the system from a runaway:** a maximum replica count, an alert when it is reached, and no scale-in during a burst.

## 6. Capacity plan and targets

One application's compute is about 22 ms. Assumptions: busiest hour carries 15 % of the day, target utilization 60 %, one spare worker. All compute only.

| Volume | Busiest hour | Workers at target | With one spare |
|---|---|---|---|
| 10,000 applications a day | 0.4 per second | 1 | 2 |
| 100,000 a day | 4.2 per second | 1 | 2 |
| 1,000,000 a day | 41.7 per second | 2 | 3 |
| 10,000,000 a day | 416.7 per second | 16 | 17 |

**Proposed targets** (to tune against real traffic): sync operations p95 under 50 ms of compute at the worker and under 200 ms at the gateway; 99.9 % of sync requests answered inside the 2 s timeout; async jobs started within 30 s of submission at the busiest hour; utilization 40–60 %; error rate by code watched, not just in total.

## 7. Overload, failure and observability

**Overload.** When the sync tier is saturated, answer `429` with `Retry-After` (Day 59) instead of queuing without limit; cap the async queue and reject new jobs with `503` when it is full; **shed batch work before quick work** (pause consumers of the batch queue first). A circuit breaker on a failing tier gives it time to recover.

**Failure.** One worker dying loses at most the requests it was serving; the balancer retries them (safe, since scoring is deterministic and job creation carries an `Idempotency-Key`). A job that fails after its attempts goes to a dead-letter list for a person (Day 59).

**What the platform must provide** (decision D4): a layer-7 load balancer with least-outstanding-requests, readiness checks and connection draining; a durable queue with competing consumers, visibility timeouts and a dead-letter queue; an autoscaler that can act on CPU, latency and queue age; a shared cache with expiry for idempotency keys.

**Metrics to collect:** p50, p95 and p99 latency per operation; requests per second; errors by code; retries; queue depth and age of the oldest job; worker CPU and resident memory; cache hit rate, entries and evictions (`all_cache_stats()`); warm-up time. **Logging:** per-request INFO lines were measured at 0.0–0.2 ms each, so they are not a problem now; at high volume sample them. Logs must never contain resume text, answers or transcripts (Day 59, tested).

## 8. How this was tested, and what is still open

| Test | Result | Kind |
|---|---|---|
| Eight threads against one ATS service | 305 → 317 → 284 → 283 requests per second for 1, 2, 4, 8 threads; latency rose in proportion | Measured |
| 1, 2, 4 worker processes | 284, 287, 257 requests per second. **The machine has 1 CPU, so this cannot show scaling**; it shows extra processes cost little when they cannot help (about 10 % at four processes here) | Measured, limited |
| Load-balancing policies and dedicated pools | Table in section 2 | Modelled; simulator matches M/M/1 within 6 % and M/M/2 within 1 % |
| Capacity plan | Table in section 6 | Arithmetic from measured service times |
| Optimized code against the old code | Identical answers (golden file, fingerprints) | Measured |

**Still open.**

1. **Run `python run_day60_load_test.py` on a multi-core machine** to measure the real scaling curve for 1, 2, 4 processes (expect near-linear until the cores run out). This is the missing measurement.
2. Real traffic and real arrival patterns; the model assumes random arrivals and one request at a time per worker.
3. Speech-to-text, telephony, object storage and database costs, which will dominate real latency and cost.
4. The gateway, queue, autoscaler and job store do not exist (Day 59); everything here is a plan for them.
5. Whether to revisit sharing a vocabulary across a batch for speed; Day 59 measured a zone change for one candidate in 16, so the answer today is no.
6. The thresholds in sections 5 and 6 are proposals.

## 9. Files

`parsers/scaling_model.py` (capacity arithmetic and simulator), `run_day60_load_test.py`, `utils/perf.py`, `utils/warmup.py`, `ats_engine/parallel.py`, results in `data/results/day60_load_test.json`. Tests: `tests/test_day60_performance.py`.
