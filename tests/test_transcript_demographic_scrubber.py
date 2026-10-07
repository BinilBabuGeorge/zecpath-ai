from parsers.transcript_demographic_scrubber import (
    detect_demographic_disclosures, mask_demographic_disclosures, REDACTED,
)


# ---------------------------------------------------------------------------
# Genuine first-person self-disclosures -- should be detected
# ---------------------------------------------------------------------------

def test_detects_age_disclosure():
    report = detect_demographic_disclosures("As a 45-year-old switching careers, I bring a lot of experience.")
    assert "Age" in report.categories_detected


def test_detects_religion_disclosure():
    report = detect_demographic_disclosures("Being Muslim, I'd need Friday prayer time.")
    assert "Religion" in report.categories_detected


def test_detects_marital_family_disclosure():
    report = detect_demographic_disclosures("I'm a single mother returning to work after a break.")
    assert "Marital/family status" in report.categories_detected


def test_detects_children_mention_as_family_status():
    report = detect_demographic_disclosures("I have two kids, so I've gotten good at prioritizing.")
    assert "Marital/family status" in report.categories_detected


def test_detects_disability_disclosure():
    report = detect_demographic_disclosures("I have a disability that I've learned to work around effectively.")
    assert "Disability" in report.categories_detected


def test_detects_nationality_disclosure():
    report = detect_demographic_disclosures("I'm an Indian national currently based abroad.")
    assert "Nationality/origin" in report.categories_detected


# ---------------------------------------------------------------------------
# Narrow scope -- must NOT flag third-party or project-context mentions
# ---------------------------------------------------------------------------

def test_does_not_flag_project_context_mention():
    report = detect_demographic_disclosures("I once built a donation platform for a Catholic charity.")
    assert report.categories_detected == []


def test_does_not_flag_third_party_family_mention():
    report = detect_demographic_disclosures("My previous manager was married with two kids.")
    assert report.categories_detected == []


def test_does_not_flag_team_age_description():
    report = detect_demographic_disclosures("The team was 45 years old on average, very experienced.")
    assert report.categories_detected == []


def test_does_not_flag_accessibility_project_description():
    report = detect_demographic_disclosures("I worked on an accessibility project for visually impaired users.")
    assert report.categories_detected == []


def test_clean_answer_has_no_disclosures():
    report = detect_demographic_disclosures("I led the migration project and delivered it two weeks early.")
    assert report.categories_detected == []
    assert report.matched_phrases == []


# ---------------------------------------------------------------------------
# Masking -- same interface shape as Day 15's mask_pii()
# ---------------------------------------------------------------------------

def test_masking_redacts_without_revealing_value():
    masked, categories = mask_demographic_disclosures("I'm a single mother returning to work.")
    assert REDACTED in masked
    assert "mother" not in masked.lower()
    assert "Marital/family status" in categories


def test_masking_preserves_surrounding_text():
    masked, _ = mask_demographic_disclosures("Being Muslim, I'd need Friday prayer time, but otherwise flexible.")
    assert "Friday prayer time" in masked
    assert "otherwise flexible" in masked


def test_masking_clean_text_returns_unchanged():
    text = "I led the migration project and delivered it two weeks early."
    masked, categories = mask_demographic_disclosures(text)
    assert masked == text
    assert categories == []


def test_masking_multiple_categories_in_one_answer():
    text = "As a 45-year-old, I'm a single mother who recently switched careers."
    masked, categories = mask_demographic_disclosures(text)
    assert "Age" in categories
    assert "Marital/family status" in categories
