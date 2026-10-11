"""
Technical Interview System Design (Day 46)

WHAT THIS DAY IS: the foundation for a FOURTH distinct phase of this
project -- technical interviews -- alongside screening (Days 22-32),
HR behavioral interviews (Days 33-45), and aptitude (Day 38). Where
HR asks how a candidate communicates and aptitude asks how they
reason abstractly, this phase asks whether they actually know the
technology they claim to, at a depth appropriate to their stated
experience. Same design-day discipline as Days 33 and 38: a real,
hand-written question bank and a real, tested session state machine,
not a diagram with no code behind it.

A NEW, FINER-GRAINED EXPERIENCE TAXONOMY, STATED HONESTLY: Day 33's
`ExperienceLevel` is a binary (FRESHER / EXPERIENCED). This day's
brief asks for three explicit experience bands (0-2 / 3-5 / 5+ years)
mapped to three difficulty tiers -- a genuinely different, finer-
grained axis, not a relabeling of Day 33's. This is the THIRD
experience/role-like taxonomy in this project now (alongside Day 13's
ATS role categories and Day 33's HR experience levels), each built for
a different question that needed answering at the time. No attempt is
made here to unify them -- same reasoning Day 41 gave for leaving its
two role taxonomies separate: forcing one onto a question it wasn't
built for creates worse answers than keeping purpose-built ones apart.

SCOPE OF THE QUESTION BANK: three domains (MERN, Java, DevOps) chosen
directly from the brief's own examples -- not an attempt at exhaustive
technology coverage. Each domain has 2 conceptual questions and 1
scenario-based problem per difficulty tier (18 conceptual + 9 scenario
= 27 tiered questions), plus one domain-specific experience-based
template and one shared introduction question. Extending to more
domains means adding entries to `QUESTION_BANK` in the same shape --
the session/difficulty logic doesn't change.

NO AUTOMATED ANSWER EVALUATION HERE, STATED HONESTLY: this day builds
the question bank, the difficulty logic, and the session flow -- it
does NOT build a technical-answer scoring engine (that would require
assessing factual/technical correctness, not just presence of
keywords, structure, or sentiment the way the HR-track engines do).
Scoring technical answers is explicitly out of scope for this design
day, left for a future day the way Day 33 left HR scoring for Day 37.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class TechnicalDomain(str, Enum):
    MERN = "mern"
    JAVA = "java"
    DEVOPS = "devops"


class DifficultyTier(str, Enum):
    BASICS = "basics"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class TechnicalInterviewPhase(str, Enum):
    INTRODUCTION = "introduction"
    EXPERIENCE_BASED = "experience_based"
    CONCEPTUAL = "conceptual"
    SCENARIO_BASED = "scenario_based"


class TechnicalQuestionType(str, Enum):
    INTRODUCTION = "introduction"
    EXPERIENCE_BASED = "experience_based"
    CONCEPTUAL = "conceptual"
    SCENARIO_BASED = "scenario_based"


def experience_years_to_tier(years: float) -> DifficultyTier:
    """0-2 -> basics, 3-5 -> intermediate, 5+ -> advanced, exactly as
    the brief specifies. Non-integer years (e.g. 2.5) are handled by
    the natural <= boundary rule rather than requiring the caller to
    round first."""
    if years < 0:
        raise ValueError(f"years of experience cannot be negative, got {years}")
    if years <= 2:
        return DifficultyTier.BASICS
    if years <= 5:
        return DifficultyTier.INTERMEDIATE
    return DifficultyTier.ADVANCED


@dataclass
class TechnicalQuestion:
    question_id: str
    domain: Optional[TechnicalDomain]   # None for the shared introduction question
    tier: Optional[DifficultyTier]      # None for introduction/experience-based (not difficulty-tiered)
    question_type: TechnicalQuestionType
    prompt_text: str
    skill_tags: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Introduction -- one shared question, not domain- or tier-specific
# ---------------------------------------------------------------------------

_INTRODUCTION_QUESTION = TechnicalQuestion(
    question_id="tech-intro-01", domain=None, tier=None, question_type=TechnicalQuestionType.INTRODUCTION,
    prompt_text="Tell me about your technical background and what you've been working on recently.",
)

# ---------------------------------------------------------------------------
# Experience-based -- one domain-specific template, not tier-specific
# (asking about THEIR actual history isn't a difficulty level)
# ---------------------------------------------------------------------------

_EXPERIENCE_BASED_QUESTIONS: Dict[TechnicalDomain, TechnicalQuestion] = {
    TechnicalDomain.MERN: TechnicalQuestion(
        question_id="tech-exp-mern-01", domain=TechnicalDomain.MERN, tier=None, question_type=TechnicalQuestionType.EXPERIENCE_BASED,
        prompt_text="Walk me through a MERN project you built end-to-end -- what was your role, and what technical decisions did you make?",
        skill_tags=["mongodb", "express", "react", "node"],
    ),
    TechnicalDomain.JAVA: TechnicalQuestion(
        question_id="tech-exp-java-01", domain=TechnicalDomain.JAVA, tier=None, question_type=TechnicalQuestionType.EXPERIENCE_BASED,
        prompt_text="Walk me through a Java project or service you've owned -- what was your role, and what technical decisions did you make?",
        skill_tags=["java", "jvm"],
    ),
    TechnicalDomain.DEVOPS: TechnicalQuestion(
        question_id="tech-exp-devops-01", domain=TechnicalDomain.DEVOPS, tier=None, question_type=TechnicalQuestionType.EXPERIENCE_BASED,
        prompt_text="Walk me through a deployment or infrastructure system you've owned -- what was your role, and what technical decisions did you make?",
        skill_tags=["ci_cd", "infrastructure"],
    ),
}

# ---------------------------------------------------------------------------
# Conceptual + scenario-based questions, hand-written per domain per tier
# ---------------------------------------------------------------------------

QUESTION_BANK: List[TechnicalQuestion] = [
    # --- MERN ---
    TechnicalQuestion("tech-mern-basics-c01", TechnicalDomain.MERN, DifficultyTier.BASICS, TechnicalQuestionType.CONCEPTUAL,
        "What is the difference between state and props in React?", ["react"]),
    TechnicalQuestion("tech-mern-basics-c02", TechnicalDomain.MERN, DifficultyTier.BASICS, TechnicalQuestionType.CONCEPTUAL,
        "What is middleware in Express, and why is it used?", ["express"]),
    TechnicalQuestion("tech-mern-basics-s01", TechnicalDomain.MERN, DifficultyTier.BASICS, TechnicalQuestionType.SCENARIO_BASED,
        "A user reports that a list of items re-renders every time they type in an unrelated search box. How would you investigate and fix this in a React app?", ["react", "performance"]),
    TechnicalQuestion("tech-mern-intermediate-c01", TechnicalDomain.MERN, DifficultyTier.INTERMEDIATE, TechnicalQuestionType.CONCEPTUAL,
        "Explain how the Node.js event loop handles asynchronous operations.", ["node"]),
    TechnicalQuestion("tech-mern-intermediate-c02", TechnicalDomain.MERN, DifficultyTier.INTERMEDIATE, TechnicalQuestionType.CONCEPTUAL,
        "What are MongoDB indexes, and how do they affect query performance?", ["mongodb"]),
    TechnicalQuestion("tech-mern-intermediate-s01", TechnicalDomain.MERN, DifficultyTier.INTERMEDIATE, TechnicalQuestionType.SCENARIO_BASED,
        "Your Express API is returning intermittent 504 timeouts under load, but works fine locally. How would you diagnose this in production?", ["express", "debugging"]),
    TechnicalQuestion("tech-mern-advanced-c01", TechnicalDomain.MERN, DifficultyTier.ADVANCED, TechnicalQuestionType.CONCEPTUAL,
        "How would you design state management for a large React application with deeply nested components, and what trade-offs would you weigh between Context, Redux, and other options?", ["react", "architecture"]),
    TechnicalQuestion("tech-mern-advanced-c02", TechnicalDomain.MERN, DifficultyTier.ADVANCED, TechnicalQuestionType.CONCEPTUAL,
        "How does MongoDB handle horizontal scaling, and what are the trade-offs of sharding a collection?", ["mongodb", "scaling"]),
    TechnicalQuestion("tech-mern-advanced-s01", TechnicalDomain.MERN, DifficultyTier.ADVANCED, TechnicalQuestionType.SCENARIO_BASED,
        "You're asked to design a MERN-based system supporting real-time collaborative editing for thousands of concurrent users. Walk me through your high-level architecture.", ["react", "node", "architecture"]),

    # --- Java ---
    TechnicalQuestion("tech-java-basics-c01", TechnicalDomain.JAVA, DifficultyTier.BASICS, TechnicalQuestionType.CONCEPTUAL,
        "What is the difference between an interface and an abstract class in Java?", ["java"]),
    TechnicalQuestion("tech-java-basics-c02", TechnicalDomain.JAVA, DifficultyTier.BASICS, TechnicalQuestionType.CONCEPTUAL,
        "What is the purpose of the 'static' keyword in Java?", ["java"]),
    TechnicalQuestion("tech-java-basics-s01", TechnicalDomain.JAVA, DifficultyTier.BASICS, TechnicalQuestionType.SCENARIO_BASED,
        "You have a NullPointerException occurring intermittently in production. How would you approach debugging it?", ["java", "debugging"]),
    TechnicalQuestion("tech-java-intermediate-c01", TechnicalDomain.JAVA, DifficultyTier.INTERMEDIATE, TechnicalQuestionType.CONCEPTUAL,
        "Explain how Java's garbage collector decides when to reclaim memory.", ["jvm"]),
    TechnicalQuestion("tech-java-intermediate-c02", TechnicalDomain.JAVA, DifficultyTier.INTERMEDIATE, TechnicalQuestionType.CONCEPTUAL,
        "What's the difference between '==' and '.equals()' when comparing objects in Java?", ["java"]),
    TechnicalQuestion("tech-java-intermediate-s01", TechnicalDomain.JAVA, DifficultyTier.INTERMEDIATE, TechnicalQuestionType.SCENARIO_BASED,
        "Your Spring Boot service is experiencing slow response times under moderate load. How would you profile and address this?", ["java", "spring", "performance"]),
    TechnicalQuestion("tech-java-advanced-c01", TechnicalDomain.JAVA, DifficultyTier.ADVANCED, TechnicalQuestionType.CONCEPTUAL,
        "How would you design a thread-safe singleton in Java, and what are the trade-offs of different approaches?", ["java", "concurrency"]),
    TechnicalQuestion("tech-java-advanced-c02", TechnicalDomain.JAVA, DifficultyTier.ADVANCED, TechnicalQuestionType.CONCEPTUAL,
        "How does the JVM's memory model (heap, stack, metaspace) affect how you'd tune a high-throughput service?", ["jvm", "performance"]),
    TechnicalQuestion("tech-java-advanced-s01", TechnicalDomain.JAVA, DifficultyTier.ADVANCED, TechnicalQuestionType.SCENARIO_BASED,
        "You're designing a Java-based microservice that must process millions of events per day with strict ordering guarantees. Walk me through your architecture.", ["java", "architecture"]),

    # --- DevOps ---
    TechnicalQuestion("tech-devops-basics-c01", TechnicalDomain.DEVOPS, DifficultyTier.BASICS, TechnicalQuestionType.CONCEPTUAL,
        "What is the difference between continuous integration and continuous deployment?", ["ci_cd"]),
    TechnicalQuestion("tech-devops-basics-c02", TechnicalDomain.DEVOPS, DifficultyTier.BASICS, TechnicalQuestionType.CONCEPTUAL,
        "What is the purpose of a Dockerfile, and what does it define?", ["docker"]),
    TechnicalQuestion("tech-devops-basics-s01", TechnicalDomain.DEVOPS, DifficultyTier.BASICS, TechnicalQuestionType.SCENARIO_BASED,
        "A deployment failed partway through and left the environment in an inconsistent state. How would you handle recovering it?", ["ci_cd", "incident_response"]),
    TechnicalQuestion("tech-devops-intermediate-c01", TechnicalDomain.DEVOPS, DifficultyTier.INTERMEDIATE, TechnicalQuestionType.CONCEPTUAL,
        "How do Kubernetes liveness and readiness probes differ, and why do both matter?", ["kubernetes"]),
    TechnicalQuestion("tech-devops-intermediate-c02", TechnicalDomain.DEVOPS, DifficultyTier.INTERMEDIATE, TechnicalQuestionType.CONCEPTUAL,
        "What's the difference between infrastructure-as-code tools like Terraform and configuration-management tools like Ansible?", ["infrastructure"]),
    TechnicalQuestion("tech-devops-intermediate-s01", TechnicalDomain.DEVOPS, DifficultyTier.INTERMEDIATE, TechnicalQuestionType.SCENARIO_BASED,
        "Your CI pipeline passes but the same build behaves differently in production. How would you investigate the discrepancy?", ["ci_cd", "debugging"]),
    TechnicalQuestion("tech-devops-advanced-c01", TechnicalDomain.DEVOPS, DifficultyTier.ADVANCED, TechnicalQuestionType.CONCEPTUAL,
        "How would you design a zero-downtime deployment strategy for a stateful service?", ["infrastructure", "architecture"]),
    TechnicalQuestion("tech-devops-advanced-c02", TechnicalDomain.DEVOPS, DifficultyTier.ADVANCED, TechnicalQuestionType.CONCEPTUAL,
        "What trade-offs would you weigh when choosing between a monolithic CI pipeline and per-service pipelines in a microservices architecture?", ["ci_cd", "architecture"]),
    TechnicalQuestion("tech-devops-advanced-s01", TechnicalDomain.DEVOPS, DifficultyTier.ADVANCED, TechnicalQuestionType.SCENARIO_BASED,
        "You need to design a multi-region, highly available infrastructure for a service with strict RPO/RTO requirements. Walk me through your approach.", ["infrastructure", "architecture"]),
]


def get_tiered_questions(domain: TechnicalDomain, tier: DifficultyTier) -> List[TechnicalQuestion]:
    """All conceptual + scenario questions for one domain/tier combination."""
    return [q for q in QUESTION_BANK if q.domain == domain and q.tier == tier]


# ---------------------------------------------------------------------------
# Interview flow states and transitions
# ---------------------------------------------------------------------------
#
#   INTRODUCTION -> EXPERIENCE_BASED -> CONCEPTUAL (x2) -> SCENARIO_BASED -> complete
#
# Strictly linear and forward-only, same shape as Day 33's and Day 38's
# sessions -- no branching, no re-entry into an earlier phase. The
# question SET for CONCEPTUAL/SCENARIO_BASED is chosen once, at
# session start, from the domain+tier derived from years_of_experience;
# it does not adapt mid-session the way Day 34's HR follow-up logic
# does -- that is a deliberately different, simpler kind of flow,
# matching this day's own "design the structure" scope rather than
# "design adaptive probing" (which HR's Day 34 already covers for its
# own track).

_PHASE_ORDER = [
    TechnicalInterviewPhase.INTRODUCTION,
    TechnicalInterviewPhase.EXPERIENCE_BASED,
    TechnicalInterviewPhase.CONCEPTUAL,
    TechnicalInterviewPhase.SCENARIO_BASED,
]


@dataclass
class TechnicalQuestionState:
    question: TechnicalQuestion
    phase: TechnicalInterviewPhase
    response_text: Optional[str] = None
    response_captured: bool = False

    def capture_response(self, text: str) -> None:
        self.response_text = text
        self.response_captured = True


@dataclass
class TechnicalInterviewSession:
    domain: TechnicalDomain
    years_of_experience: float
    tier: DifficultyTier
    questions: List[TechnicalQuestionState]
    current_index: int = 0

    @classmethod
    def start(cls, domain: TechnicalDomain, years_of_experience: float) -> "TechnicalInterviewSession":
        tier = experience_years_to_tier(years_of_experience)
        tiered = get_tiered_questions(domain, tier)
        conceptual = [q for q in tiered if q.question_type == TechnicalQuestionType.CONCEPTUAL]
        scenario = [q for q in tiered if q.question_type == TechnicalQuestionType.SCENARIO_BASED]

        sequence: List[TechnicalQuestionState] = [
            TechnicalQuestionState(_INTRODUCTION_QUESTION, TechnicalInterviewPhase.INTRODUCTION),
            TechnicalQuestionState(_EXPERIENCE_BASED_QUESTIONS[domain], TechnicalInterviewPhase.EXPERIENCE_BASED),
        ]
        sequence += [TechnicalQuestionState(q, TechnicalInterviewPhase.CONCEPTUAL) for q in conceptual]
        sequence += [TechnicalQuestionState(q, TechnicalInterviewPhase.SCENARIO_BASED) for q in scenario]

        return cls(domain=domain, years_of_experience=years_of_experience, tier=tier, questions=sequence)

    @property
    def current_question(self) -> Optional[TechnicalQuestionState]:
        if self.current_index >= len(self.questions):
            return None
        return self.questions[self.current_index]

    @property
    def current_phase(self) -> Optional[TechnicalInterviewPhase]:
        q = self.current_question
        return q.phase if q else None

    @property
    def is_complete(self) -> bool:
        return self.current_index >= len(self.questions)

    def submit_response(self, text: str) -> None:
        q = self.current_question
        if q is None:
            raise ValueError("Technical interview session already complete -- no current question.")
        q.capture_response(text)
        self.current_index += 1

    def phase_sequence_followed(self) -> List[TechnicalInterviewPhase]:
        """The distinct phases encountered in order so far -- used to
        verify the flow stayed forward-only and matched _PHASE_ORDER."""
        seen: List[TechnicalInterviewPhase] = []
        for q in self.questions[: self.current_index]:
            if not seen or seen[-1] != q.phase:
                seen.append(q.phase)
        return seen
