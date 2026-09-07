from parsers.answer_intent_engine import understand_answer
from parsers.screening_scoring_engine import score_screening_call
from parsers.confidence_sentiment_engine import build_communication_profile
from parsers.screening_report_generator import generate_screening_report, ReportHighlights


def _answer(text, category, turn_id="t000", is_silent=False):
    return understand_answer(text, expected_category=category, turn_id=turn_id, is_silent=is_silent)


def _build_pipeline(answers, durations=None):
    scoring_result = score_screening_call(answers)
    profile = build_communication_profile(answers, scoring_result.consistency_findings, durations=durations)
    return scoring_result, profile


# ---------------------------------------------------------------------------
# Key answers
# ---------------------------------------------------------------------------

def test_key_answers_include_every_turn():
    answers = [
        _answer("I have three years of experience with React.", "experience", turn_id="t000"),
        _answer("I completed my B.Tech in Computer Science.", "education", turn_id="t001"),
    ]
    scoring_result, profile = _build_pipeline(answers)
    report = generate_screening_report(answers, scoring_result, profile)
    assert len(report.key_answers) == 2
    assert {ka["turn_id"] for ka in report.key_answers} == {"t000", "t001"}


def test_key_answer_preview_truncated_for_long_text():
    long_text = "I have three years of experience. " * 10
    answers = [_answer(long_text, "experience", turn_id="t000")]
    scoring_result, profile = _build_pipeline(answers)
    report = generate_screening_report(answers, scoring_result, profile)
    assert report.key_answers[0]["raw_text_preview"].endswith("...")
    assert len(report.key_answers[0]["raw_text_preview"]) <= 163  # 160 + "..."


def test_key_answer_not_truncated_for_short_text():
    answers = [_answer("I have three years of experience.", "experience", turn_id="t000")]
    scoring_result, profile = _build_pipeline(answers)
    report = generate_screening_report(answers, scoring_result, profile)
    assert not report.key_answers[0]["raw_text_preview"].endswith("...")


# ---------------------------------------------------------------------------
# Strengths
# ---------------------------------------------------------------------------

def test_strong_answer_flagged_as_strength():
    answers = [_answer("I completed my B.Tech in Computer Science from a college in Pune.", "education", turn_id="t000")]
    scoring_result, profile = _build_pipeline(answers)
    report = generate_screening_report(answers, scoring_result, profile)
    assert any("Strong, complete answer on 'education'" in s for s in report.strengths)


def test_no_hesitation_flagged_as_strength():
    answers = [_answer("I have three years of experience with React.", "experience", turn_id="t000")]
    scoring_result, profile = _build_pipeline(answers)
    report = generate_screening_report(answers, scoring_result, profile)
    assert any("No hesitation or uncertainty" in s for s in report.strengths)


def test_no_contradictions_flagged_as_strength():
    answers = [_answer("I have three years of experience.", "experience", turn_id="t000")]
    scoring_result, profile = _build_pipeline(answers)
    report = generate_screening_report(answers, scoring_result, profile)
    assert any("No consistency conflicts" in s for s in report.strengths)


# ---------------------------------------------------------------------------
# Risks
# ---------------------------------------------------------------------------

def test_weak_answer_flagged_as_risk():
    answers = [_answer("I'm not sure, maybe.", "salary", turn_id="t000")]
    scoring_result, profile = _build_pipeline(answers)
    report = generate_screening_report(answers, scoring_result, profile)
    assert any("Weak answer on 'salary'" in r for r in report.risks)


def test_missing_answer_not_double_counted_as_weak_risk():
    # MISSING answers go to missing_data, not risks -- avoid double-reporting the same gap.
    answers = [_answer("", "experience", turn_id="t000", is_silent=True)]
    scoring_result, profile = _build_pipeline(answers)
    report = generate_screening_report(answers, scoring_result, profile)
    assert not any("Weak answer" in r for r in report.risks)


def test_contradiction_finding_surfaced_as_risk():
    answers = [
        _answer("I have three years of experience.", "experience", turn_id="t000"),
        _answer("I have eight years of experience in this field.", "experience", turn_id="t001"),
    ]
    scoring_result, profile = _build_pipeline(answers)
    report = generate_screening_report(answers, scoring_result, profile)
    assert any("mismatch" in r.lower() for r in report.risks)


def test_negative_sentiment_flagged_as_risk():
    answers = [_answer("It's been a frustrating and difficult search, I feel quite nervous.", "salary", turn_id="t000")]
    scoring_result, profile = _build_pipeline(answers)
    report = generate_screening_report(answers, scoring_result, profile)
    assert any("Negative overall sentiment" in r for r in report.risks)


def test_elevated_hesitation_flagged_as_risk():
    answers = [_answer("Um, uh, you know, it was, um, you know, around three years, uh.", "experience", turn_id="t000")]
    scoring_result, profile = _build_pipeline(answers)
    report = generate_screening_report(answers, scoring_result, profile)
    assert any("Elevated hesitation" in r for r in report.risks)


