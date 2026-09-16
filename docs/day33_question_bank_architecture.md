# Day 33 — Question Bank Architecture

## Reuse from Day 22

`get_template_text()` and `SUPPORTED_LANGUAGES` are imported directly
from `parsers.screening_question_bank`, not duplicated. Day 22
established the honest multilingual-scaffolding pattern (English
populated, `hi`/`ml`/`ta` structurally present but explicitly marked
`[NO XX TRANSLATION YET]` rather than silently showing English or
fabricating a translation) — that logic is generic to any
template-with-`localized_text` object, so this module's templates
follow the identical shape and reuse the identical function. Verified
by `test_untranslated_language_falls_back_to_english_with_marker`.

Everything else is new — the category taxonomy, the templates, and the
selection mechanics are specific to behavioral HR interview content
and don't belong in Day 22's screening-specific file.

## Category taxonomy

Six categories, each with a fixed conversation phase and a default
follow-up eligibility, declared once in `CATEGORY_METADATA`:

| Category | Phase | Follow-up eligible by default | Why |
|---|---|---|---|
| `self_introduction` | introduction | Yes | An open question genuinely invites follow-up |
| `career_journey` | core_hr | Yes | Same — history naturally has follow-up threads |
| `strengths_weaknesses` | core_hr | Yes | Same |
| `teamwork_culture_fit` | core_hr | Yes | Same |
| `career_goals` | role_based_evaluation | No | A forward-looking, mostly self-contained answer |
| `availability_commitment` | closing | No | A closed, factual answer — nothing to probe further |

## Template selection mechanics

Each `QuestionTemplate` declares which `ExperienceLevel`s and
`RoleType`s it applies to — either a single value or both (the
`_BOTH_EXPERIENCE`/`_BOTH_ROLE_TYPES` tuples). `_select_template()`
filters the category's templates to the ones matching **both** the
candidate's actual experience level and role type, and takes the exact
match. This is a lookup, not a rule engine — there's no scoring or
fuzzy matching, deliberately: the whole point is a small, auditable set
of hand-written templates, not an inference step that could produce a
combination nobody reviewed.

**Defensive fallback:** if a category somehow had no template matching
both axes exactly (a data-entry gap, not expected given the templates
shipped here), `_select_template()` falls back to the first template
defined for that category rather than raising `KeyError` mid-interview.
This mirrors the same defensive stance the rest of this project takes
at every layer — the tests confirm this branch is dead code given the
current template set, not a load-bearing "usually broken" path.

## Where role-based variation is genuine vs. where it would be padding

This is the deliberate design decision behind this whole module,
stated plainly rather than left implicit:

- **`career_journey` — varies on both axes (4 templates).** A fresher
  has no career to walk through; asking them "walk me through your
  career progression" is a category error, not a personalization. A
  technical fresher's relevant history (projects, internships in a
  tech stack) is different in kind from a non-technical fresher's
  (coursework, extracurriculars). All four combinations earn a
  genuinely distinct question.
- **`teamwork_culture_fit` — varies by experience level only (2
  templates).** An experienced candidate has real workplace team
  dynamics, possibly including conflict, worth asking about directly.
  A fresher doesn't — a college group project is the honest
  equivalent. Role type doesn't change what teamwork looks like, so
  it isn't varied on that axis.
- **`career_goals` — varies by role type only (2 templates).**
  Technical and non-technical growth paths are genuinely different
  questions. Experience level doesn't change the question itself (a
  fresher and an experienced candidate can both be asked "where do you
  see your growth heading" the same way).
- **`self_introduction`, `strengths_weaknesses`,
  `availability_commitment` — universal (1 template each).** These
  questions work identically regardless of role or experience. Adding
  role-specific variants here would be four templates that all say the
  same thing with cosmetic differences — padding a 2×2 grid instead of
  designing one.

Verified in tests: `test_career_journey_differs_across_all_four_combinations`,
`test_teamwork_varies_by_experience_only_not_role_type`,
`test_career_goals_varies_by_role_type_only_not_experience`,
`test_universal_categories_identical_across_all_combinations`.

## What this architecture explicitly does not do

- **No JD-driven or ATS-driven personalization**, unlike Day 22's
  screening bank. HR behavioral questions aren't naturally
  job-description-specific the way "do you know React" is — this is a
  deliberate scope boundary, not an oversight.
- **No dynamic question generation.** Every question is a hand-written
  template, selected by lookup. Nothing is generated on the fly by any
  model.
