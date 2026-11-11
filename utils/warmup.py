"""
Service warm-up (Day 60)

THE PROBLEM, MEASURED. The first scoring request after a process starts took about 1,070 ms; the next took about 5 ms. Almost all of
the first request is one-time work done lazily inside it: importing scikit-learn and SciPy, compiling the big skill and synonym
patterns, building dictionaries. That cost is not removed by warming up, it is MOVED: from the first candidate's request (and so
from the p99 of every freshly started or autoscaled worker) to the worker's start-up, where nobody is waiting on it.

`warm_up()` runs a tiny real request through each service the worker will serve. A worker should call it before it reports itself
ready to the load balancer, so no real request ever lands on a cold worker (see docs/day60_scalability_strategy.md).

Each component is warmed separately on purpose: a worker that only scores decisions should not pay the memory for scikit-learn
(the benchmark measures the difference). Warm-up leaves the caches empty, so it cannot influence any later result.
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
from typing import Dict, Iterable, Optional

from utils.perf import clear_all_caches

COMPONENTS = ("ats", "parsing", "screening", "interview", "decision")

_TINY_RESUME = "Skills: React, Node.js, MongoDB\nExperience:\nDeveloper, Acme (Jan 2021 - Dec 2023)\nEducation:\nB.Tech in Computer Science, XYZ, 2020"
_TINY_JD = "Job Title: MERN Developer\nRequired Skills: React, Node.js, MongoDB\nExperience: 2 years"


def _warm_ats() -> None:
    from ats_engine.service import ATSService
    ATSService().run({"resume_text": _TINY_RESUME, "job_description": _TINY_JD})


def _warm_parsing() -> None:
    import docx                                   # noqa: F401  (imported so the first real DOCX does not pay for it)
    import pdfplumber                             # noqa: F401
    from ats_engine.resume_parsing_service import ResumeParsingService
    handle, path = tempfile.mkstemp(suffix=".docx")
    os.close(handle)
    try:
        document = docx.Document()
        document.add_paragraph("Skills: Python, SQL")
        document.add_paragraph("Experience:")
        document.add_paragraph("Analyst, Acme (Jan 2021 - Dec 2023)")
        document.save(path)
        ResumeParsingService(resolver=lambda ref: path).run({"candidate_id": "warmup", "file_ref": "w.docx", "file_type": "docx", "as_of_date": "2026-01-01"})
    finally:
        os.remove(path)


def _warm_screening() -> None:
    from screening_ai.service import ScreeningService
    ScreeningService().run({"candidate_id": "warmup", "turns": [{"text": "I have three years of experience with React.", "confidence": 0.9}]})


def _warm_interview() -> None:
    from interview_ai.service import InterviewIntelligenceService
    svc = InterviewIntelligenceService()
    svc.run({"interview_type": "hr", "answers": ["I led a small team and we shipped on time."]})
    svc.run({"interview_type": "technical", "domain": "mern", "experience_years": 2, "answers": ["React uses a virtual DOM."]})


def _warm_decision() -> None:
    from scoring.service import DecisionScoringService
    DecisionScoringService().run({"candidate_id": "warmup", "ats_score": 60, "hr_interview_score": 70})


_WARMERS = {"ats": _warm_ats, "parsing": _warm_parsing, "screening": _warm_screening, "interview": _warm_interview, "decision": _warm_decision}


def warm_up(components: Optional[Iterable[str]] = None) -> Dict[str, float]:
    """Warm the named components (default: all). Returns milliseconds per component and in total. Safe to call more than once."""
    names = tuple(components) if components is not None else COMPONENTS
    unknown = [n for n in names if n not in _WARMERS]
    if unknown:
        raise ValueError(f"unknown component(s): {unknown}; choose from {COMPONENTS}")
    timings: Dict[str, float] = {}
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)                 # a warm-up request is not a real request: keep it out of the logs
    try:
        start = time.perf_counter()
        for name in names:
            t = time.perf_counter()
            _WARMERS[name]()
            timings[name] = round((time.perf_counter() - t) * 1000, 1)
        timings["total"] = round((time.perf_counter() - start) * 1000, 1)
    finally:
        logging.disable(previous)
    clear_all_caches()
    return timings
