# Day 50 — Machine Test AI Design

## What this day is, and the decision it makes up front

A machine test evaluates code a candidate wrote. The dangerous part of that
is **running untrusted code**. Doing it safely needs real isolation: a
container or microVM with no network, CPU / memory / time limits, and an
ephemeral filesystem. This project has no such sandbox, and an `exec()` call
inside a scoring service is not a substitute for one.

So this design **never runs candidate code**. The engine does two safe things:

1. **Scores execution results** — pass/fail per test case, runtimes — that a
   future sandbox runner would hand it. The contract (`CaseResult`,
   `ExecutionRun`) is specified and tested; the runner itself is not built.
2. **Analyses code statically** with `ast.parse` only. Parsing never
   executes anything. A test proves it: a snippet that would write a file if
   run does not write it when analysed.

The sandbox is listed as **not implemented, in every report**, the same
discipline Days 48 and 49 applied to camera and audio signals.

## Machine test types

| Type | What it tests | How it is evaluated | Auto-scorable? |
|---|---|---|---|
| **Coding problem** | Writing a working, efficient solution | Execution results + runtime vs reference + static quality + process | Yes, once a sandbox exists |
| **Debugging task** | Finding and fixing a bug in given code | Same, with weight shifted to correctness and process; efficiency not applicable | Yes, once a sandbox exists |
| **File-based task** | Producing correct output files from input files | Execution results over the produced files + quality + process | Yes, once a sandbox exists |
| **Mini system design** | Choosing and justifying an architecture | **Keyword / rubric proxy** (component coverage + reasoning markers), **always flagged for human review** | **No** — a person must read it |

Mini system design cannot be executed, and a keyword rubric can be gamed by
stuffing keywords. The engine says so in the report instead of presenting a
number as if it were a verdict.

## Machine test AI framework

```
 task authoring (not built)         sandbox runner (NOT BUILT)          candidate editor (not built)
┌──────────────────────┐          ┌─────────────────────────┐        ┌──────────────────────────┐
│ task + test cases     │          │ runs code in isolation   │        │ code snapshots over time  │
│ (visible + hidden),   │ ───────> │ returns per-case result, │ <───── │ "run tests" button events │
│ reference runtime     │          │ runtime, timeout, stdout │        └──────────────────────────┘
└──────────────────────┘          └───────────┬─────────────┘
                                               │ ExecutionRun / CodeSnapshot / TaskAttempt
                                               v
                          ┌─────────────────────────────────────────────┐
                          │ Machine Test Evaluation Engine (BUILT)       │
                          │ 1. select evidence ≤ deadline                │
                          │ 2. correctness  3. efficiency  4. quality    │
                          │ 5. problem-solving proxy  6. time (gated)    │
                          │ 7. redistribute unassessable weights         │
                          │ 8. difficulty-weighted aggregation + flags   │
                          └──────────────────┬──────────────────────────┘
                                              v
                     MachineTestReport  ──>  human review / Phase 70 aggregation
```

Code: `parsers/machine_test_evaluation_engine.py`.

## Evaluation metrics

Every metric is a 0–100 ratio, which is how scores stay comparable across
difficulty levels (the Day 47 approach).

| Metric | How it is computed | Notes |
|---|---|---|
| **Correctness** | Weighted pass fraction of the final run. Hidden cases weigh **1.5×** visible ones. A missing case counts as failed; a compile error fails everything | Hidden weighting stops hard-coding the visible samples from paying |
| **Efficiency** | Median runtime of passing cases ÷ the reference solution's runtime. ≤ 1.5× → 100, ≥ 10× → 0, log-linear between. Timeouts reduce it | **Measured runtime on the test inputs, not big-O analysis.** Multiplied by pass fraction |
| **Code quality** | AST analysis, **Python only**: function length (> 40 lines), nesting depth (> 3), cyclomatic complexity (> 10), naming conventions, missing docstrings, bad practices (bare `except`, `eval`/`exec`, wildcard import, mutable default argument) | Every finding has a code, line and penalty; each category is capped. `elif` chains are not counted as extra nesting |
| **Problem-solving approach** | A **process proxy** from the timeline: ran tests repeatedly, improved or passed first time, recovered from a compile error, worked incrementally, regressions deduct | Not a measure of reasoning. Starts at 20, so doing nothing earns almost nothing |
| **Time** | See below | Weak signal, low weight, gated |

