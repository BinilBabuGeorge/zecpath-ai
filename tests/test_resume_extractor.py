from pathlib import Path

import pytest

from parsers.resume_extractor import (
    clean_text,
    detect_sections,
    extract_resume,
    extract_raw_text,
)

PDF_DIR = Path("data/raw_resumes/pdf")
DOCX_DIR = Path("data/raw_resumes/docx")

ALL_PDFS = sorted(PDF_DIR.glob("*.pdf"))
ALL_DOCXS = sorted(DOCX_DIR.glob("*.docx"))


# ---------------------------------------------------------------------------
# Cleaning / normalization unit tests
# ---------------------------------------------------------------------------

def test_clean_text_normalizes_curly_quotes_and_dashes():
    raw = "Company\u2019s \u201cbest\u201d engineer \u2013 3 years"
    cleaned = clean_text(raw)
    assert "\u2019" not in cleaned
    assert "\u201c" not in cleaned
    assert "-" in cleaned


def test_clean_text_normalizes_bullet_characters():
    raw = "\u2022 First point\n\u25aa Second point\n* Third point"
    cleaned = clean_text(raw)
    for line in cleaned.split("\n"):
        assert line.startswith("- ")


def test_clean_text_collapses_excess_blank_lines():
    raw = "Line one\n\n\n\n\nLine two"
    cleaned = clean_text(raw)
    assert "\n\n\n" not in cleaned


def test_clean_text_standardizes_section_headings_case():
    raw = "SKILLS\nPython, SQL"
    cleaned = clean_text(raw)
    assert "Skills:" in cleaned


def test_detect_sections_finds_all_present_headings():
    text = "Summary:\nHi\nSkills:\nPython\nExperience:\nJob\nEducation:\nDegree\nCertifications:\nCert"
    sections = detect_sections(text)
    assert sections == ["Summary", "Skills", "Experience", "Education", "Certifications"]


def test_detect_sections_returns_empty_for_no_headings():
    assert detect_sections("Just some random text with no headings") == []


# ---------------------------------------------------------------------------
# Raw extraction tests (format-specific readers)
# ---------------------------------------------------------------------------

def test_extract_raw_text_rejects_unsupported_extension(tmp_path):
    bad_file = tmp_path / "resume.txt"
    bad_file.write_text("hello")
    with pytest.raises(ValueError):
        extract_raw_text(str(bad_file))


@pytest.mark.parametrize("pdf_path", ALL_PDFS, ids=[p.name for p in ALL_PDFS])
def test_pdf_extraction_produces_nonempty_text(pdf_path):
    text = extract_raw_text(str(pdf_path))
    assert len(text.strip()) > 0


@pytest.mark.parametrize("docx_path", ALL_DOCXS, ids=[p.name for p in ALL_DOCXS])
def test_docx_extraction_produces_nonempty_text(docx_path):
    text = extract_raw_text(str(docx_path))
    assert len(text.strip()) > 0


# ---------------------------------------------------------------------------
# End-to-end extract_resume() tests across every sample resume
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("file_path", ALL_PDFS + ALL_DOCXS, ids=[p.name for p in ALL_PDFS + ALL_DOCXS])
def test_extract_resume_detects_all_five_sections(file_path):
    result = extract_resume(str(file_path))
    expected = {"Summary", "Skills", "Experience", "Education", "Certifications"}
    assert expected.issubset(set(result.detected_sections))


@pytest.mark.parametrize("file_path", ALL_PDFS + ALL_DOCXS, ids=[p.name for p in ALL_PDFS + ALL_DOCXS])
def test_extract_resume_has_no_warnings_on_clean_samples(file_path):
    result = extract_resume(str(file_path))
    assert result.warnings == []


def test_extract_resume_pdf_and_docx_versions_agree_on_sections():
    """The same underlying resume, read as PDF vs DOCX, should detect the same sections."""
    pdf_result = extract_resume(str(PDF_DIR / "resume_01_mern_developer.pdf"))
    docx_result = extract_resume(str(DOCX_DIR / "resume_01_mern_developer.docx"))
    assert set(pdf_result.detected_sections) == set(docx_result.detected_sections)
