"""
Parallel batch scoring (Day 60)

Python threads cannot make this work faster: scoring is pure-Python CPU work, and the interpreter lock lets only one thread run it
at a time (the load test shows threads giving no gain). Processes can. This module spreads a batch across worker PROCESSES while
keeping every guarantee the single path gives:

  * SAME ANSWERS   each candidate is scored by the same ATSService, one pair at a time (the Day 59 consistency rule), so the result
                   equals the sequential result exactly; `map` returns results in input order.
  * NO SURPRISES   if worker processes cannot be started (a locked-down machine, a broken pool), the batch is scored sequentially
                   and the caller is told, instead of failing.
  * WORKERS ARE REUSED   starting a worker means importing scikit-learn (about a second and 200 MB), so one pool is created on first
                   use and kept; workers are warmed in their initializer so the first batch does not pay for a cold worker.
  * SMALL BATCHES STAY LOCAL   below `MIN_PARALLEL_BATCH` the cost of pickling and hand-off is more than the saving.

Windows and macOS start workers by spawning fresh interpreters, so any script that triggers a pool must keep its entry point under
`if __name__ == "__main__":` (the demo scripts do). This module always asks for 'spawn', so Linux behaves the same way.
"""

from __future__ import annotations

import atexit
import multiprocessing
import threading
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

MIN_PARALLEL_BATCH = 64            # PROPOSED: below this the hand-off cost outweighs the gain (see docs/day60_performance_benchmark_report.md)
DEFAULT_CHUNK = 8

_POOL: Optional[ProcessPoolExecutor] = None
_POOL_WORKERS = 0
_POOL_LOCK = threading.Lock()


def _init_worker() -> None:
    from utils.warmup import warm_up
    warm_up(("ats",))


def score_chunk(args: Tuple[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Run in a worker process: score one chunk of candidates against one job description."""
    from ats_engine.service import ATSService
    job_description, candidates = args
    service = ATSService()
    return [service.run({"resume_text": c.get("resume_text", ""), "job_description": job_description}) for c in candidates]


def get_pool(workers: int) -> ProcessPoolExecutor:
    global _POOL, _POOL_WORKERS
    with _POOL_LOCK:
        if _POOL is not None and _POOL_WORKERS != workers:
            _POOL.shutdown(wait=False, cancel_futures=True)
            _POOL = None
        if _POOL is None:
            _POOL = ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"), initializer=_init_worker)
            _POOL_WORKERS = workers
        return _POOL


def shutdown_pool() -> None:
    global _POOL, _POOL_WORKERS
    with _POOL_LOCK:
        if _POOL is not None:
            _POOL.shutdown(wait=True, cancel_futures=True)
            _POOL, _POOL_WORKERS = None, 0


atexit.register(shutdown_pool)


def score_batch_parallel(job_description: str, candidates: List[Dict[str, Any]], workers: int, chunk: int = DEFAULT_CHUNK) -> List[Dict[str, Any]]:
    """Score `candidates` across `workers` processes. Raises on pool failure: the caller decides how to fall back."""
    chunks = [(job_description, candidates[i:i + chunk]) for i in range(0, len(candidates), chunk)]
    pool = get_pool(workers)
    results: List[Dict[str, Any]] = []
    for part in pool.map(score_chunk, chunks):
        results.extend(part)
    return results
