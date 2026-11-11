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

import os
from typing import Any, Dict, List, Optional

from ats_engine.service import ATSService
from utils.base_service import BaseAIService, MAX_ITEMS, ServiceInputError


class ATSBatchService(BaseAIService):
    service_name = "ats_batch_service"

    def __init__(self, workers: Optional[int] = None, min_parallel_batch: Optional[int] = None) -> None:
        """`workers` > 1 spreads large batches over worker processes (see ats_engine/parallel.py); the default is 1, or the number in
        the environment variable ZECPATH_BATCH_WORKERS. Results are identical either way."""
        super().__init__()
        self._single = ATSService()
        self._workers = workers if workers is not None else int(os.environ.get("ZECPATH_BATCH_WORKERS", "1") or 1)
        self._min_parallel = min_parallel_batch

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
        warnings: List[str] = []
        outcomes = self._score_all(job_description, candidates, warnings)
        results: List[Dict[str, Any]] = []
        failed = 0
        for c, outcome in zip(candidates, outcomes):
            if outcome.get("status") != "success":
                failed += 1
            results.append({"candidate_id": c["candidate_id"], "outcome": outcome})

        response = self._base_response()
        response.update({"scoring_basis": "per_pair", "total": len(candidates), "succeeded": len(candidates) - failed,
                         "failed": failed, "results": results, "warnings": warnings})
        return response

    def _score_all(self, job_description: str, candidates: List[Dict[str, Any]], warnings: List[str]) -> List[Dict[str, Any]]:
        from ats_engine import parallel
        threshold = self._min_parallel if self._min_parallel is not None else parallel.MIN_PARALLEL_BATCH
        if self._workers > 1 and len(candidates) >= threshold:
            try:
                return parallel.score_batch_parallel(job_description, candidates, self._workers)
            except Exception as exc:                      # a pool that cannot start must not fail the batch
                self.logger.warning("Parallel scoring unavailable (%s); scoring sequentially", type(exc).__name__)
                warnings.append("Parallel scoring was not available, so the batch was scored one candidate at a time; the results are the same.")
        return [self._single.run({"resume_text": c.get("resume_text", ""), "job_description": job_description}) for c in candidates]


__all__ = ["ATSBatchService", "MAX_ITEMS"]
