# Day 32 — Handover: Screening-Call AI System

For a new engineer picking this up. Read `docs/day32_final_system_documentation.md`
first for the architecture; this document is about what's real, what's
mocked, and what to do next.

## What's genuinely production-quality right now

- The **decision logic** in every module (Days 25–31) — rule-based,
  deterministic, fully tested, and explainable. This is real, working
  code, not a prototype.
- The **test coverage** — 213 tests across the screening phase alone,
  all passing, with regression checks re-run after every change
  (including the two days that modified prior days' files).
- The **evidence-based validation methodology** (Days 20, 30) — if you
  add a new classifier or scorer, follow the same pattern: build a
  human-judged ground truth, measure before/after, report honestly.

## What's mocked and needs replacing before real deployment

| Component | Current state | What's needed |
|---|---|---|
| Speech-to-text (Day 24) | `RawSTTResult` is hand-constructed in every test/demo; no real audio pipeline | A real STT provider (e.g. a cloud speech API) producing genuine confidence scores and language tags |
| Sentiment lexicon (Day 27) | ~25 hand-picked words | A trained sentiment classifier, or at minimum a much larger, validated lexicon |
| Intent classification (Day 25) | Keyword/pattern matching | A trained NLU model would generalize far better to paraphrased answers |
| Location detection (Day 30's known gap) | No gazetteer — bare place names read as vague | A real places database/gazetteer |
| Multilingual support | English-only everywhere downstream of Day 24 | Real language-specific keyword lexicons and sentiment resources per supported language, not just an English-only pipeline with a language-mismatch warning bolted on |

## Known limitations, consolidated (see each day's own doc for full detail)

- **Day 25/30**: short-answer false-rejection fixed for digits/number-
  words/category-keywords, but bare place names and unrecognized degree
  abbreviations (e.g. "B.Sc" vs. "B.Tech") remain gaps — found during
  Day 32's own end-to-end evaluation, not yet fixed.
- **Day 26**: consistency checks only compare fields Day 25 already
  extracted; a contradiction phrased in an unrecognized way won't be
  caught.
- **Day 27**: text-only disfluency detection; no pause/pitch/speech-rate
  signal exists without a real audio pipeline.
- **Day 29/31**: no generative dialogue — every AI message is a fixed
  template. No code-switching detection, only whole-utterance language
  mismatch.
- **Day 32 (this day)**: a single vague/off-topic answer early in a
  call can shift subsequent turns onto the wrong category if a demo/
  test script doesn't account for Day 29's fallback-then-retry
  behavior — this is real, correct system behavior, but anyone writing
  new simulated-call scripts should verify their turn sequence
  step-by-step (as this day's own demo script's development required)
  rather than assume turn N always lands on category N.

## Prioritized next steps, if extending this system

1. Replace Day 24's mock STT with a real provider — nearly everything
   else depends on getting real confidence/language signals.
2. Wire `communication_score` (Day 27's output) into
   `scoring/service.py` and `interview_ai/service.py` — both have
   carried this as a `0`/`TODO` placeholder since Day 2; Day 27
   produces the real number but deliberately never connected it
   (documented as out of scope at the time).
3. Add a location gazetteer to close Day 30's one remaining documented
   gap.
4. Expand Day 25's degree-abbreviation keyword list (found during Day
   32's evaluation — currently only recognizes "B.Tech").
5. Consider a trained intent/sentiment model once real call data exists
   to train on — the rule-based approach was the right choice with zero
   labeled data available, but won't scale in accuracy the way a
   trained model eventually could.

## Where to look for what

- **"How does X get classified/scored?"** → the relevant day's own doc
  in `docs/` — each one explains its own logic in detail.
- **"What does the whole thing look like end to end?"** →
  `parsers/screening_pipeline.py` and `run_day32_end_to_end_demo.py`.
- **"What would the API look like?"** → `api/screening_openapi.yaml`
  and `docs/day32_screening_api_specification.md`.
- **"Is this actually tested?"** → `tests/` — every module has its own
  test file; run `python -m pytest tests/ -v` for the full suite.
