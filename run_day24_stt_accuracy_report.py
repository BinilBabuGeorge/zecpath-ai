"""
Day 24 -- STT accuracy test report.

Measures Word Error Rate (WER) -- a standard, real metric (Levenshtein
distance over word tokens, normalized by reference length) -- between
known ground-truth sentences and (a) MockSTTProvider's simulated raw
output, (b) clean_transcript()'s cleaned output, across several
accent/noise profiles.

HONEST FRAMING: this measures how well clean_transcript() recovers
ground truth from SIMULATED noise, not a real STT vendor's accuracy on
real audio -- this project has no real audio or STT API access. Treat
these numbers as "does the cleaning module do its job on realistic-
shaped noise," not "here is Whisper's/Google's actual word accuracy."
"""

import json
import logging
from pathlib import Path

from parsers.speech_to_text import MockSTTProvider, clean_transcript

LOG_DIR = Path("logs")
OUT_DIR = Path("data/results")

logger = logging.getLogger("day24")

# Real, representative candidate-answer sentences (the kind Day 22's
# screening questions actually elicit) -- not arbitrary filler text.
GROUND_TRUTH_SENTENCES = [
    "I have about three years of experience with React and Node.js.",
    "My current CTC is around eight lakhs and I am expecting ten to twelve.",
    "My notice period is thirty days but I can negotiate.",
    "Yes I am comfortable relocating to Bengaluru for this role.",
    "I completed my B.Tech in Computer Science from a college in Pune.",
]

PROFILES = [
    ("clear", 0.0), ("clear", 0.3), ("clear", 0.6),
    ("indian_en", 0.2), ("indian_en", 0.5),
]


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Standard WER: Levenshtein edit distance over word tokens,
    normalized by reference word count. 0.0 = perfect match.
    """
    ref = reference.lower().split()
    hyp = hypothesis.lower().split()
    if not ref:
        return 0.0 if not hyp else 1.0

    dp = [[0] * (len(hyp) + 1) for _ in range(len(ref) + 1)]
    for i in range(len(ref) + 1):
        dp[i][0] = i
    for j in range(len(hyp) + 1):
        dp[0][j] = j
    for i in range(1, len(ref) + 1):
        for j in range(1, len(hyp) + 1):
            if ref[i - 1] == hyp[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
    return dp[len(ref)][len(hyp)] / len(ref)


def run():
    # Logging configured here, not at module import time -- this module
    # is imported by tests/test_speech_to_text.py for its constants and
    # helper functions (word_error_rate, GROUND_TRUTH_SENTENCES,
    # PROFILES). Configuring logging.basicConfig() at import time would
    # truncate the log file as a side effect of merely importing the
    # module for testing, even when run() never executes -- exactly the
    # kind of surprising action-at-a-distance bug worth avoiding.
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO, format="%(message)s",
        handlers=[
            logging.FileHandler(LOG_DIR / "day24_stt_accuracy_run.log", mode="w", encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )

    provider = MockSTTProvider(seed=123)
    logger.info("=" * 100)
    logger.info("DAY 24 -- STT ACCURACY TEST REPORT (simulated noise, real WER measurement)")
    logger.info("=" * 100)

    rows = []
    for accent, noise in PROFILES:
        raw_wers, cleaned_wers = [], []
        logger.info(f"\nPROFILE: accent={accent}  noise_level={noise}")
        logger.info("-" * 100)
        for gt in GROUND_TRUTH_SENTENCES:
            raw = provider.simulate(gt, accent=accent, noise_level=noise)
            cleaned = clean_transcript(raw)
            raw_wer = word_error_rate(gt, raw.text)
            cleaned_wer = word_error_rate(gt, cleaned.text)
            raw_wers.append(raw_wer)
            cleaned_wers.append(cleaned_wer)
            logger.info(f"  GT:      {gt}")
            logger.info(f"  RAW:     {raw.text!r}  (WER={raw_wer:.2f}, conf={raw.confidence:.2f})")
            logger.info(f"  CLEANED: {cleaned.text!r}  (WER={cleaned_wer:.2f}, status={cleaned.status.value})")
            logger.info("")

        avg_raw = sum(raw_wers) / len(raw_wers)
        avg_cleaned = sum(cleaned_wers) / len(cleaned_wers)
        logger.info(f"  AVERAGE WER: raw={avg_raw:.3f}  cleaned={avg_cleaned:.3f}  "
                     f"(delta={avg_raw - avg_cleaned:+.3f})")
        rows.append({
            "accent": accent, "noise_level": noise,
            "avg_wer_raw": round(avg_raw, 3), "avg_wer_cleaned": round(avg_cleaned, 3),
            "improvement": round(avg_raw - avg_cleaned, 3),
        })

    logger.info("\n" + "=" * 100)
    logger.info("SUMMARY")
    logger.info("=" * 100)
    logger.info(f"{'Profile':<25}{'Raw WER':>12}{'Cleaned WER':>15}{'Improvement':>15}")
    for r in rows:
        label = f"{r['accent']}/{r['noise_level']}"
        logger.info(f"{label:<25}{r['avg_wer_raw']:>12.3f}{r['avg_wer_cleaned']:>15.3f}{r['improvement']:>15.3f}")

    logger.info("\nWhat cleaning fixes vs. cannot fix (read the transcripts above):")
    logger.info("  FIXES:      filler words, casing, missing punctuation, self-correction, cutoff detection.")
    logger.info("  CANNOT FIX: content-level mishearing (e.g. accent substitutions like 'lakhs'->'lakes') --")
    logger.info("              that's a semantic/ASR-model problem, not a text-cleaning problem, and no")
    logger.info("              amount of regex-based cleanup can honestly recover a wrongly-heard word.")

    out_path = OUT_DIR / "day24_stt_accuracy_report.json"
    out_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    logger.info(f"\nStructured report written to {out_path}")
    return rows


if __name__ == "__main__":
    run()
