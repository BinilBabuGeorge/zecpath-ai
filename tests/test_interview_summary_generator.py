from parsers.hr_interview_question_bank import InterviewSession, ExperienceLevel, RoleType
from parsers.hr_interview_scoring_engine import score_hr_interview
from parsers.aptitude_logic_engine import AptitudeSession, build_aptitude_profile
from parsers.confidence_stress_engine import build_confidence_profile
from parsers.interview_summary_generator import (
    generate_interview_summary, _band_for_score, _assess_cultural_fit, _detect_risk_flags,
)


def _strong_hr_session():
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)
    session.submit_response("For example, I led the migration project and delivered it two weeks ahead of schedule.")
    session.submit_response("I steadily grew from junior to senior engineer over four years.")
    session.submit_response("My strength is ownership; my weakness is taking on too much.")
    session.submit_response("For example, I resolved a conflict between two teammates by listening to both sides.")
    return session


def _weak_hr_session():
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.NON_TECHNICAL)
    session.submit_response("I was excited, happy, proud, confident, and motivated about it.")
    session.submit_response("Honestly, nothing comes to mind, not sure.")
    session.submit_response("It was difficult, I struggled, was frustrated, afraid, and stressed the whole time.")
    session.submit_response("I guess it was okay, not sure really.")
    return session


# ---------------------------------------------------------------------------
# Performance band classification
# ---------------------------------------------------------------------------

def test_band_for_high_score():
    assert _band_for_score(85.0) == "Strong"


def test_band_for_low_score():
    assert _band_for_score(20.0) == "Weak"


def test_band_boundaries():
    assert _band_for_score(80.0) == "Strong"
    assert _band_for_score(65.0) == "Good"
    assert _band_for_score(50.0) == "Moderate"
    assert _band_for_score(49.9) == "Weak"


# ---------------------------------------------------------------------------
# Strengths / weaknesses classification
# ---------------------------------------------------------------------------

def test_strong_session_produces_strengths():
    hr_report = score_hr_interview(_strong_hr_session())
    summary = generate_interview_summary(hr_report)
    assert len(summary.strengths) >= 1


def test_weak_session_produces_weaknesses_or_risk_flags():
    hr_report = score_hr_interview(_weak_hr_session())
    summary = generate_interview_summary(hr_report)
    # A weak session should surface either a weakness or a risk flag -- not read as clean.
    assert summary.weaknesses or summary.risk_flags


def test_middling_scores_not_listed_as_strength_or_weakness():
    hr_report = score_hr_interview(_strong_hr_session())
    summary = generate_interview_summary(hr_report)
    listed_components = {s.component for s in summary.strengths} | {w.component for w in summary.weaknesses}
    # Every listed component must actually cross a threshold, not sit in the middle band.
    for s in summary.strengths:
        assert s.score >= 80.0
    for w in summary.weaknesses:
        assert w.score < 50.0


# ---------------------------------------------------------------------------
# Cultural fit indicator
# ---------------------------------------------------------------------------

def test_cultural_fit_uses_teamwork_category():
    hr_report = score_hr_interview(_strong_hr_session())
    indicator = _assess_cultural_fit(hr_report)
    assert indicator.score is not None
    assert indicator.band in ("positive indicator", "neutral", "needs attention")


def test_cultural_fit_no_signal_when_category_absent():
    session = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)
    session.submit_response("For example, I led the migration project.")  # only answers self_introduction
    hr_report = score_hr_interview(session)
    indicator = _assess_cultural_fit(hr_report)
    assert indicator.score is None
    assert indicator.band == "no signal"


# ---------------------------------------------------------------------------
# Risk flags
# ---------------------------------------------------------------------------

def test_vague_answer_produces_risk_flag():
    hr_report = score_hr_interview(_weak_hr_session())
    flags = _detect_risk_flags(hr_report, None, None)
    assert any(f.label == "Vague or missing answer content" for f in flags)


def test_inconsistency_produces_risk_flag():
    hr_report = score_hr_interview(_weak_hr_session())
    flags = _detect_risk_flags(hr_report, None, None)
    assert any(f.label == "Possible response inconsistency" for f in flags)


def test_elevated_stress_produces_risk_flag():
    session = _weak_hr_session()
    hr_report = score_hr_interview(session)
    confidence_profile = build_confidence_profile(session)
    flags = _detect_risk_flags(hr_report, None, confidence_profile)
    if confidence_profile.overall_stress_score >= 50.0:
        assert any(f.label == "Elevated stress-indicative language" for f in flags)


def test_weak_aptitude_produces_risk_flag():
    session = _strong_hr_session()
    hr_report = score_hr_interview(session)
    apt_session = AptitudeSession.start()
    for _ in range(6):
        apt_session.submit_response("Not sure, maybe.")
    apt_profile = build_aptitude_profile(apt_session)
    flags = _detect_risk_flags(hr_report, apt_profile, None)
    assert any(f.label == "Weak logical reasoning performance" for f in flags)


def test_clean_session_has_no_risk_flags():
    hr_report = score_hr_interview(_strong_hr_session())
    flags = _detect_risk_flags(hr_report, None, None)
    assert flags == []


# ---------------------------------------------------------------------------
# Combined score / full report
# ---------------------------------------------------------------------------

def test_combined_score_without_aptitude_equals_hr_score():
    hr_report = score_hr_interview(_strong_hr_session())
    summary = generate_interview_summary(hr_report)
    assert summary.combined_overall_score == hr_report.overall_hr_score
    assert summary.aptitude_score is None


def test_combined_score_with_aptitude_blends_both():
    session = _strong_hr_session()
    hr_report = score_hr_interview(session)
    apt_session = AptitudeSession.start()
    for _ in range(6):
        apt_session.submit_response("For example, because therefore this addresses it clearly.")
    apt_profile = build_aptitude_profile(apt_session)
    summary = generate_interview_summary(hr_report, aptitude_profile=apt_profile)
    assert summary.aptitude_score == apt_profile.overall_aptitude_score
    assert summary.combined_overall_score != hr_report.overall_hr_score


def test_empty_aptitude_profile_treated_as_not_supplied():
    hr_report = score_hr_interview(_strong_hr_session())
    empty_apt_session = AptitudeSession.start()
    empty_apt_profile = build_aptitude_profile(empty_apt_session)  # no responses submitted
    summary = generate_interview_summary(hr_report, aptitude_profile=empty_apt_profile)
    assert summary.aptitude_score is None
    assert summary.combined_overall_score == hr_report.overall_hr_score


def test_to_narrative_contains_key_sections():
    hr_report = score_hr_interview(_strong_hr_session())
    summary = generate_interview_summary(hr_report)
    text = summary.to_narrative()
    assert "Overall Performance" in text
    assert "Strengths:" in text and "Weaknesses:" in text
    assert "Cultural Fit Indicator" in text and "Risk Flags:" in text


def test_to_dict_round_trips_key_fields():
    hr_report = score_hr_interview(_strong_hr_session())
    summary = generate_interview_summary(hr_report)
    d = summary.to_dict()
    assert d["combined_overall_score"] == summary.combined_overall_score
    assert d["performance_band"] == summary.performance_band
    assert "strengths" in d and "weaknesses" in d and "cultural_fit" in d and "risk_flags" in d