Process and quality are deliberately labelled as proxies. A report that said
"problem-solving: 85" without saying how it was derived would be implying
more than the evidence supports.

## Input / output capture

| Captured | Schema | Used for |
|---|---|---|
| **Code snapshots** | `CodeSnapshot(timestamp, code, trigger)` — taken on an interval, on each run, and on submit | Final-code quality analysis; progress timeline |
| **Execution results** | `ExecutionRun(timestamp, per-case CaseResult, compile_error)` where `CaseResult(case_id, passed, runtime_ms, timed_out)` | Correctness, efficiency, process |
| **stdout / stderr** | Truncated to the **last 2,000 characters** per run | Human reviewer only — never scored |
| **Design write-up** | Free text | System-design proxy |

- Evidence **after the deadline is ignored** and flagged.
- Snapshots over 100,000 characters are not analysed.
- `capture_summary()` reports sizes and counts for audit, not content.
- Captured code can contain personal data. Consent capture, retention rules
  and access control are **not built** (Day 43 finding; PRD Phase 75).

## Time-based scoring logic

```
fraction = time_taken / effective_limit
raw      = 100                           if fraction ≤ 0.5
           100 → 60 (linear)             if 0.5 < fraction < 1.0
           60                            at the limit
time     = raw × weighted pass fraction
```

- **Gated by correctness:** fast and wrong earns nothing. Demo scenario D
  submits at 4% of the limit with nothing passing and gets 0 time credit.
- **Low weight (10%):** speed is a weak predictor of skill.
- **Accommodations:** `extension_multiplier ≥ 1.0` scales the deadline for an
  approved accommodation. It can never shorten the time.
- **Late submission** (explicit submit time after the deadline): flagged,
  no time credit, human review required.
- Time limits are per task, so a basics task and an advanced task are each
  judged against their own limit.

## Task evaluation logic

| Task type | Correctness | Efficiency | Quality | Process | Time |
|---|---|---|---|---|---|
| Coding | 0.45 | 0.20 | 0.15 | 0.10 | 0.10 |
| Debugging | 0.55 | — | 0.15 | 0.20 | 0.10 |
| File-based | 0.55 | 0.05 | 0.15 | 0.15 | 0.10 |
| System design | 0.60 (coverage) | — | — | 0.30 (reasoning) | 0.10 |

**Redistribution.** A metric that *cannot be assessed* — no reference
runtime, non-Python code, no timeline — is reported as "not assessed" and its
weight is spread proportionally over the assessed metrics. It is never
silently scored as zero. This is the same pattern as Day 13's ATS scorer and
Day 41's unified scorer.

A metric that *can* be assessed but earns nothing (efficiency of a solution
that passes nothing) scores **0** — it is not redistributed, because that
would let a failed solution lean on its style score.

**Anti-gaming signals** (flags, no score change):

- `PASSES_VISIBLE_FAILS_HIDDEN` — passes every visible case but fails most
  hidden ones: possible special-casing of the samples.
- `SANDBOX_RELEVANT_API` — imports `subprocess` / `socket` / `ctypes`, calls
  `os.system`, etc. Informational: the sandbox is the real control, but a
  human should glance at it.

**Quality counts at half value** when the solution passes nothing
(`QUALITY_FLOOR = 0.5`): clean code that does not work is worth something,
but not much.

## Scoring model for real-world tasks

1. Score each task 0–100 from its redistributed metric weights.
2. Overall score = **difficulty-weighted average** (basics 1.0,
   intermediate 1.5, advanced 2.0), reusing Day 46's `DifficultyTier`.
