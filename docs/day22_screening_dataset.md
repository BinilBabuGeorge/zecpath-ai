# Day 22 — HR Screening Dataset Creation

## What this builds, and why it's not just a static question list

The brief asks for a question bank for AI screening calls. The easy
version is a hardcoded list of generic questions. This instead builds
the questions from the ATS pipeline that already exists across Days
9–21, so the dataset is genuinely **role-aware** and, when candidate
data is available, **candidate-aware**:

- JD-derived personalization uses `jd_parser.parse_jd()` — an existing
  module from earlier in the project that wasn't being used by the
  current pipeline — to pull structured facts (education requirement,
  experience band, salary range) into the questions themselves.
- Candidate-driven personalization uses Day 13's `ATSScoreResult`
  directly: `missing_data_notes` becomes clarifying questions, the
  skill-match component's `matched_skills`/`missing_skills` becomes
  targeted verification and depth questions.
- The `notice_period` category is where Day 21's documented,
  intentional gap gets closed: `EligibilityRules.require_availability`
  was never a real gate because resumes don't capture notice period —
  this is the actual mechanism that collects it, live, per the PRD's own
  design.

## Category mapping (the taxonomy deliverable)

| Category | Default mandatory | Default importance | Applicability |
|---|---|---|---|
| introduction | Yes | high | universal |
| education | Yes | medium | universal |
| experience | Yes | high | universal |
| skills | Yes | high | job-specific |
| location | Yes | medium | universal |
| salary | Yes | medium | universal |
| notice_period | Yes | high | universal |

"Universal" categories get one instance per candidate regardless of
role; "job-specific" (skills) generates one question per required skill
pulled from the JD.

## Reusable question templates (the templates deliverable)

14 templates across the 7 categories, each carrying its own
`expected_answer_type`, `mandatory`, and `scoring_importance` — the
literal "tag questions with" requirement. Every template is a Python
format string (`{degree}`, `{skill}`, `{min_years}`, etc.) rendered at
generation time — no question in the final output ever contains an
unfilled placeholder (tested directly).

## A real bug found and fixed while building this

The first version used `jd_parser.parse_jd()`'s `requiredSkills` field
directly for skill questions — and produced this:

> "Could you describe your experience with **Strong proficiency in
> React.js and Node.js**?"

`jd_parser`'s skill extraction returns whole requirement *sentences*,
not individual skill names — a mismatch nobody would catch just by
reading the code, only by actually running it and reading the output.
Fixed by using `skill_extractor.extract_skills()` instead — the same,
already-proven module every other day in this project already trusts
for clean canonical skill names (`"React.js"`, `"Node.js"`,
`"MongoDB"`) — and added a regression test
(`test_jd_only_generation_includes_skill_questions_from_jd`) asserting
no generated question contains `"Strong proficiency"` or exceeds a
sane length, so this specific mistake can't silently return.

## AI conversation-ready question objects (the output deliverable)

```python
@dataclass
class ScreeningQuestion:
    id: str
    category: str
    text: str  # fully rendered, ready to speak/display
    expected_answer_type: str
    mandatory: bool
    scoring_importance: str
    source: str  # "template" | "jd_derived" | "ats_followup"
    language: str = "en"
```

`source` traces exactly where each question came from — a static
template, something derived from the JD's structured parse, or a
follow-up generated from real ATS findings about this specific
candidate. This matters for a real screening call: an `ats_followup`
question about a missing mandatory skill should probably be weighted
differently by a human reviewer than a generic template question.

Example, personalized generation for a candidate missing the JD's
education requirement (`resume_14_no_education` vs
`jd_01_mern_developer`):

```
[education | ats_followup] We weren't able to find a formal education
section on your application -- could you walk me through your
educational background?
```

vs. the same JD with no candidate data:

```
[education | jd_derived] This role prefers candidates with B.Tech/B.E.
in Computer Science or related field. Could you tell me about your
educational background in that context?
```

Same category, same underlying template infrastructure, genuinely
different — and appropriately different — questions.

## Multilingual readiness — honestly incomplete, not fabricated

`SUPPORTED_LANGUAGES = ["en", "hi", "ml", "ta"]` matches the PRD's
stated language set (English, Hindi, Malayalam, Tamil). **Only English
is actually populated.** `get_template_text()` explicitly marks any
unpopulated language request rather than silently returning English:

```
[NO HI TRANSLATION YET -- showing English] Could you briefly introduce...
```

This was a deliberate choice, not a shortcut: producing Hindi/Malayalam/
Tamil text without a verified fluent translator risks shipping wrong or
awkward phrasing into a live candidate-facing screening call, which is
worse than clearly marking it as not-yet-done. The schema is fully
ready to receive real translations (every template already has
`localized_text["hi"]`, `["ml"]`, `["ta"]` keys present, just empty) —
this is a data-entry task for a qualified translator, not a code change.

## Validation

- **24 automated tests** covering the category/template deliverables
  structurally, JD-only generation (including the skill-name regression
  test above), and personalized generation (education/experience/skill
  follow-ups triggered correctly, or correctly absent when not
  applicable).
- **290/290 tests pass project-wide** (266 from Days 9–21, unchanged,
  plus 24 new) — zero regressions.
- `run_day22_question_bank.py` generates the dataset for 2 JD-only
  targets (one tech, one business role) and 3 personalized targets
  (clean match, missing-education, wrong-stack) end to end.

Run with: `pytest tests/test_screening_question_bank.py -v`

## What's out of scope for this day

- Actual voice/TTS integration, adaptive real-time follow-up generation
  during a live call, and answer scoring are PRD Phase 5/16 concerns —
  this day builds the question *dataset*, not the calling system itself.
- Non-English content, as covered above.
- `jd_parser.py`'s skill extraction remains available but is not used
  by this module (see the bug above) — it may be worth revisiting for
  other purposes (department/responsibilities extraction, which it does
  do cleanly), just not for skill names.
