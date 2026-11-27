"""
Day 62: builds the Word versions of the three Day 62 documents from the generated Markdown.

    python run_day62_handbook.py      (writes the Markdown documents)
    python run_day62_docx.py          (this script: Markdown -> Zecpath_AI_Technical_Handbook.docx)

Needs `pandoc` on the PATH and python-docx. The Markdown is the source of truth; the Word file is a rendering of it, styled to match the
Day 60 and Day 61 deliverables (A4, Arial, light-blue table headers). Output: docs/Zecpath_AI_Technical_Handbook.docx, Zecpath_AI_System_Architecture.docx, Zecpath_AI_Developer_Onboarding_Guide.docx
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Emu, Pt, RGBColor

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
# (Markdown source, Word output, title used in the footer and the file properties, start each numbered section on a new page?)
DOCUMENTS = [
    (DOCS / "day62_zecpath_ai_technical_handbook.md", DOCS / "Zecpath_AI_Technical_Handbook.docx", "Zecpath AI Technical Handbook", True),
    (DOCS / "day62_system_architecture.md", DOCS / "Zecpath_AI_System_Architecture.docx", "Zecpath AI System Architecture", False),
    (DOCS / "day62_developer_onboarding_guide.md", DOCS / "Zecpath_AI_Developer_Onboarding_Guide.docx", "Zecpath AI Developer Onboarding Guide", False),
]

PAGE_W, PAGE_H, MARGIN = 11906, 16838, 1134             # A4 in twentieths of a point, same margins as the Day 61 deliverable
TEXT_W = PAGE_W - 2 * MARGIN                             # 9638
HEADER_FILL = "E6ECF5"
NAVY = RGBColor(0x1F, 0x3A, 0x5F)
GREY = RGBColor(0x55, 0x55, 0x55)
FONT = "Arial"


def _set_font(style, size, bold=None, color=None, name=FONT) -> None:
    style.font.name = name
    style.element.rPr.rFonts.set(qn("w:eastAsia"), name)
    style.font.size = Pt(size)
    if bold is not None:
        style.font.bold = bold
    if color is not None:
        style.font.color.rgb = color


def _spacing(style, before, after, keep_next=False) -> None:
    fmt = style.paragraph_format
    fmt.space_before, fmt.space_after, fmt.keep_with_next = Pt(before), Pt(after), keep_next


def _shade(element_pr, fill: str) -> None:
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    element_pr.append(shd)


class _Styles:
    """Style lookup by display name: pandoc's style names do not go through python-docx's own name translation."""

    def __init__(self, doc: Document) -> None:
        self._by_name = {style.name: style for style in doc.styles}

    def __contains__(self, name: str) -> bool:
        return name in self._by_name

    def __getitem__(self, name: str):
        return self._by_name[name]


def _style_styles(doc: Document) -> None:
    styles = _Styles(doc)
    for name in ("Normal", "Body Text", "First Paragraph", "Compact"):
        if name in styles:
            _set_font(styles[name], 10)
            _spacing(styles[name], 0, 5)
    _set_font(styles["Heading 1"], 22, True, RGBColor(0, 0, 0)); _spacing(styles["Heading 1"], 0, 4, True)
    _set_font(styles["Heading 2"], 14, True, NAVY); _spacing(styles["Heading 2"], 14, 6, True)
    _set_font(styles["Heading 3"], 11.5, True, NAVY); _spacing(styles["Heading 3"], 10, 4, True)
    if "Source Code" in styles:
        _set_font(styles["Source Code"], 8, name="Consolas")
        _spacing(styles["Source Code"], 0, 0)
        ppr = styles["Source Code"].element.get_or_add_pPr()
        _shade(ppr, "F2F2F2")
    if "Verbatim Char" in styles:
        _set_font(styles["Verbatim Char"], 9, name="Consolas")
    if "Image Caption" in styles:
        _set_font(styles["Image Caption"], 9, False, GREY)
        styles["Image Caption"].font.italic = True
    for name in ("Heading 1", "Heading 2", "Heading 3"):
        styles[name].font.italic = False


def _page_setup(doc: Document, title: str, day: str = "Day 62") -> None:
    for section in doc.sections:
        section.page_width, section.page_height = Emu(PAGE_W * 635), Emu(PAGE_H * 635)
        section.left_margin = section.right_margin = section.top_margin = section.bottom_margin = Emu(MARGIN * 635)
        section.header_distance = section.footer_distance = Emu(708 * 635)
        footer = section.footer
        para = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
        para.text = ""
        run = para.add_run(f"{title}  |  {day}  |  Page ")
        run.font.size, run.font.name, run.font.color.rgb = Pt(8), FONT, GREY
        for kind, text in (("begin", None), (None, "PAGE"), ("end", None)):
            r = para.add_run()
            r.font.size, r.font.name, r.font.color.rgb = Pt(8), FONT, GREY
            if kind:
                fld = OxmlElement("w:fldChar")
                fld.set(qn("w:fldCharType"), kind)
                r._r.append(fld)
            else:
                instr = OxmlElement("w:instrText")
                instr.set(qn("xml:space"), "preserve")
                instr.text = text
                r._r.append(instr)
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER


def _column_weights(table) -> list:
    """Relative column widths from the text each column holds (long text gets room; short ids stay narrow)."""
    count = len(table.columns)
    weights = []
    for c in range(count):
        lengths = [len(row.cells[c].text) for row in table.rows]
        longest = max(lengths) if lengths else 1
        mean = sum(lengths) / len(lengths)
        weights.append(max(6.0, min(0.6 * mean + 0.4 * min(longest, 90), 70.0)))
    return weights


def _style_table(table) -> None:
    tbl = table._tbl
    tbl_pr = tbl.tblPr
    for tag in ("w:tblStyle", "w:tblW", "w:tblLayout", "w:tblBorders", "w:tblCellMar", "w:tblLook"):
        for el in tbl_pr.findall(qn(tag)):
            tbl_pr.remove(el)
    width = OxmlElement("w:tblW"); width.set(qn("w:w"), str(TEXT_W)); width.set(qn("w:type"), "dxa"); tbl_pr.append(width)
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        b = OxmlElement(f"w:{side}")
        b.set(qn("w:val"), "single"); b.set(qn("w:sz"), "4"); b.set(qn("w:color"), "BFBFBF")
        borders.append(b)
    tbl_pr.append(borders)
    layout = OxmlElement("w:tblLayout"); layout.set(qn("w:type"), "fixed"); tbl_pr.append(layout)
    margins = OxmlElement("w:tblCellMar")
    for side, w in (("top", 40), ("left", 80), ("bottom", 40), ("right", 80)):
        m = OxmlElement(f"w:{side}"); m.set(qn("w:w"), str(w)); m.set(qn("w:type"), "dxa"); margins.append(m)
    tbl_pr.append(margins)

    weights = _column_weights(table)
    total = sum(weights)
    widths = [TEXT_W * w / total for w in weights]
    minimums = []
    for c in range(len(table.columns)):
        longest = max((len(tok) for row in table.rows for tok in row.cells[c].text.split()), default=4)
        minimums.append(min(longest, 38) * 95 + 180)                 # about 95 twips per character at 8.5 pt, plus the cell margins
    widths = [max(w, m) for w, m in zip(widths, minimums)]
    excess = sum(widths) - TEXT_W
    if excess > 0:                                                   # take the excess from columns that have room above their minimum
        slack = [w - m for w, m in zip(widths, minimums)]
        room = sum(slack) or 1
        widths = [w - excess * sl / room for w, sl in zip(widths, slack)]
    widths = [int(w) for w in widths]
    widths[-1] += TEXT_W - sum(widths)
    grid = tbl.find(qn("w:tblGrid"))
    if grid is not None:
        for col, w in zip(grid.findall(qn("w:gridCol")), widths):
            col.set(qn("w:w"), str(w))
    small = 8.5 if len(table.columns) >= 4 else 9
    for r_index, row in enumerate(table.rows):
        tr_pr = row._tr.get_or_add_trPr()
        tr_pr.append(OxmlElement("w:cantSplit"))
        if r_index == 0:
            tr_pr.append(OxmlElement("w:tblHeader"))
        for cell, w in zip(row.cells, widths):
            tc_pr = cell._tc.get_or_add_tcPr()
            for el in tc_pr.findall(qn("w:tcW")):
                tc_pr.remove(el)
            tcw = OxmlElement("w:tcW"); tcw.set(qn("w:w"), str(w)); tcw.set(qn("w:type"), "dxa"); tc_pr.insert(0, tcw)
            if r_index == 0:
                _shade(tc_pr, HEADER_FILL)
            for para in cell.paragraphs:
                para.paragraph_format.space_after = Pt(0)
                para.paragraph_format.space_before = Pt(0)
                for run in para.runs:
                    run.font.size = Pt(small)
                    if r_index == 0:
                        run.font.bold = True
                    if run.style is not None and run.style.name == "Verbatim Char":
                        run.font.size = Pt(small - 0.5)


def _drop_horizontal_rules(doc: Document) -> None:
    """The Markdown `---` separators become empty rule paragraphs; every section already starts on a new page with a ruled heading."""
    for para in list(doc.paragraphs):
        if "o:hr" in para._p.xml and not para.text.strip():
            para._p.getparent().remove(para._p)


def _style_body(doc: Document, page_breaks: bool) -> None:
    _drop_horizontal_rules(doc)
    first_h1_seen = False
    for index, para in enumerate(doc.paragraphs):
        name = para.style.name
        if name == "Heading 1" and not first_h1_seen:
            first_h1_seen = True
            nxt = doc.paragraphs[index + 1] if index + 1 < len(doc.paragraphs) else None
            if nxt is not None:
                for run in nxt.runs:
                    run.font.size, run.font.color.rgb = Pt(11), GREY
        if name == "Heading 2":
            text = para.text.strip()
            if page_breaks and (text[:1].isdigit() or text.startswith("Appendix")):
                para.paragraph_format.page_break_before = True
        if name == "Heading 2":
            ppr = para._p.get_or_add_pPr()
            bdr = OxmlElement("w:pBdr")
            bottom = OxmlElement("w:bottom")
            bottom.set(qn("w:val"), "single"); bottom.set(qn("w:sz"), "6"); bottom.set(qn("w:space"), "1"); bottom.set(qn("w:color"), "1F3A5F")
            bdr.append(bottom)
            ppr.append(bdr)
        if name in ("Source Code",):
            para.paragraph_format.left_indent = Emu(100 * 635)
    max_w = Emu(int(TEXT_W * 635 * 0.98))
    for shape in doc.inline_shapes:                        # the PNGs are 160 dpi, so filling the text width stays sharp
        ratio = max_w / shape.width
        shape.width, shape.height = max_w, Emu(int(shape.height * ratio))
    for para in doc.paragraphs:                            # keep a figure with its caption and centre both
        if para.style.name in ("Captioned Figure", "Image Caption"):
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            para.paragraph_format.keep_with_next = para.style.name == "Captioned Figure"


def _space_around_tables(doc: Document) -> None:
    """Breathing room after a table, and keep the sentence that introduces a table with it."""
    body = doc.element.body
    children = list(body.iterchildren())
    for i, el in enumerate(children):
        if el.tag == qn("w:tbl"):
            if i + 1 < len(children) and children[i + 1].tag == qn("w:p"):
                ppr = children[i + 1].get_or_add_pPr()
                spacing = ppr.find(qn("w:spacing"))
                if spacing is None:
                    spacing = OxmlElement("w:spacing"); ppr.append(spacing)
                spacing.set(qn("w:before"), "140")
            if i > 0 and children[i - 1].tag == qn("w:p"):
                ppr = children[i - 1].get_or_add_pPr()
                if ppr.find(qn("w:keepNext")) is None:
                    ppr.insert(0, OxmlElement("w:keepNext"))


def build(source: Path, output: Path, title: str, page_breaks: bool = True, day: str = "Day 62") -> Path:
    raw = output.with_suffix(".raw.docx")
    subprocess.run(["pandoc", str(source), "-f", "gfm", "-t", "docx", "-o", str(raw), f"--resource-path={source.parent}"], check=True)
    doc = Document(str(raw))
    _style_styles(doc)
    _page_setup(doc, title, day)
    _style_body(doc, page_breaks)
    _space_around_tables(doc)
    for table in doc.tables:
        _style_table(table)
    doc.core_properties.title = title
    doc.core_properties.author = "Zecpath AI team"
    doc.save(str(output))
    raw.unlink()
    return output


if __name__ == "__main__":
    for src, out, ttl, breaks in DOCUMENTS:
        path = build(src, out, ttl, breaks)
        print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size / 1024:.0f} KB)")
    sys.exit(0)
