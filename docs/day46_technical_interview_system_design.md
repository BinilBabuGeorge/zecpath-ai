# Day 46 — Technical Interview System Design

## What this day is

The foundation for a fourth distinct phase of this project — technical
interviews — alongside screening (Days 22–32), HR behavioral
interviews (Days 33–45), and aptitude (Day 38). Where HR asks how a
candidate communicates and aptitude asks how they reason abstractly,
this phase asks whether they actually know the technology they claim
to, at a depth appropriate to their stated experience. Same
design-day discipline as Days 33 and 38: a real, hand-written question
bank and a real, tested session state machine, not a diagram with no
code behind it.

## A new, finer-grained experience taxonomy, stated honestly

Day 33's `ExperienceLevel` is a binary (`FRESHER` / `EXPERIENCED`).
This day's brief asks for three explicit experience bands (0–2 / 3–5 /
5+ years) mapped to three difficulty tiers — a genuinely different,
finer-grained axis, not a relabeling of Day 33's. This is the **third**
experience/role-like taxonomy in this project now (alongside Day 13's
ATS role categories and Day 33's HR experience levels), each built for
a different question that needed answering at the time. No attempt is
made to unify them — the same reasoning Day 41 gave for leaving its
two role taxonomies separate: forcing one onto a question it wasn't
built for produces worse answers than keeping purpose-built ones apart.

## Technical interview structure

```
┌─────────────────┐     ┌───────────────────┐     ┌─────────────┐     ┌──────────────────┐
│  INTRODUCTION     │ --> │ EXPERIENCE_BASED    │ --> │ CONCEPTUAL   │ --> │ SCENARIO_BASED      │ --> complete
│  (1 shared        │     │ (1 domain-specific   │     │ (2 questions  │     │ (1 question,         │
│   question)        │     │  template)            │     │  at tier)     │     │  at tier)             │
└─────────────────┘     └───────────────────┘     └─────────────┘     └──────────────────┘
```

Strictly linear and forward-only — no branching, no re-entry into an
earlier phase. This is deliberately simpler than Day 34's HR follow-up
logic, which adaptively probes mid-conversation; this day's scope is
"design the structure," not "design adaptive probing" (HR's Day 34
already covers that for its own track).

The question **set** for `CONCEPTUAL`/`SCENARIO_BASED` is chosen once,
at session start, from the domain + tier derived from
`years_of_experience` — it does not change mid-session.

## Experience-based difficulty logic

| Years of experience | Tier | Question depth |
|---|---|---|
| 0–2 | `basics` | Fundamentals (React state vs props, Java interfaces vs abstract classes, CI vs CD) |
| 3–5 | `intermediate` | Mechanism-level understanding (Node event loop, JVM garbage collection, Kubernetes probes) |
| 5+ | `advanced` | System design and trade-offs (MERN real-time collaboration architecture, Java ordered-event microservices, multi-region infrastructure) |

Boundary rule: `years <= 2` → basics, `years <= 5` → intermediate, else
advanced — matching the brief's inclusive ranges exactly, with
fractional years (e.g. 2.5) handled by the natural `<=` comparison
rather than requiring the caller to round first. Verified directly:
all 21 domain × representative-years combinations tested produce the
correct tier and exactly 5 questions each.

## Question hierarchy model

27 hand-written tiered questions (18 conceptual + 9 scenario-based)
across 3 domains × 3 tiers, chosen directly from the brief's own
examples:

| Domain | Basics | Intermediate | Advanced |
|---|---|---|---|
| MERN | React state/props, Express middleware; scenario: unnecessary re-renders | Node event loop, MongoDB indexes; scenario: intermittent 504s | React state architecture at scale, MongoDB sharding; scenario: real-time collaborative editing |
| Java | Interface vs abstract class, `static` keyword; scenario: intermittent NPE | GC mechanics, `==` vs `.equals()`; scenario: slow Spring Boot service | Thread-safe singleton design, JVM memory tuning; scenario: ordered high-throughput event processing |
| DevOps | CI vs CD, Dockerfile purpose; scenario: failed deployment recovery | K8s probes, Terraform vs Ansible; scenario: CI-passes-but-prod-differs | Zero-downtime deployment design, pipeline architecture trade-offs; scenario: multi-region HA with strict RPO/RTO |

Plus 3 domain-specific experience-based templates and 1 shared
introduction question — 31 question templates total.

Extending to a new domain means adding entries to `QUESTION_BANK` in
the same shape (2 conceptual + 1 scenario per tier, 1 experience-based
template) — the session/difficulty logic itself doesn't change.

## No automated answer evaluation here, stated honestly

This day builds the question bank, the difficulty logic, and the
session flow — it does **not** build a technical-answer scoring
engine. Scoring a technical answer would require assessing factual/
technical correctness, not just presence of keywords, structure, or
sentiment the way the HR-track engines (Days 34–37) do for behavioral
answers. That's a meaningfully different problem, explicitly left for
a future day, the same way Day 33 left HR scoring for Day 37.

## Deliverables

- **Technical interview AI blueprint** —
  `parsers/technical_interview_question_bank.py`: the domain/tier
  taxonomy, the question bank, and the session state machine.
- **Question hierarchy model** — the table above, and
  `get_tiered_questions()` as the programmatic access point.
- **Interview flow design diagram** — the phase diagram above, backed
  by `phase_sequence_followed()`, which verifies at runtime that a
  session actually stayed forward-only and matched the designed order
  (not just claimed to).

## Verification

17 new tests (`tests/test_technical_interview_question_bank.py`),
covering tier-boundary mapping (including the fractional-years case
and a negative-years rejection), question-bank structural integrity
(every domain/tier combination has exactly 2 conceptual + 1 scenario
question, no duplicate IDs, every tiered question carries skill tags),
session construction for both junior and senior candidates, and the
full forward-only flow verified end to end. All 27 hand-written
question texts confirmed unique (no accidental duplication). `pytest`
isn't installable in this build environment (no network access), so
these ran via the same assert-based Python runner used since Day 35.
Full project regression (339 tests, 322 previous + 17 new) passed
clean with zero regressions.

Demo run: three candidates (junior MERN, mid-level Java, senior
DevOps) each correctly selected a different tier — confirmed by a
built-in sanity check that all three tiers were actually exercised
across the demo, not just one tier reused three times — and all three
followed the exact designed phase order.

## Not done here (left for a future day)

- A technical-answer scoring engine (the Day 37 equivalent for this
  track) — explicitly out of scope, see above.
- Reconciling this day's three-tier experience taxonomy with Day 33's
  binary one or Day 13's ATS role categories.
- Additional domains beyond MERN/Java/DevOps — straightforward to add
  in the same shape, not done here since the brief named these three.