3. Indicative band: ≥ 75 `strong`, ≥ 50 `moderate`, else `limited`.
4. `automated_decision` is always `"none"`. The next stage (PRD Phase 70/71)
   aggregates rounds; this report is an input to that and to a human.

## Sandbox runner requirements (specification for a future build)

Not built — recorded here so the contract is not lost:

- Each run in a fresh container or microVM, destroyed afterwards
- No network; read-only base filesystem; small ephemeral scratch space
- Hard CPU, memory, process-count and wall-clock limits per case
- Non-root user, dropped capabilities, seccomp-style syscall filtering
- Per-case result reporting as `CaseResult`, plus a measured reference
  runtime per task on the same hardware class
- Output truncation on the sandbox side, before anything reaches the engine

## Integration plan

| Integration point | Plan | Status |
|---|---|---|
| Day 46 `DifficultyTier` | Reused for task difficulty | **Done** |
| Day 47 normalization pattern | 0–100 ratios + difficulty-weighted aggregation | **Done** |
| Day 49 integrity tag | `build_machine_test_report(attempts, integrity_risk_tag=...)` carries the tag through; MEDIUM/HIGH adds a human-review requirement and **never changes a score** | **Done, tested** |
| Day 41 unified scoring | `ROUND_NAMES` is currently `ats / screening / hr_interview`; a `machine_test` round would be a deliberate extension | Planned, not wired |
| PRD Phase 62 (test generation) | Task authoring is not built; `DifficultyTier` is the hook | Not built |
| PRD Phase 63 (live coding editor) | Needs an editor and the sandbox | Not built |
| PRD Phase 64 (AI guidance) | Not designed here | Not built |
| PRD Phase 67 (copy-paste abuse) | Would extend Day 49's event model with paste events | Not built |
| PRD Phase 68 (screen recording) | Not built; snapshots are the text-only substitute | Not built |

## Fairness and false-positive design

- **Accommodations** extend deadlines; speed is low-weight and gated.
- **Language support is uneven:** quality analysis covers Python only; other
  languages are "not assessed" with weights redistributed, so a JavaScript
  candidate is not scored as having bad code.
- **Test quality drives everything.** Weak or leaky test cases produce
  misleading correctness scores; test authoring needs its own review.
- **Hidden-case weighting** rewards genuine solutions over sample-fitting.
- **No demographic input** of any kind.
- **The process proxy can mislead:** a strong candidate who thinks first and
  runs once scores lower on that metric than one who iterates. Its weight is
  therefore 10–20%, never dominant.

## Demo results

Synthetic stand-ins: the execution results and code snapshots are
hand-written, because no sandbox exists (labelled in the demo). The scoring,
static analysis, time logic and flags are real.

| Scenario | Task score | Why |
|---|---|---|
| A. Iterates, correct, efficient, clean, fast | **98.5** | Strong on every metric |
| B. Passes only the visible samples | **43.5** | `PASSES_VISIBLE_FAILS_HIDDEN`; flagged for review |
| C. Correct but 9× slower, messy, finishes at 95% of the limit | **67.9** | Correctness 100, efficiency 4.6, quality 67, reduced time credit |
| D. Submits at 4% of the limit, nothing passes | **10.5** | Zero time and efficiency credit; quality at half value |
| E. JavaScript debugging task | **96.5** | Quality "not assessed"; weights still sum to 1.0 |
| F. Hostile snippet that writes a file if run | — | Analysed, **not executed**; file does not exist afterwards |
| Full mixed test with a real Day 49 `MEDIUM` tag | **98.1** | Tag added review, score unchanged |

## Known limits

- No sandbox runner, so no real candidate code has been executed or scored end to end.
- Efficiency is measured runtime, not algorithmic complexity.
- No plagiarism or AI-generated-code detection.
- Quality analysis is Python only.
- System-design scoring is a gameable keyword proxy.
- Weights and thresholds are reasoned, not calibrated; no labelled data exists.
- Consent, retention and access control for captured code are not built.
