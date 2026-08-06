"""
ATS AI Service (Day 2 Process 1.0)
Input:  resume file + job requirements
Output: structured candidate profile + ATS score
"""

from typing import Any, Dict

from utils.base_service import BaseAIService


class ATSService(BaseAIService):
    service_name = "ats_ai_service"

    def process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        resume_text = payload.get("resume_text", "")
        job_requirements = payload.get("job_requirements", [])

        self.logger.info("Scoring resume against %d requirements", len(job_requirements))

        # TODO: replace with real NLP parsing & scoring logic
        matched_keywords = [kw for kw in job_requirements if kw.lower() in resume_text.lower()]
        score = round(100 * len(matched_keywords) / max(len(job_requirements), 1), 2)

        response = self._base_response()
        response.update({
            "matched_keywords": matched_keywords,
            "ats_score": score,
        })
        return response


if __name__ == "__main__":
    demo_payload = {
        "resume_text": "Experienced MERN stack developer skilled in React and Node.js",
        "job_requirements": ["React", "Node.js", "MongoDB"],
    }
    print(ATSService().process(demo_payload))
