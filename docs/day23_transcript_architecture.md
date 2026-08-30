# Day 23 — Transcript Data Architecture

## What this is, and what it explicitly is not

This defines how a voice screening call — once Day 22's questions are
asked and a candidate answers out loud — gets turned into structured,
AI-processable data. **Nothing in this project performs real speech-to-
text.** Every transcript this module consumes is either a human-typed
proxy for what ASR would produce, or a synthetic example clearly marked
as such (`run_day23_transcript_demo.py`). What IS real and independently
verified this session: the schema, the normalization logic (tested
against real edge cases, including three genuine bugs found and fixed —
see below), and the DB DDL (proven by actually creating the tables in
SQLite and exercising its constraints, not just eyeballing SQL text).

## Two storage granularities

- **`CallSession`** — one call: who, which job, when, overall outcome.
- **`TranscriptTurn`** — one Q&A exchange within that call: which
  question (linking back to Day 22's `ScreeningQuestion.id`), the raw
  ASR text, ASR confidence, and the normalized value once that raw text
  is coerced toward the question's `expected_answer_type`.

The Day 23 brief's five metadata fields (Candidate ID, Job ID, Question
ID, Timestamp, Confidence level) live at the **turn** level, not the call
level — confidence is inherently a per-utterance ASR concept, and a call
is just the sum of its turns plus a timing envelope. Storing one averaged
confidence per call would hide exactly the turns that need a human's
attention.

## Transcript normalization rules

`normalize_answer(raw_text, expected_answer_type, asr_confidence)` is
the single entry point every turn's answer goes through, gated in this
order:

1. **Empty transcript** → `NEEDS_REVIEW` immediately.
2. **Low ASR confidence** (below 0.55) → `NEEDS_REVIEW`, even if the text
   superficially parses cleanly. A low-confidence transcript is exactly
   the case where a plausible-looking parse is most likely to be wrong —
   demonstrated directly in the Day 23 demo, where a salary answer with
   genuinely parseable numbers ("eleven lakhs... twelve to fourteen")
   was correctly withheld from auto-normalization because its ASR
   confidence was 0.40.
3. **Type-specific coercion** — `free_text`/`list` pass through
   unchanged (no coercion attempted — a human or downstream NLP reader
   handles these, not a numeric/boolean scorer); `yes_no` matches
   against phrase lists; `number` extracts digits or single word-numbers;
   `duration` extracts a structured `{amount, unit, immediate}` object
   (kept structured rather than collapsed to a bare number, since "2
   weeks" and "2 months" mean very different things for a notice-period
   decision).

## Three real bugs found and fixed this session

Not hypothetical edge cases — each was caught by a test written against
the module's own stated design intent, then verified against the actual
running code, which didn't match its own documentation until fixed.

**1. Substring false-positive in yes/no matching.** The original
`_extract_yes_no` used plain `phrase in lowered` containment. Since `"no"`
is one of the recognized No-phrases, and the three characters `n`-`o`-`t`
contain `"no"` as a contiguous substring, **any answer containing the
word "not" was silently misread as a confident "No"** — e.g. "maybe, I'm
not totally sure" (an ambiguous, uncertain answer) was being recorded as
a definite `False`. Fixed with word-boundary regex matching
(`\bno\b` instead of `"no" in text`).

**2. Negation-scope blindness surfaced by fixing bug #1.** Once the
substring bug was fixed, the same test phrase then matched the bare word
`"sure"` (a Yes-phrase) inside "not totally **sure**" — flipping the
wrong answer to `True` instead of `None`. Fixed by checking for a
negator (`"not "`, `"n't "`, `"never "`) in the ~12 characters before a
matched phrase; a negated match is skipped rather than accepted.
Deliberately conservative: a negated match falls through toward
`NEEDS_REVIEW` if nothing else matches, rather than being flipped to the
opposite answer — "not correct" might mean "no," but guessing that
confidently risks being wrong in the direction that matters most for a
hiring decision. Consistent with this project's established stance (Day
20: fail toward human review, not a wrong autonomous call).

