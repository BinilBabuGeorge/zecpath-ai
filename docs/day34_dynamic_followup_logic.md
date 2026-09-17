# Day 34 — Dynamic Follow-Up Logic

## What this day adds

Day 33 explicitly deferred the real decision logic for HR interview
follow-ups — it built `InterviewQuestionState` with a
`follow_up_eligible` flag and a place to *record* one, but nothing
that decided *when* to ask a follow-up or *what kind*. Day 33's own
docs named this as future work: "a real decision tree over
`InterviewSession`... the same relationship Day 22's screening
question bank had to Day 29's conversation flow engine." This is that
day.

## Scope, stated honestly up front

Day 25's `understand_answer()` cannot be reused here. It classifies
FACTUAL screening answers (experience, salary, skills) against
category keyword lexicons that have no bearing on behavioral content —
"tell me about a time you disagreed with a teammate" has no "salary"
or "skills" vocabulary to score against. This module builds its own,
differently-scoped, rule-based classifier for behavioral answers —
still deterministic and keyword/pattern-based, still not a trained
model, same honesty stance as every classifier in this project.

**Reuse, not reimplementation:** `detect_repeated_answer()` is
imported directly from Day 29's `conversation_flow_engine` — it's a
generic word-overlap check with no screening-specific logic in it, so
reusing it for "prevent repetitive questioning" is the right call
rather than duplicating that function.

## Reconciling the brief's two lists into one decision

The brief names three follow-up trigger types (clarification,
deepening, example-based prompts) and two difficulty-adaptation rules
(simple → deeper probe, confident → scenario-based). These aren't two
separate mechanisms — they're the same mapping, viewed from two
angles:

| Behavioral answer quality | Follow-up type | What it does |
|---|---|---|
| **VAGUE** (hedged, "nothing comes to mind") | Clarification | Ask them to restate what they mean |
| **THIN** (short, generic, no concrete example) | Deepening | "Simple responses → deeper probe" |
| **CONFIDENT** (substantive, concrete example given) | Example-based | "Confident responses → scenario-based follow-up" |

Every answer quality gets exactly **one** follow-up type suited to it.
Adaptivity here means the *nature* of the follow-up changes with the
answer, not that only "bad" answers get followed up on — a confident,
complete answer to "tell me about your strengths" still benefits from
a scenario-based probe, which is genuine interview practice, not a
consolation prize for a good answer.

## Behavioral answer quality — a genuinely different signal from Day 25/26/29

Day 29's "thin answer" concept was purely word-count-based (≤5 words
for factual content). That doesn't transfer to behavioral answers,
where a long, generic answer ("I'm hardworking, dedicated, a fast
learner, a great communicator...") is exactly as unhelpful as a short
one. This module instead checks for **concrete example markers** —
"for example," "once," "I remember," "in my last job," a specific
narrative anchor — regardless of length. A short answer with a real
example is CONFIDENT; a long answer without one is still THIN.
Verified by `test_thin_long_but_generic_answer` and
`test_confident_with_concrete_example`.

## Preventing repetitive questioning — two distinct mechanisms

1. **A hard cap of one follow-up per question.** After one follow-up,
   even if the candidate's answer to it is still imperfect, the
   interview moves on rather than grilling further — matching how a
   real interview is actually conducted, not an interrogation.
2. **Repeated-answer detection**, reused from Day 29. If a candidate's
   response to the follow-up closely repeats what they already said,
   no second follow-up fires — asking again wouldn't surface anything
   new. Both mechanisms are independently testable and independently
   verified in the demo run.

## What's deliberately out of scope

Silence is **not** handled by this module — a missing answer isn't
something a follow-up fixes; that's retry-logic territory, the same
concern Day 29 built for the screening phase and Day 33 explicitly
deferred for this one. `decide_follow_up()` returns
`should_follow_up=False` for a silent turn with a reason naming this
boundary directly, rather than silently no-opping.

## Demo run

One complete 6-question interview, engineered so every category hits
a different, deliberate answer quality:

- `self_introduction`: vague → clarification fired, second attempt correctly capped.
- `career_journey`: thin → deepening fired, capped.
- `strengths_weaknesses`: confident → example_based fired, capped.
- `teamwork_culture_fit`: thin → deepening fired again (independently, on a different question).
- `career_goals`, `availability_commitment`: correctly skipped — not follow-up eligible by Day 33's category defaults.

All three follow-up types fired at least once in a single run, and
every repetition-prevention path (the cap) triggered exactly where
expected.

## Deliverables (per the Day 34 brief)

- **Follow-up engine module** — `parsers/hr_followup_engine.py`.
- **Adaptive questioning framework** — the quality-to-follow-up-type
  mapping, applied per-category via 18 hand-written templates (6
  categories × 3 types).
- **Decision tree logic** — `decide_follow_up()`, with its ordered
  checks (eligibility → repetition cap → repeated-answer detection →
  quality-based type selection) each independently testable.

## Testing

23 tests in `tests/test_hr_followup_engine.py`: quality classification
across all four tiers (including the long-but-generic and
short-but-concrete edge cases), the full decision tree (every
quality → type mapping, ineligibility, the cap, repeated-answer
detection, category-specific templates), and live-session integration
via `process_response_with_follow_up()`. 256 tests pass project-wide
(Days 1–34) — zero regressions, including Day 33's own 20 tests
passing unmodified despite one small, additive field
(`follow_up_type`) added to `InterviewQuestionState`.

## Honest limitations carried forward

- The concrete-example marker list is a fixed, reasonable set, not
  exhaustive — a genuine example phrased without any of these markers
  would still be misread as THIN.
- The hedge-phrase list for behavioral vagueness is separate from
  Day 25's factual hedge list and from Day 26's; some overlap is
  intentional (universal hedges like "I don't know"), but this list
  hasn't been validated against real behavioral interview transcripts.
- No calibration against real interview outcomes — the word-count
  threshold (20) and the single-follow-up cap are reasonable defaults,
  not tuned figures.
