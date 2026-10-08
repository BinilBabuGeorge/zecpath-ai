# Day 44 — Developer Integration Guide

## How to actually use this today

There is no running server — `api/hr_interview_openapi.yaml` (and its
two companion specs) describe a **future** REST contract, explicitly
marked `# Production (placeholder -- not yet deployed)` in every
server block. Today, integration means calling the Python modules
directly, in-process. This guide shows that, with real output from
running each example against this project — not illustrative/invented
output.

## Quickstart: run a full HR interview

```python
from parsers.hr_interview_question_bank import InterviewSession, ExperienceLevel, RoleType

session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)

while not session.is_complete:
    question = session.current_question
    print(question.category, "->", question.question_id)
    answer = input("candidate's answer: ")   # replace with your real input source
    session.submit_response(answer)
```

`session.questions` now holds every `InterviewQuestionState`, each with
`.response_text` filled in.

## Getting a follow-up decision (Day 34)

Call this right after `submit_response()`, while you still have the
question object, if `question.follow_up_eligible` is `True`:

```python
from parsers.hr_followup_engine import decide_follow_up

question = session.questions[0]
session.submit_response("I think, uh, I did some stuff at my last job.")
decision = decide_follow_up(question, question.response_text)

print(decision.should_follow_up)   # True
print(decision.follow_up_type)     # FollowUpType.DEEPENING
print(decision.answer_quality)     # BehavioralAnswerQuality.THIN
print(decision.follow_up_text)     # "Could you tell me a bit more -- what's your background in a bit more detail?"
print(decision.reason)             # "Answer was thin/generic with no concrete example -- probing deeper."
```

Real output from running this exact snippet against this project,
captured while writing this guide — not invented.

## Scoring a session (Day 37) — not re-verified this environment

```python
from parsers.hr_interview_scoring_engine import score_hr_interview

hr_report = score_hr_interview(session)
print(hr_report.overall_hr_score)
print(hr_report.to_dict())   # JSON-serializable, same shape api/hr_interview_openapi.yaml's HRInterviewScoreReport schema mirrors
```

## Generating the recruiter summary (Day 39) — not re-verified this environment

```python
from parsers.interview_summary_generator import generate_interview_summary

summary = generate_interview_summary(hr_report)
print(summary.to_narrative())   # human-readable, template-generated text
print(summary.to_dict())        # JSON-serializable
```

## Computing the cross-round unified score (Day 41) — verified, real output below

```python
from parsers.unified_scoring_engine import RoundScores, compute_unified_score
from parsers.hr_interview_question_bank import RoleType

scores = RoundScores(ats_score=82.0, screening_score=74.0, hr_interview_score=88.0)
result = compute_unified_score(scores, role_type=RoleType.TECHNICAL, candidate_id="EXAMPLE-001")
print(result.to_dict())
```

Real output:

```json
{
  "candidate_id": "EXAMPLE-001",
  "role_type": "technical",
  "hiring_fit_percentage": 83.5,
  "decision": "selected",
  "weights_used": {"ats": 0.4, "screening": 0.15, "hr_interview": 0.45},
  "missing_rounds": [],
  "contributions": [
    {"round_name": "ats", "raw_score": 82.0, "base_weight": 0.4, "effective_weight": 0.4, "contribution": 32.8, "included": true},
    {"round_name": "screening", "raw_score": 74.0, "base_weight": 0.15, "effective_weight": 0.15, "contribution": 11.1, "included": true},
    "... (hr_interview contribution follows the same shape)"
  ]
}
```

If a round hasn't happened yet, pass `None` for it — its weight gets
proportionally redistributed across the rounds that are present, not
silently treated as zero:

```python
scores = RoundScores(ats_score=82.0, screening_score=None, hr_interview_score=88.0)
result = compute_unified_score(scores, role_type=RoleType.TECHNICAL)
print(result.missing_rounds)   # ["screening"]
```

## Scrubbing transcripts before storage (Day 43) — verified

```python
from parsers.transcript_demographic_scrubber import mask_demographic_disclosures

text = "I'm a single mother returning to work after a break, so I'm very focused on time management."
masked, categories = mask_demographic_disclosures(text)
print(masked)       # "[REDACTED] returning to work after a break, so I'm very focused on time management."
print(categories)   # ["Marital/family status"]
```

**Not wired into the session flow above** — call this yourself on
`response_text` before you store or forward it, until a future day
integrates it directly into `InterviewSession.submit_response()`.

## Troubleshooting

### "My answer got classified `thin` but it's a real, specific story"

Check whether it uses a concrete-example marker phrase ("for
example"), narrative transition language ("started as", "then I",
"after that"), or a specific quantity ("three years", "a couple of
teammates"). Day 42 broadened detection to catch the second and third
categories — if your text has none of the three, see
`hr_followup_engine._CONCRETE_EXAMPLE_MARKERS` and
`_NARRATIVE_TRANSITION_MARKERS` for the exact phrase lists; this is
keyword matching, not language understanding, and will miss a real
story phrased unusually. Day 40's own simulation report documents this
exact limitation.

### "`decide_follow_up()` says `should_follow_up: False` but I expected a follow-up"

Check `question.follow_up_eligible` first — some categories default to
`False` (see `CATEGORY_METADATA` in `hr_interview_question_bank.py`).
Also check whether the repetition cap has already been hit
(`question.follow_up_asked` is already `True`) — Day 34 only allows one
follow-up per question by design.

### "`compute_unified_score()` raised `ValueError: RoundWeights must sum to 1.0`"

If you're passing a custom `weights=` argument, the three values
(`ats`, `screening`, `hr_interview`) must sum to exactly 1.0 (±0.001).
Omit `weights` entirely to use the role-based default instead of
building one from scratch.

### "I passed a session with zero answered questions to a scoring function"

Both `score_hr_interview()` and `build_aptitude_profile()` (not
re-verified this environment, but documented this way on their
originating days) return a valid report with all scores at `0.0` and
empty breakdown lists, rather than raising — check
`num_questions_answered == 0` (or the aptitude equivalent) before
trusting a zero score as a real result.

### "The OpenAPI spec and the actual dataclass don't match"

For the schemas marked `verified against live source` in
`api/hr_interview_openapi.yaml`'s info block
(`InterviewQuestionState`, `FollowUpDecision`, `UnifiedCandidateScore`,
`ComponentContribution`, `ScrubResult`), this would be a real bug —
`tests/test_day44_hr_interview_openapi.py` checks these four
programmatically against the live dataclasses and would have caught a
mismatch; please report it. For the schemas marked `reconstructed, not
re-verified` (everything from Days 35/36/37/38/39), the spec was
written from documented scope without the source file in front of it
— treat it as a strong draft, not a guarantee, until someone diffs it
against the real classes.

## Deliverables

- **HR AI architecture document** — `day44_hr_ai_architecture.md`.
- **API specification** — `api/hr_interview_openapi.yaml`.
- **Developer handbook** — this document (integration guide +
  troubleshooting).

## Verification

13 new tests (`tests/test_day44_hr_interview_openapi.py`) — structural
spec validation (valid YAML, every `$ref` resolves, every schema is
referenced, the `ErrorResponse` shape matches the two existing API
specs' convention) plus, for the five schemas this day could actually
verify, a direct field-by-field comparison against the live
`@dataclass` definitions. Full regression in this environment: 311
tests (298 previous + 13 new) passed clean with zero regressions.