**3. Compound number words extracted the wrong number.** The module's
own docstring states compound number words ("twenty-three") are **not**
handled and should fall through to `NEEDS_REVIEW`. The actual code
didn't do this: `\bthree\b` matched the "three" inside "twenty-three"
because a hyphen is a non-word character and creates a legitimate `\b`
boundary on its own — so "twenty-three years old" silently extracted
`3.0`, contradicting the code's own documented design. Fixed by checking
for an adjacent hyphen on either side of a word-number match and skipping
it if found, making the code actually match its stated intent.

All three are covered by dedicated regression tests
(`test_article_a_does_not_false_positive_as_one`,
`test_ambiguous_yes_no_needs_review`,
`test_compound_number_words_are_a_documented_gap_not_a_wrong_guess`) so
they can't silently regress.

## Database schema for screening interactions

Two tables (`schemas/transcript_schema.sql`), matching the two dataclass
granularities:

```sql
call_sessions (call_id PK, candidate_id, job_id, started_at, ended_at,
               status CHECK IN (...), language)
transcript_turns (turn_id PK, call_id FK, candidate_id, job_id,
                   question_id, turn_index, question_text, raw_transcript,
                   asr_confidence CHECK 0.0-1.0, timestamp,
                   expected_answer_type CHECK IN (...),
                   normalized_value, normalization_status CHECK IN (...),
                   normalization_note,
                   UNIQUE(call_id, turn_index))
```

**Why `candidate_id`/`job_id` are denormalized onto `transcript_turns`**
(duplicated from `call_sessions` rather than requiring a join): every
realistic query against this data — "show me all of this candidate's
answers across every call," "flag every low-confidence turn for this
job" — filters by candidate or job directly on the turns table. Forcing
a join through `call_sessions` for every such query is pure overhead for
data that's static for the lifetime of a call and costs a few extra
bytes per row. A partial index
(`WHERE normalization_status = 'needs_review'`) exists specifically for
the human-review queue, so that query stays fast without scanning every
turn ever recorded.

**This SQL is proven executable, not just typed text.** The demo script
creates these exact tables in an in-memory SQLite database, inserts a
full real call session, and queries the review-flag index — not a
simulation, an actual `sqlite3.connect()` and `executescript()` call.
The CHECK constraints are proven to actually fire (not just declared) via
dedicated tests: inserting an out-of-range `asr_confidence`, an invalid
`status` enum value, or a duplicate `(call_id, turn_index)` pair are all
confirmed to raise `sqlite3.IntegrityError`, not silently succeed.

## Validation

- **38 automated tests** (`tests/test_transcript_schema.py`): ID/timestamp
  helpers, every normalization branch (including the 3 fixed bugs above
  as explicit regressions), dataclass serialization, and DB-constraint
  tests that create a real SQLite connection per test.
- **Real demo run** (`run_day23_transcript_demo.py`): Day 22's actual
  question generator produces 12 questions for a real candidate/JD pair,
  synthetic (clearly labeled) answers are normalized, 1 of 12 turns is
  correctly flagged `needs_review` (the deliberately low-confidence
  salary answer), and the full session is stored in and queried back
  from real SQLite.
- A real `CallSession.to_dict()` output is verified to conform to
  `schemas/transcript_schema.json` field-for-field.

## Known limitations (stated honestly)

- Word-number extraction only handles single words (`"three"`), not
  compounds (`"twenty-three"`) — documented as a gap, verified to
  actually behave as a gap (fall through to `NEEDS_REVIEW`) after the
  bug fix above, not silently mishandled.
- Yes/no and negation detection is phrase-list and proximity based, not
  a real NLU model — sufficiently robust for the phrasings tested, but
  not exhaustive; genuinely novel phrasings will correctly fall through
  to `NEEDS_REVIEW` rather than guess, which is the intended safe
  failure mode, not a bug.
- No real ASR integration exists — `asr_confidence` is a required input
  to this module's functions, supplied by whatever ASR system eventually
  produces it; this module only defines what happens once that number
  exists.
