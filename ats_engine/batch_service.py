"""
ATS Batch Scoring Service (Day 59)

The asynchronous counterpart of `ATSService`: one job description, many resumes, one result per candidate. It is what a queue
worker runs for the "score everyone who applied" job (the Day 16 `/scoring-jobs` idea, now expressed through the Day 57 contract).

THE DESIGN CHOICE, WITH ITS EVIDENCE. Day 57 noted that `ATSService` accepts a shared `matcher` for batch work, and a shared
vocabulary is faster. Day 59 measured what it costs (16 sample resumes against one job description, `run_day59_integration_demo.py`):

  * shared corpus: the same resume scores up to 0.3 points differently than when scored alone, and one of the 16 candidates
    changed ZONE (shortlist when scored alone, review inside the batch);
  * per-pair scoring: about 1.7x slower in total, which is milliseconds at this size.

A candidate's zone must not depend on who else applied that day, so this service scores every candidate EXACTLY as `ATSService`
would alone (a matcher fitted on that resume and the job description only). A batch result therefore equals the single-request
result for the same pair, and a retry or a re-run of a job gives the same answer. If a shared corpus is ever wanted for speed, it
needs its own decision and a fairness check; it is not the default.

PARTIAL FAILURE. One bad resume does not fail the batch: its entry carries the ordinary error envelope and the others are scored.
`succeeded` and `failed` say how many of each. The job as a whole fails only when the request itself is unusable.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ats_engine.service import ATSService
from utils.base_service import BaseAIService, MAX_ITEMS, ServiceInputError


class ATSBatchService(BaseAIService):
    service_name = "ats_batch_service"

    def __init__(self) -> None:
        super().__init__()
        self._single = ATSService()

    def process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        job_description = self._get_text(payload, "job_description")
        candidates = self._get_list(payload, "candidates", required=True)
        if not candidates:
            raise ServiceInputError("invalid_input", "'candidates' must hold at least one candidate.", "candidates")

        seen = set()
        for i, c in enumerate(candidates):
            if not isinstance(c, dict):
                raise ServiceInputError("invalid_input", f"candidates[{i}] must be an object.", f"candidates[{i}]")
            cid = c.get("candidate_id")
            if not isinstance(cid, str) or not cid.strip():
                raise ServiceInputError("missing_field", f"candidates[{i}].candidate_id is required text.", f"candidates[{i}].candidate_id")
            if cid in seen:
                raise ServiceInputError("invalid_input", f"candidate_id {cid!r} appears twice in one batch.", f"candidates[{i}].candidate_id")
            seen.add(cid)

        self.logger.info("Scoring a batch of %d candidates against one job description (%d chars)", len(candidates), len(job_description))
        results: List[Dict[str, Any]] = []
        failed = 0
        for c in candidates:
            outcome = self._single.run({"resume_text": c.get("resume_text", ""), "job_description": job_description})
            if outcome.get("status") != "success":
                failed += 1
            results.append({"candidate_id": c["candidate_id"], "outcome": outcome})

        response = self._base_response()
        response.update({"scoring_basis": "per_pair", "total": len(candidates), "succeeded": len(candidates) - failed,
                         "failed": failed, "results": results, "warnings": []})
        return response


__all__ = ["ATSBatchService", "MAX_ITEMS"]
