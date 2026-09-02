from parsers.answer_intent_engine import (
    AnswerIntent, AnswerQuality, IntentClassification, StructuredAnswer,
    classify_intent, extract_experience_years, extract_availability,
    extract_salary_expectation, understand_answer,
)


# ---------------------------------------------------------------------------
# classify_intent -- category detection
# ---------------------------------------------------------------------------

def test_classifies_skills_answer_via_real_skill_extraction():
    result = classify_intent("Yeah, I've used React and Node.js quite a bit.")
    assert result.intent == AnswerIntent.SKILLS


def test_classifies_salary_answer():
    result = classify_intent("My current CTC is around eight lakhs and I'm expecting ten to twelve.")
    assert result.intent == AnswerIntent.SALARY


def test_classifies_availability_answer():
    result = classify_intent("My notice period is thirty days but I can negotiate.")
    assert result.intent == AnswerIntent.AVAILABILITY


def test_classifies_experience_answer():
    result = classify_intent("I have been working as a developer for three years now.")
    assert result.intent == AnswerIntent.EXPERIENCE


def test_classifies_education_answer():
    result = classify_intent("I completed my B.Tech in Computer Science from a college in Pune.")
    assert result.intent == AnswerIntent.EDUCATION


def test_classifies_location_answer():
    result = classify_intent("I'm currently based in Bengaluru and open to relocating.")
    assert result.intent == AnswerIntent.LOCATION


def test_empty_text_is_unknown_not_a_guess():
    result = classify_intent("")
    assert result.intent == AnswerIntent.UNKNOWN
    assert result.confidence == 0.0


def test_no_keyword_match_is_unknown_with_honest_note():
    result = classify_intent("The weather has been quite nice lately.")
    assert result.intent == AnswerIntent.UNKNOWN
    assert result.note is not None


def test_category_scores_are_all_present_for_auditability():
    result = classify_intent("I have three years of experience.")
    for cat in ["introduction", "education", "experience", "location", "salary", "availability", "skills"]:
        assert cat in result.category_scores


def test_confidence_is_between_zero_and_one():
    result = classify_intent("My notice period is immediate.")
    assert 0.0 <= result.confidence <= 1.0


# ---------------------------------------------------------------------------
# Entity extraction -- reused Day 23 entry points
# ---------------------------------------------------------------------------

def test_extract_experience_years_finds_digit_number():
    assert extract_experience_years("I have 3 years of experience") == 3.0


def test_extract_experience_years_finds_word_number():
    assert extract_experience_years("I have three years of experience") == 3.0


def test_extract_experience_years_returns_none_when_absent():
    assert extract_experience_years("I have plenty of relevant experience") is None


def test_extract_availability_immediate():
    result = extract_availability("I can join immediately, no notice period.")
    assert result["immediate"] is True


def test_extract_availability_duration():
    result = extract_availability("My notice period is two weeks.")
    assert result["amount"] == 2
    assert result["unit"] == "weeks"


def test_extract_salary_lakhs():
    result = extract_salary_expectation("I'm expecting around ten lakhs per annum.")
    assert result["amount"] == 10
    assert result["unit"] == "lakhs_per_annum"


def test_extract_salary_word_number_lakhs():
    result = extract_salary_expectation("My current CTC is eight lakhs.")
    assert result["amount"] == 8
    assert result["unit"] == "lakhs_per_annum"


def test_extract_salary_thousand_per_month():
    result = extract_salary_expectation("I'm looking for around 45k a month.")
    assert result["amount"] == 45.0
    assert result["unit"] == "thousand_per_month"


def test_extract_salary_returns_none_when_unit_missing():
    # Documented gap: a bare number with no lakh/LPA/k unit is not
    # guessed at -- see extract_salary_expectation()'s docstring.
    assert extract_salary_expectation("I'm expecting around eight hundred thousand rupees") is None


# ---------------------------------------------------------------------------
# understand_answer -- full pipeline, quality gating
# ---------------------------------------------------------------------------

def test_understand_answer_ok_case_extracts_matching_entities():
    result = understand_answer("I have three years of experience with React and Node.js.", expected_category="experience")
    assert result.quality == AnswerQuality.OK
    assert result.entities.experience_years == 3.0
    assert "React.js" in result.entities.skills


def test_understand_answer_multi_entity_from_one_free_form_answer():
    text = "Hi, I'm a developer with three years of experience in React, currently based in Pune."
    result = understand_answer(text, expected_category="introduction")
    assert result.entities.experience_years == 3.0
    assert "React.js" in result.entities.skills


def test_understand_answer_missing_when_silent():
    result = understand_answer("", expected_category="salary", is_silent=True)
    assert result.quality == AnswerQuality.MISSING


def test_understand_answer_missing_when_empty_text_even_without_flag():
    result = understand_answer("   ", expected_category="salary", is_silent=False)
    assert result.quality == AnswerQuality.MISSING


def test_understand_answer_vague_hedge_phrase():
    result = understand_answer("I'm not sure, maybe.", expected_category="salary")
    assert result.quality == AnswerQuality.VAGUE


def test_understand_answer_vague_too_short():
    result = understand_answer("dunno", expected_category="salary")
    assert result.quality == AnswerQuality.VAGUE


def test_understand_answer_yes_no_short_answer_not_flagged_vague():
    result = understand_answer("yes", expected_category="availability")
    assert result.quality != AnswerQuality.VAGUE


def test_understand_answer_off_topic_when_answer_matches_a_different_category():
    result = understand_answer("My current CTC is twelve lakhs.", expected_category="location")
    assert result.quality == AnswerQuality.OFF_TOPIC
    assert "salary" in result.notes[0]


def test_understand_answer_unknown_vocabulary_is_not_confidently_off_topic():
    # No category matched at all -- OFF_TOPIC requires POSITIVE evidence
    # of a different topic, not just absence of the expected one.
    result = understand_answer("The weather has been quite nice lately.", expected_category="salary")
    assert result.quality != AnswerQuality.OFF_TOPIC


def test_notice_period_category_alias_maps_to_availability():
    result = understand_answer("My notice period is immediate.", expected_category="notice_period")
    assert result.question_category == "availability"
    assert result.quality == AnswerQuality.OK


def test_to_dict_round_trips_expected_keys():
    result = understand_answer("I have three years of experience.", expected_category="experience", turn_id="call_x-t000")
    d = result.to_dict()
    assert d["turn_id"] == "call_x-t000"
    assert d["quality"] == "ok"
    assert "intent" in d and "entities" in d


def test_salary_relevant_answer_with_unparseable_amount_gets_a_note():
    result = understand_answer("I'm expecting a good salary package, negotiable.", expected_category="salary")
    assert result.entities.salary_expectation is None
    assert any("Salary-relevant" in n for n in result.notes)
