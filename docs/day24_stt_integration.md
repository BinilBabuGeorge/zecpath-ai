# Day 24 — Speech-to-Text Integration & Cleaning

## Scope, stated honestly up front

This sandbox has no network access and no real audio files exist
anywhere in this project. **There is no real speech-to-text integration
here, and there cannot honestly be one under these constraints** —
claiming otherwise would be exactly the kind of fabricated capability
this project has consistently avoided (Day 16: "PDF/DOCX not
implemented"; Day 23: "nothing performs real speech-to-text").

What IS real and independently verified this session:
1. A genuine, usable **integration interface** (`STTProvider`) any real
   vendor could implement.
2. A clearly-labeled **mock provider** (`MockSTTProvider`) that injects
   realistic, seeded, reproducible noise into known ground-truth text —
   the only honest way to test "multiple accents and noise conditions"
   without real audio.
3. A fully real, working **`clean_transcript()`** — this is the actual
   deliverable, and it doesn't depend on the mock being realistic to be
   independently correct and tested.

## Pipeline position

```
audio → STTProvider.transcribe() → raw noisy text
      → clean_transcript() (Day 24, this module)
      → TranscriptTurn.raw_transcript (Day 23)
      → normalize_answer() (Day 23)
      → typed value
```

Day 24 sits between a raw ASR engine's output and Day 23's typed-value
normalization — cleaning (fillers, case, punctuation, corrections,
cutoffs) happens first, so Day 23's number/duration/yes-no extraction
sees text closer to what a careful human transcriber would have
produced.

## The clean transcript processor — what it does

`clean_transcript(raw: RawSTTResult) -> CleanedTranscript`, in order:

1. **Silence check** — `is_silent=True` or empty/whitespace-only text →
   `CleanStatus.SILENT` immediately, with a note distinguishing "no
   speech detected" from "a low-confidence mumble was transcribed" —
   these call for different next actions (re-prompt vs. flag for
   review).
2. **Self-correction detection** — looks for markers ("no wait", "sorry,
   I mean", "actually no", "scratch that", em/en dashes) and keeps only
   the text **after the last** marker (the candidate's final, corrected
   statement), not the abandoned first attempt.
3. **Filler word removal** — strips only unambiguous discourse fillers
   (`um`, `uh`, `erm`, `hmm`, "you know", "I mean"), word-boundary safe
   so "umbrella" is never mistaken for "um" + "brella" (the exact class
   of bug found and fixed in Day 23's yes/no matching — same lesson
   applied proactively here, verified by
   `test_filler_word_removal_is_word_boundary_safe`).
4. **Partial-answer detection** — flags text trailing off on a bare
   connector word ("and", "but", "so", "with", …) as `PARTIAL_ANSWER`.
5. **Punctuation and case normalization** — sentence-initial
   capitalization, standalone "i" → "I", terminal punctuation, collapsed
   whitespace.

### A deliberate scope decision: which filler words are NOT removed

`"like"`, `"actually"`, `"sort of"`, `"kind of"` are common fillers but
are **excluded** from removal — they're also real content words ("I'd
**like** to...", "it was **actually** broken"). Stripping them
unconditionally risks silently deleting meaning the same way Day 23's
substring bug silently misread answers. Consistent with this project's
established preference throughout: an honest gap (leave it in) over a
confident wrong guess (strip it and maybe change the meaning).

## STT accuracy test report — real WER, honestly framed

`run_day24_stt_accuracy_report.py` measures **Word Error Rate** (a
standard Levenshtein-distance-over-words metric, not invented for this
report) between 5 real candidate-answer-style ground-truth sentences and
both the mock's raw noisy output and `clean_transcript()`'s cleaned
output, across 5 accent/noise profiles.

| Profile | Raw WER | Cleaned WER | Improvement |
|---|---|---|---|
| clear / 0.0 | 0.000 | 0.000 | 0.000 |
| clear / 0.3 | 0.096 | 0.031 | 0.065 |
| clear / 0.6 | 0.309 | 0.142 | 0.167 |
| indian_en / 0.2 | 0.157 | 0.092 | 0.065 |
| indian_en / 0.5 | 0.371 | 0.142 | 0.229 |

**What this measures, precisely**: how well `clean_transcript()`
recovers ground truth from *simulated* noise. It is **not** a real STT
vendor's accuracy on real audio — this project has no way to obtain
that. A dedicated test
(`test_cleaning_never_increases_wer_across_all_simulated_profiles`)
locks in the property observed across every profile tested: cleaning
never makes WER *worse* than the raw transcript, only equal or better.

### What cleaning fixes, and what it fundamentally cannot

Reading the actual transcripts in the log (`logs/day24_stt_accuracy_run.log`)
makes the boundary concrete. At `indian_en/0.5`:

```
GT:      My current CTC is around eight lakhs and I am expecting ten to twelve.
RAW:     'my current ctc is you know around eight lakes and i am like expecting ten to twelve'
CLEANED: 'My current ctc is around eight lakes and I am like expecting ten to twelve.'
```

Cleaning correctly removed "you know" and fixed casing/punctuation — but
**"lakhs" stayed mis-transcribed as "lakes."** This is not a bug in
`clean_transcript()`. Accent-driven word substitution is a
content-level, semantic ASR error, not a structural noise problem —
fixing it would require actually understanding that "eight lakes" makes
no sense in a salary context and guessing at intended meaning, which is
a fundamentally different (and much riskier) kind of correction than
removing a filler word. No amount of regex-based cleanup can honestly
recover a wrongly-heard word without risking inventing what was actually
said.

## Handling the brief's three specific cases

| Brief requirement | Implementation |
|---|---|
| Interrupted speech | `_detect_self_correction()` — keeps final statement after the last correction marker |
| Partial answers | `_looks_like_partial_answer()` — flags text trailing off on a connector word |
| Silence detection | `is_silent` flag (from the STT layer) or empty text → `CleanStatus.SILENT`, distinct from a low-confidence transcription |

## Validation

- **28 automated tests** (`tests/test_speech_to_text.py`): mock provider
  determinism and word-boundary-safe substitution, every cleaning rule
  independently (filler removal, self-correction, partial-answer
  detection, silence, punctuation/case), WER correctness against known
  hand-computed cases, and the cross-cutting "cleaning never increases
  WER" guarantee across all 25 simulated (profile × sentence)
  combinations.
- **356 tests pass project-wide** (328 from Days 9–23, unchanged, plus
  28 new) — zero regressions.
- All 28 new tests passed on first real run — no bugs found in this
  module this session (unlike Day 23, where testing surfaced 3 genuine
  bugs). Worth stating plainly rather than manufacturing a "finding" that
  didn't occur.

## Known limitations (stated honestly)

- No real ASR integration exists — `STTProvider` is a usable contract,
  not a working implementation. Someone with real API access would
  implement it against a real vendor.
- The mock's accent-substitution pairs (`lakhs→lakes`, `years→yours`,
  etc.) are illustrative examples of a well-documented ASR failure
  class, not measured against any real ASR engine's actual error
  distribution — there is no way to obtain that distribution in this
  environment.
- Filler and correction-marker detection is phrase-list and regex based,
  not a language model — robust for the phrasings tested, but not
  exhaustive. A genuinely novel phrasing will simply not be caught,
  which is the safe failure mode (text passes through mostly as-is)
  rather than a wrong transformation.
- Acronym casing (e.g. "CTC") is not restored if the (simulated) ASR
  output was already lowercased — `clean_transcript()` only restores
  sentence-initial and standalone-"I" capitalization, not acronym
  detection, which would require a dictionary of known acronyms this
  project doesn't maintain.
