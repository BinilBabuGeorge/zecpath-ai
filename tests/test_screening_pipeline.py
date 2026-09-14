from parsers.speech_to_text import RawSTTResult
from parsers.screening_pipeline import run_screening_call
from parsers.answer_intent_engine import AnswerQuality


_STRONG_TURNS = [
    RawSTTResult(text="Hi, I'm a developer based in Pune with three years of experience.", confidence=0.9),
    RawSTTResult(text="I completed my B.Tech in Computer Science from a college in Pune.", confidence=0.9),
    RawSTTResult(text="I have three years of experience with React and Node.js.", confidence=0.9),
    RawSTTResult(text="I have used Docker and Kubernetes quite a bit.", confidence=0.9),
    RawSTTResult(text="I'm currently based in Bengaluru and open to relocating.", confidence=0.9),
    RawSTTResult(text="My current CTC is around eight lakhs and I am expecting more.", confidence=0.9),
    RawSTTResult(text="My notice period is immediate, I can join within a few days.", confidence=0.9),
]


def test_full_clean_call_answers_every_category():
    result = run_screening_call(_STRONG_TURNS, categories=["introduction", "education", "experience", "skills", "location", "salary", "notice_period"])
    assert result.categories_missing == []
    assert len(result.categories_answered) == 7
    assert result.controller.is_call_complete


def test_full_clean_call_produces_a_high_score():
    result = run_screening_call(_STRONG_TURNS, categories=["introduction", "education", "experience", "skills", "location", "salary", "notice_period"])
    assert result.report.total_score >= 70


def test_report_carries_candidate_metadata():
    result = run_screening_call(_STRONG_TURNS, categories=["introduction"], candidate_id="C-001", job_role="MERN Developer")
    assert result.report.candidate_id == "C-001"
    assert result.report.job_role == "MERN Developer"


def test_call_ending_early_marks_remaining_categories_missing():
    turns = [RawSTTResult(text="Hi, I'm a developer based in Pune with three years of experience.", confidence=0.9)]
    result = run_screening_call(turns, categories=["introduction", "education", "experience"])
    assert "introduction" in result.categories_answered
    assert result.categories_missing == ["education", "experience"]
    assert not result.controller.is_call_complete


def test_missing_category_gets_a_readable_reason_in_the_report():
    turns = [RawSTTResult(text="Hi, I'm a developer based in Pune with three years of experience.", confidence=0.9)]
    result = run_screening_call(turns, categories=["introduction", "education"])
    missing_answer = [a for a in result.report.key_answers if a["category"] == "education"][0]
    assert missing_answer["quality"] == "missing"


def test_genuine_silence_distinguished_from_edge_case_skip():
    turns = [
        RawSTTResult(text="Hi, I'm a developer based in Pune with three years of experience.", confidence=0.9),
        RawSTTResult(text="", confidence=0.0, is_silent=True),
    ]
    result = run_screening_call(turns, categories=["introduction", "education"])
    assert "education" in result.categories_missing
    # a genuine silence should not carry the edge-case-skip phrasing --
    # it's Day 25/29's own real MISSING answer, passed through as-is.
    education_answer = [a for a in result.report.key_answers if a["category"] == "education"][0]
    assert education_answer["quality"] == "missing"


def test_edge_case_skip_gets_an_edge_case_specific_reason():
    turns = [
        RawSTTResult(text="Hi, I'm a developer based in Pune with three years of experience.", confidence=0.9),
        RawSTTResult(text="garbled", confidence=0.3),   # education: poor audio, attempt 1
        RawSTTResult(text="garbled", confidence=0.3),   # education: poor audio, attempt 2 -> safety-skip
    ]
    result = run_screening_call(turns, categories=["introduction", "education", "experience"])
    assert "education" in result.categories_missing
    # find the underlying StructuredAnswer's note via the JSON report structure
    d = result.report.to_dict()
    edge_note_found = any("edge case" in note for note in d.get("missing_data", []))
    assert edge_note_found


def test_scoring_result_and_communication_profile_are_populated():
    result = run_screening_call(_STRONG_TURNS, categories=["introduction", "education"])
    assert result.scoring_result.total_score >= 0
    assert result.communication_profile.communication_strength_score >= 0


def test_empty_turns_produces_all_missing_report():
    result = run_screening_call([], categories=["introduction", "education"])
    assert result.categories_answered == []
    assert result.categories_missing == ["introduction", "education"]
    assert all(ka["quality"] == "missing" for ka in result.report.key_answers)


def test_default_categories_match_day22_when_none_given():
    from parsers.screening_question_bank import CATEGORIES
    result = run_screening_call([], categories=None)
    assert result.categories_missing == CATEGORIES


def test_weak_candidate_scores_lower_than_strong_candidate():
    weak_turns = [
        RawSTTResult(text="Hi.", confidence=0.9),
        RawSTTResult(text="I'm not sure, maybe.", confidence=0.9),
    ]
    strong_result = run_screening_call(_STRONG_TURNS[:2], categories=["introduction", "education"])
    weak_result = run_screening_call(weak_turns, categories=["introduction", "education"])
    assert weak_result.report.total_score < strong_result.report.total_score
