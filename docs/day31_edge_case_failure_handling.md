# Day 31 — Edge Case & Failure Handling

## Scope, stated honestly up front

This module handles exactly two new detectable conditions — poor/noisy
audio and language mismatch — plus a generic crash-safety net. It does
**not** add real noise-cancellation, real language identification, or
real code-switching (intra-sentence language mixing) detection,
because none of those exist anywhere in this project to build on:

- **"Poor audio" and "background noise" are collapsed into one signal**
  here: Day 24's mock STT confidence score. This project's STT layer
  has never modeled noise and audio quality as separate signals — both
  manifest as "confidence is low" in the only data this pipeline has
  ever produced, so treating them as one condition is honest, not a
  shortcut around a distinction that was never real to begin with.
- **"Language mixing" is handled only at the whole-utterance level**:
  Day 24's `RawSTTResult.language` is a single field describing the
  entire transcribed utterance. Real code-switching would require
  token-level language identification this project has never had and
  does not attempt here. What IS handled: the whole utterance being
  tagged in a different language than the call expects.
- **The pipeline is, and remains, English-only.** Day 25's category
  keyword lexicons, Day 27's sentiment lexicon, and everything else
  downstream only understand English. A language-mismatch turn is
  handled by asking the candidate to switch to English, not by
  attempting to process what they said in another language.

## Reuse, not reimplementation

Silence is still Day 25/29's job, completely unchanged. Retry/
clarification/polite-skip messaging follows the same shape Day 29
established. The **only** change to Day 29's own file is one small,
additive public method — `force_skip_current_category()` — for edge-
case and crash recovery. Nothing else in Day 29 changes; its own 25
tests all still pass unmodified.

## Pipeline position

This wraps Day 29's controller by **composition**, sitting between the
raw STT result and Day 29's normal per-turn logic:

```
RawSTTResult (Day 24)
    → RobustConversationController.process_turn()  (Day 31, this module)
         ├─ edge case detected? → handle directly (retry/clarify/
         │                        safety fallback) — Day 29 never
         │                        sees this turn
         └─ no edge case?       → clean_transcript() (Day 24)
                                    → ConversationFlowController.
                                       process_turn()  (Day 29, unchanged)
```

## The three layers of protection

### 1. Poor / unusable audio

Day 24's confidence score is bucketed into `good` (≥0.4), `poor`
(0.15–0.4), or `unusable` (<0.15) — thresholds named as constants,
reasonable defaults in the same spirit as every prior day's. Checked
**before** language, since a low-confidence transcript's language tag
isn't trustworthy either — there's no point clarifying a language
reading produced from a signal too weak to trust in the first place.

- 1st occurrence → retry (stronger wording if "unusable" vs. "poor").
- 2nd occurrence (same category) → safety-skip this question via
  Day 29's new public method.

### 2. Language mismatch

Compares `RawSTTResult.language` against a fixed expected language
(`"en"`, since that's all this pipeline understands). 1st occurrence →
ask the candidate to switch to English. 2nd occurrence → safety-skip.
A candidate who switches to English after being asked resumes normal
processing immediately (verified in the demo: `Namaste...` → clarify →
`Sorry, I have three years...` → passes straight through).

### 3. The crash-safety net

Every `process_turn()` call is wrapped in a try/except that catches
**any** unexpected exception — not just the two conditions above — and
converts it into a graceful skip via `force_skip_current_category()`,
logging the real cause internally while showing the candidate an
ordinary "let's move on" message. Verified against a genuine exception
(`None.strip()` deep inside Day 25's pipeline, triggered by malformed
input), not a synthetic mock: the demo shows the real
`AttributeError: 'NoneType' object has no attribute 'strip'` being
caught and the call correctly advancing to the next category.

**A stronger safety property found while testing:** once a call is
already complete, `RobustConversationController` returns Day 29's own
`end_call` action **without ever touching `raw.text`/`confidence`/
`language`** — so a malformed `RawSTTResult` after call completion
can't even reach the code that would raise an exception. This is
better than routing it through the crash guard: the risky fields are
never read in the first place. Verified by
`test_call_already_complete_short_circuits_before_touching_raw_fields`.

## The call-wide safety fallback

A **consecutive** streak of edge-case turns (poor audio or language
mismatch, in any combination, across any categories) resets to zero on
every clean turn but, if it reaches 3 in a row, ends the whole call
gracefully rather than continuing to grind through more questions a
systemic connection problem will keep failing anyway. Verified in an
isolated demo run (separate from the main call, so it doesn't cut a
working demo short): 3 consecutive poor-audio turns across 2 categories
correctly trigger `safety_fallback_end_call`.

## Demo run

A 7-turn main call exercising every non-terminal condition in sequence
(clean → poor-audio retry → clean → language clarify → resolved →
crash guard → clean), completing all 5 categories successfully despite
three separate failures along the way — plus a second, isolated 3-turn
call demonstrating the consecutive-failure call-ending fallback.

## Deliverables (per the Day 31 brief)

- **Robust AI flow logic** — `RobustConversationController`, wrapping
  Day 29 without modifying its behavior.
- **Error-handling framework** — the three-layer structure above:
  specific handling for known conditions (audio, language), a generic
  catch-all for unknown ones (crash guard), and a call-wide circuit
  breaker for systemic failure (consecutive-edge-case end-call).
- **Edge-case documentation** — this document, stating plainly which
  real-world conditions from the brief are handled by an actual signal
  this project has (audio confidence, utterance-level language) versus
  which ones would need infrastructure this project doesn't have
  (noise/audio-quality separation, code-switching detection).

## Testing

24 tests in `tests/test_edge_case_handler.py`: audio quality
classification, language mismatch detection, normal passthrough (both
clean and silent), poor/unusable audio at every attempt threshold, per-
category attempt tracking, language mismatch and recovery, priority
ordering (audio checked before language), the consecutive-failure call
end, streak reset on a clean turn, the crash guard against a genuine
exception, the stronger post-completion short-circuit, and the outcome
log / serialization. 202 tests pass project-wide across the pytest-
independent test modules (Days 1–31) — zero regressions, including
Day 29's own 25 tests passing unmodified despite the one additive
method.

## Honest limitations carried forward

- No real noise/audio-quality distinction — both collapse to "low STT
  confidence," which is the only signal this project's STT layer has
  ever produced.
- No intra-utterance code-switching detection — only whole-utterance
  language mismatch is handled.
- Hard-coded to English as the only supported call language — matches
  every downstream module's actual capability, not a design ambition
  this project can currently back up.
- All thresholds (confidence cutoffs, max attempts, consecutive-failure
  ceiling) are fixed, reasonable defaults, not calibrated against real
  call data.
- The crash guard protects against *any* exception, but by design gives
  no visibility into *what specifically* went wrong without reading the
  internal notes field — appropriate for what the candidate should see,
  but a real production system would want this surfaced to engineers
  through proper logging/alerting, not just an in-memory note.
