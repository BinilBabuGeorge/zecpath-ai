# Day 29 — AI Conversation Flow Design

## Scope, stated honestly up front

This is a deterministic decision tree / state machine over Day 25's
already-tested quality gating — not an LLM-driven conversational
agent. Every message the AI would say is a fixed template filled from
the current category and attempt number, exactly the same
"template, not generated prose" discipline Day 28 applied to report
bullets. A real conversational AI would want natural, varied phrasing
generated per-turn; this module deliberately does not claim that,
since nothing here has been tested against real candidate speech
patterns, only against hand-written example text like every prior
demo.

**Reuse, not reimplementation.** Silence and off-topic/vague detection
are **not** redone here — Day 25's `understand_answer()` already
produces `AnswerQuality.MISSING/VAGUE/OFF_TOPIC/OK` for exactly this
purpose, and this module calls it directly for every turn. Only two
genuinely new detectors were needed for what Day 25 doesn't cover:

- **Confusion** — a candidate reacting to the *question itself*
  ("what do you mean?", "can you repeat that?"), which is fundamentally
  different from judging an answer's content, so it isn't and
  shouldn't be part of Day 25's quality gate.
- **Repeated answers** — comparing a turn's text against everything
  said earlier in the *same call*, which requires call-level state
  Day 25 never had (it evaluates one answer at a time, with no memory
  of the rest of the call).

## Pipeline position

This sits **beside** Days 25–28, not after them. Those days evaluate a
call's answers once it's transcribed. This module decides, live, what
the AI should ask/say next while the call is still happening:

```
(existing) audio → STT → clean → understand_answer() → scoring/report
(this day) ConversationFlowController.process_turn() — decides the
           NEXT prompt the AI plays, turn by turn, during the call
```

## Decision priority order

For each turn, checks run in this order, with the reasoning for the
order stated in code comments:

1. **Confusion** — checked first, since it's a reaction to the
   question and should be resolved before judging the (non-)answer
   that came with it.
2. **Silence** — nothing else to evaluate if there's no speech.
3. **Repeated answer** — checked before quality, since a copy-pasted
   answer shouldn't be scored as new content for the current category.
4. **Off-topic** (Day 25) → redirect.
5. **Vague** (Day 25) → fallback.
6. **OK** (Day 25) → thin-answer follow-up, or advance.

### A deliberate simplification: one shared attempt counter per category

`attempts` counts *every* engagement with a category — silences,
confusion, off-topic, vague — not a separate counter per failure type.
This means a category that's already exhausted its silence retries and
then receives a confusion signal correctly moves straight to a polite
skip, rather than opening a *second* independent retry loop for
confusion on top of the one already used for silence. Verified by
`test_repeated_confusion_eventually_skips` and confirmed in the demo
run.

## Handling each condition

| Condition | First occurrence | Second occurrence (same category) |
|---|---|---|
| Silence | Retry (re-prompt) | Simplified fallback question |
| Confusion | Simplified restatement | Polite skip |
| Off-topic | Redirect, naming the expected category | Polite skip |
| Vague | Simplified fallback question | Polite skip |
| Repeated answer | Acknowledge + advance immediately (no retry) | — |
| OK, thin (≤5 words) | One follow-up probe | (next OK answer just advances) |
| OK, substantial | Advance immediately | — |

Fallback questions and confusion clarifications deliberately **share
one bank** of simplified restatements — both situations need the same
thing (a shorter, plainer version of the same question), so one
templated bank serves both rather than maintaining two near-duplicate
phrasing sets.

## Demo run

A 15-turn simulated call, engineered to exercise **every** `FlowAction`
at least once (verified turn-by-turn before finalizing, not just
described):

- Silence → retry → OK (introduction)
- Silence ×2 → fallback → OK (education)
- Confusion → clarify → thin OK → follow-up → OK (experience)
- Off-topic ×2 → redirect → polite skip (skills)
- Vague → fallback → OK (location)
- Repeated answer (verbatim match against an earlier off-topic
  turn) → acknowledge + advance (salary)
- OK → advance (notice_period) → **call complete**
- One more turn after completion → `end_call`

Final action-type distribution:
`{retry_silence: 2, advance: 5, ask_fallback: 2, clarify_confusion: 1,
ask_follow_up: 1, redirect_off_topic: 1, polite_skip: 1,
acknowledge_repeated: 1, end_call: 1}` — 15 actions total, full detail
in `data/results/day29_conversation_flow_report.json`.

## Deliverables (per the Day 29 brief)

- **AI call flow logic** — the decision-tree priority order and
  per-condition handlers in `ConversationFlowController.process_turn()`.
- **Conversation state machine** — `ConversationFlowController`, with
  explicit per-category state (`attempts`, `fallback_used`,
  `follow_up_used`), a call-wide history for repeated-answer detection,
  and a full `action_log` audit trail.
- **Error-handling flow design** — the silence/confusion/repeated/
  off-topic/vague handling table above, each with a bounded retry
  count and a defined graceful exit (polite skip) rather than an
  unbounded loop.

## Testing

25 tests in `tests/test_conversation_flow_engine.py`: both new
detectors independently, every condition's first-occurrence and
repeat-occurrence behavior, the thin-answer follow-up (triggered once
per category, never twice), call completion and post-completion
`end_call` behavior, the action log, and the default category list
matching Day 22's `CATEGORIES` exactly. 157 tests pass project-wide
across the pytest-independent test modules (Days 1–29) — zero
regressions from this change.

## Honest limitations carried forward

- No generative dialogue — every message is a fixed template; a real
  deployment would likely want more natural, varied phrasing, which
  is explicitly out of scope here.
- Repeated-answer detection is lexical (word-overlap), not semantic —
  two answers saying the same thing in different words will not be
  caught. Stated plainly, not smoothed over.
- All thresholds (`max attempts = 2`, `thin answer ≤ 5 words`, `80%
  word overlap for repeats`) are fixed, reasonable defaults, not
  calibrated against real call data.
- This module has not been tested against real, messy candidate
  speech — only hand-written example text, same as every other demo
  in this project.
