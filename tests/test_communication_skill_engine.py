from parsers.hr_interview_question_bank import (
    InterviewQuestionState, InterviewPhase, InterviewSession, ExperienceLevel, RoleType,
)
from parsers.communication_skill_engine import (
    assess_fluency, assess_grammar, assess_vocabulary, assess_clarity, assess_structure,
    evaluate_answer_communication, build_interview_communication_profile,
)


def _question(qid="q1", category="career_journey"):
    return InterviewQuestionState(question_id=qid, category=category, phase=InterviewPhase.CORE_HR, follow_up_eligible=True)


# ---------------------------------------------------------------------------
# Fluency
# ---------------------------------------------------------------------------

def test_fluency_penalizes_run_on_sentence():
    # Punctuated into multiple sentences so boundary confidence stays "normal" --
    # the run-on penalty only applies once segmentation is trustworthy (see module docstring).
    run_on = "I started the day. " + "I went to work and then did the task and then met the client and then reported back and then left " * 3 + ". I went home."
    normal = "I went to work. I finished the task. Then I met the client."
    assert assess_fluency(run_on).fluency_score < assess_fluency(normal).fluency_score
    assert assess_fluency(run_on).sentence_boundary_confidence == "normal"


def test_fluency_rewards_continuity_connectors():
    with_connectors = "I started the project. Because the deadline was tight, I prioritized the core feature. As a result, we shipped on time."
    without_connectors = "I started the project. The deadline was tight. We shipped on time."
    assert assess_fluency(with_connectors).fluency_score >= assess_fluency(without_connectors).fluency_score


def test_fluency_flags_low_boundary_confidence_on_unpunctuated_long_text():
    unpunctuated = "so i joined the company and worked on the backend and then moved to the frontend team and later led a small project " * 3
    result = assess_fluency(unpunctuated)
    assert result.sentence_boundary_confidence == "low"


# ---------------------------------------------------------------------------
# Grammar
# ---------------------------------------------------------------------------

def test_grammar_flags_known_error_pattern():
    result = assess_grammar("He don't like the current process much.")
    assert "he don't" in result.errors_found
    assert result.grammar_score < 100.0


def test_grammar_flags_repeated_word():
    result = assess_grammar("I think think this is the right approach.")
    assert result.repeated_word_pairs
    assert result.grammar_score < 100.0


def test_grammar_clean_sentence_scores_full():
    result = assess_grammar("I led the migration project and delivered it two weeks early.")
    assert result.grammar_score == 100.0


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

def test_vocabulary_higher_for_varied_words():
    varied = "I architected a resilient distributed pipeline that reconciled inconsistent upstream telemetry."
    repetitive = "I did the work and I did the work and I did the work and I did the work."
    assert assess_vocabulary(varied).vocabulary_score > assess_vocabulary(repetitive).vocabulary_score


def test_vocabulary_empty_text_scores_zero():
    result = assess_vocabulary("")
    assert result.total_words == 0
    assert result.vocabulary_score == 0.0


# ---------------------------------------------------------------------------
# Clarity -- reuses Day 34's concreteness/hedge detectors
# ---------------------------------------------------------------------------

def test_clarity_rewards_concrete_example():
    text = "For example, in my last role I redesigned the onboarding flow, which cut signup time in half."
    result = assess_clarity(text)
    assert result.has_concrete_grounding is True
    assert result.clarity_score > 60.0


def test_clarity_penalizes_vague_answer():
    result = assess_clarity("Honestly, nothing comes to mind right now.")
    assert result.is_vague is True
    assert result.clarity_score < 60.0


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

def test_structure_rewards_sequencing_connectors():
    structured = "First, I gathered requirements. Then I built a prototype. Finally, I presented it to the team."
    unstructured = "I did a lot of things for the project."
    assert assess_structure(structured).structure_score > assess_structure(unstructured).structure_score


# ---------------------------------------------------------------------------
# Per-answer composite evaluation
# ---------------------------------------------------------------------------

def test_evaluate_answer_communication_returns_bounded_score():
    text = "For example, in my previous role I first identified the bottleneck. Then I redesigned the workflow, and as a result throughput improved."
    result = evaluate_answer_communication(text, question_id="q1", category="career_journey")
    assert 0.0 <= result.communication_score <= 100.0
    assert result.sample_size_reliability == "normal"


def test_evaluate_answer_communication_flags_short_answer_reliability():
    result = evaluate_answer_communication("I did okay I guess.", question_id="q2")
    assert result.sample_size_reliability == "low"


def test_filler_words_reduce_score():
    with_fillers = "Um, I think, uh, it was, um, you know, kind of a good experience I guess."
    without_fillers = "It was a genuinely good experience that taught me a lot about ownership."
    with_score = evaluate_answer_communication(with_fillers).communication_score
    without_score = evaluate_answer_communication(without_fillers).communication_score
    assert with_score < without_score


def test_short_answer_filler_penalty_is_halved():
    # Same filler word, but one answer is below the short-answer threshold.
    short = evaluate_answer_communication("Um, it was fine.")
    long_text = (
        "Um, it was overall a genuinely productive and rewarding experience that helped me grow "
        "significantly as a professional and as a communicator on cross-functional teams."
    )
    long_eval = evaluate_answer_communication(long_text)
    assert short.sample_size_reliability == "low"
    assert long_eval.sample_size_reliability == "normal"
    # The penalty applied (not the raw rate) should be smaller in absolute terms for the short one.
    assert abs(short.component_breakdown["filler_penalty"]) <= 10.0


# ---------------------------------------------------------------------------
# Interview-level aggregate
# ---------------------------------------------------------------------------

def test_build_interview_communication_profile_empty_session():
    session = InterviewSession.start(ExperienceLevel.FRESHER, RoleType.TECHNICAL)
    profile = build_interview_communication_profile(session)
    assert profile.overall_communication_score == 0.0
    assert profile.answer_evaluations == []


def test_build_interview_communication_profile_skips_unanswered_questions():
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)
    session.submit_response("For example, I once led a migration that reduced downtime significantly.")
    profile = build_interview_communication_profile(session)
    # Only the one answered question should be evaluated, not the whole question bank.
    assert len(profile.answer_evaluations) == 1


def test_build_interview_communication_profile_category_scores():
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.NON_TECHNICAL)
    session.submit_response("First, I introduced myself. Then I described my background clearly.")
    session.submit_response("For example, in my last job I resolved a conflict between two teammates by listening to both sides.")
    profile = build_interview_communication_profile(session)
    assert len(profile.answer_evaluations) == 2
    assert set(profile.category_scores.keys()) == {q.category for q in profile.answer_evaluations}
    assert 0.0 <= profile.overall_communication_score <= 100.0


def test_build_interview_communication_profile_tracks_low_reliability_count():
    session = InterviewSession.start(ExperienceLevel.FRESHER, RoleType.NON_TECHNICAL)
    session.submit_response("Okay.")
    profile = build_interview_communication_profile(session)
    assert profile.low_reliability_answer_count == 1
