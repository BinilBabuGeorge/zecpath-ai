# Day 33 — HR Interview AI Structure Diagram

## A new phase, not an extension of the screening phase

Days 22–32 built the **screening-call phase**: gathering FACTS
(education, experience, skills, salary, notice period) to filter
candidates before a human ever talks to them. Day 33 begins the **HR
interview phase**: BEHAVIORAL questions a human HR interviewer asks
once a candidate has already cleared screening. These are genuinely
different concerns with different question types, which is why this
is a new module (`parsers/hr_interview_question_bank.py`) rather than
an extension of Day 22's `screening_question_bank.py` — reusing only
what's genuinely shared (`get_template_text()`'s honest multilingual-
fallback behavior).

## Structure diagram

```
                    CATEGORY_METADATA
                    (6 behavioral categories,
                     each mapped to a phase)
                            |
                            v
                    QUESTION_TEMPLATES
                    keyed by (category,
                    experience_level, role_type)
                    -- variation ONLY where
                    genuinely justified
                            |
              generate_hr_interview_questions(
                  experience_level, role_type, lang
              )
                            |
                            v
                    HRInterviewQuestion (x6)
                    id, category, phase, text,
                    follow_up_eligible
                            |
                InterviewSession.start(...)
                            |
                            v
                    InterviewQuestionState (x6)
                    -- the live, mutable state
                    response_text, captured,
                    follow_up_asked/text
                            |
                session.submit_response(text)
                session.current_question / current_phase
                session.questions_by_phase(phase)
```

## The two independent axes of the role-based generator

```
                     RoleType
                Technical      Non-Technical
              +-------------+---------------+
   Fresher    |  variant A  |   variant B   |   career_journey varies
              +-------------+---------------+   on BOTH axes -- 4
ExperienceLevel                                 distinct questions
   Experienced|  variant C  |   variant D   |
              +-------------+---------------+
```

`career_journey` is the only category needing the full 2×2 — both axes
genuinely change what history exists to ask about. `teamwork_culture_fit`
varies only down the rows (experience level: a fresher has no
workplace team yet). `career_goals` varies only across the columns
(role type: technical vs. non-technical growth paths differ).
`self_introduction`, `strengths_weaknesses`, and
`availability_commitment` are flat — one cell serves the whole grid,
because forcing variation there would be padding, not design.

## Conversation phase sequencing

```
INTRODUCTION  ->  CORE_HR  ->  ROLE_BASED_EVALUATION  ->  CLOSING
     |               |                   |                   |
self_intro    career_journey       career_goals      availability_
              strengths_weak-     (role-tailored)      commitment
              nesses,
              teamwork_
              culture_fit
```

See `docs/day33_interview_flow_design.md` for the reasoning behind
this specific phase assignment, and
`docs/day33_question_bank_architecture.md` for the template/selection
mechanics in full detail.
