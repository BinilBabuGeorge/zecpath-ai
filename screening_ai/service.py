"""
Screening AI Service (Day 2 Process 2.0)
Input:  candidate contact info, job role, voice/language settings, call trigger
Output: call status, transcript, screening score
"""

from typing import Any, Dict

from utils.base_service import BaseAIService


class ScreeningService(BaseAIService):
    service_name = "screening_ai_service"

    def process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        candidate_id = payload.get("candidate_id")
        language = payload.get("language", "en")

        self.logger.info("Triggering screening call for candidate %s (%s)", candidate_id, language)

        # TODO: integrate real voice-call provider (e.g. Twilio) + voice-to-text
        response = self._base_response()
        response.update({
            "candidate_id": candidate_id,
            "call_status": "answered",
            "transcript": "[placeholder transcript]",
            "screening_score": 0,
        })
        return response


if __name__ == "__main__":
    print(ScreeningService().process({"candidate_id": "C001", "language": "en"}))
