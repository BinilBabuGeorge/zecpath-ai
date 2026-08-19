# Day 15 — Fairness, Normalization & Bias Reduction

## What problem this addresses

Days 9–14 built a working, explainable scoring and ranking pipeline. Day 15
audited that pipeline specifically for **bias vectors and fairness gaps**,
rather than adding new scoring capability.

## Concrete finding

Day 12's semantic matcher (`semantic_matcher.py`) compares three text
components between resume and JD — `skills`, `experience`, and `overall` —
weighted 45/35/20. `section_extractor.extract_resume_sections()["overall"]`
is the **entire raw resume text**, unfiltered. That means a candidate's name,
email, phone number, and location are literally tokenized and fed into the
TF-IDF cosine-similarity calculation that's supposed to measure job fit.

Measured on a real resume/JD pair in this dataset: stripping the header
(Name/Email/Phone/Location) shifted the `overall` TF-IDF sub-score from
`0.1818` to `0.1893`. Small per-candidate, but systematic — every single
score computed by this system carries this vector, and it is scoring
something (a name matching JD text by coincidence) with zero legitimate
job-fit signal.

## What was implemented

### 1. Resume normalization (`normalize_resume_text`)
Standardizes line endings, bullet characters (•, ◦, ▪, *, ● → `-`), trailing
whitespace, and excess blank lines before any parsing happens. Formatting
differences between resumes (which bullet symbol someone's word processor
used) shouldn't affect parsing reliability or token noise in TF-IDF.

### 2. Reducing over-dependence on keywords
Two separate mechanisms, because "keyword dependence" shows up in two
different places:
- **`detect_keyword_stuffing`** — a text-level integrity check. Flags a
  skill mentioned 5+ times literally in a resume (calibrated against this
  project's own sample data: legitimate resumes here top out at 4 natural
  mentions of one skill — once each in Skills/Summary/Experience/
  Certifications — so 5+ is the point where it stops looking like normal
  writing and starts looking like the resume was edited to game a scanner).
  Verified against all 15 sample resumes with **zero false positives**.
- **`fairness_adjusted_weights`** — a scoring-formula level check. Shifts a
  configurable fraction (default 30%) of `skill_match`'s weight to the other
  three components, so no single exact-keyword-match component can dominate
  the overall score. Opt-in — Day 13's default `WEIGHT_PROFILES` are
  untouched; a caller has to explicitly ask for the fairness-adjusted
  profile via `score_with_fairness(..., use_fairness_weights=True)`.

### 3. Scoring normalization (`normalize_scores_batch`)
Raw overall scores aren't comparable across role categories — Day 13's own
weight profiles mean a strong tech match and a strong business match don't
land on the same numeric scale (observed ceiling on this sample dataset:
~50–55 for tech roles, ~61–63 for business roles). Min-max normalizing
within a batch, plus a percentile rank, makes "top of the pool" mean the
same thing regardless of which JD or category a candidate was scored
against — which matters the moment recruiters compare candidates across
departments.

### 4. Masking non-essential personal attributes (`mask_pii`)
Redacts the *value* of Name, Email, Phone, Location, and — when present —
Gender, Date of Birth, Age, Marital Status, Religion, Nationality, Father's/
Husband's Name, and Photo, while keeping the field label so line structure
and section boundaries (`Skills:`, `Experience:`, `Education:`) are
untouched. None of these fields carry job-relevant signal; several are
classic bias proxies (name → gender/ethnicity inference, photo → age/
ethnicity, location → regional/caste proxy in some contexts).

The 14 original sample resumes only carry Name/Email/Phone/Location — a new
sample resume, `resume_15_bias_fields.txt`, was added with the fuller set
(Gender, DOB, Marital Status, Religion, Nationality, Father's Name, Photo)
specifically to prove the masking logic works on fields a real-world
uploaded resume might contain even though this project's own sample data
doesn't exercise them.

### 5. Bias indicator evaluation (`evaluate_bias_indicators`)
Produces a `BiasReport` per resume: which non-essential fields were found,
whether keyword stuffing was detected, and a heuristic risk level (low /
medium / high) based on how many flags were raised. This is a **checklist,
not a statistical fairness audit** — see limitations below.

### Tying it together (`score_with_fairness`)
Wraps `score_candidate()`: normalizes → masks PII → (optionally) applies
fairness-adjusted weights → scores. Also scores the untouched original for
comparison and reports `score_delta`, so it's possible to verify masking
removed bias vectors *without* silently changing a candidate's legitimate
standing. On `resume_15_bias_fields.txt` vs `jd_01_mern_developer`: raw
score 50.0 → fair score 50.1 (delta +0.1) — proof the masking is doing what
it's supposed to: removing noise, not content.

## Known limitations (stated honestly, not hidden)

- **This is not a statistical fairness audit.** Metrics like demographic
  parity or equal opportunity require protected-attribute ground truth
  (actual demographic labels on real candidates) that this system
  deliberately does not collect. What's implemented here is a defensible
  bias-*risk* checklist: known bias vectors flagged and removed, not a
  measured fairness guarantee.
- **Keyword stuffing threshold (5+ mentions) is heuristic**, calibrated
  against this project's own 15-resume sample. A much longer or much
  shorter resume format might need a different threshold or a
  length-normalized version of the same check.
- **Location masking is a judgment call.** Location can be a legitimate
  need (relocation, timezone, in-office requirements) as well as a bias
  proxy. It's currently masked before scoring since nothing in the scoring
  formula legitimately needs it, but a production system might want to
  keep it available post-scoring for logistics.
- **Fairness-adjusted weights are opt-in, not default**, specifically so
  this change doesn't silently alter every score already validated in Day
  13/14's test suites. A product decision is needed on whether to make it
  the default going forward.
- Every limitation already documented in Days 9–13 (skill dictionary
  coverage, TF-IDF as a proxy for semantic understanding, default
  degree-level assumption) still applies — this layer reduces specific bias
  vectors in the existing pipeline, it doesn't replace the pipeline.
