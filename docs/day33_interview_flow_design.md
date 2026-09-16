# Day 33 — Interview Flow Design

## Scope, stated honestly up front

This is a **design** day: the interview state structure and phase
sequencing are built and tested, but the runtime DECISION logic
(when to actually trigger a follow-up, how to handle a vague or
off-topic behavioral answer, retry/clarification) is deliberately
**not** built here. That's exactly the relationship Day 22's screening
question bank had to Day 29's conversation flow engine — a real
schema existed for seven days before a real decision tree was built on
top of it. This document describes what exists now and names what a
future day would add, rather than quietly skipping it.

## Interview state structure

Two dataclasses, one per level of granularity:

### `InterviewQuestionState` — one question's state
```python
question_id: str
category: str
phase: InterviewPhase
follow_up_eligible: bool          # fixed at creation, from the template
response_text: Optional[str]      # the "response capture" deliverable
response_captured: bool
follow_up_asked: bool
follow_up_text: Optional[str]
```

`capture_response()` sets the text and flag together — there's no way
to have `response_captured=True` with `response_text=None`, or vice
versa, since both are only ever set by the one method that owns both.

`record_follow_up()` enforces `follow_up_eligible` at the state level,
not just at generation time — even if calling code got the eligibility
check wrong elsewhere, a follow-up literally cannot be recorded on an
ineligible question; it raises `ValueError` instead of silently
storing inconsistent state. Verified by
`test_record_follow_up_raises_when_not_eligible`.

### `InterviewSession` — the whole interview
```python
experience_level: ExperienceLevel
role_type: RoleType
questions: List[InterviewQuestionState]
```

`InterviewSession.start()` is the constructor that actually calls the
question generator and builds one `InterviewQuestionState` per
generated question — the session's `questions` list and the generator's
output are never out of sync because one is built directly from the
other, not maintained in parallel.

`submit_response()` is deliberately **linear only** — it captures the
answer on the current question and advances to the next one. No
retry, no branching, no re-asking. This is the honest boundary: a
linear sequencer is what "design the state structure" asks for; a
decision tree over that structure is a different, larger piece of work
this day doesn't claim to have done.

## Conversation phases — reasoning behind the sequencing

| Phase | Categories | Why here |
|---|---|---|
| **Introduction** | `self_introduction` | Every real interview opens with this — it's the only category that belongs first by convention, not by dependency. |
| **Core HR** | `career_journey`, `strengths_weaknesses`, `teamwork_culture_fit` | The substantive behavioral core. Grouped together because none of the three depends on the others' answers — order within this phase doesn't matter, only that they come after the opener and before the role-specific and closing content. |
| **Role-Based Evaluation** | `career_goals` | Placed after the core behavioral questions and before closing because a growth-path question naturally follows once the interviewer has heard about background and teamwork — asking it first would be premature, asking it last would bury it under closing logistics. |
| **Closing** | `availability_commitment` | Notice period and commitment are exactly the kind of practical, logistics-oriented question real interviews end on — asking this first would feel transactional before any rapport is built. |

This ordering is a design choice grounded in how real HR interviews
are actually structured, not an arbitrary assignment — but it is a
choice, not a derived fact, and a future day extending this could
reasonably re-order `role_based_evaluation` relative to `closing` for
a different interview style without contradicting anything built here.

## Relationship to the screening phase (Days 22–32)

This module does not call into or depend on any screening-phase code.
The two phases are architecturally independent — a candidate's
screening call (Days 22–32) and their later HR interview (Day 33+) are
different sessions with different state, different categories, and
(for now) different flow logic. The only shared piece is Day 22's
`get_template_text()` multilingual-fallback helper, reused because it's
genuinely generic, not because the two phases are otherwise coupled.

## What a future day would add

Following the same precedent as Day 29 building on Day 22:

1. **A real decision tree** over `InterviewSession` — deciding when a
   thin or vague behavioral answer warrants a follow-up, not just
   recording one when asked.
2. **Answer understanding** for behavioral content — Day 25's
   `understand_answer()` is scoped to factual screening categories
   (experience, salary, etc.); a behavioral answer like "tell me about
   a time you disagreed with a teammate" needs different quality
   signals entirely (e.g., did they describe a concrete example vs.
   speak in generalities), which doesn't exist yet.
3. **Scoring** — nothing in this day evaluates the QUALITY of a
   behavioral answer, only captures it. A Day 26-equivalent for this
   phase is future work.
