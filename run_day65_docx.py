"""Day 65: builds docs/Zecpath_Day65_Deliverables.docx from docs/day65_feature_enhancement_report.md (needs pandoc, like run_day62_docx.py)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import run_day62_docx as docx_builder  # noqa: E402

if __name__ == "__main__":
    DOCS = ROOT / "docs"
    path = docx_builder.build(DOCS / "day65_feature_enhancement_report.md", DOCS / "Zecpath_Day65_Deliverables.docx", "Zecpath Day 65 Feature Enhancement Report", False, "Day 65")
    print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size / 1024:.0f} KB)")
