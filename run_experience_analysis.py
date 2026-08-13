"""
Runs experience_parser + experience_relevance across every sample resume,
saves structured output (parsed entries + total experience + relevance
score against a defined target role) as JSON, plus a summary log.
"""

import json
import logging
from dataclasses import asdict
from pathlib import Path

from parsers.experience_parser import parse_experience, compute_total_experience
from parsers.experience_relevance import score_experience_relevance

SAMPLE_DIR = Path("data/samples")
OUT_DIR = Path("data/structured_experience")
LOG_DIR = Path("logs")

OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_DIR / "experience_run.log", mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("experience_batch")

# One target job definition per sample, chosen to fit that resume's domain.
TARGETS = {
    "resume_gap_and_overlap": ("Product Manager", ["SQL", "Prototyping"]),
    "resume_skills_in_bullets": ("MERN Stack Developer", ["React.js", "Node.js", "MongoDB", "Docker", "AWS"]),
    "resume_single_role": ("UX Researcher", ["User Research", "Prototyping"]),
}


def entry_to_dict(entry):
    d = {
        "title": entry.title,
        "company": entry.company,
        "start": f"{entry.start_year}-{entry.start_month:02d}",
        "end": "Present" if entry.is_current else f"{entry.end_year}-{entry.end_month:02d}",
        "duration_months": entry.duration_months,
        "description": entry.description,
    }
    return d


def run():
    files = sorted(SAMPLE_DIR.glob("*.txt"))
    logger.info("Found %d resumes to process", len(files))

    for file_path in files:
        text = file_path.read_text(encoding="utf-8")
        entries = parse_experience(text)
        summary = compute_total_experience(entries)

        target_title, required_skills = TARGETS.get(file_path.stem, ("Unknown Role", []))
        relevance = score_experience_relevance(entries, target_title, required_skills)

        output = {
            "entries": [entry_to_dict(e) for e in entries],
            "total_experience": {
                "years": summary.total_years,
                "months": summary.total_months,
                "gap_count": len(summary.gaps),
                "overlap_count": len(summary.overlaps),
            },
            "relevance": {
                "target_title": relevance.target_title,
                "overall_score": relevance.overall_score,
                "role_breakdown": [asdict(r) for r in relevance.role_breakdown],
            },
        }

        out_path = OUT_DIR / f"{file_path.stem}_structured.json"
        out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")

        logger.info(
            "%s -> %d roles | %.1f yrs total | %d gap(s), %d overlap(s) | relevance vs '%s': %.1f/100",
            file_path.name, len(entries), summary.total_years,
            len(summary.gaps), len(summary.overlaps),
            target_title, relevance.overall_score,
        )

    logger.info("Done. Output written to %s/", OUT_DIR)


if __name__ == "__main__":
    run()
