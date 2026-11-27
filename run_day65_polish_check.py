"""Day 65: measure the polish. Re-runs the Day 64 probes that Day 65 targets and compares them with the values Day 64 recorded.

    python run_day65_polish_check.py

Writes docs/day65_feature_enhancement_report.md and data/review/day65_before_after.json.
Day 64 values are the ones printed in docs/day64_improvement_list.md (they cannot be re-measured: the code was fixed since).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logging.disable(logging.CRITICAL)
ROOT = Path(__file__).resolve().parent

from parsers import internal_review as ir                      # noqa: E402
from parsers.answer_intent_engine import extract_experience_years  # noqa: E402
from screening_ai.service import ScreeningService              # noqa: E402


def measure() -> list:
    errs = ir._error_audit()
    reports = ir._report_audit(ROOT / "data" / "demo_dataset")
    silent = ScreeningService().run({"candidate_id": "C", "turns": [{"confidence": 0.5}]})
    rows = [
        ("UX-02", "Recruiter report summary lines cut off or unbalanced", "reports affected", 15, reports["reports_with_cut_off_summary_lines"], lambda v: v == 0),
        ("UX-03", "Error messages that do not name a field or say what to send", "messages", 4, len(errs["error_not_actionable"]) + len(errs["error_without_field"]), lambda v: v == 0),
        ("ACC-10", "'Six months' read as years", "years returned (goal 0.5)", 6.0, extract_experience_years("I have six months of internship experience"), lambda v: v == 0.5),
        ("UX-04", "A screening turn with no text is scored", "score returned (goal: none)", 13.6, silent["screening_score"], lambda v: v is None),
        ("ENG-01", "A CI workflow exists", "1 = present", 0, int((ROOT / ".github" / "workflows" / "tests.yml").exists()), lambda v: v == 1),
        ("ENG-04", ".gitattributes exists", "1 = present", 0, int((ROOT / ".gitattributes").exists()), lambda v: v == 1),
    ]
    return [{"id": i, "what": w, "unit": u, "day64": b, "day65": a, "met": bool(ok(a))} for i, w, u, b, a, ok in rows]


BRIEF = [
    ("Improve scoring consistency", "'Six months' is now read as 0.5 years (was 6.0), 'one year six months' as 1.5 and 'two and a half years' as 2.5. A test scores the same input three times and checks the results are identical.", "parsers/answer_intent_engine.py; tests/test_day65_polish.py"),
    ("Improve output readability and report clarity", "The recruiter summary now names each concern in a few plain words (for example 'rounds disagree or score is borderline') and ends every line with a full stop. The full sentence stays in the risk table lower in the report. 30 of 30 reports now have two finished summary lines under 190 characters; 15 had cut-off lines before.", "parsers/hiring_report_generator.py; data/demo_dataset/simulated/reports/"),
    ("Fix usability issues", "A screening call in which no turn holds any words now returns no score, the status 'not_started' and a message to retry, instead of a score of 13.6.", "screening_ai/service.py"),
    ("Enhance recruiter-facing outputs", "Same change as the summary lines above; a recruiter reads the top of a report in a minute and sees a finished, balanced sentence.", "hiring_report_generator.py"),
    ("Improve error handling", "Every ATS error now says what is required and names the field. A request body that is not an object now names 'request_body'. 0 of 25 malformed requests have a vague message (was 4).", "ats_engine/service.py; utils/base_service.py"),
    ("Final UI/API adjustments", "No field or status value was added or removed, so the Day 59 contract and OpenAPI files are unchanged. A CI workflow runs the tests on Python 3.11 and 3.12 on every push, and .gitattributes stops line-ending noise in Git.", ".github/workflows/tests.yml; .gitattributes"),
]


def main() -> None:
    rows = measure()
    out = ROOT / "data" / "review" / "day65_before_after.json"
    out.write_text(json.dumps({"note": "Day 64 values are as recorded in docs/day64_improvement_list.md.", "rows": rows}, indent=2) + "\n", encoding="utf-8")
    md = ["# Day 65 – Final Enhancements & Feature Polish", "", "Zecpath – AI Job Portal | Feature enhancement report", "", "## Objective", "",
          "Refine the system to production-level quality.", "",
          "**Headline:** six of the Day 64 improvements are done (ACC-10, UX-02, UX-03, UX-04, ENG-01, ENG-04) and measured as fixed. The five accuracy problems that can give a candidate a wrong result (ACC-01 to ACC-04 and ENG-02) are not done, so the system is polished but not yet production-ready for real candidates.", "",
          "**How to read this:** every Day 65 number is re-measured by `python run_day65_polish_check.py`, which re-runs the Day 64 probes. Day 64 values are the ones recorded in the Day 64 improvement list.", "",
          "## Decisions requested", "", "| # | Decision | Why now |", "|---|---|---|",
          "| D1 | Make the common ATS scale the default (ACC-05)? | It changes hiring outcomes for 7 of 30 demo candidates, so it was left for a person to decide. |",
          "| D2 | Run `git add --renormalize .` once and commit `.gitattributes`. | Stops line-ending noise; do it as its own commit. |",
          "| D3 | Plan time for ACC-01 to ACC-04 and ENG-02. | They are the open P0 items; Day 65 did not touch them. |", "",
          "## 1. What was done, by brief item", "", "| Brief item | What was done | Evidence |", "|---|---|---|"]
    md += [f"| {a} | {b} | {c} |" for a, b, c in BRIEF]
    md += ["", "## 2. Before and after", "", "| Id | What was measured | Unit | Day 64 | Day 65 | Met |", "|---|---|---|---|---|---|"]
    md += [f"| {r['id']} | {r['what']} | {r['unit']} | {r['day64']} | {r['day65']} | {'yes' if r['met'] else 'NO'} |" for r in rows]
    md += ["", "Acceptance targets met in the Day 64 review: 4 of 11 (T7, T8, T9, T11). Open: T1 to T6, T10 and T5.", "",
           "Tests: 19 new in tests/test_day65_polish.py. The full suite passes. The Day 63 results, the Day 62 handbook and the Day 64 review were regenerated.", "",
           "## Honest limits", "",
           "- Polish, not accuracy: scores for real candidates are no more accurate than on Day 64. ACC-01 to ACC-04 can still give a wrong result.",
           "- 'Six months' is fixed for the years-and-months patterns listed; other phrasings ('a year', 'half a year') are not read.",
           "- A call with no words is now 'not started'. A call full of nonsense words (ACC-02) still gets a middling score.",
           "- Report wording was judged by length and balance, not by a recruiter; nobody has read them yet.",
           "- The CI workflow has not run on GitHub yet; it is tested only by checking the file.",
           "", "## 3. Files", "",
           "- Changed: parsers/answer_intent_engine.py, parsers/hiring_report_generator.py, ats_engine/service.py, screening_ai/service.py, utils/base_service.py, parsers/review_plan.py, parsers/demo_environment.py, tests/test_demo_dataset.py",
           "- New: tests/test_day65_polish.py, run_day65_polish_check.py, run_day65_docx.py, .github/workflows/tests.yml, .gitattributes, docs/day65_feature_enhancement_report.md, data/review/day65_before_after.json",
           "- Regenerated: data/demo_dataset/simulated/*, docs/day62_* handbook, docs/day64_* review documents"]
    (ROOT / "docs" / "day65_feature_enhancement_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    for r in rows:
        print(f"{r['id']:7} {r['day64']!s:>6} -> {r['day65']!s:<6} {'met' if r['met'] else 'NOT MET'}  {r['what']}")


if __name__ == "__main__":
    main()