# ---------------------------------------------------------------------------
# Missing data
# ---------------------------------------------------------------------------

def test_missing_answer_listed_in_missing_data():
    answers = [_answer("", "experience", turn_id="t000", is_silent=True)]
    scoring_result, profile = _build_pipeline(answers)
    report = generate_screening_report(answers, scoring_result, profile)
    assert any("No answer given for 'experience'" in m for m in report.missing_data)


def test_unparseable_salary_listed_in_missing_data():
    answers = [_answer("I'm expecting a good package, it's negotiable.", "salary", turn_id="t000")]
    scoring_result, profile = _build_pipeline(answers)
    report = generate_screening_report(answers, scoring_result, profile)
    assert any("salary" in m and "t000" in m for m in report.missing_data)


def test_no_missing_data_when_all_answers_complete():
    answers = [_answer("I have three years of experience.", "experience", turn_id="t000")]
    scoring_result, profile = _build_pipeline(answers)
    report = generate_screening_report(answers, scoring_result, profile)
    assert report.missing_data == []


# ---------------------------------------------------------------------------
# Highlights
# ---------------------------------------------------------------------------

def test_highlights_pull_salary_availability_skills():
    answers = [
        _answer("I have three years of experience with React and Node.js.", "experience", turn_id="t000"),
        _answer("My current CTC is around eight lakhs.", "salary", turn_id="t001"),
        _answer("My notice period is immediate.", "availability", turn_id="t002"),
    ]
    scoring_result, profile = _build_pipeline(answers)
    report = generate_screening_report(answers, scoring_result, profile)
    assert report.highlights.salary_expectation
    assert report.highlights.availability
    assert "React.js" in report.highlights.confirmed_skills
    assert "Node.js" in report.highlights.confirmed_skills


def test_highlights_skills_deduplicated_across_answers():
    answers = [
        _answer("I've used React for two years.", "skills", turn_id="t000"),
        _answer("I also use React on my current project.", "skills", turn_id="t001"),
    ]
    scoring_result, profile = _build_pipeline(answers)
    report = generate_screening_report(answers, scoring_result, profile)
    assert report.highlights.confirmed_skills.count("React.js") == 1


def test_highlights_empty_when_nothing_extracted():
    answers = [_answer("I completed my B.Tech in Computer Science.", "education", turn_id="t000")]
    scoring_result, profile = _build_pipeline(answers)
    report = generate_screening_report(answers, scoring_result, profile)
    assert report.highlights.salary_expectation == []
    assert report.highlights.availability == []
    assert report.highlights.confirmed_skills == []


# ---------------------------------------------------------------------------
# Whole-report / export format
# ---------------------------------------------------------------------------

def test_report_carries_total_and_communication_scores():
    answers = [_answer("I have three years of experience.", "experience", turn_id="t000")]
    scoring_result, profile = _build_pipeline(answers)
    report = generate_screening_report(answers, scoring_result, profile, candidate_id="C001", job_role="MERN Developer")
    assert report.total_score == scoring_result.total_score
    assert report.communication_strength_score == profile.communication_strength_score
    assert report.candidate_id == "C001"
    assert report.job_role == "MERN Developer"


def test_to_dict_round_trips_expected_keys():
    answers = [_answer("I have three years of experience.", "experience", turn_id="t000")]
    scoring_result, profile = _build_pipeline(answers)
    report = generate_screening_report(answers, scoring_result, profile)
    d = report.to_dict()
    for key in ["candidate_id", "job_role", "generated_at", "total_score", "communication_strength_score",
                "key_answers", "strengths", "risks", "missing_data", "highlights"]:
        assert key in d


def test_to_json_is_valid_json():
    import json
    answers = [_answer("I have three years of experience.", "experience", turn_id="t000")]
    scoring_result, profile = _build_pipeline(answers)
    report = generate_screening_report(answers, scoring_result, profile)
    parsed = json.loads(report.to_json())
    assert parsed["total_score"] == report.total_score


def test_to_markdown_contains_key_sections():
    answers = [_answer("I have three years of experience.", "experience", turn_id="t000")]
    scoring_result, profile = _build_pipeline(answers)
    report = generate_screening_report(answers, scoring_result, profile, candidate_id="C001")
    md = report.to_markdown()
    assert "# Screening Report — C001" in md
    assert "## Key Answers" in md
    assert "## Strengths" in md
    assert "## Risks" in md
    assert "## Missing Data" in md
    assert "## Highlights" in md


def test_to_markdown_handles_empty_sections_gracefully():
    answers = [_answer("", "experience", turn_id="t000", is_silent=True)]
    scoring_result, profile = _build_pipeline(answers)
    report = generate_screening_report(answers, scoring_result, profile)
    md = report.to_markdown()
    # A fully-missing single answer should have no strengths, but should
    # still render a readable section rather than an empty gap.
    assert "None identified" in md or "None -- every question" in md
