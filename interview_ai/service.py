"""
Interview Intelligence Service (Day 2 Process 3.0)
Input:  interview type, the candidate's answers, and the context needed to pick questions
Output: interview scores (HR or technical)

DAY 57: this service used to return a placeholder transcript and scores of 0 for any request. It now scores the answers it is
given with the real engines (`hr`: Day 37 scoring; `technical`: Day 47 scoring). With no answers it reports
`interview_status: "not_started"` and null scores instead of a fake zero.

`machine_test` and `final` interviews have their own engines but no service wiring yet; they return the error code
`unsupported_value` rather than a placeholder that looks like a result.
"""

from typing import Any, Dict

from utils.base_service import BaseAIService, ServiceInputError

SUPPORTED_TYPES = ("hr", "technical")


class InterviewIntelligenceService(BaseAIService):
    service_name = "interview_intelligence_service"

    def process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        interview_type = self._get_choice(payload, "interview_type", SUPPORTED_TYPES, default="hr")
        answers = self._get_list(payload, "answers") or []
        for i, a in enumerate(answers):
            if not isinstance(a, str):
                raise ServiceInputError("invalid_input", f"answers[{i}] must be text, got {type(a).__name__}.", f"answers[{i}]")
            if len(a) > 20_000:
                raise ServiceInputError("too_large", f"answers[{i}] is {len(a)} characters; the limit is 20000.", f"answers[{i}]")
        self.logger.info("Scoring %s interview (%d answers)", interview_type, len(answers))
        return self._hr(payload, answers) if interview_type == "hr" else self._technical(payload, answers)

    def _hr(self, payload: Dict[str, Any], answers: list) -> Dict[str, Any]:
        from parsers.hr_interview_question_bank import ExperienceLevel, InterviewSession, RoleType
        from parsers.hr_interview_scoring_engine import score_hr_interview

        role = RoleType(self._get_choice(payload, "role_type", [r.value for r in RoleType], default="technical"))
        level = ExperienceLevel(self._get_choice(payload, "experience_level", [e.value for e in ExperienceLevel], default="experienced"))
        response = self._base_response()
        response["interview_type"] = "hr"
        if not any(a.strip() for a in answers):
            response.update({"interview_status": "not_started", "hr_score": None, "communication_score": None, "technical_score": None,
                             "answers_scored": 0, "answers_ignored": len(answers), "warnings": ["No answers were supplied, so there is nothing to score."]})
            return response
        session = InterviewSession.start(level, role)
        used = 0
        for a in answers:
            if session.is_complete:
                break
            session.submit_response(a)
            used += 1
        report = score_hr_interview(session)
        response.update({
            "interview_status": "scored", "hr_score": round(report.overall_hr_score, 2),
            "communication_score": round(report.avg_communication, 2), "technical_score": None,
            "relevance_score": round(report.avg_relevance, 2), "confidence_score": round(report.avg_confidence, 2),
            "answers_scored": report.num_questions_answered, "answers_ignored": len(answers) - used,
            "non_substantive_answers": sum(1 for b in report.answer_breakdowns if b.non_substantive),
            "warnings": ([f"{len(answers) - used} answer(s) beyond the number of questions were ignored."] if len(answers) > used else []),
        })
        return response

    def _technical(self, payload: Dict[str, Any], answers: list) -> Dict[str, Any]:
        from parsers.technical_interview_question_bank import TechnicalDomain, TechnicalInterviewSession
        from parsers.technical_skill_scoring_engine import build_technical_evaluation_report

        domain = self._get_choice(payload, "domain", [d.value for d in TechnicalDomain], default="mern")
        years = payload.get("experience_years")
        if years is None:
            raise ServiceInputError("missing_field", "'experience_years' is required for a technical interview (it selects the question tier).", "experience_years")
        response = self._base_response()
        response["interview_type"] = "technical"
        session = TechnicalInterviewSession.start(TechnicalDomain(domain), years)      # validates years (finite, >= 0, a number)
        response["tier"] = session.tier.value
        if not any(a.strip() for a in answers):
            response.update({"interview_status": "not_started", "technical_score": None, "communication_score": None,
                             "answers_scored": 0, "answers_ignored": len(answers), "warnings": ["No answers were supplied, so there is nothing to score."]})
            return response
        used = 0
        for a in answers:
            if session.is_complete:
                break
            session.submit_response(a)
            used += 1
        report = build_technical_evaluation_report(session)
        response.update({
            "interview_status": "scored", "technical_score": round(report.overall_score, 2), "communication_score": None,
            "answers_scored": used, "answers_ignored": len(answers) - used,
            "warnings": ([f"{len(answers) - used} answer(s) beyond the number of questions were ignored."] if len(answers) > used else []),
        })
        return response


if __name__ == "__main__":
    print(InterviewIntelligenceService().run({"interview_type": "hr"}))
