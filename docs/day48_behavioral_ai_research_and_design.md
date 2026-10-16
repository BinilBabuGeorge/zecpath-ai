# Day 48 — Behavioral AI Research & Design

## What this document is, and the decision it makes up front

The brief's "research behavior signals" list — eye movement, gaze
stability, head movement, facial engagement — describes **camera-based
biometric analysis**. This project has no video pipeline anywhere: no
camera input, no frame processing, no face/landmark detection library.
Verified directly: a project-wide search for `cv2`, `opencv`,
`mediapipe`, `dlib`, `face_recognition`, `webcam`, `video` across every
Python file returns zero hits.

Building functions named `detect_gaze_stability()` or
`detect_nervous_gestures()` that don't actually process any image data
would not be a limited or approximate version of that capability — it
would be **fabricating a capability that does not exist**, exactly
what every prior day in this project has gone out of its way not to
do. That line isn't crossed here either. This document explains why,
and what was built instead.

## The brief's own last task is the way through this

"Design a **non-invasive** behavioral scoring approach" is the binding
constraint this day treats as real, not a throwaway phrase. Camera-
based gaze/facial analysis is the invasive option:

- It requires collecting biometric data. This project's own Day 43
  audit already found **zero consent-capture infrastructure exists
  anywhere**, for even plain text. Video/facial data is a materially
  higher-stakes category than text — most privacy frameworks, and
  emerging AI-specific regulation in several jurisdictions, treat
  biometric categorization and emotion inference in employment
  contexts as high-risk or restricted. (General awareness of the
  regulatory landscape, not legal advice — a real deployment should
  get real legal review before touching biometric data at all.)
- Facial-analysis-based emotion/engagement inference is well-
  documented elsewhere to carry demographic bias risk, and this
  project's only fairness module (Day 15) covers resume PII, not
  biometric signals of any kind.
- Adding it would directly compound two problems Day 43 already named
  as open (no consent, no fairness review for non-ATS rounds), rather
  than fixing either.

**The design decision this day makes**: treat "non-invasive" as
meaning *no new sensor, no camera, no biometric capture at all* — and
build genuinely observable signals from **interaction timing and
text**, data this project already collects or can collect without
adding any new capability class.

## Signal mapping — what the brief asked for vs what this builds

| Brief's signal | Status | What's actually measured instead |
|---|---|---|
| Eye movement / gaze stability | **Not implemented** | — (needs camera) |
| Head movement | **Not implemented** | — (needs camera) |
| Facial engagement | **Not implemented** | — (needs camera) |
| Focus level | Reinterpreted | Response-latency **consistency** across a session (low variance = steady pacing) |
| Distraction frequency | Reinterpreted | Anomalous latency **spikes** relative to the candidate's own median pace |
| Nervous gestures | **Not implemented as asked** | Verbal hesitation (filler words, reused from Day 27) — a genuinely *different* signal (speech disfluency, not gesture), labeled as such rather than silently substituted |

Every report this engine produces lists the four not-implemented
camera signals **explicitly**, every time — verified by a dedicated
test (`test_report_explicitly_lists_unimplemented_camera_signals`) —
so a consumer of this report can never mistake "not implemented" for
"implemented and returned zero."

## Reuse

`detect_hesitation()` is imported directly from Day 27's
`confidence_sentiment_engine`, unchanged — the same generic, screening-
independent filler-word detector Day 36 already reused for a different
purpose. Timing itself is new: no session in this project currently
records when a question was presented or when a response arrived, so
this day adds that via the same additive, opt-in wrapper pattern
Day 45 established (`submit_scrubbed_response()`) — a new
`TimedSessionTracker` that works with **either** `InterviewSession`
(Day 33) or `TechnicalInterviewSession` (Day 46) via light duck-typing,
verified directly against both, and leaves both session classes
completely untouched for every existing caller.

## Signal-to-score mapping model

- **Focus level** = `(1 − coefficient_of_variation) × 100`, clamped to
  0–100. A candidate answering at a steady pace scores high regardless
  of whether that pace is fast or slow — consistency is the signal,
  not speed, deliberately avoiding penalizing candidates who simply
  think carefully.
- **Distraction frequency** = 100 minus the percentage of answers
  whose latency exceeds 2× the session's own median. The *candidate's
  own* median, not a fixed global threshold, so this adapts to
  individual pace rather than assuming everyone should answer equally
  fast.
- **Verbal hesitation rate** — Day 27's existing per-100-words filler
  rate, averaged across the session, reported as its own distinct
  number rather than folded into "distraction" or "nervousness."

All three are reasoned, not data-calibrated — the same caveat stated
on every scoring day since 34. Demo run: a deliberately exaggerated
0.6-second pause against an ~0.08-second baseline (compressed for fast
test execution) correctly triggered the distraction-spike detector at
the expected question, and a filler-heavy answer correctly raised the
verbal-hesitation rate above zero — both confirmed by the demo's own
sanity checks, not just asserted. The focus-level score dropped to 0.0
in that run specifically because of how exaggerated the artificial
delay was relative to the other answers; real interview pacing
variation would typically be less extreme in relative terms.

## Deliverables

- **Behavioral AI design document** — this document: the research
  finding (camera-based signals aren't buildable here, and building
  fake versions would be dishonest), the "non-invasive" design
  decision, and the explicit signal-mapping table.
- **Signal-to-score mapping model** — the focus/distraction/hesitation
  formulas above, implemented in
  `parsers/behavioral_signal_engine.py`.
- **Behavioral analysis framework** — `TimedSessionTracker` (works
  with either existing session type) +
  `build_behavioral_insight_report()`, producing a fully explainable
  `BehavioralInsightReport` with both `to_dict()` and
  `to_summary_text()`.

## Verification

16 new tests (`tests/test_behavioral_signal_engine.py`), covering the
tracker against both session types, focus-consistency scoring at both
extremes (perfectly steady and highly variable pacing), real spike
detection, the too-few-records edge case, verbal hesitation reuse, and
— explicitly — that the camera-dependent signals are always named as
not implemented in every report. `pytest` isn't installable in this
build environment (no network access), so these ran via the same
assert-based Python runner used since Day 35. Full project regression
(373 tests, 357 previous + 16 new) passed clean with zero regressions.

## Not done here (left for a future day, or not done at all)

- **Camera-based signals** — not a "future day" item in the usual
  sense of this project's notes. Building them would require adding an
  entirely new capability class (video capture, a face/landmark
  detection model) to a project that has been exclusively text/timing-
  based through 47 prior days, plus resolving the consent and fairness
  gaps Day 43 already found *before* collecting a materially more
  sensitive data type. If this capability is genuinely wanted, it
  needs a dedicated decision — ideally informed by real legal/privacy
  review — not a quiet addition tucked into a "research and design"
  day.
- Wiring `TimedSessionTracker` into Day 41's unified scoring or Day 39's
  summary generator as an additional input.
- Calibrating the latency-spike threshold or focus-score formula
  against real interview timing data — none exists in this project yet.
