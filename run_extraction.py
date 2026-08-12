"""
Runs skill_extractor across every sample resume and saves the structured
skill output (name, group, category, confidence, method) as JSON, plus a
summary log.
"""

import json
import logging
from dataclasses import asdict
from pathlib import Path

from parsers.skill_extractor import extract_skills

SAMPLE_DIR = Path("data/samples")
OUT_DIR = Path("data/extracted_skills")
LOG_DIR = Path("logs")

OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_DIR / "extraction_run.log", mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("skill_batch")


def run():
    files = sorted(SAMPLE_DIR.glob("*.txt"))
    logger.info("Found %d resumes to extract skills from", len(files))

    for file_path in files:
        text = file_path.read_text(encoding="utf-8")
        skills = extract_skills(text)

        by_group = {}
        for s in skills:
            by_group.setdefault(s.group, 0)
            by_group[s.group] += 1

        output = [asdict(s) for s in skills]
        out_path = OUT_DIR / f"{file_path.stem}_skills.json"
        out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")

        method_counts = {}
        for s in skills:
            method_counts[s.method] = method_counts.get(s.method, 0) + 1

        logger.info(
            "%s -> %d skills | groups: %s | methods: %s",
            file_path.name, len(skills), by_group, method_counts,
        )

    logger.info("Done. Output written to %s/", OUT_DIR)


if __name__ == "__main__":
    run()
