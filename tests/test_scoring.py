"""
Decision & Scoring Service tests.

DAY 57 -- WHY THIS FILE CHANGED. The two Day 2 tests asserted the placeholder's behaviour: five hard-coded rounds including a
"behavior" round that does not exist in the aggregation, "selected" on partial evidence, and an AUTOMATIC "rejected" below 50.
The service now delegates to the real engines (Days 51-52), whose rules are different on purpose: a missing round is absent
(not zero), a technical role is not decided until its machine test exists, and a rejection is only ever a recommendation a
person confirms. The intent of both tests is kept -- strong evidence selects, very weak evidence recommends rejection -- and
the new rules are tested beside them. More thorough contract tests: tests/test_service_contracts.py.
"""

from scoring.service import DecisionScoringService

FULL_TECHNICAL = {"role_type": "technical", "experience_level": "experienced"}


def test_high_scores_result_in_selection():
    service = DecisionScoringService()
    result = service.run({**FULL_TECHNICAL, "candidate_id": "C001", "ats_score": 70, "screening_score": 85, "hr_interview_score": 88,
                          "technical_score": 92, "machine_test_score": 90, "ats_zone": "shortlist"})
    assert result["status"] == "success"
    assert result["decision"] == "selected"
    assert result["hiring_fit_score"] > 70
    assert result["human_confirmation_required"] is False


def test_low_scores_result_in_a_rejection_recommendation_a_person_must_confirm():
    service = DecisionScoringService()
    result = service.run({**FULL_TECHNICAL, "candidate_id": "C002", "ats_score": 5, "screening_score": 10, "hr_interview_score": 8,
                          "technical_score": 5, "machine_test_score": 5})
    assert result["decision"] == "rejected"
    assert result["human_confirmation_required"] is True
    assert result["automated_action"] in (None, "none")          # nothing is rejected automatically
