# Day 25 — Answer Intent & Understanding Engine

## Scope, stated honestly up front

"Intent classification" in this module is a **deterministic,
keyword-and-pattern-based classifier** — not a trained NLU/ML model.
This project has no labeled intent-classification training data and no
model-training infrastructure, so claiming a real learned classifier
would be exactly the kind of fabricated capability this project has
consistently avoided (Day 16: "PDF/DOCX not implemented"; Day 23/24:
"nothing performs real speech-to-text").

What IS real and independently tested this session:
1. A genuinely useful **rule-based intent classifier** that performs
   well on the direct, keyword-bearing answers a screening call
   actually produces.
2. Real **entity extraction** for skills, experience-years, and
   availability — reusing Day 4's `extract_skills()` and Day 23's
   `normalize_answer()` through their public entry points, not by
   re-implementing or reaching into their private helpers.
3. New **salary-expectation parsing** (lakhs / LPA / thousand-per-month)
   — nothing upstream handles Indian salary phrasing, so this is
   genuinely new logic, deliberately scoped to not guess a rupee amount
   when no unit is stated.
4. Honestly-gated **quality assessment** (vague / off-topic / missing)
   that only calls an answer off-topic when there's *positive evidence*
   of a different topic — absence of the expected topic's vocabulary
   alone is treated as "unknown," not "wrong," matching this project's
   established "an honest can't-tell beats a confident wrong guess"
   stance (Day 20).

A documented limitation found *during* this session, not swept under
the rug: Day 23's duration/number parser only recognizes single
word-numbers up to fifteen (`_WORD_NUMBERS`, Day 23) and does not
handle compound word-numbers like "thirty days." A demo answer using
"thirty days" therefore correctly falls through to "no duration found"
rather than being silently misread — see the demo report,
`t007`. Fixing that is Day 23 scope, not this module's; it's called out
here because Day 25 is the first module to exercise that gap on
realistic screening-call phrasing.

## Pipeline position

```
audio → STTProvider.transcribe()  (Day 24)
      → clean_transcript()         (Day 24)
      → understand_answer()        (Day 25, this module)
      → StructuredAnswer            (Day 25 semantic object)
```

Day 23's `normalize_answer()` coerces a *single* question's answer to
its declared `expected_answer_type` (number / duration / yes_no /
free_text). Day 25 solves a different, complementary problem:
figuring out what a free-form answer is actually *about* (intent),
pulling out whichever of several entity types it happens to mention —
useful because a real candidate's answer to "tell me about yourself"
routinely mentions two or three of these at once, not just the one the
question nominally targets — and flagging answers that don't engage
with the question at all (off-topic), don't say anything concrete
(vague), or say nothing (missing).

## Design

### Intent classification (`classify_intent`)

Six keyword-lexicon categories (introduction, education, experience,
location, salary, availability) matched with word-boundary regex —
guarding from the start against the same substring-matching bug class
Day 23 found and fixed ("no" inside "not"). The seventh category,
**skills**, is deliberately *not* a keyword list — it's scored from a
real `extract_skills()` call, which is strictly better evidence than a
hand-picked keyword list for a category whose whole vocabulary is "any
known tech/soft skill term."

`confidence` is a heuristic scaling (winning category's score ÷ total
matched score across all categories) — explicitly documented as *not*
a calibrated probability. Ties are broken by a fixed priority order
(skills/experience ahead of a passing introduction-phrase mention),
not silently by dict ordering.

If no category's vocabulary matches at all, the result is
`AnswerIntent.UNKNOWN` with an explanatory note — an honest "don't
know," not a guess, and explicitly distinct from a confident
`OFF_TOPIC` call (see below).

### Entity extraction

| Entity | Source | Notes |
|---|---|---|
| Skills | `skill_extractor.extract_skills()` (Day 4) | reused as-is |
| Experience years | `transcript_schema.normalize_answer(..., "number")` (Day 23) | public entry point only |
| Availability | `transcript_schema.normalize_answer(..., "duration")` (Day 23) | public entry point only; inherits Day 23's word-number range limit |
| Salary expectation | new: `extract_salary_expectation()` | lakhs/LPA vs. thousand-per-month kept as separate units, never collapsed to a bare rupee figure — same reasoning Day 23 applied to keeping duration as `{amount, unit}` instead of a bare number |

Entities are only extracted for whichever categories an answer
actually scored on (not just the question's expected category), since
one free-form answer routinely touches more than one — the multi-entity
introduction example in the demo report (`t000`) mentions skills *and*
experience years in a single sentence.

### Quality gating (`AnswerQuality`)

- **MISSING** — silent (Day 24 `is_silent`) or empty text.
- **VAGUE** — hedge phrases ("not sure," "I guess," "depends," …) or a
  1–2 word non-yes/no answer.
- **OFF_TOPIC** — the expected category scored zero *and* some other
  category scored positively. Requires positive evidence; a
  no-vocabulary-matched-anywhere answer is `UNKNOWN`/not extracted, not
  confidently flagged off-topic.
- **OK** — everything else; entity extraction runs.

## Deliverables (per the Day 25 brief)

- **Answer understanding engine** — `understand_answer()`, the single
  pipeline entry point.
- **Intent classifier** — `classify_intent()`.
- **Structured answer format** — `StructuredAnswer` dataclass /
  `.to_dict()`, covering intent, quality, extracted entities, and
  human-readable notes for anything that couldn't be confidently
  extracted.

## Testing

31 tests in `tests/test_answer_intent_engine.py`, covering: each
category's classification, empty/no-match handling, all four entity
extractors (including the documented salary-unit gap and the inherited
duration word-number gap), and every `AnswerQuality` branch including
the multi-entity and category-alias (`notice_period` → `availability`)
cases. Full existing suite (65 tests across Days 1–25, excluding the
pytest-dependent files this sandbox can't install) re-run clean after
this change — no regressions.

## Honest limitations carried forward

- No real ML/NLU — paraphrased or obliquely-worded answers that don't
  hit any keyword or `extract_skills()` match will read as `UNKNOWN`,
  not correctly classified. A production system would want a trained
  intent model here.
- Salary parsing requires an explicit unit (lakh/LPA/k) — a bare
  number ("eight hundred thousand rupees") is not parsed, by design,
  rather than guessing an annual/monthly convention the candidate never
  stated.
- Inherits Day 23's word-number range limit (zero–fifteen) for both
  number and duration extraction — compound numbers ("thirty days,"
  "twenty-two years") are not parsed and correctly report "not found"
  rather than misreading.
