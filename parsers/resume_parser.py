"""
Resume parsing utilities — shared by ats_engine and any other service
that needs to turn a raw resume file into structured text/fields.

Kept separate from ats_engine/ so screening_ai or interview_ai can also
reuse parsing logic without importing the scoring engine.
"""

from typing import Dict
from utils.logger import get_logger

logger = get_logger(__name__)


def extract_text(file_path: str) -> str:
    """
    Extract raw text from a resume file (PDF/DOC/DOCX).
    TODO: wire up real extraction (e.g. pdfplumber, python-docx).
    """
    logger.info("Extracting text from %s", file_path)
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def extract_fields(resume_text: str) -> Dict[str, str]:
    """
    Pull structured fields (skills, experience, education) out of resume text.
    TODO: replace with a real NLP/NER pipeline.
    """
    return {
        "skills": "",
        "experience_years": "",
        "education": "",
    }
