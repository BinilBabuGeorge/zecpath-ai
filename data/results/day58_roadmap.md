### Phase 0 - Built (Days 1-57)
Exit gate (proposed): Rule-based scoring layer, governance logic, simulation and stabilization complete; no persistence, login, real speech or video.

### Phase 1 - Make it real and safe
Exit gate (proposed): Services behind login with a persisted, anchored audit log; consent wired to intake; at least two recruiters have rated a defined set of real cases; the confidence/stress question is decided; the resume check is live.
| ID | Feature | Value | Effort | Feasibility | Priority | Depends on |
|---|---|---|---|---|---|---|
| C1 | Resume readiness check | 5 | 1 | 5 | 14 | - |
| F3 | Human rating pipeline | 5 | 2 | 4 | 12 | - |
| R1 | Review and relabel the text-based confidence and stress signals | 4 | 1 | 5 | 12 | - |
| F2 | Continuous evaluation harness | 4 | 2 | 5 | 11 | - |
| F1 | Persistence, authentication and deployment baseline | 5 | 4 | 3 | 9 | - |
| F4 | Consent and data-subject rights wired to intake | 5 | 3 | 4 | 11 | F1 |

### Phase 2 - Candidate and recruiter value
Exit gate (proposed): Coach and dashboard in pilot with measured outcomes; bias monitoring producing aggregate selection rates; jurisdiction switches working; real speech pipeline with measured latency and word-error rate.
| ID | Feature | Value | Effort | Feasibility | Priority | Depends on |
|---|---|---|---|---|---|---|
| C2 | Practice interview coach (HR and technical) | 5 | 3 | 3 | 10 | F1, F4, C1 |
| S4 | Jurisdiction policy engine | 4 | 2 | 4 | 10 | F1 |
| C5 | Interview analytics dashboard | 4 | 3 | 4 | 9 | F1 |
| F6 | Bias audit and adverse-impact monitoring | 5 | 4 | 3 | 9 | F1, F3 |
| C4 | Candidate feedback after a decision | 4 | 3 | 3 | 8 | F1, F3 |
| F7 | Multi-tenant isolation with per-tenant keys | 4 | 3 | 3 | 8 | F1 |
| F5 | Real speech pipeline with asynchronous workers | 4 | 4 | 3 | 7 | F1 |
| C3 | Speech delivery feedback inside the coach | 4 | 2 | 3 | 9 | C2, F5 |
| V4 | Live non-evaluative technical checks | 3 | 2 | 4 | 8 | F5 |

### Phase 3 - Media and scale
Exit gate (proposed): Real calls and the machine-test stage in pilot; any video flag launched only if its false-flag rate is low and equal across groups.
| ID | Feature | Value | Effort | Feasibility | Priority | Depends on |
|---|---|---|---|---|---|---|
| C6 | Fairness and drift panel | 4 | 2 | 3 | 9 | C5, F6 |
| S2 | Machine-test stage in the orchestrated pipeline | 4 | 3 | 3 | 8 | F5 |
| V6 | Real-time feedback inside practice mode | 4 | 3 | 3 | 8 | C2, C3, F5 |
| S1 | Telephony provider integration for AI screening calls | 4 | 4 | 3 | 7 | F1, F4, F5 |
| V1 | Interview integrity signals from video (detection only) | 3 | 4 | 2 | 4 | F1, F4, F5, F6 |

### Phase 4 - Learn responsibly
Exit gate (proposed): A learned scorer promoted only after shadow-mode agreement with human ratings beats the baseline with no subgroup gap beyond the agreed limit.
| ID | Feature | Value | Effort | Feasibility | Priority | Depends on |
|---|---|---|---|---|---|---|
| S3 | Learned or semantic scoring with evaluation gates | 4 | 5 | 2 | 5 | F2, F3, F6 |

### Not recommended (decision needed)
* V2: Emotion, stress, confidence or honesty inference from face or voice, used in hiring decisions (PRD Phases 18, 41 and 87, and the 'Emotion & confidence analysis' future enhancement) [prohibited_in_recruitment_eu; evidence contradicted]
* V3: Emotion detection inside the candidate coach [restricted; evidence unvalidated]
* V5: Real-time evaluative feedback to candidates during a scored interview [allowed; evidence unvalidated]