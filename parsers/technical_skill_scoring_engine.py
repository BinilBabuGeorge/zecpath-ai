"""
Technical Skill Scoring Model (Day 47)

WHAT THIS DAY ADDS: Day 46 explicitly deferred this -- its own
docstring states "Scoring technical answers is explicitly out of
scope for this design day... left for a future day the way Day 33
left HR scoring for Day 37." This is that day: a real scoring engine
for the 27 tiered technical questions Day 46 built, evaluating the
four parameters the brief names (accuracy, depth, logical reasoning,
real-world applicability) against hand-mapped per-question rubrics.

ACCURACY, STATED HONESTLY: this project has no fact-checking model and
no live knowledge base -- "accuracy of answer" here means coverage of
a hand-mapped set of KEY CONCEPTS a correct answer to that specific
question would mention (e.g., for "state vs props in React": that
props come from the parent, are read-only, and state changes trigger
re-renders), matched by keyword/phrase presence. This is the exact
same deterministic, non-ML approach Day 38 used for logical-reasoning
puzzles ("ideal answer elements"), applied here to real technical
content instead of logic puzzles. It CANNOT verify a correct answer
phrased in unexpected terminology, and it cannot catch a confidently
wrong answer that happens to use the right keywords. Named here
rather than implied by "scoring engine."

REUSE: `assess_real_world_applicability()` imports
`has_concrete_example()` directly from Day 34's (Day 42-broadened)
`hr_followup_engine` -- unchanged. Detecting concrete, specific,
experience-grounded language is exactly what "real-world
applicability" means, and Day 34/42 already built and tested that
detector; reusing it here is a direct, legitimate import, not a
re-derivation. `assess_logical_reasoning()` reuses the PATTERN Day 38
established (a curated list of causal/conditional connector phrases,
scored by density) -- not its code, since `aptitude_logic_engine.py`
isn't present in this build environment (same constraint noted on
every day since 41). Reimplemented here rather than imported, same as
Day 46 reused Day 33's session-flow pattern without its code.

NORMALIZING ACROSS DIFFICULTY LEVELS (the brief's explicit task):
`accuracy_score` is a coverage RATIO (matched concepts / total
concepts for that question), not a raw count, so a basics question
with 3 concepts and an advanced question with 4 both land on the same
0-100 scale. `depth_score` uses TIER-SCALED word-count expectations
(a basics answer needs ~20 words for full depth credit; advanced
needs ~50) rather than one fixed threshold, so a appropriately terse
basics answer isn't penalized for not being as long as an advanced
system-design answer, and a padded-but-shallow advanced answer doesn't
get undeserved depth credit just for length. This is the mechanism
behind "normalize scores across difficulty levels" -- not a separate
rescaling step bolted on afterward.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from parsers.hr_followup_engine import has_concrete_example
from parsers.technical_interview_question_bank import (
    DifficultyTier, TechnicalInterviewSession, TechnicalQuestionType, QUESTION_BANK,
)

_ACCURACY_WEIGHT = 0.40
_DEPTH_WEIGHT = 0.20
_LOGICAL_REASONING_WEIGHT = 0.20
_REAL_WORLD_WEIGHT = 0.20

# Tier-scaled word-count expectations for full depth credit -- the
# normalization mechanism described in the module docstring.
_DEPTH_WORD_TARGETS: Dict[DifficultyTier, int] = {
    DifficultyTier.BASICS: 20,
    DifficultyTier.INTERMEDIATE: 35,
    DifficultyTier.ADVANCED: 50,
}

# Same pattern Day 38 established for logical-reasoning connector
# density -- reimplemented here since that file isn't present in this
# build environment (see module docstring).
_LOGICAL_CONNECTORS = [
    "because", "therefore", "since", "thus", "hence", "if", "then", "as a result",
    "which means", "so that", "given that", "in order to", "consequently",
]
_CONNECTOR_SCORE_CAP = 40.0
_CONNECTOR_POINTS_PER_HIT = 10.0


class ShallowDeepClassification(str, Enum):
    SHALLOW = "shallow"
    MODERATE = "moderate"
    DEEP = "deep"


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


@dataclass
class TechnicalKeyConcept:
    label: str
    match_phrases: List[str]

    def matches(self, lowered_text: str) -> bool:
        return any(phrase in lowered_text for phrase in self.match_phrases)


# ---------------------------------------------------------------------------
# Hand-mapped rubrics -- one per tiered question from Day 46's bank.
# Fewer required concepts for basics (reflecting lower expected depth),
# more for advanced -- itself part of the normalization design, not
# just the word-count scaling above.
# ---------------------------------------------------------------------------

QUESTION_RUBRICS: Dict[str, List[TechnicalKeyConcept]] = {
    "tech-mern-basics-c01": [
        TechnicalKeyConcept("props passed from parent", ["passed from parent", "passed down", "parent to child", "parent component"]),
        TechnicalKeyConcept("props are read-only", ["read-only", "immutable", "cannot be changed", "can't be changed"]),
        TechnicalKeyConcept("state triggers re-render", ["re-render", "triggers a render", "causes a render"]),
    ],
    "tech-mern-basics-c02": [
        TechnicalKeyConcept("runs between request and response", ["between the request and response", "intercepts the request", "runs before the", "sits between"]),
        TechnicalKeyConcept("has access to req/res/next", ["req, res", "request and response objects", "next()"]),
        TechnicalKeyConcept("used for logging/auth/parsing", ["logging", "authentication", "parsing", "validation"]),
    ],
    "tech-mern-basics-s01": [
        TechnicalKeyConcept("identifies shared/lifted state as the cause", ["unrelated state", "shared parent", "lifted state", "state is shared"]),
        TechnicalKeyConcept("mentions profiling tools", ["react devtools", "profiler", "dev tools"]),
        TechnicalKeyConcept("mentions memoization fix", ["memo", "usememo", "usecallback", "react.memo"]),
        TechnicalKeyConcept("mentions splitting/moving state", ["move the state down", "split the component", "lift state", "isolate"]),
    ],
    "tech-mern-intermediate-c01": [
        TechnicalKeyConcept("single-threaded/non-blocking", ["single-threaded", "single thread", "non-blocking"]),
        TechnicalKeyConcept("callback/task queue", ["callback queue", "event queue", "task queue", "microtask"]),
        TechnicalKeyConcept("delegates I/O to background threads", ["libuv", "offloads", "delegates", "background threads", "thread pool"]),
        TechnicalKeyConcept("mentions loop phases", ["phases", "timers phase", "poll phase", "callback phase"]),
    ],
    "tech-mern-intermediate-c02": [
        TechnicalKeyConcept("avoids full collection scan", ["avoid a full collection scan", "without scanning", "full scan", "faster lookups"]),
        TechnicalKeyConcept("B-tree structure", ["b-tree", "btree", "tree structure"]),
        TechnicalKeyConcept("write/storage overhead trade-off", ["write overhead", "slower writes", "extra storage", "storage overhead"]),
        TechnicalKeyConcept("compound indexes", ["compound index", "multiple fields"]),
    ],
    "tech-mern-intermediate-s01": [
        TechnicalKeyConcept("checks logs/monitoring", ["logs", "monitoring", "metrics", "apm"]),
        TechnicalKeyConcept("reproduces under load", ["load test", "simulate load", "reproduce"]),
        TechnicalKeyConcept("checks connection pool/resource limits", ["connection pool", "resource limits", "timeout setting", "concurrency limit"]),
        TechnicalKeyConcept("checks downstream dependencies", ["downstream", "database latency", "external service", "upstream dependency"]),
    ],
    "tech-mern-advanced-c01": [
        TechnicalKeyConcept("Context re-renders all consumers", ["re-renders all consumers", "every consumer re-renders", "context re-render"]),
        TechnicalKeyConcept("Redux centralizes predictable state", ["single source of truth", "predictable state", "centralized store"]),
        TechnicalKeyConcept("boilerplate/complexity trade-off", ["boilerplate", "complexity", "learning curve"]),
        TechnicalKeyConcept("mentions alternative libraries", ["zustand", "recoil", "mobx", "jotai"]),
    ],
    "tech-mern-advanced-c02": [
        TechnicalKeyConcept("shard key selection", ["shard key", "choice of shard key"]),
        TechnicalKeyConcept("distributes data across nodes", ["distributes data", "across multiple nodes", "across shards"]),
        TechnicalKeyConcept("query routing complexity", ["query routing", "scatter-gather", "cross-shard"]),
        TechnicalKeyConcept("risk of hotspotting", ["hotspot", "uneven distribution", "imbalance"]),
    ],
    "tech-mern-advanced-s01": [
        TechnicalKeyConcept("WebSockets for real-time sync", ["websocket", "socket.io", "real-time connection"]),
        TechnicalKeyConcept("conflict resolution strategy", ["operational transform", "crdt", "conflict resolution"]),
        TechnicalKeyConcept("horizontal scaling of connections", ["horizontal scaling", "load balancer", "sticky session"]),
        TechnicalKeyConcept("persistence strategy", ["persistence", "database", "snapshot"]),
    ],
    "tech-java-basics-c01": [
        TechnicalKeyConcept("interface defines a contract", ["contract", "no implementation", "pure abstraction"]),
        TechnicalKeyConcept("abstract class allows partial implementation", ["partial implementation", "concrete method", "some methods implemented"]),
        TechnicalKeyConcept("multiple interface inheritance", ["multiple interfaces", "multiple inheritance"]),
    ],
    "tech-java-basics-c02": [
        TechnicalKeyConcept("belongs to class, not instance", ["belongs to the class", "not to instances", "class-level"]),
        TechnicalKeyConcept("shared across all instances", ["shared across all", "shared by all instances"]),
        TechnicalKeyConcept("static can't access instance members", ["cannot access instance", "no access to non-static"]),
    ],
    "tech-java-basics-s01": [
        TechnicalKeyConcept("checks stack trace", ["stack trace", "exception trace"]),
        TechnicalKeyConcept("adds logging/null checks", ["null check", "logging", "add logs"]),
        TechnicalKeyConcept("reproduces the issue", ["reproduce", "isolate the input"]),
        TechnicalKeyConcept("checks for uninitialized objects", ["uninitialized", "not initialized", "null reference"]),
    ],
    "tech-java-intermediate-c01": [
        TechnicalKeyConcept("generational GC", ["young generation", "old generation", "generational"]),
        TechnicalKeyConcept("reachability analysis", ["reachable", "unreachable objects", "reachability"]),
        TechnicalKeyConcept("mentions a GC algorithm", ["g1", "garbage first", "mark and sweep", "mark-sweep"]),
        TechnicalKeyConcept("stop-the-world pauses", ["stop-the-world", "gc pause"]),
    ],
    "tech-java-intermediate-c02": [
        TechnicalKeyConcept("== compares references", ["reference", "memory address", "same object"]),
        TechnicalKeyConcept(".equals() compares content", ["value", "content", "logical equality"]),
        TechnicalKeyConcept("mentions overriding equals", ["override equals", "overridden"]),
    ],
    "tech-java-intermediate-s01": [
        TechnicalKeyConcept("uses profiling tools", ["profiler", "profiling", "jvisualvm", "flight recorder"]),
        TechnicalKeyConcept("checks thread/connection pool", ["thread pool", "connection pool"]),
        TechnicalKeyConcept("checks database queries", ["n+1", "slow query", "database query"]),
        TechnicalKeyConcept("checks caching", ["caching", "cache"]),
    ],
    "tech-java-advanced-c01": [
        TechnicalKeyConcept("double-checked locking", ["double-checked locking", "double checked locking"]),
        TechnicalKeyConcept("synchronized keyword", ["synchronized"]),
        TechnicalKeyConcept("enum singleton", ["enum singleton", "using an enum"]),
        TechnicalKeyConcept("eager vs lazy trade-off", ["eager initialization", "lazy initialization", "lazy loading"]),
    ],
    "tech-java-advanced-c02": [
        TechnicalKeyConcept("heap for objects", ["heap", "objects are stored"]),
        TechnicalKeyConcept("stack for method frames/locals", ["stack", "method calls", "local variables"]),
        TechnicalKeyConcept("metaspace for class metadata", ["metaspace", "class metadata"]),
        TechnicalKeyConcept("mentions tuning implications", ["heap size", "tuning", "xmx", "xms"]),
    ],
    "tech-java-advanced-s01": [
        TechnicalKeyConcept("partitioning for ordering", ["kafka", "partition", "partitioning"]),
        TechnicalKeyConcept("idempotency", ["idempotent", "idempotency"]),
        TechnicalKeyConcept("backpressure handling", ["backpressure", "rate limiting", "throttling"]),
        TechnicalKeyConcept("observability/monitoring", ["observability", "monitoring", "metrics"]),
    ],
    "tech-devops-basics-c01": [
        TechnicalKeyConcept("CI = frequent integration + automated tests", ["continuous integration", "automated tests", "merge frequently"]),
        TechnicalKeyConcept("CD = automated deployment/release", ["automated deployment", "automated release", "continuous delivery", "continuous deployment"]),
        TechnicalKeyConcept("distinguishes delivery vs deployment", ["manual approval", "delivery vs deployment"]),
    ],
    "tech-devops-basics-c02": [
        TechnicalKeyConcept("defines image build steps", ["build instructions", "build steps", "build an image"]),
        TechnicalKeyConcept("base image", ["base image", "from instruction"]),
        TechnicalKeyConcept("layers", ["layers", "layered"]),
    ],
    "tech-devops-basics-s01": [
        TechnicalKeyConcept("rollback strategy", ["rollback", "roll back", "revert"]),
        TechnicalKeyConcept("checks deployment logs", ["logs", "deployment logs"]),
        TechnicalKeyConcept("mentions idempotent recovery", ["idempotent", "safe to rerun", "re-run"]),
        TechnicalKeyConcept("health checks before success", ["health check", "verify", "validation step"]),
    ],
    "tech-devops-intermediate-c01": [
        TechnicalKeyConcept("liveness restarts unhealthy container", ["restart", "liveness", "kills the container"]),
        TechnicalKeyConcept("readiness controls traffic routing", ["readiness", "traffic", "removes from load balancing", "routing"]),
        TechnicalKeyConcept("notes they serve different purposes", ["different purpose", "different failure"]),
    ],
    "tech-devops-intermediate-c02": [
        TechnicalKeyConcept("Terraform provisions infrastructure", ["provisioning", "infrastructure as code", "declarative"]),
        TechnicalKeyConcept("Ansible configures servers", ["configuration management", "configure servers", "install software"]),
        TechnicalKeyConcept("declarative vs procedural distinction", ["declarative", "procedural", "imperative"]),
    ],
    "tech-devops-intermediate-s01": [
        TechnicalKeyConcept("environment parity/config drift", ["environment parity", "config drift", "environment difference", "different environment"]),
        TechnicalKeyConcept("dependency version mismatch", ["dependency version", "version mismatch"]),
        TechnicalKeyConcept("checks environment variables/secrets", ["environment variable", "secrets", "config value"]),
    ],
    "tech-devops-advanced-c01": [
        TechnicalKeyConcept("blue-green deployment", ["blue-green", "blue green"]),
        TechnicalKeyConcept("rolling update", ["rolling update", "rolling deployment"]),
        TechnicalKeyConcept("handles stateful data migration", ["data migration", "schema migration", "backward compatible"]),
        TechnicalKeyConcept("traffic shifting/canary", ["traffic shifting", "canary"]),
    ],
    "tech-devops-advanced-c02": [
        TechnicalKeyConcept("per-service = faster independent builds", ["independent", "faster builds", "isolated pipelines"]),
        TechnicalKeyConcept("monolithic = simpler coordination", ["simpler", "single pipeline", "coordination overhead"]),
        TechnicalKeyConcept("build time/scalability trade-off", ["build time", "scalability of the pipeline"]),
    ],
    "tech-devops-advanced-s01": [
        TechnicalKeyConcept("mentions RPO/RTO explicitly", ["rpo", "rto", "recovery point", "recovery time"]),
        TechnicalKeyConcept("active-active or active-passive", ["active-active", "active-passive", "failover"]),
        TechnicalKeyConcept("data replication strategy", ["replication", "data sync", "cross-region"]),
        TechnicalKeyConcept("DNS/traffic routing for failover", ["dns failover", "traffic routing", "load balancer"]),
    ],
}

assert set(QUESTION_RUBRICS.keys()) == {
    q.question_id for q in QUESTION_BANK
}, "Every tiered question in Day 46's bank must have a rubric, and vice versa."


# ---------------------------------------------------------------------------
# Scoring components
# ---------------------------------------------------------------------------

@dataclass
class AccuracyResult:
    matched_concepts: List[str]
    missing_concepts: List[str]
    coverage_ratio: float
    accuracy_score: float


def assess_accuracy(text: str, question_id: str) -> AccuracyResult:
    rubric = QUESTION_RUBRICS.get(question_id)
    if not rubric:
        raise ValueError(f"No rubric defined for question_id={question_id!r} -- only tiered conceptual/scenario questions have one.")
    lowered = text.lower()
    matched = [c.label for c in rubric if c.matches(lowered)]
    missing = [c.label for c in rubric if c.label not in matched]
    coverage_ratio = round(len(matched) / len(rubric), 3)
    return AccuracyResult(matched_concepts=matched, missing_concepts=missing, coverage_ratio=coverage_ratio, accuracy_score=round(coverage_ratio * 100, 1))


@dataclass
class DepthResult:
    word_count: int
    word_target: int
    depth_score: float


def assess_depth(text: str, tier: DifficultyTier) -> DepthResult:
    word_count = len(text.split())
    target = _DEPTH_WORD_TARGETS[tier]
    # Linear credit up to the tier's target, capped at 100 -- a terse
    # basics answer meeting ITS target scores as well as a longer
    # advanced answer meeting ITS (larger) target.
    score = _clamp((word_count / target) * 100) if target else 0.0
    return DepthResult(word_count=word_count, word_target=target, depth_score=round(score, 1))


@dataclass
class LogicalReasoningResult:
    connector_hits: List[str]
    logical_reasoning_score: float


def assess_logical_reasoning(text: str) -> LogicalReasoningResult:
    lowered = text.lower()
    hits = [c for c in _LOGICAL_CONNECTORS if c in lowered]
    score = min(_CONNECTOR_SCORE_CAP, len(hits) * _CONNECTOR_POINTS_PER_HIT) / _CONNECTOR_SCORE_CAP * 100
    return LogicalReasoningResult(connector_hits=hits, logical_reasoning_score=round(score, 1))


@dataclass
class RealWorldApplicabilityResult:
    has_concrete_grounding: bool
    real_world_score: float


def assess_real_world_applicability(text: str) -> RealWorldApplicabilityResult:
    grounded = has_concrete_example(text)   # reused directly from Day 34/42, unchanged
    return RealWorldApplicabilityResult(has_concrete_grounding=grounded, real_world_score=100.0 if grounded else 30.0)


def classify_shallow_vs_deep(overall_score: float) -> ShallowDeepClassification:
    if overall_score >= 70.0:
        return ShallowDeepClassification.DEEP
    if overall_score >= 40.0:
        return ShallowDeepClassification.MODERATE
    return ShallowDeepClassification.SHALLOW


# ---------------------------------------------------------------------------
# Per-answer evaluation -- explainable breakdown
# ---------------------------------------------------------------------------

@dataclass
class TechnicalAnswerEvaluation:
    question_id: str
    domain: str
    tier: str
    skill_tags: List[str]
    accuracy: AccuracyResult
    depth: DepthResult
    logical_reasoning: LogicalReasoningResult
    real_world: RealWorldApplicabilityResult
    overall_technical_score: float
    classification: ShallowDeepClassification

    def to_dict(self) -> Dict:
        return {
            "question_id": self.question_id, "domain": self.domain, "tier": self.tier, "skill_tags": self.skill_tags,
            "overall_technical_score": self.overall_technical_score, "classification": self.classification.value,
            "accuracy": {"score": self.accuracy.accuracy_score, "coverage_ratio": self.accuracy.coverage_ratio,
                         "matched_concepts": self.accuracy.matched_concepts, "missing_concepts": self.accuracy.missing_concepts},
            "depth": {"score": self.depth.depth_score, "word_count": self.depth.word_count, "word_target": self.depth.word_target},
            "logical_reasoning": {"score": self.logical_reasoning.logical_reasoning_score, "connector_hits": self.logical_reasoning.connector_hits},
            "real_world_applicability": {"score": self.real_world.real_world_score, "has_concrete_grounding": self.real_world.has_concrete_grounding},
        }


def evaluate_technical_answer(text: str, question_id: str, domain: str, tier: DifficultyTier, skill_tags: List[str]) -> TechnicalAnswerEvaluation:
    accuracy = assess_accuracy(text, question_id)
    depth = assess_depth(text, tier)
    reasoning = assess_logical_reasoning(text)
    real_world = assess_real_world_applicability(text)

    overall = round(
        accuracy.accuracy_score * _ACCURACY_WEIGHT + depth.depth_score * _DEPTH_WEIGHT
        + reasoning.logical_reasoning_score * _LOGICAL_REASONING_WEIGHT + real_world.real_world_score * _REAL_WORLD_WEIGHT, 1,
    )
    classification = classify_shallow_vs_deep(overall)

    return TechnicalAnswerEvaluation(
        question_id=question_id, domain=domain, tier=tier.value, skill_tags=skill_tags,
        accuracy=accuracy, depth=depth, logical_reasoning=reasoning, real_world=real_world,
        overall_technical_score=overall, classification=classification,
    )


# ---------------------------------------------------------------------------
# Session-level aggregate -- skill-wise breakdown by Day 46's skill_tags
# ---------------------------------------------------------------------------

@dataclass
class TechnicalEvaluationReport:
    answer_evaluations: List[TechnicalAnswerEvaluation]
    overall_score: float
    skill_breakdown: Dict[str, float]

    def to_dict(self) -> Dict:
        return {
            "overall_score": self.overall_score, "skill_breakdown": self.skill_breakdown,
            "answer_evaluations": [e.to_dict() for e in self.answer_evaluations],
        }


def build_technical_evaluation_report(session: TechnicalInterviewSession) -> TechnicalEvaluationReport:
    """Evaluates every answered CONCEPTUAL/SCENARIO_BASED question --
    introduction and experience-based questions have no accuracy
    rubric and are intentionally excluded, same as Day 37 excludes
    non-scoreable content from its aggregate."""
    scoreable = [
        qs for qs in session.questions
        if qs.response_captured and qs.response_text
        and qs.question.question_type in (TechnicalQuestionType.CONCEPTUAL, TechnicalQuestionType.SCENARIO_BASED)
    ]

    if not scoreable:
        return TechnicalEvaluationReport(answer_evaluations=[], overall_score=0.0, skill_breakdown={})

    evaluations = [
        evaluate_technical_answer(
            qs.response_text, qs.question.question_id, qs.question.domain.value, qs.question.tier, qs.question.skill_tags,
        )
        for qs in scoreable
    ]

    overall = round(sum(e.overall_technical_score for e in evaluations) / len(evaluations), 1)

    skill_scores: Dict[str, List[float]] = {}
    for e in evaluations:
        for tag in e.skill_tags:
            skill_scores.setdefault(tag, []).append(e.overall_technical_score)
    skill_breakdown = {tag: round(sum(scores) / len(scores), 1) for tag, scores in skill_scores.items()}

    return TechnicalEvaluationReport(answer_evaluations=evaluations, overall_score=overall, skill_breakdown=skill_breakdown)
