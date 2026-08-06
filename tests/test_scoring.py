from scoring.service import DecisionScoringService


def test_high_scores_result_in_selection():
    service = DecisionScoringService()
    result = service.process({
        "candidate_id": "C001",
        "ats_score": 90,
        "screening_score": 85,
        "communication_score": 88,
        "technical_score": 92,
        "behavior_score": 95,
    })
    assert result["decision"] == "selected"
    assert result["hiring_fit_score"] > 70


def test_low_scores_result_in_rejection():
    service = DecisionScoringService()
    result = service.process({
        "candidate_id": "C002",
        "ats_score": 20,
        "screening_score": 15,
        "communication_score": 10,
        "technical_score": 5,
        "behavior_score": 30,
    })
    assert result["decision"] == "rejected"
