"""
HR Interview Simulation (Day 40)

WHAT THIS DAY IS: the capstone validation for the entire HR-interview
pipeline built across Days 33-39 (question bank, follow-up logic,
communication scoring, confidence/stress, HR scoring, aptitude, and
summary generation). This is a TEST day, not a feature day -- the
brief asks to simulate candidates, compare AI output against manual
(human-reasoned) expectations, and identify scoring inconsistencies.
No new scoring signal is introduced here; this module's only job is
to run the existing pipeline end-to-end against four deliberately
different candidate personas and report, honestly, where the AI's
output does and does not match what a human reviewer would conclude.

FOUR PERSONAS, CHOSEN TO PROBE SPECIFIC RISKS, NOT JUST RUN HAPPILY:
  - CONFIDENT: clean, concrete, well-structured answers -- the
    baseline the pipeline is best tuned for.
  - HESITANT: substantively reasonable content, delivered with heavy
    filler words and hedging ("um", "I think", "I guess") -- probes
    whether the pipeline conflates DELIVERY STYLE with CONTENT
    QUALITY.
  - INEXPERIENCED: short, generic, low-content answers from a
    plausible fresher -- probes whether "weak" gets correctly kept
    separate from "risky/inconsistent."
  - OVERQUALIFIED: dense, technically strong answers that include
    candid self-disclosure of impatience/frustration -- probes
    whether nuanced, partially negative self-reflection gets
    mis-flagged as a contradiction.

MANUAL EXPECTATIONS ARE HAND-WRITTEN, STATED HONESTLY: there is no
human-rated dataset in this project (as every prior scoring day has
noted). The "manual evaluation" baseline here is a single reasoned
sentence per persona, written by hand before running the pipeline,
describing what a competent human interviewer would likely conclude.
This is a sanity-check baseline, not a statistically validated ground
truth -- named as such rather than presented as authoritative.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from parsers.hr_interview_question_bank import InterviewSession, ExperienceLevel, RoleType
from parsers.hr_interview_scoring_engine import score_hr_interview, HRInterviewScoreReport
from parsers.aptitude_logic_engine import AptitudeSession, build_aptitude_profile, AptitudeProfile
from parsers.confidence_stress_engine import build_confidence_profile, InterviewConfidenceProfile
from parsers.interview_summary_generator import generate_interview_summary, InterviewSummaryReport


@dataclass
class PersonaDefinition:
    name: str
    description: str
    hr_answers: List[str]
    aptitude_answers: List[str]
    manual_expectation: str
    experience_level: ExperienceLevel = ExperienceLevel.EXPERIENCED
    role_type: RoleType = RoleType.TECHNICAL


PERSONAS: List[PersonaDefinition] = [
    PersonaDefinition(
        name="Confident",
        description="Clean, concrete, well-structured answers with no disfluency.",
        hr_answers=[
            "For example, I led the migration project and delivered it two weeks ahead of schedule. I'm confident in my ability to own complex systems end to end.",
            "I steadily grew from junior to senior engineer over four years, taking on more ownership each year and mentoring two junior developers.",
            "My strength is ownership; my weakness is that I sometimes move fast and need to slow down to document things properly.",
            "For example, I resolved a conflict between two teammates by listening to both sides and proposing a compromise that both accepted.",
        ],
        aptitude_answers=[
            "Since all labels are wrong, I would pick from the box labeled Mixed, then deduce the other two and relabel correctly.",
            "First take the chicken across, then go back alone, bring the grain, then bring the chicken back, take the fox, then return for the chicken.",
            "No, we cannot conclude that, because the blips that are trons might be a different subset than the zorgs.",
            "For example, I would talk to them privately to understand why, and offer to help. If it continues, I would escalate.",
            "I would explain my concern with reasoning, but respect their decision and document it in writing.",
            "I would assess business impact, communicate with both stakeholders, and negotiate the deadline.",
        ],
        manual_expectation="A human interviewer would likely rate this candidate highly across the board -- clear content, calm delivery, no red flags. Expected: Strong/Good band, minimal or no risk flags.",
    ),
    PersonaDefinition(
        name="Hesitant",
        description="Reasonable, relevant content delivered with heavy filler words and hedging.",
        hr_answers=[
            "Um, I think, uh, I have been working as a developer for about three years, I guess, and, um, I worked on a couple of projects.",
            "So, um, I started as an intern, and then, uh, I think I became a full-time developer after that, and, um, I have been growing since then I think.",
            "Um, I think my strength is, uh, problem solving I guess, and my weakness is, um, public speaking maybe.",
            "For example, um, I helped a teammate who was stuck, uh, by pairing with them for a while, I think it helped.",
        ],
        aptitude_answers=["Not sure, maybe."] * 6,
        manual_expectation="A human interviewer would likely note the content is substantively fine (real experience, a concrete teamwork example) despite nervous delivery, and would recommend a follow-up conversation rather than a low score. Expected: content-based scores (relevance) should hold up reasonably even though delivery-based scores (confidence, some of communication) are low -- the two should NOT collapse into one uniformly low score.",
    ),
    PersonaDefinition(
        name="Inexperienced",
        description="Short, generic, low-content answers from a plausible fresher -- calm, not contradictory.",
        hr_answers=[
            "I'm a recent graduate and I'm looking for my first job in software.",
            "I don't have much work experience yet, just my college projects.",
            "My strength is that I learn fast. My weakness is I don't have real work experience.",
            "I worked in a group project in college. It went okay.",
        ],
        aptitude_answers=["I'm not sure how to approach this one."] * 6,
        experience_level=ExperienceLevel.FRESHER, role_type=RoleType.NON_TECHNICAL,
        manual_expectation="A human interviewer would score this candidate low on content depth (expected for a fresher) but would NOT consider them 'risky' or inconsistent -- the answers are uniformly modest, not contradictory. Expected: low relevance/aptitude scores, but no (or minimal) consistency/inconsistency risk flags.",
    ),
    PersonaDefinition(
        name="Overqualified",
        description="Dense, technically strong answers with candid self-disclosure of impatience.",
        hr_answers=[
            "For example, I've spent the last ten years architecting large-scale distributed systems, and honestly this role looks a bit junior for my background, but I'm interested in the mentorship angle.",
            "I've done this kind of work many times before, so it feels repetitive at this point, but I understand teams need this done well.",
            "My strength is deep technical expertise; my weakness is I can get impatient and frustrated with slower-paced teams.",
            "For example, I once had to hold back frustration when a junior teammate made repeated mistakes, but I coached them through it patiently and it worked out well.",
        ],
        aptitude_answers=[
            "Since all labels are wrong, I would pick from the box labeled Mixed, then deduce the other two.",
            "Take the chicken first, then go back, bring the grain, bring the chicken back, take the fox, then return for the chicken.",
            "No, we cannot conclude that, because the trons might be a different subset than the zorgs.",
            "For example, I would talk to them privately to understand why, and offer to help.",
            "I would explain my concern with reasoning and respect their final decision.",
            "I would assess impact and communicate with both stakeholders.",
        ],
        manual_expectation="A human interviewer would likely rate the technical content highly, but note the candid mix of frustration and patience as a genuine, single-answer nuance worth a culture-fit conversation -- not a fabricated contradiction between separate answers. Expected: strong relevance/aptitude, and any consistency signal should trace to the ONE answer with mixed sentiment, not be misread as swings between unrelated answers.",
    ),
]


@dataclass
class PersonaSimulationResult:
    persona: PersonaDefinition
    hr_report: HRInterviewScoreReport
    aptitude_profile: AptitudeProfile
    confidence_profile: InterviewConfidenceProfile
    summary: InterviewSummaryReport


def run_persona_simulation(persona: PersonaDefinition) -> PersonaSimulationResult:
    session = InterviewSession.start(persona.experience_level, persona.role_type)
    for text in persona.hr_answers:
        session.submit_response(text)

    apt_session = AptitudeSession.start()
    for text in persona.aptitude_answers:
        apt_session.submit_response(text)

    hr_report = score_hr_interview(session)
    aptitude_profile = build_aptitude_profile(apt_session)
    confidence_profile = build_confidence_profile(session)
    summary = generate_interview_summary(hr_report, aptitude_profile=aptitude_profile, confidence_profile=confidence_profile)

    return PersonaSimulationResult(
        persona=persona, hr_report=hr_report, aptitude_profile=aptitude_profile,
        confidence_profile=confidence_profile, summary=summary,
    )


def run_all_personas() -> List[PersonaSimulationResult]:
    return [run_persona_simulation(p) for p in PERSONAS]
