"""
Decision & Scoring Service (Day 2 Process 5.0)
Input:  the scores of whichever rounds have happened, plus role type and experience level
Output: hiring-fit score and a RECOMMENDATION for a human to act on

DAY 57 -- WHY THIS WAS REPLACED. The Day 2 stub had its own hard-coded weights (ats 0.2 / screening 0.1 / communication 0.25 /
technical 0.35 / behavior 0.1) and its own thresholds, and it disagreed with the real engines (Days 41, 51, 52) in ways that
matter:
  * a score that was MISSING counted as ZERO (`payload.get(key, 0)`), dragging a candidate down for a round that had not happened;
  * it returned "rejected" automatically below 50, on any evidence, however incomplete -- the project's own rule (Day 52) is
    that a rejection is only ever a recommendation a person confirms, and never on incomplete evidence;
  * it could not see an ATS "reject" zone, integrity flags, critical-round floors or confidence.
The service now delegates to the real aggregation (Day 51) and recommendation (Day 52) engines. Day 41's own docs listed this
wiring as the deferred follow-up.

CONTRACT CHANGES vs the stub (API_VERSION 1.0 starts here):
  * missing score = absent, never zero; at least one round score is required;
  * `decision` is now one of selected | hold_review | rejected (was selected | hold | rejected) and is a RECOMMENDATION:
    `human_confirmation_required` is true for rejected, and `automated_action` never rejects;
  * with a round still outstanding the decision is hold_review / pending_evidence (a technical role with no machine test is
    never "selected" or "rejected" on partial evidence);
  * input keys are the real round names; `communication_score` is accepted as an alias for `hr_interview_score`, and
    `behavior_score` is ignored with a warning (there is no separate behavior round in the aggregation).
"""

from typing import Any, Dict, List

from utils.base_service import BaseAIService, ServiceInputError

ROUND_KEYS = {
    "ats": "ats_score",
    "screening": "screening_score",
    "hr_interview": "hr_interview_score",
    "technical_interview": "technical_score",
    "machine_test": "machine_test_score",
}
LEGACY_ALIASES = {"communication_score": "hr_interview_score"}
IGNORED_LEGACY_KEYS = ("behavior_score",)
ZONES = ("shortlist", "review", "reject")


class DecisionScoringService(BaseAIService):
    service_name = "decision_scoring_service"

    def process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        from parsers.cross_round_aggregation_engine import RoundResult, compute_cross_round_score, zone_review_reasons
        from parsers.final_recommendation_engine import decide
        from parsers.hr_interview_question_bank import ExperienceLevel, RoleType

        candidate_id = payload.get("candidate_id")
        if candidate_id is not None and not isinstance(candidate_id, str):
            raise ServiceInputError("invalid_input", "'candidate_id' must be text.", "candidate_id")
        role = RoleType(self._get_choice(payload, "role_type", [r.value for r in RoleType], default="technical"))
        level = ExperienceLevel(self._get_choice(payload, "experience_level", [e.value for e in ExperienceLevel], default="experienced"))
        zone = payload.get("ats_zone")
        if zone is not None:
            zone = self._get_choice(payload, "ats_zone", ZONES, default="shortlist")

        warnings: List[str] = []
        merged = dict(payload)
        for old, new in LEGACY_ALIASES.items():
            if old in payload:
                if new in payload:
                    raise ServiceInputError("invalid_input", f"Send either '{new}' or its legacy alias '{old}', not both.", old)
                merged[new] = payload[old]
                warnings.append(f"'{old}' is a legacy alias; use '{new}'.")
        for key in IGNORED_LEGACY_KEYS:
            if key in payload:
                warnings.append(f"'{key}' is ignored: there is no separate behavior round in the aggregation.")

        rounds = []
        for round_name, key in ROUND_KEYS.items():
            score = self._get_score(merged, key)
            if score is None:
                continue
            reasons = zone_review_reasons(zone) if (round_name == "ats" and zone) else []
            rounds.append(RoundResult(round_name, score, review_reasons=reasons))
        if not rounds:
            raise ServiceInputError("missing_field", f"At least one round score is required: {list(ROUND_KEYS.values())}.", "ats_score")

        self.logger.info("Aggregating %d round score(s) for candidate %s", len(rounds), candidate_id)
        score = compute_cross_round_score(rounds, role, level, candidate_id or "unknown")
        decision = decide(score)

        response = self._base_response()
        response.update({
            "candidate_id": candidate_id,
            "hiring_fit_score": round(score.hiring_fit_percentage, 2),
            "decision": decision.outcome.value,
            "hold_kind": decision.hold_kind.value if decision.hold_kind else None,
            "confidence": decision.confidence.score,
            "provisional": score.provisional,
            "missing_rounds": list(score.missing_rounds),
            "human_review_required": score.human_review_required,
            "human_review_reasons": list(score.human_review_reasons),
            "human_confirmation_required": decision.outcome.value == "rejected",
            "automation_eligible": decision.automation_eligible,
            "automated_action": decision.automated_action,
            "reasons": list(decision.reasons),
            "warnings": warnings,
        })
        return response


if __name__ == "__main__":
    demo_scores = {
        "candidate_id": "C001", "role_type": "non_technical",
        "ats_score": 60, "screening_score": 70, "hr_interview_score": 85,
    }
    print(DecisionScoringService().run(demo_scores))
