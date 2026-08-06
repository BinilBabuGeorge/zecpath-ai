"""
Decision & Scoring Service (Day 2 Process 5.0)
Input:  all round scores — ATS, screening, interview, behavior
Output: final decision, hiring-fit score, offer letter data
"""

from typing import Any, Dict

from utils.base_service import BaseAIService


class DecisionScoringService(BaseAIService):
    service_name = "decision_scoring_service"

    # Configurable weighting per round (should sum to 1.0)
    WEIGHTS = {
        "ats_score": 0.2,
        "screening_score": 0.1,
        "communication_score": 0.25,
        "technical_score": 0.35,
        "behavior_score": 0.1,
    }

    def process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.info("Aggregating scores for candidate %s", payload.get("candidate_id"))

        weighted_total = sum(
            payload.get(key, 0) * weight for key, weight in self.WEIGHTS.items()
        )

        decision = "selected" if weighted_total >= 70 else "hold" if weighted_total >= 50 else "rejected"

        response = self._base_response()
        response.update({
            "hiring_fit_score": round(weighted_total, 2),
            "decision": decision,
        })
        return response


if __name__ == "__main__":
    demo_scores = {
        "candidate_id": "C001",
        "ats_score": 80,
        "screening_score": 70,
        "communication_score": 75,
        "technical_score": 85,
        "behavior_score": 90,
    }
    print(DecisionScoringService().process(demo_scores))
