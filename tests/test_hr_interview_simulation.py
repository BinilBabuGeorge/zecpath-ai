from parsers.hr_interview_simulation import PERSONAS, run_persona_simulation, run_all_personas


def _get(name):
    return next(p for p in PERSONAS if p.name == name)


# ---------------------------------------------------------------------------
# Persona definitions
# ---------------------------------------------------------------------------

def test_four_personas_defined():
    names = {p.name for p in PERSONAS}
    assert names == {"Confident", "Hesitant", "Inexperienced", "Overqualified"}


def test_every_persona_has_full_answer_sets():
    for p in PERSONAS:
        assert len(p.hr_answers) == 4
        assert len(p.aptitude_answers) == 6
        assert p.manual_expectation


# ---------------------------------------------------------------------------
# Simulation runs end-to-end without error for every persona
# ---------------------------------------------------------------------------

def test_run_persona_simulation_produces_full_result():
    result = run_persona_simulation(_get("Confident"))
    assert result.hr_report.num_questions_answered == 4
    assert len(result.aptitude_profile.answer_evaluations) == 6
    assert result.summary is not None


def test_run_all_personas_returns_four_results():
    results = run_all_personas()
    assert len(results) == 4
    assert {r.persona.name for r in results} == {"Confident", "Hesitant", "Inexperienced", "Overqualified"}


# ---------------------------------------------------------------------------
# Directional sanity checks against the hand-written manual expectations
# ---------------------------------------------------------------------------

def test_confident_scores_well_with_no_risk_flags():
    result = run_persona_simulation(_get("Confident"))
    assert result.summary.combined_overall_score >= 65.0
    assert result.summary.risk_flags == []


def test_inexperienced_is_not_flagged_as_inconsistent():
    # Core claim this persona probes: "weak" must not be conflated with "risky".
    result = run_persona_simulation(_get("Inexperienced"))
    assert result.hr_report.consistency.findings == []
    inconsistency_flags = [f for f in result.summary.risk_flags if f.label == "Possible response inconsistency"]
    assert inconsistency_flags == []


def test_inexperienced_scores_lower_relevance_than_confident():
    inexperienced = run_persona_simulation(_get("Inexperienced"))
    confident = run_persona_simulation(_get("Confident"))
    assert inexperienced.hr_report.avg_relevance < confident.hr_report.avg_relevance


def test_hesitant_relevance_differs_from_confidence_score():
    # The core claim this persona probes: delivery-based and content-based
    # scores should not collapse into one identical number.
    result = run_persona_simulation(_get("Hesitant"))
    assert result.hr_report.avg_relevance != result.hr_report.avg_confidence


def test_overqualified_scores_strong_technical_relevance():
    result = run_persona_simulation(_get("Overqualified"))
    assert result.hr_report.avg_relevance >= 70.0


def test_all_personas_land_in_a_valid_performance_band():
    valid_bands = {"Strong", "Good", "Moderate", "Weak"}
    for result in run_all_personas():
        assert result.summary.performance_band in valid_bands


def test_all_personas_produce_a_readable_narrative():
    for result in run_all_personas():
        text = result.summary.to_narrative()
        assert "Overall Performance" in text
        assert len(text) > 100
