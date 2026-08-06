from ats_engine.service import ATSService


def test_ats_score_matches_keywords():
    service = ATSService()
    payload = {
        "resume_text": "Skilled in React, Node.js and MongoDB with 3 years experience",
        "job_requirements": ["React", "Node.js", "MongoDB", "GraphQL"],
    }
    result = service.process(payload)

    assert result["status"] == "success"
    assert result["ats_score"] == 75.0  # 3 of 4 keywords matched
    assert "GraphQL" not in result["matched_keywords"]


def test_ats_score_zero_when_no_requirements_given():
    service = ATSService()
    result = service.process({"resume_text": "Anything", "job_requirements": []})
    assert result["ats_score"] == 0.0
