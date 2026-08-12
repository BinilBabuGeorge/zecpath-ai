"""
Runs the extraction engine across every sample resume (PDF + DOCX)
and saves cleaned text + a JSON summary for each into data/extracted/.
"""

import json
import logging
from pathlib import Path

from parsers.resume_extractor import extract_resume

RAW_DIR = Path("data/raw_resumes")
OUT_DIR = Path("data/extracted")
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
logger = logging.getLogger("batch_extract")


def run():
    files = sorted(RAW_DIR.glob("**/*.pdf")) + sorted(RAW_DIR.glob("**/*.docx"))
    logger.info("Found %d resume files to process", len(files))

    total_warnings = 0
    for file_path in files:
        result = extract_resume(str(file_path))
        out_stem = f"{file_path.parent.name}_{file_path.stem}"

        # Save cleaned text
        (OUT_DIR / f"{out_stem}.txt").write_text(result.cleaned_text, encoding="utf-8")

        # Save structured summary
        summary = {
            "file_path": result.file_path,
            "file_type": result.file_type,
            "line_count": result.line_count,
            "detected_sections": result.detected_sections,
            "warnings": result.warnings,
        }
        (OUT_DIR / f"{out_stem}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

        if result.warnings:
            total_warnings += len(result.warnings)
            for w in result.warnings:
                logger.warning("%s -> %s", file_path.name, w)
        else:
            logger.info("%s -> OK, %d sections detected", file_path.name, len(result.detected_sections))

    logger.info("Done. %d files processed, %d warnings total.", len(files), total_warnings)


if __name__ == "__main__":
    run()
