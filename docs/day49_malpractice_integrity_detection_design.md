# Day 49 — Malpractice & Integrity Detection Design

## What this day is, and the decision it makes up front

The brief asks for a system that detects cheating or external assistance
during interviews, built around four signals: tab-switching frequency,
loss of screen focus, external voice detection, and repeated looking away.

Those four are not the same kind of signal. Two of them come from the
**browser** and need no sensor at all. Two of them need **audio or camera
analysis**, which this project does not have — verified the same way Day 48
verified it: nothing in the codebase processes audio or image data.

This day therefore builds the two observable signals for real, and lists the
other two as **not implemented, with the reason, in every report** — exactly
the discipline Day 48 applied to its four camera signals.

| Brief's signal | Status | What it needs / what is built |
|---|---|---|
| Tab switching frequency | **Implemented** | Browser `visibilitychange` events (tab hidden / visible) |
| Loss of screen focus | **Implemented** | Browser window `blur` / `focus` events |
| External voice detection | **Not implemented** | Audio analysis. No audio pipeline exists, and it would also record bystanders' voices — a third-party privacy problem on top of the consent gap Day 43 found |
| Repeated looking away | **Not implemented** | Camera / computer vision. Same blockers Day 48 documented: biometric data, no consent capture, no fairness review for facial signals |
| *(PRD Phases 19 / 42: mobile or secondary-device usage)* | **Not implemented** | Not observable from browser events — a second device is invisible to this system |

## Integrity detection framework

```
 client browser                      Integrity Detection Engine                          consumers
┌────────────────┐   events   ┌────────────────────────────────────────────────┐
│ tab hidden/     │ ─────────> │ 1. Pair events -> away-intervals (merge        │
│ visible,        │            │    hidden+blur, ignore blips < 1.5 s)          │
│ window blur/    │            │ 2. Signals: counts, time away, longest absence │
│ focus           │            │ 3. Threshold flags                             │
└────────────────┘            │ 4. Pattern recognition (burst, lookup)         │
                              │ 5. Corroboration with Day 48 latency spikes    │
 Day 48 timed                 │ 6. Risk tag + reasons                          │ ──> IntegrityReport
 records  ───────────────────>│ 7. Real-time alerts (IntegrityMonitor)         │ ──> candidate notices
                              └────────────────────────────────────────────────┘     (never accusations)
```

Code: `parsers/integrity_detection_engine.py`.

## Malpractice detection logic

### Threshold-based flags

All thresholds are **reasoned, not calibrated** — no labelled malpractice
data exists in this project, the same caveat every scoring day since Day 34
has stated.

| Flag | Trigger | Points |
|---|---|---|
| `FREQUENT_FOCUS_LOSS` | 2–3 counted focus losses / 4–5 / 6+ | 1 / 2 / 3 |
| `SIGNIFICANT_AWAY_TIME` | ≥ 5% / ≥ 15% of the session spent away | 1 / 2 |
| `LONG_SINGLE_ABSENCE` | one absence ≥ 10 s / ≥ 30 s | 1 / 2 |

A focus loss shorter than **1.5 seconds** is not counted — OS notifications
and pop-ups steal focus too — but it is still reported as `ignored_blips`
so nothing is silently dropped.

### Pattern recognition

Thresholds count things. Patterns look at *shape and timing*, which is what
separates an interrupted candidate from a candidate who is looking things up.

| Pattern | Definition | Points |
|---|---|---|
| `BURST_SWITCHING` | 3+ counted focus losses inside 60 seconds | 2 |
| `QUESTION_LOOKUP_PATTERN` | On **2+ different questions**, the candidate left within 5 s of the question appearing and returned within 10 s of submitting the answer (and was away ≥ 3 s) | 3 |

The lookup pattern needs two occurrences on purpose: one is coincidence
(everyone checks a message once), two is a pattern. Question timing is rebuilt
from Day 48's timed records — cumulative latency *is* the question timeline,
because Day 48's tracker presents each question the instant the previous one
is submitted. Nothing in Day 48 or the session classes was modified.

### Corroboration (integration with Day 48)

`LATENCY_CORROBORATION` (up to +2): a Day 48 latency spike on a question
where a focus loss **also** occurred.

> **Rule: behavioral signals can only corroborate, never accuse.** A long
> pause, slow answers, or filler words with *no* browser event produce no
> flag and a `CLEAR` tag. Slowness is not malpractice. This is tested
> directly (`test_latency_spike_alone_never_raises_integrity_risk`) and shown
> in the demo (scenario D).

## Warning & flagging system

### Real-time alerts (`IntegrityMonitor`)

