"""
Day 64: builds the Word versions of the four Day 64 documents from the generated Markdown.

    python run_day64_internal_review.py      (writes the Markdown)
    python run_day64_docx.py                 (this script; needs pandoc, like run_day62_docx.py)

Output: docs/Zecpath_Day64_Internal_Review_Report.docx, Zecpath_Day64_Improvement_List.docx, Zecpath_Day64_Action_Plan.docx, Zecpath_Day64_Review_Session_Kit.docx
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import run_day62_docx as docx_builder  # noqa: E402

DOCS = ROOT / "docs"
DOCUMENTS = [
    (DOCS / "day64_internal_review_report.md", DOCS / "Zecpath_Day64_Internal_Review_Report.docx", "Zecpath Day 64 Internal Review Report"),
    (DOCS / "day64_improvement_list.md", DOCS / "Zecpath_Day64_Improvement_List.docx", "Zecpath Day 64 Improvement List"),
    (DOCS / "day64_action_plan.md", DOCS / "Zecpath_Day64_Action_Plan.docx", "Zecpath Day 64 Action Plan"),
    (DOCS / "day64_review_session_kit.md", DOCS / "Zecpath_Day64_Review_Session_Kit.docx", "Zecpath Day 64 Review Session Kit"),
]

if __name__ == "__main__":
    for src, out, title in DOCUMENTS:
        path = docx_builder.build(src, out, title, False, "Day 64")
        print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size / 1024:.0f} KB)")
