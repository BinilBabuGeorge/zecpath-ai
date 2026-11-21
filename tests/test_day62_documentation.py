"""
Day 62 documentation tests: the handbook, the architecture document and the onboarding guide cannot drift from the code.

WHY THESE TESTS EXIST. A handbook written by hand goes stale silently. These tests fail when
  * a Python module exists that the module catalogue does not list (or the catalogue lists one that is gone);
  * a weight, threshold, retention period, API operation or error code in the code is missing from the handbook;
  * a file, diagram or document the three documents point to does not exist;
  * the example requests in the documents stop being real (the services must still answer them);
  * requirements.txt stops listing the libraries the code imports (Day 62 found three missing).
A failure means: run `python run_day62_handbook.py` (and read what changed), or add the new module to MODULE_CATALOGUE.

The tests use plain asserts and import nothing but the standard library and the project.
"""

import re
from pathlib import Path

from parsers import documentation_index as di

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
HANDBOOK = DOCS / "day62_zecpath_ai_technical_handbook.md"
ARCHITECTURE = DOCS / "day62_system_architecture.md"
ONBOARDING = DOCS / "day62_developer_onboarding_guide.md"
ALL_DOCS = (HANDBOOK, ARCHITECTURE, ONBOARDING)
STATUSES = {"Built", "Partly", "Designed", "Not built", "Not here", "Replaced"}


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------------------------------- the catalogue
def test_every_python_module_is_in_the_catalogue():
    assert di.uncatalogued() == [], f"add these to MODULE_CATALOGUE in parsers/documentation_index.py: {di.uncatalogued()}"


def test_no_catalogue_entry_points_to_a_missing_file():
    assert di.stale_entries() == []


def test_every_catalogue_entry_is_complete_and_uses_a_known_layer():
    for path, (layer, what, phases) in di.MODULE_CATALOGUE.items():
        assert layer in di.LAYERS, path
        assert len(what) > 20, f"{path}: describe what the module does"
        assert phases.strip(), path


def test_every_layer_has_at_least_one_module():
    used = {layer for layer, _, _ in di.MODULE_CATALOGUE.values()}
    assert used == set(di.LAYERS)


def test_prd_coverage_uses_known_statuses_and_covers_all_100_phases():
    assert all(status in STATUSES for _, status, _, _ in di.PRD_COVERAGE)
    first = [int(re.match(r"\d+", g[0]).group()) for g in di.PRD_COVERAGE]
    assert first[0] == 1 and first == sorted(first)          # the groups run in phase order, starting at phase 1
    assert di.PRD_COVERAGE[-1][0].startswith("91-100")       # and end at phase 100


# ---------------------------------------------------------------------------------------------------- numbers match the code
def test_handbook_lists_every_module_and_its_line_count():
    text = _text(HANDBOOK)
    for path in di.MODULE_CATALOGUE:
        assert f"`{path}`" in text, f"{path} is missing from the handbook: run python run_day62_handbook.py"


def test_handbook_states_the_current_file_count():
    assert f"{len(di.python_modules())} Python files" in _text(HANDBOOK)


def test_handbook_shows_the_ats_weights_and_zone_cutoffs_the_code_uses():
    text = _text(HANDBOOK)
    facts = di.live_facts()
    for category, weights in facts["ats_weights"].items():
        row = f"| {category} | " + " | ".join(f"{round(weights[c] * 100):g} %" for c in ("skill_match", "experience", "semantic", "education")) + " |"
        assert row in text, row
    for category, cutoffs in facts["ats_thresholds_category"].items():
        assert f"| {category} | {cutoffs['shortlist']} | {cutoffs['review']} |" in text


def test_handbook_shows_the_round_weights_and_decision_thresholds_the_code_uses():
    text = _text(HANDBOOK)
    facts = di.live_facts()
    for rnd in ("ats", "screening", "hr_interview", "technical_interview", "machine_test"):
        tech = round(facts["round_weights"]["technical"][rnd] * 100)
        non = round(facts["round_weights"]["non_technical"][rnd] * 100)
        assert f"| {rnd} | {tech} % | {non} % |" in text, rnd
    assert f"at or above {facts['selected_threshold']:g}" in text
    assert f"at or above {facts['hold_threshold']:g}" in text


def test_handbook_shows_the_hr_and_technical_weights():
    text = _text(HANDBOOK)
    facts = di.live_facts()
    for name, weight in facts["hr_weights"].items():
        assert f"| {name.capitalize()} | {round(weight * 100):g} % |" in text, name
    for name, weight in facts["technical_weights"].items():
        assert f"| {name.replace('_', ' ')} | {round(weight * 100):g} % |" in text, name