Events are fed in one at a time; an alert is returned the moment a counted
focus loss completes and crosses a rung.

| Counted focus loss | Alert | Who sees it |
|---|---|---|
| 1st | `NOTICE` — gentle reminder to keep the window in front | Candidate |
| 2nd–3rd | `WARNING` — firmer reminder that leaving may be recorded and reviewed | Candidate |
| 4th | `FLAG` — internal review flag, raised once | **Recruiter side only** |
| Still away ≥ 30 s (`poll()`) | `WARNING` (once per absence) | Candidate |

The candidate is warned, but is **not accused mid-interview** — the `FLAG`
has no candidate-facing message. The monitor never pauses, ends, or
re-scores an interview.

### Interview risk tagging

Flag points are summed into a tag. The tag always travels with its reasons.

| Tag | Points | Meaning |
|---|---|---|
| `CLEAR` | 0 | No indicators in the signals this system can see — **not proof none exist** |
| `LOW` | 1–2 | Consistent with ordinary distraction. No action |
| `MEDIUM` | 3–5 | Review recommended before relying on this interview |
| `HIGH` | 6+ | Human review required before any decision relies on this interview |

Every report carries `automated_action: "none"` and `scoring_impact: "none"`.
The PRD calls for "auto-flag interview" (Phases 19 and 42) — this design
flags for a human, and stops there.

## Plan for integration with behavioral signals

| Integration point | Plan | Status |
|---|---|---|
| Day 48 `TimedSessionTracker` | `build_integrity_report(events, records=tracker.records)` rebuilds question windows and enables corroboration | **Done** |
| Day 48 spikes → risk | Corroborate only, never raise risk alone | **Done, tested** |
| Client → engine event contract | `{"event_type": "tab_hidden" \| "tab_visible" \| "window_blur" \| "window_focus", "timestamp": <seconds since session start>}` per event, streamed to `IntegrityMonitor.record_event()` | **Specified, no client exists yet** |
| Day 39 summary generator | Show the tag + flags as a *separate* "Integrity" section, never merged into strengths/weaknesses | Planned, not wired |
| Day 41 unified scoring | Report integrity **beside** the score, not inside it. Recommended: no score adjustment, because the signal is unvalidated and a wrong adjustment silently changes a hiring outcome | Planned, not wired — product decision |
| Future audio / camera signals | Reserved only. Each would need: a consent capture flow, a fairness review for that signal type, a bystander-privacy answer (audio), and legal review — before any code is written. Events would enter as extra flag types with `source` and `model_version`, never as hidden score inputs | Blocked, by design |

## False-positive and fairness design

- **Benign causes are documented in every report** (`caveats`): notifications,
  OS dialogs, assistive technology, second monitors, browser and network
  trouble.
- **Blip filter** (< 1.5 s) and the **two-occurrence rule** for the lookup
  pattern exist specifically to keep ordinary candidates at `CLEAR`/`LOW`.
- **No demographic input** of any kind; thresholds are the same for everyone.
  They do not adapt to who the candidate is.
- **Accessibility is an open risk.** Screen readers and other assistive tools
  can legitimately change window focus. This design cannot yet tell the
  difference, which is a reason the tag requires human review and never
  triggers automatic action.
- **A `CLEAR` tag is not a guarantee.** Browser events can be blocked or
  spoofed, and a second device is invisible here.

## Demo results

Synthetic timeline (real question IDs and answers from a Day 33 HR session,
realistic latencies, hand-placed browser events — labelled as such in the
demo); the detection logic is real.

| Scenario | Tag | Why |
|---|---|---|
| A. One 0.9 s notification blip | `CLEAR` | Blip ignored but reported |
| B. Two short mid-question switches (6 s, 4 s) | `LOW` | `FREQUENT_FOCUS_LOSS` only; no review required |
| C. Leaves right after two questions, returns before answering | `HIGH` | Lookup pattern + latency corroboration + long absences |
| D. One huge pause, no browser events | `CLEAR` | Slowness alone is never malpractice |

The monitor replay of scenario C escalated `NOTICE` → `WARNING`, with any
`FLAG` staying internal.

## Known limits

- Thresholds are reasoned, not calibrated; real interview data is needed.
- A single absence lasting several minutes can alone reach `MEDIUM` (the
  long-absence and away-time flags stack). That is a deliberate "ask a human"
  choice, but it means one genuine interruption (power cut, network drop)
  will be queued for review.
- No browser client exists; the event contract is specified, not exercised
  against a real `visibilitychange` stream.
- Consent and retention infrastructure still do not exist (Day 43).
  Candidates must be told about monitoring before it runs.
- Accessibility interaction (assistive tech vs. focus events) is untested.
