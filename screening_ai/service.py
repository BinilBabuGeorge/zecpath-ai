"""
Screening AI Service (Day 2 Process 2.0)
Input:  candidate id and the call transcript turns (speech-to-text output)
Output: call status, screening score, categories answered / missing

DAY 57: this service used to return `call_status: "answered"`, a placeholder transcript and a score of 0 for ANY request, even
though no call had taken place -- a success-shaped answer with no information behind it. It now runs the real screening
pipeline on the turns it is given. With no turns it says so (`call_status: "not_started"`, `screening_score: null`).

Placing the call (a voice provider such as Twilio) is still NOT implemented here; this service scores a conversation that has
already happened or is being fed to it turn by turn.
"""

from typing import Any, Dict

from utils.base_service import BaseAIService, ServiceInputError


class ScreeningService(BaseAIService):
    service_name = "screening_ai_service"

    def process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        candidate_id = payload.get("candidate_id")
        if candidate_id is not None and not isinstance(candidate_id, str):
            raise ServiceInputError("invalid_input", "'candidate_id' must be text.", "candidate_id")
        turns = self._get_list(payload, "turns")
        response = self._base_response()
        response["candidate_id"] = candidate_id

        if not turns:
            self.logger.info("No turns supplied for candidate %s: call not started", candidate_id)
            response.update({"call_status": "not_started", "screening_score": None, "categories_answered": [], "categories_missing": [],
                             "turns_used": 0,
                             "warnings": ["No call turns were supplied, so there is nothing to score. A voice provider is not integrated."]})
            return response

        from parsers.screening_pipeline import run_screening_call
        from parsers.speech_to_text import RawSTTResult

        raw_turns = []
        for i, t in enumerate(turns):
            if not isinstance(t, dict) or not isinstance(t.get("text", ""), str):
                raise ServiceInputError("invalid_input", f"turns[{i}] must be an object with a text field.", f"turns[{i}]")
            conf = t.get("confidence", 0.9)
            if isinstance(conf, bool) or not isinstance(conf, (int, float)) or conf != conf or not 0 <= conf <= 1:
                raise ServiceInputError("invalid_input", f"turns[{i}].confidence must be a number between 0 and 1.", f"turns[{i}].confidence")
            raw_turns.append(RawSTTResult(text=t.get("text", ""), confidence=float(conf), is_silent=bool(t.get("is_silent", False))))

        self.logger.info("Scoring screening call for candidate %s (%d turns)", candidate_id, len(raw_turns))
        call = run_screening_call(raw_turns, candidate_id=candidate_id or "unknown", job_role=str(payload.get("job_role", "unspecified")))
        status = "ended_early" if call.controller.call_ended_early else "completed" if call.controller.is_call_complete else "incomplete"
        response.update({
            "call_status": status,
            "screening_score": round(call.scoring_result.total_score, 2),
            "categories_answered": list(call.categories_answered),
            "categories_missing": list(call.categories_missing),
            "turns_used": len(raw_turns),
            "warnings": [] if status == "completed" else [f"The call is {status.replace('_', ' ')}: the score covers only the answered categories."],
        })
        return response


if __name__ == "__main__":
    print(ScreeningService().run({"candidate_id": "C001"}))
