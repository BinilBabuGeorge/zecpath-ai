"""
Runs jd_parser across every sample JD, validates each result against
schemas/job_description_schema.json (Day 4), and saves structured
JobProfile JSON into data/jds_structured/.
"""

import json
import logging
from pathlib import Path

from jsonschema import Draft202012Validator

from parsers.jd_parser import parse_jd

RAW_DIR = Path("data/jds_raw")
OUT_DIR = Path("data/jds_structured")
SCHEMA_DIR = Path("schemas")
LOG_DIR = Path("logs")

OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_DIR / "jd_parsing_run.log", mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("jd_batch")


def load_schema_for_loose_validation() -> dict:
    """Load job_description_schema.json but drop $ref to resume_schema.json's
    SkillObject (not resolvable offline here) and inline an equivalent
    definition instead, so we can still validate structurally."""
    schema = json.loads((SCHEMA_DIR / "job_description_schema.json").read_text())
    skill_object = {
        "type": "object",
        "required": ["name"],
        "properties": {
            "name": {"type": "string"},
            "category": {"type": "string"},
            "proficiency": {"type": "string"},
        },
    }
    schema["properties"]["requiredSkills"]["items"] = skill_object
    schema["properties"]["niceToHaveSkills"]["items"] = skill_object
    return schema


def run():
    schema = load_schema_for_loose_validation()
    validator = Draft202012Validator(schema)

    files = sorted(RAW_DIR.glob("*.txt"))
    logger.info("Found %d job descriptions to parse", len(files))

    total_errors = 0
    for idx, file_path in enumerate(files, start=1):
        raw_text = file_path.read_text(encoding="utf-8")
        job_id = f"JOB-{idx:04d}"
        profile = parse_jd(raw_text, job_id=job_id)

        errors = list(validator.iter_errors(profile))
        out_path = OUT_DIR / f"{file_path.stem}_structured.json"
        out_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")

        if errors:
            total_errors += len(errors)
            for e in errors:
                logger.warning("%s -> SCHEMA ISSUE: %s (at %s)", file_path.name, e.message, list(e.path))
        else:
            logger.info(
                "%s -> OK | role: '%s' (from '%s') | %d required skills | %d nice-to-have",
                file_path.name, profile["jobTitle"], profile["jobTitleOriginal"],
                len(profile["requiredSkills"]), len(profile["niceToHaveSkills"]),
            )

    logger.info("Done. %d JDs parsed, %d schema validation issues total.", len(files), total_errors)


if __name__ == "__main__":
    run()
