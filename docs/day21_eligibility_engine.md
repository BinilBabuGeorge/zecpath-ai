# Day 21 — Eligibility Decision Engine

## What this answers, and why it's a different question from Day 20

Day 20 asked "how strong is this candidate overall?" (SHORTLIST/REVIEW/
REJECT). Day 21 asks a narrower, more consequential question: **does
this specific candidate qualify to receive an AI screening call for
this specific job's hard requirements?** These are genuinely different
questions — a candidate can be a strong overall match (Day 20: SHORTLIST)
while still failing a hard, job-specific requirement (e.g. missing a
mandatory certification), and should be rejected from the call queue
regardless of how good their overall score looks.

## Design: hard gates first, score second

`evaluate_eligibility()` checks, in order:

1. **Mandatory skills** (hard gate) — every skill in
   `rules.mandatory_skills` must appear in the ATS result's matched
   skills, or the candidate is `REJECTED` regardless of score.
2. **Experience range** (hard gate) — below `min_experience_years` or
   above `max_experience_years` (if set) forces `REJECTED`.
3. **Location** (soft gate) — a mismatch downgrades `ELIGIBLE` to
   `REVIEW`, but never forces `REJECTED` on its own (relocation is
   negotiable in a way a missing mandatory skill is not).
4. **Availability** — deliberately **not implemented as an active gate**.
   See "What's honestly not implemented" below.
5. **Score-based classification** — reuses Day 20's
   `ranking_engine.classify_zone()` (category-aware thresholds +
   skill-relevance floor) by default, or a recruiter-specified
   `min_ats_score` if explicitly configured.

This ordering matters: a candidate can't buy their way past a hard gate
with a high score in an unrelated component, which mirrors how real
recruiting works (score-based ranking chooses among *qualified*
candidates; it doesn't decide who's qualified).

## Rule configuration format

`EligibilityRules` — a flat, JSON-serializable dataclass per job:

```json
{
  "job_id": "jd_01_mern_developer",
  "min_ats_score": null,
  "mandatory_skills": ["React.js", "Node.js"],
  "min_experience_years": 1.0,
  "max_experience_years": null,
  "allowed_locations": null,
  "require_availability": false
}
```

Every field except `job_id` is optional and defaults to "no constraint,"
not "reject everyone" — a recruiter who only cares about mandatory
skills shouldn't have to also specify an experience range.
`max_experience_years` in particular should rarely be set: Day 20
established that penalizing candidates for having *more* experience
than a junior-scoped JD asked for is a bug, not a feature.

Three example configs are bundled in `data/eligibility_rules/`,
demonstrating that the *same* JD can have different eligibility rules
for different hiring tracks:

| Config | What it shows |
|---|---|
| `jd_01_mern_developer.json` | Standard config: 1-year experience floor, React.js + Node.js mandatory |
| `jd_01_junior_track.json` | Same JD, junior track: no experience floor, only React.js mandatory |
| `jd_02_sales_executive.json` | A business role with a location constraint, showing the soft-gate behavior |

Running both MERN configs against `resume_13_fresher_no_experience`
produces two different, both-correct outcomes:
`jd_01_mern_developer.json` → `REJECTED` (missing Node.js, under the
experience floor); `jd_01_junior_track.json` → `REVIEW` (same candidate,
same score, different job requirements). The rule configuration is doing
its job — the code didn't change, the recruiter's stated requirements
did.

## Candidate eligibility result structure

```python
@dataclass
class EligibilityResult:
    candidate_id: str
    job_id: str
    tag: str  # "ELIGIBLE" | "REVIEW" | "REJECTED"
    overall_score: float
    score_zone: str  # underlying ranking_engine zone, for traceability
    reasons: List[str]  # always non-empty, always human-readable
    gates_applied: Dict[str, bool]  # only contains gates that were configured
```

`reasons` is never empty — even a clean pass states which zone drove the
decision, so nobody has to infer "why" from the tag alone.
`gates_applied` only contains keys for gates the job actually
configured, so its absence is meaningful (not evaluated) and distinct
from `False` (evaluated and failed).

## A real bug this module caught in itself

While writing this module's own example config,
`mandatory_skills: ["Salesforce CRM"]` was written — a natural-sounding
name that does **not** exactly match the skill dictionary's canonical
entry (`"Salesforce"`). This is a genuinely dangerous class of bug: it
doesn't error, doesn't crash, and produces a plausible-looking
`REJECTED` for every single candidate with no obvious symptom other than
"nobody is ever eligible for this job." `validate_rules_against_dictionary()`
was added specifically because of this — call it once when loading a
config (not on every evaluation) and it flags exactly this mistake, with
a `difflib`-based suggestion of the likely intended skill name.

## What's honestly not implemented: availability

`EligibilityRules.require_availability` exists in the schema (matching
the brief's four parameter categories) but is **never used as an active
gate**. Reason: this system's resumes — and the product's own design —
don't capture availability or notice period ahead of time. The PRD's own
Phase 5 AI screening questions list "Notice period" as something asked
**live on the call**, not present on the resume. Building a gate against
data that doesn't exist would mean either silently always-passing
(dishonest — looks like it checked something it didn't) or fabricating a
signal from nothing. Instead, setting `require_availability=True`
always adds an explicit note to `reasons` saying exactly this, so nobody
mistakes silence for "checked and fine."

## Validation

- **28 automated tests** (`tests/test_eligibility_engine.py`) covering
  rule serialization round-trips, the score-based default path (proven
  to match `ranking_engine.classify_zone()` exactly), each hard/soft
  gate independently, gate-priority ordering (hard gates beat even a
  trivially-passing score), the documented availability non-gate, and
  the config validator (including a regression test that reproduces the
  exact `"Salesforce CRM"` bug found while building this module).
- `run_day21_eligibility.py` demonstrates all three bundled configs
  against real candidates end to end, validating each config on load.

Run with: `pytest tests/test_eligibility_engine.py -v`
