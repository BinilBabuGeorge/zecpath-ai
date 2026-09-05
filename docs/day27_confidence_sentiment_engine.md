# Day 27 — Confidence & Sentiment Signal Analysis

## Scope, stated honestly up front

Every signal in this module is a deterministic, lexicon/pattern-based
heuristic — not a trained sentiment/confidence model. Same reasoning
as every prior day: no labeled sentiment or confidence training data
exists in this project. What IS real: a genuinely useful set of
rule-based communication signals, each independently visible and
explainable, built on top of Day 25/26's already-tested output rather
than duplicating their logic.

**A specific limitation worth stating before anything else:**
hesitation/filler detection on **text alone** is fundamentally weaker
than on audio. A real disfluency detector would use pause timing,
pitch, and speech rate from the audio signal — none of which exists
here, because Day 24's speech-to-text layer is a documented mock with
no real audio pipeline behind it. This module can only count
word-level filler patterns in the transcribed text, and several common
filler words ("like", "actually", "basically", "well") are also
ordinary content words ("I like React" vs. "it's, like, really hard to
explain"). This is handled by **excluding** those ambiguous words from
the scored hesitation count entirely, and tracking them separately as
`ambiguous_words_flagged` — visible, but not silently folded into a
number that would otherwise overstate confidence in a naive keyword
count.

## Pipeline position

```
audio → STTProvider.transcribe()      (Day 24)
      → clean_transcript()             (Day 24)
      → understand_answer()            (Day 25) → StructuredAnswer
      → score_screening_call()         (Day 26) → ScreeningScoreResult
      → build_communication_profile()  (Day 27, this module)
      → CommunicationProfile
```

**Contradiction detection is reused, not reimplemented.** Day 26's
`score_screening_call()` already cross-checks every answer in a call
against every other and produces `consistency_findings`. Day 27 takes
that list as-is for its "detect uncertainty and contradictions" task
— the same reuse discipline Day 25/26 applied to Day 23's
`normalize_answer()`.

This module's output is the first real implementation of the
`communication_score` field that `interview_ai/service.py` and
`scoring/service.py` (Day 2's original architecture) have carried as a
`0`/`TODO` placeholder since Day 2. **Wiring it into those services is
out of Day 27's stated scope** and is flagged here as a clear
follow-on, not silently done.

## The four signal types

| Signal | What it measures | Key design decision |
|---|---|---|
| **Hesitation** | Filler word/phrase density | Unambiguous fillers (um, uh, "you know", "sort of") counted directly; ambiguous words (like, actually, basically, well) tracked separately, never scored |
| **Length & pace** | Word count, words-per-minute | WPM only computed when real audio duration is supplied — otherwise honestly reports "not computed," never guesses a duration from word count |
| **Sentiment** | Positive/negative word lexicon | Small curated lexicon, net-hit-based score scaled by word count, labeled positive/neutral/negative |
| **Uncertainty** | Hedging-language density | A *different*, denser lexicon than Day 25's `_HEDGE_PHRASES` — Day 25 uses a short list as a binary vague/not-vague gate; Day 27 measures uncertainty markers as a density signal across *any* answer, including confident-sounding, complete, on-topic ones |

### Why Uncertainty is a separate lexicon from Day 25's hedge gate

Day 25's `_is_vague()` uses a short hedge-phrase list to decide whether
an *entire answer* is too thin to score at all — a binary gate. Day
27's `detect_uncertainty()` asks a different question of *any* answer,
including ones Day 25 already scored `OK`: "I think it was around
three years, probably" is a complete, on-topic, extractable answer
that still carries real uncertainty language worth surfacing as a
behavioral signal. Reusing Day 25's gate list here would conflate two
different questions, so this module defines its own, deliberately
overlapping-but-distinct lexicon and documents the difference rather
than silently reusing a list built for a different purpose.

## Communication strength score

```
score = 100
      − min(30, avg_hesitation_rate × 2)
      − min(30, avg_uncertainty_rate × 2)
      − min(30, len(consistency_findings) × 15)
      + (avg_sentiment_score × 0.2)
clamped to [0, 100]
```

Every constant here (`×2`, `×15`, `×0.2`, the `30` caps) is a
reasonable-but-arbitrary choice, not calibrated against real hiring
outcomes this project doesn't have data for — stated plainly rather
than presented as tuned.

## Demo run

Four sample answers from one candidate, deliberately mixed: a
confident/positive introduction, an hesitant answer with a genuine
experience-years conflict against the first answer, a plain skills
answer, and a negative-sentiment salary answer:

- t000: 0 fillers, positive sentiment (score 25.0), no uncertainty.
- t001: 2 fillers ("um" + "you know"), 2 uncertainty markers ("i
  think", "probably") — correctly distinct signals on the same answer.
- t003: negative sentiment (score −76.9) from "nervous" and
  "frustrating."
- Day 26's consistency check (reused, not recomputed) correctly caught
  the t000/t001 experience-years conflict (3.0 vs. 8.0 years).
- **Communication Strength Score: 68.0** — full breakdown, including
  every penalty/adjustment term, in
  `data/results/day27_communication_signal_report.json`.

## Deliverables (per the Day 27 brief)

- **Confidence analysis logic** — `detect_hesitation()`,
  `detect_uncertainty()`, and the reused Day 26 contradiction findings.
- **Sentiment scoring module** — `analyze_sentiment()`.
- **Behavioral indicators report** — `CommunicationProfile` /
  `build_communication_profile()`, with every per-answer signal and
  the call-level `communication_strength_score` breakdown fully visible.

## Testing

26 tests in `tests/test_confidence_sentiment_engine.py`: hesitation
counting (including the ambiguous-word exclusion), pace with/without
duration, sentiment across positive/negative/neutral/bounded cases,
uncertainty detection and its distinctness from hesitation, and the
full aggregate profile including contradiction reuse and score
bounding. 110 tests pass project-wide across the pytest-independent
test modules (Days 1–27) — zero regressions from this change.

## Honest limitations carried forward

- Text-only disfluency detection is a real, stated ceiling — no pause
  timing, pitch, or speech rate is available without a real audio
  pipeline behind Day 24's STT layer.
- The sentiment lexicon is small and hand-curated, not a trained
  classifier — sarcasm, negation ("not bad" reading as negative because
  of "bad"), and domain-specific phrasing will be missed or misread.
- Pace (WPM) requires the caller to supply real audio duration; without
  it, every answer's pace honestly reports "not computed."
- The communication-strength formula's constants are reasonable
  defaults, not calibrated against real hiring outcomes.
- `communication_score` in `interview_ai/service.py` and
  `scoring/service.py` remains an unwired `0`/`TODO` — this module
  produces the real number but does not connect it, by design, since
  that's outside Day 27's stated brief.
