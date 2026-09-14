# Day 32 — Final System Documentation: The Screening-Call AI System

This document is the architectural map of Days 22–31 — the screening-
call phase — now that Day 32 has wired every piece together into one
callable pipeline. It points to each day's own doc for detail rather
than duplicating it; this is the "how it all fits together" view.

## The complete pipeline

```
Day 22: screening_question_bank.py
    CATEGORIES, generate_screening_questions()
    -- defines what gets asked and in what order
        |
        v
Day 24: speech_to_text.py
    RawSTTResult, clean_transcript()
    -- mock STT layer: confidence score, language tag, cleaned text
        |
        v
Day 31: edge_case_handler.py
    RobustConversationController  (wraps Day 29 by composition)
    -- catches poor audio, language mismatch, and any unexpected
       exception BEFORE Day 29 ever sees a bad turn
        |
        v
Day 29: conversation_flow_engine.py
    ConversationFlowController
    -- the live decision tree: retry / clarify / redirect / fallback /
       follow-up / advance / polite-skip / end-call
        |  (calls, per turn:)
        v
Day 25: answer_intent_engine.py
    understand_answer() -> StructuredAnswer
    -- intent classification, entity extraction, quality gating
       (Day 30 fixed a real false-rejection bug here)
        |
        v  (once the call is over, ALL StructuredAnswers together:)
Day 26: screening_scoring_engine.py
    score_screening_call() -> ScreeningScoreResult
    -- per-question Clarity/Relevance/Completeness/Consistency scoring
        |
        v
Day 27: confidence_sentiment_engine.py
    build_communication_profile() -> CommunicationProfile
    -- hesitation, pace, sentiment, uncertainty; reuses Day 26's
       consistency findings rather than re-detecting contradictions
        |
        v
Day 28: screening_report_generator.py
    generate_screening_report() -> ScreeningReport
    -- template-filled (never LLM-generated) recruiter report:
       key answers, strengths, risks, missing data, highlights
        |
        v
Day 32: screening_pipeline.py  <-- THIS DAY
    run_screening_call()
    -- the assembly: threads a list of RawSTTResults through every
       layer above and returns one final EndToEndCallResult
```

## Module responsibility table

| Day | File | Responsibility | Depends on |
|---|---|---|---|
| 22 | `screening_question_bank.py` | Question categories & templates | — |
| 24 | `speech_to_text.py` | Mock STT, transcript cleaning | — |
| 25 | `answer_intent_engine.py` | Intent classification, entity extraction, quality gating | Day 4 (`skill_extractor`), Day 23 (`normalize_answer`) |
| 26 | `screening_scoring_engine.py` | Per-question explainable scoring | Day 25 |
| 27 | `confidence_sentiment_engine.py` | Hesitation/sentiment/uncertainty signals | Day 25, Day 26 (reuses consistency findings) |
| 28 | `screening_report_generator.py` | Recruiter-facing report, two export formats | Day 25, Day 26, Day 27 |
| 29 | `conversation_flow_engine.py` | Live per-turn decision tree | Day 22, Day 25 |
| 30 | *(fix to Day 25)* | False-rejection bug fix, evidence-based testing methodology | Day 25 |
| 31 | `edge_case_handler.py` | Audio/language/crash resilience, wraps Day 29 | Day 24, Day 29 (+1 additive method) |
| 32 | `screening_pipeline.py` | End-to-end assembly | All of the above |

## Design principles that held across all ten days

1. **Rule-based and explainable, never a claimed ML model.** Every
   classifier, scorer, and signal detector in this phase is
   deterministic and inspectable. Stated explicitly in every single
   day's docs, not just this one.
2. **Reuse over reimplementation.** Day 27 doesn't re-detect
   contradictions — it reuses Day 26's own `consistency_findings`.
   Day 29 doesn't re-detect silence — it calls Day 25's
   `understand_answer()` directly. Day 31 doesn't rebuild Day 29's
   state machine — it wraps it by composition.
3. **Honestly bounded scope, stated in each day's own docs.** Text-only
   disfluency detection (Day 27), no code-switching detection (Day 31),
   no location gazetteer (Day 30), English-only throughout — every one
   of these is a stated limitation, not a silent gap discovered later.
4. **Evidence-based validation, not assumed correctness.** Day 20 and
   Day 30 both built human-judged ground truths and reported measured
   before/after numbers, including a bug found in the *test harness
   itself* during Day 30 — caught and disclosed, not swept under the rug.

## What Day 32 specifically closes

Before this day, no single test or demo ran a candidate through the
*entire* chain above — each day tested against its immediate
predecessor's output only. `parsers/screening_pipeline.py`'s
`run_screening_call()` is the first code in this project to do that,
and `run_day32_end_to_end_demo.py` is the first script to actually run
it, across three distinct simulated candidates (strong/mixed/weak) —
see `docs/day32_screening_ai_evaluation_report.md` for the results.

Building that first true end-to-end run also surfaced one small, real
integration gap: Day 28's report builder didn't yet surface *why* a
question was missing (genuine silence vs. an edge-case skip) in its
Missing Data section — only a generic line. Fixed with a small,
backward-compatible addition to `_build_missing_data()`, verified
against Day 28's own existing tests (all still pass) plus new Day 32
tests covering the distinction.

For API-level detail, see `docs/day32_screening_api_specification.md`
and `api/screening_openapi.yaml`. For a new-engineer orientation, see
`docs/day32_handover.md`.
