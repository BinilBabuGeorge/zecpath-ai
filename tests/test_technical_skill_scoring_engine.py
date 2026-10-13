from parsers.technical_skill_scoring_engine import (
    QUESTION_RUBRICS, assess_accuracy, assess_depth, assess_logical_reasoning,
    assess_real_world_applicability, classify_shallow_vs_deep, evaluate_technical_answer,
    build_technical_evaluation_report, ShallowDeepClassification,
)
from parsers.technical_interview_question_bank import (
    QUESTION_BANK, TechnicalDomain, DifficultyTier, TechnicalInterviewSession,
)
from parsers.hr_followup_engine import has_concrete_example


# ---------------------------------------------------------------------------
# Rubric coverage -- every tiered question has one, and vice versa
# ---------------------------------------------------------------------------

def test_every_tiered_question_has_a_rubric():
    tiered_ids = {q.question_id for q in QUESTION_BANK}
    assert set(QUESTION_RUBRICS.keys()) == tiered_ids


def test_every_rubric_has_at_least_three_concepts():
    for qid, concepts in QUESTION_RUBRICS.items():
        assert len(concepts) >= 3, f"{qid} has only {len(concepts)} concepts"


# ---------------------------------------------------------------------------
# Accuracy -- coverage ratio, not raw count (normalization mechanism)
# ---------------------------------------------------------------------------

def test_accuracy_full_coverage_scores_100():
    text = "Props are passed from parent to child components and are read-only. State changes trigger a re-render."
    result = assess_accuracy(text, "tech-mern-basics-c01")
    assert result.accuracy_score == 100.0
    assert result.coverage_ratio == 1.0


def test_accuracy_zero_coverage_scores_0():
    result = assess_accuracy("I'm not entirely sure how that works.", "tech-mern-basics-c01")
    assert result.accuracy_score == 0.0
    assert result.missing_concepts


def test_accuracy_raises_for_unknown_question_id():
    raised = False
    try:
        assess_accuracy("some text", "not-a-real-question-id")
    except ValueError:
        raised = True
    assert raised


# ---------------------------------------------------------------------------
# Depth -- tier-scaled word-count expectations (normalization mechanism)
# ---------------------------------------------------------------------------

def test_depth_score_scales_by_tier():
    text = " ".join(["word"] * 25)   # 25 words
    basics_depth = assess_depth(text, DifficultyTier.BASICS)        # target 20 -> full credit
    advanced_depth = assess_depth(text, DifficultyTier.ADVANCED)    # target 50 -> partial credit
    assert basics_depth.depth_score == 100.0
    assert advanced_depth.depth_score < 100.0


def test_depth_score_capped_at_100():
    text = " ".join(["word"] * 200)
    result = assess_depth(text, DifficultyTier.BASICS)
    assert result.depth_score == 100.0


# ---------------------------------------------------------------------------
# Logical reasoning -- connector density
# ---------------------------------------------------------------------------

def test_logical_reasoning_rewards_connector_usage():
    with_connectors = "This happens because of X, therefore Y occurs, which means Z follows."
    without_connectors = "This happens. Y occurs. Z follows."
    with_score = assess_logical_reasoning(with_connectors).logical_reasoning_score
    without_score = assess_logical_reasoning(without_connectors).logical_reasoning_score
    assert with_score > without_score


def test_logical_reasoning_score_capped_at_100():
    text = "because therefore since thus hence if then as a result which means so that given that"
    result = assess_logical_reasoning(text)
    assert result.logical_reasoning_score <= 100.0


# ---------------------------------------------------------------------------
# Real-world applicability -- reused from Day 34/42, and the bug this
# day's own balance check found and fixed in that reused function
# ---------------------------------------------------------------------------

def test_real_world_applicability_rewards_concrete_grounding():
    grounded = "For example, in a project I built, I had a search component re-rendering unnecessarily."
    result = assess_real_world_applicability(grounded)
    assert result.has_concrete_grounding is True
    assert result.real_world_score == 100.0


def test_real_world_applicability_low_for_pure_textbook_answer():
    textbook = "Props are immutable data passed to a component."
    result = assess_real_world_applicability(textbook)
    assert result.has_concrete_grounding is False
    assert result.real_world_score == 30.0


def test_discovered_false_positive_fixed_when_it_and_then_it():
    # Found via this day's own balance check: "when it changes" and
    # "then it fails" are extremely common in technical explanations
    # and were false-matching has_concrete_example()'s "when i"/"then i"
    # substring markers before the Day 47 word-boundary fix.
    assert has_concrete_example("State changes when it updates.") is False
    assert has_concrete_example("The function returns null, then it fails downstream.") is False
    # True positives for the same markers must still work.
    assert has_concrete_example("When I debugged this, I found the root cause.") is True
    assert has_concrete_example("I checked the logs, then I realized the real issue.") is True


# ---------------------------------------------------------------------------
# Shallow vs deep classification
# ---------------------------------------------------------------------------

def test_classification_bands():
    assert classify_shallow_vs_deep(85.0) == ShallowDeepClassification.DEEP
    assert classify_shallow_vs_deep(55.0) == ShallowDeepClassification.MODERATE
    assert classify_shallow_vs_deep(20.0) == ShallowDeepClassification.SHALLOW


# ---------------------------------------------------------------------------
# Full per-answer evaluation
# ---------------------------------------------------------------------------

def test_strong_answer_scores_higher_than_weak_answer():
    strong = "Props are passed from parent to child and are read-only. State is managed internally, and because it changes, the component re-renders."
    weak = "Props and state are kind of similar things."
    strong_eval = evaluate_technical_answer(strong, "tech-mern-basics-c01", "mern", DifficultyTier.BASICS, ["react"])
    weak_eval = evaluate_technical_answer(weak, "tech-mern-basics-c01", "mern", DifficultyTier.BASICS, ["react"])
    assert strong_eval.overall_technical_score > weak_eval.overall_technical_score


def test_evaluation_score_bounded_0_to_100():
    result = evaluate_technical_answer("some answer text here", "tech-java-advanced-c01", "java", DifficultyTier.ADVANCED, ["java"])
    assert 0.0 <= result.overall_technical_score <= 100.0


# ---------------------------------------------------------------------------
# Session-level aggregate -- skill-wise breakdown
# ---------------------------------------------------------------------------

def test_build_report_empty_session_has_zero_score():
    session = TechnicalInterviewSession.start(TechnicalDomain.MERN, 1)
    report = build_technical_evaluation_report(session)
    assert report.overall_score == 0.0
    assert report.answer_evaluations == []


def test_build_report_excludes_intro_and_experience_based():
    session = TechnicalInterviewSession.start(TechnicalDomain.JAVA, 4)
    for _ in range(len(session.questions)):
        session.submit_response("because therefore this is a reasonably detailed technical answer with some explanation.")
    report = build_technical_evaluation_report(session)
    # 5 total questions (intro + experience + 2 conceptual + 1 scenario) -> only 3 scoreable.
    assert len(report.answer_evaluations) == 3


def test_build_report_produces_skill_breakdown():
    session = TechnicalInterviewSession.start(TechnicalDomain.DEVOPS, 7)
    for _ in range(len(session.questions)):
        session.submit_response("because therefore this answer discusses rollback and monitoring in reasonable detail.")
    report = build_technical_evaluation_report(session)
    assert report.skill_breakdown
    assert all(0.0 <= v <= 100.0 for v in report.skill_breakdown.values())
