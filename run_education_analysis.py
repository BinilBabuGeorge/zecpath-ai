"""
Runs education_parser + education_relevance across every sample resume,
saves structured output as JSON, plus a summary log.
"""

import json
import logging
from dataclasses import asdict
from pathlib import Path

from parsers.education_parser import parse_education, parse_certifications
from parsers.education_relevance import score_education_relevance

SAMPLE_DIR = Path("data/samples")
OUT_DIR = Path("data/structured_academic")
LOG_DIR = Path("logs")

OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_DIR / "education_run.log", mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("education_batch")

# One target profile per sample, matched to that resume's intended role.
TARGETS = {
    "resume_diploma_no_certs": ("Bachelor's", ["Computer Science"], ["Software Development"]),
    "resume_dual_degree": ("Bachelor's", ["Data Science", "Statistics"], ["Data/Analytics"]),
    "resume_01_mern_developer": ("Bachelor's", ["Computer Science"], ["Software Development"]),
    "resume_09_accountant": ("Bachelor's", ["Commerce", "Accounting"], ["Finance/Accounting"]),
}


def run():
    files = sorted(SAMPLE_DIR.glob("*.txt"))
    logger.info("Found %d resumes to process", len(files))

    for file_path in files:
        text = file_path.read_text(encoding="utf-8")
        education = parse_education(text)
        certifications = parse_certifications(text)

        target_level, target_fields, target_cats = TARGETS.get(file_path.stem, ("Bachelor's", [], []))
        relevance = score_education_relevance(education, certifications, target_level, target_fields, target_cats)

        output = {
            "education": [
                {
                    "raw_degree": e.raw_degree, "degree": e.degree, "level": e.level,
                    "field_of_study": e.field_of_study, "institution": e.institution, "year": e.year,
                }
                for e in education
            ],
            "certifications": [
                {"name": c.name, "issuer": c.issuer, "year": c.year, "category": c.category}
                for c in certifications
            ],
            "relevance": asdict(relevance),
        }

        out_path = OUT_DIR / f"{file_path.stem}_structured.json"
        out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")

        logger.info(
            "%s -> %d education entries, %d certifications | relevance: %.1f/100 (degree=%.1f, field=%.1f, cert_bonus=+%.1f)",
            file_path.name, len(education), len(certifications),
            relevance.overall_score, relevance.degree_level_score,
            relevance.field_match_score, relevance.certification_bonus,
        )

    logger.info("Done. Output written to %s/", OUT_DIR)


if __name__ == "__main__":
    run()