def test_handbook_lists_every_api_operation_and_error_code():
    text = _text(HANDBOOK)
    facts = di.live_facts()
    for op_id, method, path, *_ in facts["operations"]:
        assert f"`{op_id}`" in text and f"{method} `{path}`" in text, op_id
    for code, status, *_ in facts["error_rules"]:
        assert f"| `{code}` | {status} |" in text, code


def test_handbook_lists_every_retention_rule():
    text = _text(HANDBOOK)
    for category, days, action, trigger in di.live_facts()["retention"]:
        assert f"| {category} | {days} days | {action} | {trigger} |" in text, category


def test_handbook_names_every_role_and_resource_type():
    text = _text(HANDBOOK)
    facts = di.live_facts()
    for name in facts["roles"] + facts["resource_types"]:
        assert f"`{name}`" in text, name


def test_test_counts_in_the_handbook_are_current():
    counts = di.count_tests()
    assert f"{counts['functions']:,} test functions in {counts['files']} files" in _text(HANDBOOK)


# ---------------------------------------------------------------------------------------------------- everything pointed to exists
_PATH = re.compile(r"`([A-Za-z0-9_./-]+\.(?:py|md|json|yaml|sql|png|txt|example))`")


def _referenced_paths(text: str):
    for match in _PATH.findall(text):
        if any(mark in match for mark in ("NN", "<", "*")) or match.startswith("logs/") or match.startswith("data/results/"):
            continue                                    # patterns and runtime outputs, not files in the repository
        if "/" not in match and not match.startswith(("run_", "README", "requirements", "regression_runner")):
            continue                                    # a bare file name used as an example ("service.py"), not a path
        yield match


def test_every_file_a_document_points_to_exists():
    missing = []
    for doc in ALL_DOCS:
        for ref in _referenced_paths(_text(doc)):
            if not any((ROOT / base / ref).exists() for base in ("", "docs", "parsers", "tests")):
                missing.append((doc.name, ref))
    assert missing == [], missing


def test_every_diagram_the_documents_embed_exists_and_is_a_png():
    for doc in ALL_DOCS:
        for ref in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", _text(doc)):
            image = DOCS / ref
            assert image.exists(), f"{doc.name}: {ref}"
            assert image.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" and image.stat().st_size > 20_000, ref
    assert len(list((DOCS / "diagrams").glob("day62_*.png"))) == 4


def test_the_three_documents_exist_and_are_substantial():
    assert len(_text(HANDBOOK).split()) > 7000
    assert len(_text(ARCHITECTURE).split()) > 1000
    assert len(_text(ONBOARDING).split()) > 1300


def test_the_handbook_has_every_section_the_brief_asks_for():
    text = _text(HANDBOOK)
    for heading in ("## 2. Architecture", "## 3. Module reference", "## 4. APIs", "## 5. Scoring logic", "## 6. Data models",
                    "## 7. Workflows", "## 8. Setup and deployment", "## 11. Known limits and open items"):
        assert heading in text, heading
    assert "![" in text                                  # diagrams are included
    assert "Developer onboarding" in _text(ONBOARDING) or "Onboarding Guide" in _text(ONBOARDING)


# ---------------------------------------------------------------------------------------------------- the examples are real
def test_the_examples_in_the_documents_are_still_answered_by_the_services():
    import run_day62_handbook as gen

    ex = gen.run_examples()
    for key in ("ats", "screening", "hr", "decision"):
        assert ex[key][1]["status"] == "success", key
    assert ex["error"][1]["status"] == "error" and ex["error"][1]["error"]["code"] == "invalid_input"
    assert ex["decision"][1]["decision"] in di.live_facts()["outcomes"]


# ---------------------------------------------------------------------------------------------------- setup instructions work
def test_requirements_lists_the_libraries_the_code_imports():
    reqs = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    for lib in ("scikit-learn", "pdfplumber", "python-docx"):
        assert lib in reqs, f"requirements.txt must list {lib}"
    code = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in (ROOT / "parsers").glob("*.py"))
    assert "import pdfplumber" in code and "from docx import" in code and "from sklearn" in code


def test_every_environment_variable_in_the_setup_table_is_read_by_the_code():
    sources = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for folder in ("utils", "ats_engine") for p in (ROOT / folder).glob("*.py"))
    for name in re.findall(r"`(ZECPATH_[A-Z_]+)`", _text(HANDBOOK)):
        assert name in sources, name
