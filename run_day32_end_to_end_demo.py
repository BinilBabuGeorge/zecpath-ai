"""
Day 32 demo -- THE actual end-to-end run this whole project has been
building toward: three simulated candidates (strong, mixed, weak) run
through the complete assembled pipeline (Days 22-31), each producing a
real, final ScreeningReport. This IS the "Live demo output" and forms
the evidence base for the "Screening AI evaluation report" deliverable
(docs/day32_screening_ai_evaluation_report.md).

All three candidates' turns are hand-written, clearly-labeled examples
standing in for real screening calls, not real candidate speech --
same honesty stance as every prior demo script in this project. The
"mixed" candidate deliberately includes two answers that trigger
already-documented, known engine gaps (a non-B.Tech degree abbreviation
Day 25's keyword list doesn't recognize, and a bare place name Day 30
already found and left honestly unfixed) -- this is real system
behavior on realistic input, not a staged failure.
"""

import json
import logging
from pathlib import Path

from parsers.speech_to_text import RawSTTResult
from parsers.screening_pipeline import run_screening_call

OUT_DIR = Path("data/results")
REPORTS_DIR = Path("data/reports")
LOG_DIR = Path("logs")
OUT_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "day32_end_to_end_demo.log", mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("day32")

CATEGORIES = ["introduction", "education", "experience", "skills", "location", "salary", "notice_period"]

CANDIDATES = {
    "strong": {
        "candidate_id": "CAND-STRONG-01", "job_role": "MERN Stack Developer",
        "turns": [
            RawSTTResult(text="Hi, I'm a developer based in Pune with three years of experience.", confidence=0.9),
            RawSTTResult(text="I completed my B.Tech in Computer Science from a college in Pune.", confidence=0.9),
            RawSTTResult(text="I have three years of experience with React and Node.js.", confidence=0.9),
            RawSTTResult(text="I have used Docker and Kubernetes quite a bit.", confidence=0.9),
            RawSTTResult(text="I'm currently based in Bengaluru and open to relocating.", confidence=0.9),
            RawSTTResult(text="My current CTC is around eight lakhs and I am expecting more.", confidence=0.9),
            RawSTTResult(text="My notice period is immediate, I can join within a few days.", confidence=0.9),
        ],
    },
    "mixed": {
        "candidate_id": "CAND-MIXED-01", "job_role": "QA Tester",
        "turns": [
            RawSTTResult(text="Hi, I am a tester with about one year of experience in manual testing.", confidence=0.9),
            RawSTTResult(text="B.Sc IT", confidence=0.9),  # KNOWN GAP: Day 25's education keywords only recognize "B.Tech" -- vague, triggers fallback
            RawSTTResult(text="B.Sc IT", confidence=0.9),  # candidate repeats the same short answer to the fallback -- still vague -> polite-skip, advances
            RawSTTResult(text="About one year of experience, mostly manual testing work.", confidence=0.9),
            RawSTTResult(text="I have used Selenium and Postman for automation and API testing.", confidence=0.9),
            RawSTTResult(text="Chennai", confidence=0.9),  # KNOWN GAP: bare place name, documented since Day 30 -- vague, triggers fallback
            RawSTTResult(text="Chennai", confidence=0.9),  # candidate repeats the same short answer -- still vague -> polite-skip, advances
            RawSTTResult(text="Around four lakhs, negotiable depending on the role.", confidence=0.9),
            RawSTTResult(text="My notice period is about one month from acceptance.", confidence=0.9),
        ],
    },
    "weak": {
        "candidate_id": "CAND-WEAK-01", "job_role": "Sales Executive",
        "turns": [
            RawSTTResult(text="I guess I have done some work before.", confidence=0.9),
            RawSTTResult(text="not sure", confidence=0.9),
            RawSTTResult(text="My current CTC is around six lakhs.", confidence=0.9),  # off-topic for "experience"
            RawSTTResult(text="maybe a few things", confidence=0.9),
            RawSTTResult(text="", confidence=0.0, is_silent=True),
            RawSTTResult(text="I dont know, whatever is standard", confidence=0.9),
            RawSTTResult(text="depends", confidence=0.9),
        ],
    },
}


def run_one(name: str, spec: dict) -> dict:
    logger.info("=" * 90)
    logger.info(f"CANDIDATE: {name.upper()} ({spec['candidate_id']}, {spec['job_role']})")
    logger.info("=" * 90)

    result = run_screening_call(spec["turns"], categories=CATEGORIES, candidate_id=spec["candidate_id"], job_role=spec["job_role"])

    logger.info(f"Total Screening Score: {result.report.total_score}")
    logger.info(f"Communication Strength Score: {result.report.communication_strength_score}")
    logger.info(f"Categories answered: {result.categories_answered}")
    logger.info(f"Categories missing: {result.categories_missing}")
    logger.info("Strengths:")
    for s in result.report.strengths:
        logger.info(f"  - {s}")
    logger.info("Risks:")
    for r in result.report.risks:
        logger.info(f"  - {r}")
    logger.info("Missing Data:")
    for m in result.report.missing_data:
        logger.info(f"  - {m}")

    md_path = REPORTS_DIR / f"day32_sample_report_{spec['candidate_id']}.md"
    json_path = REPORTS_DIR / f"day32_sample_report_{spec['candidate_id']}.json"
    md_path.write_text(result.report.to_markdown(), encoding="utf-8")
    json_path.write_text(result.report.to_json(), encoding="utf-8")
    logger.info(f"Report written to {md_path} and {json_path}")

    return {
        "candidate_id": spec["candidate_id"], "job_role": spec["job_role"],
        "total_score": result.report.total_score,
        "communication_strength_score": result.report.communication_strength_score,
        "categories_answered": result.categories_answered,
        "categories_missing": result.categories_missing,
        "strengths_count": len(result.report.strengths),
        "risks_count": len(result.report.risks),
    }


def main():
    logger.info("#" * 90)
    logger.info("DAY 32 -- Screening System Finalization: end-to-end demo across 3 candidates")
    logger.info("#" * 90)

    summary = {name: run_one(name, spec) for name, spec in CANDIDATES.items()}

    logger.info("=" * 90)
    logger.info("COMPARISON SUMMARY")
    logger.info("=" * 90)
    for name, s in summary.items():
        logger.info(f"{name:8s}: total_score={s['total_score']:6.1f}  communication={s['communication_strength_score']:6.1f}  "
                     f"answered={len(s['categories_answered'])}/7  strengths={s['strengths_count']}  risks={s['risks_count']}")

    out_path = OUT_DIR / "day32_evaluation_summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logger.info(f"Summary written to {out_path}")


if __name__ == "__main__":
    main()
