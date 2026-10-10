"""
HR Interview Demo & Finalization (Day 45)

WHAT THIS DAY IS: the wrap-up for the HR interview AI (Days 33-44) --
one real, scoped "final improvement" closing a gap flagged twice
already (Days 43 and 44), a live end-to-end demo, and the production-
readiness assessment the brief's "handover system" task actually asks
for. Not a new scoring engine -- everything scored here is produced by
engines that already exist; this day packages and closes out.

FINAL IMPROVEMENT -- WIRING DAY 43'S SCRUBBER IN (closes the gap
flagged in day43_compliance_readiness_report.md and
day44_developer_integration_guide.md): rather than modify
`InterviewSession.submit_response()` directly -- a method every
engine from Days 34-41 calls or depends on the shape of, and a risky
place to change behavior this late -- this adds a thin, OPT-IN wrapper
function instead. Existing callers and every existing test are
completely unaffected; nothing about `InterviewSession` itself
changes. A caller who wants scrubbing gets it explicitly; a caller who
doesn't is unaffected, including every test from Days 33-44 that calls
`submit_response()` directly.

ENVIRONMENT NOTE, same as Days 41-44: this build has the base project
through Day 34, plus Days 41, 42, 43's own additions. Days 35, 36, 37,
38, 39, 40 aren't present locally. The live demo below is built
honestly around that constraint -- it runs every piece that's actually
executable here (the real interview session, real follow-up decisions,
real demographic scrubbing, real unified scoring) and uses clearly
labeled REPRESENTATIVE numbers, not fabricated engine output, for the
three scores (communication, confidence, HR composite) this
environment can't compute live. See
`docs/day45_manager_evaluation_feedback.md` for the honest accounting
of what that means for "production-ready."
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from parsers.hr_interview_question_bank import InterviewSession, InterviewQuestionState
from parsers.hr_followup_engine import decide_follow_up, FollowUpDecision
from parsers.transcript_demographic_scrubber import mask_demographic_disclosures


@dataclass
class ScrubbedSubmissionResult:
    question: InterviewQuestionState
    categories_detected: List[str]
    follow_up: Optional[FollowUpDecision]


def submit_scrubbed_response(
    session: InterviewSession, text: str, decide_follow_ups: bool = True,
) -> ScrubbedSubmissionResult:
    """Opt-in wrapper around InterviewSession.submit_response() that
    runs Day 43's demographic scrubber on the text BEFORE it's stored,
    and (optionally, on by default) runs Day 34's follow-up decision
    immediately after -- the two things Day 43/44 noted were real but
    not yet connected to the actual session flow. Returns both results
    so a caller doesn't have to make two more calls to get what
    submitting a response already implies they'll want.

    Does not change InterviewSession in any way -- a caller using
    submit_response() directly, as every test from Days 33-41 does,
    is completely unaffected.
    """
    question = session.current_question
    if question is None:
        raise ValueError("Interview already complete -- no current question to respond to.")

    masked_text, categories = mask_demographic_disclosures(text)
    session.submit_response(masked_text)

    follow_up = None
    if decide_follow_ups and question.follow_up_eligible:
        follow_up = decide_follow_up(question, masked_text)

    return ScrubbedSubmissionResult(question=question, categories_detected=categories, follow_up=follow_up)
