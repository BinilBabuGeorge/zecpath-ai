"""
HR Interview Engine Design (Day 33)

WHAT THIS DAY IS: the foundational architecture for a NEW phase of this
project -- the AI HR Interviewer (behavioral interview), distinct from
the screening-call phase (Days 22-32). Screening (Day 22) gathers
FACTS to filter candidates (education, experience, skills, salary,
notice period). This day's questions are BEHAVIORAL -- self-
introduction, career journey, strengths/weaknesses, teamwork/culture
fit, career goals, availability/commitment -- the kind an actual human
HR interviewer asks once a candidate has already cleared screening.

Per the brief, this is a DESIGN day: category taxonomy, a role-based
question generator, an interview state structure, and conversation
phases. Consistent with every other day in this project, "design"
still means real, tested, runnable code -- not just a diagram. What is
correctly OUT of scope here (left for a future day, the same way
Day 22's question bank existed for years before Day 29 built real
conversational logic on top of it): retry/clarification/follow-up
DECISION logic. This day defines whether a question is CAPABLE of a
follow-up (`follow_up_eligible`) and a place to store one
(`follow_up_text`) -- it does not decide algorithmically WHEN to ask
one. That is exactly the kind of runtime decision Day 29 built for the
screening phase, once Day 22's structures existed to build on.

Role-based variation is used ONLY where it's genuinely justified, not
manufactured to hit a 2x2 grid mechanically:
  - career_journey varies on BOTH axes (fresher vs. experienced changes
    what career history even exists to ask about; technical vs.
    non-technical changes what kind of history matters) -- the
    flagship example of real role-based variation.
  - teamwork_culture_fit varies by experience level only (a fresher has
    no workplace team to ask about yet; a non-technical/technical split
    doesn't change what teamwork looks like).
  - career_goals varies by role type only (growth paths genuinely
    differ between technical and non-technical tracks; fresher vs.
    experienced doesn't change the question itself).
  - self_introduction, strengths_weaknesses, and
    availability_commitment are universal -- forcing role variation
    onto these would be padding, not design.

Reuses Day 22's `get_template_text()` directly for the same honest
multilingual-scaffolding behavior (English populated, other languages
structurally present but explicitly marked as untranslated) rather
than duplicating that logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from parsers.screening_question_bank import get_template_text, SUPPORTED_LANGUAGES

# ---------------------------------------------------------------------------
# Role dimensions -- the two axes the brief's role-based generator varies on
# ---------------------------------------------------------------------------

class ExperienceLevel(str, Enum):
    FRESHER = "fresher"
    EXPERIENCED = "experienced"


class RoleType(str, Enum):
    TECHNICAL = "technical"
    NON_TECHNICAL = "non_technical"


_BOTH_EXPERIENCE = (ExperienceLevel.FRESHER, ExperienceLevel.EXPERIENCED)
_BOTH_ROLE_TYPES = (RoleType.TECHNICAL, RoleType.NON_TECHNICAL)


# ---------------------------------------------------------------------------
# Conversation phases -- the "define conversation phases" deliverable
# ---------------------------------------------------------------------------

class InterviewPhase(str, Enum):
    INTRODUCTION = "introduction"
    CORE_HR = "core_hr"
    ROLE_BASED_EVALUATION = "role_based_evaluation"
    CLOSING = "closing"


# ---------------------------------------------------------------------------
# Category taxonomy -- the "define HR interview categories" deliverable
# ---------------------------------------------------------------------------

CATEGORY_METADATA: Dict[str, Dict] = {
    "self_introduction":      {"phase": InterviewPhase.INTRODUCTION, "default_follow_up_eligible": True},
    "career_journey":         {"phase": InterviewPhase.CORE_HR, "default_follow_up_eligible": True},
    "strengths_weaknesses":   {"phase": InterviewPhase.CORE_HR, "default_follow_up_eligible": True},
    "teamwork_culture_fit":   {"phase": InterviewPhase.CORE_HR, "default_follow_up_eligible": True},
    "career_goals":           {"phase": InterviewPhase.ROLE_BASED_EVALUATION, "default_follow_up_eligible": False},
    "availability_commitment": {"phase": InterviewPhase.CLOSING, "default_follow_up_eligible": False},
}
CATEGORIES = list(CATEGORY_METADATA.keys())


# ---------------------------------------------------------------------------
# Reusable question templates -- the role-based question generator
# ---------------------------------------------------------------------------

@dataclass
class QuestionTemplate:
    template_id: str
    category: str
    localized_text: Dict[str, str]
    applicable_experience_levels: tuple
    applicable_role_types: tuple
    follow_up_eligible: bool


def _tmpl(template_id, category, en_text, experience_levels=_BOTH_EXPERIENCE, role_types=_BOTH_ROLE_TYPES, follow_up_eligible=None):
    meta = CATEGORY_METADATA[category]
    return QuestionTemplate(
        template_id=template_id, category=category,
        localized_text={lang: (en_text if lang == "en" else "") for lang in SUPPORTED_LANGUAGES},
        applicable_experience_levels=experience_levels, applicable_role_types=role_types,
        follow_up_eligible=meta["default_follow_up_eligible"] if follow_up_eligible is None else follow_up_eligible,
    )


QUESTION_TEMPLATES: Dict[str, QuestionTemplate] = {
    # -- self_introduction: universal, no role variation needed --
    "self_intro": _tmpl(
        "self_intro", "self_introduction",
        "Tell me a little about yourself and what's brought you to this interview.",
    ),

    # -- career_journey: varies on BOTH axes -- the flagship example --
    "career_journey_fresher_technical": _tmpl(
        "career_journey_fresher_technical", "career_journey",
        "Walk me through your academic projects and any internships where you applied your technical skills.",
        experience_levels=(ExperienceLevel.FRESHER,), role_types=(RoleType.TECHNICAL,),
    ),
    "career_journey_fresher_non_technical": _tmpl(
        "career_journey_fresher_non_technical", "career_journey",
        "Walk me through your coursework, internships, or extracurricular experience relevant to this role.",
        experience_levels=(ExperienceLevel.FRESHER,), role_types=(RoleType.NON_TECHNICAL,),
    ),
    "career_journey_experienced_technical": _tmpl(
        "career_journey_experienced_technical", "career_journey",
        "Walk me through your career progression -- the roles, technologies, and projects that got you here.",
        experience_levels=(ExperienceLevel.EXPERIENCED,), role_types=(RoleType.TECHNICAL,),
    ),
    "career_journey_experienced_non_technical": _tmpl(
        "career_journey_experienced_non_technical", "career_journey",
        "Walk me through your career progression and the key responsibilities that shaped it.",
        experience_levels=(ExperienceLevel.EXPERIENCED,), role_types=(RoleType.NON_TECHNICAL,),
    ),

    # -- strengths_weaknesses: universal --
    "strengths_weaknesses_general": _tmpl(
        "strengths_weaknesses_general", "strengths_weaknesses",
        "What would you say are your greatest strengths, and a weakness you're actively working on?",
    ),

    # -- teamwork_culture_fit: varies by experience level only --
    "teamwork_fresher": _tmpl(
        "teamwork_fresher", "teamwork_culture_fit",
        "Tell me about a time you worked in a group -- a college project or team activity -- and how you contributed.",
        experience_levels=(ExperienceLevel.FRESHER,),
    ),
    "teamwork_experienced": _tmpl(
        "teamwork_experienced", "teamwork_culture_fit",
        "Tell me about how you've worked within a team at your current or most recent job, including any conflicts you navigated.",
        experience_levels=(ExperienceLevel.EXPERIENCED,),
    ),

    # -- career_goals: varies by role type only --
    "career_goals_technical": _tmpl(
        "career_goals_technical", "career_goals",
        "Where do you see your technical growth heading over the next few years?",
        role_types=(RoleType.TECHNICAL,),
    ),
    "career_goals_non_technical": _tmpl(
        "career_goals_non_technical", "career_goals",
        "Where do you see your career heading over the next few years, and what draws you to this path?",
        role_types=(RoleType.NON_TECHNICAL,),
    ),

    # -- availability_commitment: universal --
    "availability_commitment_general": _tmpl(
        "availability_commitment_general", "availability_commitment",
        "How committed are you to a long-term role here, and what's your current availability to join?",
    ),
}


def _select_template(category: str, experience_level: ExperienceLevel, role_type: RoleType) -> QuestionTemplate:
    """Picks the one template matching both axes for a category. Falls
    back to the first template found for the category if, due to a
    data-entry gap, nothing matches both axes exactly -- defensive, not
    expected to trigger with the templates defined above (covered by
    tests), same defensive stance the rest of this project takes rather
    than letting a KeyError surface mid-interview.
    """
    candidates = [t for t in QUESTION_TEMPLATES.values() if t.category == category]
    exact = [t for t in candidates if experience_level in t.applicable_experience_levels and role_type in t.applicable_role_types]
    if exact:
        return exact[0]
    return candidates[0]


# ---------------------------------------------------------------------------
# Rendered output -- the AI-conversation-ready question
# ---------------------------------------------------------------------------

@dataclass
class HRInterviewQuestion:
    id: str
    category: str
    phase: InterviewPhase
    text: str
    follow_up_eligible: bool
    language: str = "en"


def generate_hr_interview_questions(
    experience_level: ExperienceLevel, role_type: RoleType, lang: str = "en",
) -> List[HRInterviewQuestion]:
    """Builds one question per category, in CATEGORIES order, selecting
    the role-appropriate template for each. This is the "role-based
    question generator" deliverable -- the only thing that changes
    based on experience_level/role_type is WHICH pre-written template
    gets selected per category; nothing is generated on the fly.
    """
    questions = []
    for i, category in enumerate(CATEGORIES, start=1):
        tmpl = _select_template(category, experience_level, role_type)
        text = get_template_text(tmpl.template_id, QUESTION_TEMPLATES, lang)
        questions.append(HRInterviewQuestion(
            id=f"hr-q{i:02d}", category=category, phase=CATEGORY_METADATA[category]["phase"],
            text=text, follow_up_eligible=tmpl.follow_up_eligible, language=lang,
        ))
    return questions


# ---------------------------------------------------------------------------
# Interview state structure -- the "design interview state structure"
# deliverable. Deliberately minimal: question ID, response capture,
# and follow-up eligibility/bookkeeping ONLY -- no retry/branching
# decision logic. That's a future day's job, once this structure
# exists to build on (the same relationship Day 22 has to Day 29).
# ---------------------------------------------------------------------------

@dataclass
class InterviewQuestionState:
    question_id: str
    category: str
    phase: InterviewPhase
    follow_up_eligible: bool
    response_text: Optional[str] = None
    response_captured: bool = False
    follow_up_asked: bool = False
    follow_up_text: Optional[str] = None
    follow_up_type: Optional[str] = None   # Day 34 addition: which trigger type was used (clarification/deepening/example_based), for state tracking and repetition-prevention

    def capture_response(self, text: str) -> None:
        self.response_text = text
        self.response_captured = True

    def record_follow_up(self, follow_up_text: str, follow_up_type: Optional[str] = None) -> None:
        if not self.follow_up_eligible:
            raise ValueError(f"Question {self.question_id} is not eligible for a follow-up.")
        self.follow_up_asked = True
        self.follow_up_text = follow_up_text
        self.follow_up_type = follow_up_type


@dataclass
class InterviewSession:
    """A minimal, linear container sequencing an interview's questions
    by phase. Advances one question at a time; captures responses.
    Does NOT retry, redirect, or decide follow-ups -- see module
    docstring for why that's correctly out of scope here.
    """
    experience_level: ExperienceLevel
    role_type: RoleType
    questions: List[InterviewQuestionState] = field(default_factory=list)
    _index: int = 0

    @classmethod
    def start(cls, experience_level: ExperienceLevel, role_type: RoleType, lang: str = "en") -> "InterviewSession":
        rendered = generate_hr_interview_questions(experience_level, role_type, lang)
        states = [
            InterviewQuestionState(question_id=q.id, category=q.category, phase=q.phase, follow_up_eligible=q.follow_up_eligible)
            for q in rendered
        ]
        return cls(experience_level=experience_level, role_type=role_type, questions=states)

    @property
    def current_question(self) -> Optional[InterviewQuestionState]:
        if self._index >= len(self.questions):
            return None
        return self.questions[self._index]

    @property
    def current_phase(self) -> Optional[InterviewPhase]:
        q = self.current_question
        return q.phase if q else None

    @property
    def is_complete(self) -> bool:
        return self._index >= len(self.questions)

    def submit_response(self, text: str) -> None:
        q = self.current_question
        if q is None:
            raise ValueError("Interview already complete -- no current question to respond to.")
        q.capture_response(text)
        self._index += 1

    def questions_by_phase(self, phase: InterviewPhase) -> List[InterviewQuestionState]:
        return [q for q in self.questions if q.phase == phase]
