"""
Day 62 demo: builds the Zecpath AI Technical Handbook, the system architecture document and the developer onboarding guide.

    python run_day62_handbook.py            (a few seconds)

WHAT IT DOES
  1. reads every weight, threshold, retention period, API operation and error rule FROM THE CODE (parsers/documentation_index.live_facts);
  2. runs the five real services on small sample inputs, so every example payload in the documents is a real output, not typed by hand;
  3. writes three Markdown documents into docs/ (the diagrams in docs/diagrams/ are drawn by `python run_day62_diagrams.py`);
  4. writes data/results/day62_documentation_report.json with the counts the Deliverables document quotes.

The prose is written by hand in this file; the numbers and tables are generated. tests/test_day62_documentation.py fails if a document
disagrees with the code, if a module is missing from the catalogue, or if a file or diagram a document points to does not exist.

Writes: docs/day62_zecpath_ai_technical_handbook.md, docs/day62_system_architecture.md, docs/day62_developer_onboarding_guide.md,
        data/results/day62_documentation_report.json
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
logging.disable(logging.CRITICAL)

from parsers import documentation_index as di  # noqa: E402

AS_OF = "2026-11-20"
DOCS = ROOT / "docs"
HANDBOOK = DOCS / "day62_zecpath_ai_technical_handbook.md"
ARCHITECTURE = DOCS / "day62_system_architecture.md"
ONBOARDING = DOCS / "day62_developer_onboarding_guide.md"
REPORT = ROOT / "data" / "results" / "day62_documentation_report.json"
DIAGRAMS = ["day62_architecture.png", "day62_candidate_workflow.png", "day62_scoring_flow.png", "day62_request_lifecycle.png"]


# ---------------------------------------------------------------------------------------------------- code blocks
# Kept out of the f-strings below on purpose: before Python 3.12 an f-string expression may not contain a backslash or '#'.
FOLDER_TREE = r'''zecpath-ai/
  ats_engine/      resume parsing, ATS scoring, batch scoring            (services)
  screening_ai/    screening-call scoring                                (service)
  interview_ai/    HR and technical interview scoring                    (service)
  scoring/         decision and recommendation                           (service)
  parsers/         all engines, governance, integration and ops modules
  utils/           base service, config, logger, cache, warm-up
  api/             OpenAPI files (ATS, screening, HR interview, integration)
  schemas/         JSON Schemas and the transcript SQL schema
  tests/           pytest suite, one file per module; tests/golden/ holds golden outputs
  docs/            one document per day's work; docs/diagrams/ holds the pictures
  data/            sample resumes and job descriptions, reports, results (real data is gitignored)
  logs/            run logs (gitignored except .gitkeep)
  run_dayNN_*.py   one demo script per day'''

HB_SETUP = r'''git clone <your-repo-url>
cd zecpath-ai
python -m venv venv
venv\Scripts\activate           # macOS / Linux:  source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env           # macOS / Linux:  cp .env.example .env
python run_day62_handbook.py     # regenerates this handbook from the code (proves the install works)
pytest                           # full suite'''

HB_RUN_SERVICE = r'''python -c "from ats_engine.service import ATSService; print(ATSService().run({'resume_text': 'React, Node.js', 'job_description': 'Needs React and Node.js'}))"'''

DOCKERFILE = r'''FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ats_engine screening_ai interview_ai scoring parsers utils schemas api ./
ENV ZECPATH_ENV=production
# a worker entry point (an HTTP server around run(payload)) does not exist yet; it is part of the gateway work'''

ONB_SETUP = r'''git clone <your-repo-url>
cd zecpath-ai
python -m venv venv
venv\Scripts\activate            # macOS / Linux:  source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # macOS / Linux:  cp .env.example .env'''

ONB_CHECK = r'''python -c "from ats_engine.service import ATSService; print(ATSService().run({'resume_text': 'React, Node.js', 'job_description': 'Needs React and Node.js'}))"
pytest tests/test_ats_engine.py tests/test_scoring.py tests/test_service_contracts.py
pytest                      # the full suite; the Day 61 run was 2,017 passed, 6 skipped'''

ONB_TREE = r'''ats_engine/      services: ATS, batch ATS, resume parsing          start: service.py
screening_ai/    service: screening call scoring
interview_ai/    service: HR and technical interviews
scoring/         service: decision and recommendation
parsers/         every engine (resume, ATS, screening, HR, technical, machine test,
                 aggregation, recommendation, governance, integration, observability)
utils/           base_service, config, logger, perf (cache), warmup
api/, schemas/   OpenAPI and JSON Schemas (some are GENERATED; see section 7)
tests/           one test file per module; tests/golden/ holds golden outputs
docs/            one document per day; docs/diagrams/ holds the pictures
run_dayNN_*.py   one demo script per day; each writes logs/dayNN_*.log'''


# ------------------------------------------------------------------------------------------------------------ helpers
def table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    """A Markdown table; pipes inside cells are escaped."""
    def cell(v: Any) -> str:
        return str(v).replace("|", "\\|").replace("\n", " ")
    out = ["| " + " | ".join(cell(h) for h in headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(cell(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def code(text: str, lang: str = "") -> str:
    """A fenced code block."""
    return f"```{lang}\n{text.rstrip()}\n```"


def pct(x: float) -> str:
    """0.35 -> '35 %'."""
    return f"{round(x * 100):g} %"


def weights_line(w: Dict[str, float]) -> str:
    return ", ".join(f"{k} {pct(v)}" for k, v in w.items())


def run_examples() -> Dict[str, Any]:
    """Run each service on a small sample input and return (request, response) pairs: every example in the documents is real output."""
    from ats_engine.service import ATSService
    from interview_ai.service import InterviewIntelligenceService
    from scoring.service import DecisionScoringService
    from screening_ai.service import ScreeningService

    resume = ("Asha Nair\nSkills\nReact, Node.js, MongoDB, Express, JavaScript, Git\nExperience\nSoftware Engineer, Acme Tech (2021-2024)\n"
              "Built MERN applications and REST APIs\nEducation\nB.Tech Computer Science, 2021")
    jd = ("MERN Stack Developer\nRequirements\nReact, Node.js, MongoDB, Express\n3+ years experience\nResponsibilities\n"
          "Build and maintain web applications")
    ats_req = {"resume_text": resume, "job_description": jd}
    turns = [{"text": t} for t in (
        "Hi, I am Asha, a software engineer with three years of experience in web development.",
        "I did my B.Tech in computer science in 2021.",
        "I have three years of experience.",
        "I work with React, Node and MongoDB.",
        "I am based in Kochi.",
        "My notice period is 30 days.",
        "I expect around eight lakhs per annum.")]
    scr_req = {"candidate_id": "C001", "job_role": "MERN Stack Developer", "turns": turns}
    hr_req = {"interview_type": "hr", "role_type": "technical", "experience_level": "experienced", "answers": [
        "I enjoy building products and working in a team where we review each other's code regularly.",
        "My biggest strength is debugging; a weakness is that I take on too much, so I now plan my week."]}
    dec_req = {"candidate_id": "C001", "role_type": "non_technical", "ats_score": 60, "screening_score": 70, "hr_interview_score": 85}
    bad_req = {"resume_text": 5, "job_description": jd}
    return {
        "ats": (ats_req, ATSService().run(ats_req)),
        "screening": (scr_req, ScreeningService().run(scr_req)),
        "hr": (hr_req, InterviewIntelligenceService().run(hr_req)),
        "decision": (dec_req, DecisionScoringService().run(dec_req)),
        "error": (bad_req, ATSService().run(bad_req)),
    }


def pretty(obj: Any, limit: int = 1800) -> str:
    text = json.dumps(obj, indent=2, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit].rsplit("\n", 1)[0] + "\n  ..."


def short_request(req: Dict[str, Any]) -> Dict[str, Any]:
    """Shorten long text fields so an example fits on a page."""
    out: Dict[str, Any] = {}
    for k, v in req.items():
        if isinstance(v, str) and len(v) > 90:
            out[k] = v[:87] + "..."
        elif isinstance(v, list) and len(v) > 3:
            out[k] = v[:2] + [f"... {len(v) - 2} more"]
        else:
            out[k] = v
    return out


def module_tables(layers: Sequence[str]) -> str:
    """One table per layer from the catalogue: path, lines, what it does, PRD phases."""
    parts = []
    for layer in layers:
        rows = [(f"`{p}`", di.line_count(p), what, phases) for p, (lyr, what, phases) in sorted(di.MODULE_CATALOGUE.items()) if lyr == layer]
        if rows:
            parts.append(f"### {di.LAYERS[layer]}\n\n" + table(["Module", "Lines", "What it does", "PRD phase"], rows))
    return "\n\n".join(parts)


def doc_index() -> str:
    """One row per docs/dayNN_*.md file with its first heading."""
    rows = []
    for f in sorted(DOCS.glob("*.md")):
        first = next((ln.lstrip("# ").strip() for ln in f.read_text(encoding="utf-8", errors="ignore").splitlines() if ln.startswith("#")), f.stem)
        rows.append((f"`docs/{f.name}`", first))
    return table(["File", "Title"], rows)


# ------------------------------------------------------------------------------------------------------------ the handbook
def build_handbook(facts: Dict[str, Any], ex: Dict[str, Any]) -> str:
    n_mod = len(di.python_modules())
    tests = di.count_tests()
    parsers_n = sum(1 for m in di.python_modules() if m.startswith("parsers/"))
    ats_w = facts["ats_weights"]
    rw = facts["round_weights"]
    fr = facts["fresher_multipliers"]["fresher"]
    cat = facts["ats_thresholds_category"]
    dflt = facts["ats_thresholds_default"]

    ats_rows = [(name, *(pct(w[c]) for c in ("skill_match", "experience", "semantic", "education"))) for name, w in ats_w.items()]
    thr_rows = [(k, v["shortlist"], v["review"]) for k, v in cat.items()] + [("anything else (default)", dflt["shortlist"], dflt["review"])]
    round_rows = [(r, *(pct(rw[role][r]) for role in ("technical", "non_technical")))
                  for r in ("ats", "screening", "hr_interview", "technical_interview", "machine_test")]
    mt_rows = [(t, *(pct(w[m]) for m in ("correctness", "efficiency", "code_quality", "problem_solving", "time"))) for t, w in facts["machine_test_weights"].items()]
    ops_rows = [(f"`{o[0]}`", f"{o[1]} `{o[2]}`", o[3], f"`{o[4]}`" if o[4] != "none" else "none", f"{o[5]:g} s", o[6].rsplit(".", 1)[-1]) for o in facts["operations"]]
    err_rows = [(f"`{c}`", status, source, retries) for c, status, source, retries in facts["error_rules"]]
    ret_rows = [(cat_, f"{days} days", action, trig) for cat_, days, action, trig in facts["retention"]]

    return f"""# Zecpath AI Technical Handbook

Zecpath: AI Job Portal | Technical handbook for the AI system | Built {AS_OF} (Day 62)

## How to read this handbook

**Who it is for.** Developers who will build, change or run the Zecpath AI layer; reviewers who need to know what exists; and the next person who inherits the project.

**What it covers.** The AI layer in this repository: {n_mod} Python files ({parsers_n} in `parsers/`, 7 service files and 5 shared utilities), its schemas, tests and documents. It does **not** cover the Zecpath backend, frontend, telephony, video, email or payments: they are not in this repository (section 1.3 says exactly where the line is).

**Three words are used with care.**

| Word | Meaning here |
|---|---|
| **Built** | The code exists, has tests, and was run on real inputs in this project. |
| **Designed** | The logic or plan exists as code or a document, but nothing enforces it yet (no database, gateway, queue, login or dashboard exists). |
| **Not built** | Nothing in this repository does it. |

**Where the numbers come from.** Every weight, threshold, retention period, API operation and error rule in this handbook is read from the code when the handbook is built (`parsers/documentation_index.py`), and every example request and response is real service output. A test fails when this document and the code disagree. Prose is written by hand and is the author's judgement.

**Contents.** 1 System overview. 2 Architecture. 3 Module reference. 4 APIs. 5 Scoring logic. 6 Data models. 7 Workflows. 8 Setup and deployment. 9 Quality, performance and operations. 10 Governance and security. 11 Known limits and open items. 12 Where to go next. Appendices: glossary, document index.

The system architecture document (`docs/day62_system_architecture.md`) and the developer onboarding guide (`docs/day62_developer_onboarding_guide.md`) are the two companion deliverables; this handbook contains the same facts in one place.

---

## 1. System overview

### 1.1 What the AI layer is

Zecpath is an AI-powered hiring platform. A candidate moves through rounds (resume screening, voice screening, HR interview, technical interview, machine test, final round), and each round produces evidence about the candidate. **The AI layer is the part that turns raw inputs (a resume file, a job description, call turns, interview answers) into scores, explanations and a recommendation a recruiter can act on.** It is a set of small, stateless services written in Python.

It does five things:

1. **Reads resumes and job descriptions** and scores the fit (the ATS).
2. **Scores a screening call** from its transcript turns.
3. **Scores an HR interview and a technical interview** from the candidate's answers; evaluates machine-test attempts.
4. **Combines the rounds** into one Hiring Fit Score and a recommendation: selected, hold for review, or rejected.
5. **Explains and records** every decision, with governance rules (access, consent, retention, audit) and observability designed around it.

### 1.2 Design principles

These ten rules shape every module. They were reached by finding real problems (the Day number is where each was decided) and a new module is expected to follow them.

| # | Principle | What it means in practice |
|---|---|---|
| 1 | **The boundary never throws** (Day 57) | Call `run(payload)`, not `process()`. It always returns a success or an error envelope, and never leaks a stack trace. |
| 2 | **Stateless** (Day 59) | A service reads its payload and returns a result. It never connects to a database; the backend saves results and writes the audit entry. |
| 3 | **Explainable** (Days 13, 51, 52) | A score carries its components, weights and contributions; a decision carries its rule trace and reasons. |
| 4 | **Missing is not zero** (Days 13, 51, 57) | A missing section redistributes weight; a round that has not happened makes the result *provisional*, never a zero. |
| 5 | **A rejection is only a recommendation** (Days 41, 52) | The policy object refuses to be configured to reject automatically; a named person must confirm every rejection. |
| 6 | **No personal content in logs or audit entries** (Days 55, 61) | Fields are allowlisted; text, names, emails and transcripts are refused. |
| 7 | **Reduce bias before scoring** (Days 15, 43) | Personal fields are masked before a resume is scored; volunteered demographic disclosures are scrubbed from transcripts. |
| 8 | **Never claim a capability that does not exist** (Days 48, 49, 50) | Gaze tracking, external-voice detection and running candidate code were deliberately not faked; every report lists what it cannot see. |
| 9 | **Rules and reasoned weights, not trained models** | The scoring is rule-based and deterministic. Weights and thresholds are reasoned, not calibrated: no labelled hiring-outcome data exists in this project. |
| 10 | **Change without changing answers** (Day 60) | Optimisations are checked against golden files generated from the code before the change. |

### 1.3 What the PRD asks for and what this repository holds

The PRD (Parts 1 to 6) describes 100 phases. This repository is the AI layer only, so many phases are, rightly, elsewhere. This table is the honest map.

{table(["PRD phase", "Status", "What this repository holds", "What is not here"], di.PRD_COVERAGE)}

### 1.4 The numbers at a glance

{table(["Measure", "Value"], [
    ("Python files in the AI layer", n_mod),
    ("Engines in `parsers/`", parsers_n),
    ("Services (stable API boundary)", 7),
    ("Test files / test functions", f"{tests['files']} / {tests['functions']:,}"),
    ("API version", facts["api_version"]),
    ("Documents in `docs/`", len(list(DOCS.glob('*.md')))),
])}

The last full regression recorded in the repository (Day 61) reports 2,017 passed and 6 skipped; a parametrised test counts once per case, which is why that is more than the number of test functions.

---

## 2. Architecture

![Where the AI layer sits](diagrams/day62_architecture.png)

### 2.1 The three levels

1. **Backend and frontend (not in this repository).** Accounts, job posting, scheduling, telephony, video, email, payments and the database. The backend authenticates users, reads inputs from its stores, calls the AI layer, saves the results and appends the audit entry.
2. **AI gateway (designed in Day 59, not built).** Authentication with scoped service tokens, request-schema checks, idempotency keys, a queue for asynchronous jobs.
3. **The AI layer (this repository).** Seven service classes behind one contract, built on the engines in `parsers/`.

### 2.2 One request

![One API call](diagrams/day62_request_lifecycle.png)

Every service subclasses `BaseAIService` (`utils/base_service.py`) and implements `process(payload)`. Callers use `run(payload)`, which:

- checks the payload is a JSON object, calls `process`, and makes the result JSON-safe (NaN and infinity become `null`, enums become values, dataclasses become dictionaries);
- turns a bad input into an error envelope with a machine-readable `code` and the `field` at fault;
- turns an unexpected exception into `internal_error` with a generic message, and logs the full trace;
- refuses text over {facts['max_text_chars']:,} characters and lists over {facts['max_items']} items rather than truncating silently.

### 2.3 Layers of the code

{table(["Layer", "What it holds", "Modules"], [(k, v, sum(1 for _, (lyr, _, _) in di.MODULE_CATALOGUE.items() if lyr == k)) for k, v in di.LAYERS.items()])}

**Rule: services do not import one another.** Communication between services goes through the gateway (REST, queue or webhook). Inside `tests/` direct imports are fine. The engines in `parsers/` are shared libraries and may import each other.

### 2.4 Folder structure

{code(FOLDER_TREE)}

---

## 3. Module reference

Every module starts with a docstring that states what it does, its input contract and its output contract; the docstring is the source of truth and this table is the map. Lines are counted from the files. **PRD phase** names the phases (section 1.3) the module serves; "-" means it serves the platform rather than one phase.

### 3.1 How the layers cooperate

- **B (understanding)** turns files and text into structured resume and job data: `resume_extractor` reads the file, `section_classifier` and `section_extractor` find the sections, `skill_extractor`, `experience_parser` and `education_parser` read each, `jd_parser` does the same for a job description, `semantic_matcher` compares the two texts, and `fairness_engine` masks personal fields first.
- **C (ATS)** combines the four component scores in `ats_scoring_engine.score_candidate()`, assigns a zone with `ranking_engine.classify_zone()`, and decides who may receive a call with `eligibility_engine.evaluate_eligibility()`.
- **D (screening)** runs a call as a state machine (`conversation_flow_engine`), understands each answer (`answer_intent_engine`), scores the call (`screening_scoring_engine`) and writes the report; `screening_pipeline.run_screening_call()` runs the whole chain.
- **E (HR interview)** asks questions (`hr_interview_question_bank`), decides follow-ups, scores communication, confidence, relevance and consistency and combines them in `hr_interview_scoring_engine.score_hr_interview()`; `aptitude_logic_engine` adds logic and situational questions.
- **F (technical)** has its own question bank and scoring (`technical_skill_scoring_engine.build_technical_evaluation_report()`); `machine_test_evaluation_engine.build_machine_test_report()` scores code attempts without running them; `behavioral_signal_engine` and `integrity_detection_engine` supply timing and tab-focus signals.
- **G (decision)** combines every round in `cross_round_aggregation_engine.compute_cross_round_score()`, turns it into an outcome with `final_recommendation_engine.decide()`, and `hiring_report_generator.generate_hiring_report()` assembles the recruiter report.
- **H (governance)** wraps the above: audit log, retention, consent, access control, a storage plan, and `governance_framework.GovernanceService` applies them in one call.
- **I (operations)** holds the API contract, observability, the capacity model and the quality tools.

{module_tables(["S", "A", "B", "C", "D", "E", "F", "G", "H", "I"])}

---

## 4. APIs

### 4.1 The operations

All paths start with `/v1/ai`. **Sync** operations answer at once (HTTP 200); **async** operations return 202 and a job to poll. "Implemented by" names the class that exists today; the HTTP gateway around every row is **planned**, not built.

{table(["Operation", "Method and path", "Mode", "Scope", "Timeout (proposed)", "Implemented by (class)"], ops_rows)}

Machine-readable contracts: `schemas/integration_api_schemas.json` (JSON Schema 2020-12) and `api/integration_openapi.yaml` (OpenAPI 3.1) are **generated** from `parsers/integration_contract.py`, and a test fails if the files in the repository differ from what the code generates. Older session-style contracts remain: `api/openapi.yaml` (ATS), `api/screening_openapi.yaml`, `api/hr_interview_openapi.yaml`.

### 4.2 The response envelope

Every response, from every service, is one of two shapes.

**Success** (real output of `ATSService().run(...)`):

{code(pretty(short_request(ex['ats'][0])) , 'json')}

{code(pretty(ex['ats'][1]), 'json')}

**Error** (a bad request, real output):

{code(pretty(ex['error'][1]), 'json')}

`status` is `success` or `error`. On error, `error.code` is machine-readable and `error.field` names the input at fault (or `null`).

### 4.3 More real examples

**Screening call.** Seven turns; `notice_period` comes back in `categories_missing`, so the call is `incomplete` and the score covers the answered categories only:

{code(pretty(short_request(ex['screening'][0]), 900), 'json')}

{code(pretty(ex['screening'][1]), 'json')}

**HR interview** (`interview_type: hr`):

{code(pretty(ex['hr'][1]), 'json')}

**Decision** (the recommendation; read the flags):

{code(pretty(ex['decision'][1]), 'json')}

### 4.4 Errors and retries

{table(["Error code", "HTTP", "Raised by", "Max retries"], err_rows)}

Gateway errors `429`, `503` and `504` are retried with backoff; `internal_error` is retried once (the scoring is deterministic, so a second failure is a bug) and `file_not_found` twice (the file may not have replicated yet). Every other error is not retried: the same request fails the same way. The proposed retry policy is base delay 0.5 s, cap 30 s, at most 4 retries inside a 20 s budget, with full jitter. Job creation carries an `Idempotency-Key` (kept {86400 // 3600} hours, proposed): the same key with the same body returns the same job; the same key with a different body is `idempotency_conflict`.

### 4.5 Asynchronous jobs

States: {" -> ".join(facts["job_states"][:3])}, or `failed` / `cancelled`. Allowed transitions: `queued` to `running` or `cancelled`; `running` to `completed`, `failed` or `cancelled`; the other states are final. A job may be attempted up to 3 times inside `running`.

### 4.6 Security of the API (designed)

Service tokens carry a scope per operation (the Scope column above), the tenant and a pseudonymous actor. Proposed lifetimes: 5 minutes for a service token, 15 minutes for a user token. `candidate_id` must look like a pseudonymous reference (letters, digits, `_`, `-`, up to 64 characters), so a name or an email cannot pass.

---

## 5. Scoring logic

Everything below is rule-based and deterministic: the same input always gives the same score. Weights are **reasoned defaults, not calibrated**.

![How a score becomes a recommendation](diagrams/day62_scoring_flow.png)

### 5.1 ATS score (resume against job description)

`score_candidate(resume_text, jd_text, matcher, role_category)` combines four components, each 0 to 100, and returns every component with its weight and contribution. The role category (tech, business, creative or default) is chosen from the job and picks the weight profile.

{table(["Role category", "Skill match", "Experience", "Semantic", "Education"], ats_rows)}

- **Skill match:** required skills found in the resume (dictionary in `skill_dictionary`).
- **Experience:** relevance of the work history to the job title and the years found.
- **Semantic:** TF-IDF cosine similarity of the two texts (a bag-of-words measure, not a neural model). The vocabulary is fitted on exactly the resume and job description of the request, so the same pair always scores the same.
- **Education:** alignment of degree level with the target (default target: bachelor's).
- **Missing data:** if a section is absent, the component is marked unavailable and its weight is redistributed over the others in proportion; the result says so. It is never a silent zero.
- **Fairness:** personal fields (name, contact, gender, age, religion, photo and the like) are masked before scoring, and keyword stuffing is damped (`fairness_engine`).

**Zones.** `classify_zone` maps the overall score to a shortlisting zone. The boundaries are inclusive on the lower edge.

{table(["Role category", "Shortlist at or above", "Review at or above"], thr_rows)}

Below the review cutoff the zone is `reject`. A skill-match score below {10.0:g} forces `reject` whatever the total (the skill-relevance floor). If no skills could be compared at all, the zone is capped at `review`: a reject needs skill evidence. The ATS engine's scores structurally top out near 50 to 60 for a strong match, which is why the ATS has its own cutoffs (47 or 55) and not 70.

**Eligibility** (`evaluate_eligibility`) answers a narrower question, "may this candidate receive a screening call?": hard gates first (mandatory skills, an experience floor), then the zone. A high score cannot compensate for a missing mandatory requirement.

### 5.2 Screening call score

Each answer is understood (`answer_intent_engine`), then scored on four parameters, and the call score aggregates the answers. The weights depend on the kind of question: a **structured** question (experience, salary, availability) asks for a fact, so completeness weighs more; an **open-ended** one (introduction, skills, education, location) asks for a description, so clarity weighs more.

| Question kind | Clarity | Relevance | Completeness | Consistency |
|---|---|---|---|---|
| structured | 15 % | 30 % | 40 % | 15 % |
| open-ended | 35 % | 35 % | 20 % | 10 % |
| other | 25 % | 25 % | 25 % | 25 % |

Consistency (does the candidate contradict themselves, for example three years in one answer and five in another) can only be judged across the whole call, so it is computed in a second pass. The seven categories asked are introduction, education, experience, skills, location, notice period and salary. The conversation itself is a deterministic state machine whose actions are retry on silence, clarify, redirect, fallback, acknowledge a repeat, follow up, advance, polite skip and end call: fixed templates, not generated speech.

### 5.3 HR interview score

Per-answer averages (so a short and a long interview land on the same scale):

{table(["Parameter", "Weight", "Why"], [
    ("Relevance", pct(facts["hr_weights"]["relevance"]), "the most direct check that the question was answered"),
    ("Communication", pct(facts["hr_weights"]["communication"]), "an independently useful skill signal"),
    ("Confidence", pct(facts["hr_weights"]["confidence"]), "useful but more heuristic (text only, no audio)"),
    ("Consistency", pct(facts["hr_weights"]["consistency"]), "least certain input, so the smallest say"),
])}

The weights live in `WeightConfig` and can be supplied by a caller. The aptitude engine scores logical reasoning and situational judgement separately.

### 5.4 Technical interview score

{table(["Parameter", "Weight"], [(k.replace("_", " "), pct(v)) for k, v in facts["technical_weights"].items()])}

Questions come from the domain (MERN, Java or DevOps) and an experience tier (basics, intermediate, advanced). Answers are scored against the question that was asked: see the onboarding guide for the consequence.

### 5.5 Machine test score

`machine_test_evaluation_engine` **never runs candidate code**. It scores execution results handed to it (pass or fail per case, runtimes) and analyses Python statically with `ast.parse`. Hidden cases weigh 1.5 times the visible ones, so hard-coding the visible samples does not pay; efficiency and time are multiplied by the pass fraction, so a fast wrong answer earns nothing. System-design tasks are scored by a keyword proxy and always flagged for human review.

{table(["Task type", "Correctness", "Efficiency", "Code quality", "Problem solving", "Time"], mt_rows)}

### 5.6 Hiring Fit Score (all rounds)

`compute_cross_round_score` combines the rounds with weights that depend on the role.

{table(["Round", "Technical role", "Non-technical role"], round_rows)}

- **Fresher adjustment:** for a fresher the ATS weight is multiplied by {fr['ats']:g} and the technical and machine-test rounds by {fr['technical_interview']:g}, then weights are renormalised to 1. The adjustment is listed in the result.
- **Not applicable vs missing:** a round the role does not use is *not applicable*; a round the role needs but that has not happened is *missing*. A candidate with a missing round gets a **provisional** fit and the recommendation "hold for evidence"; ranking only includes complete candidates of one role type.
- **Scale:** every score is validated and converted to 0-100; out-of-range or NaN input is refused, not clamped. The ATS round defaults to its raw score; `ats_scale="zone_aligned"` (opt-in, Day 54) maps it onto the common scale using the ATS's own cutoffs.
- **Transparency:** the result carries the weight profile, adjustments, per-round contributions, the formula, a leave-one-out sensitivity and a plain-language `explain()`.

### 5.7 Final recommendation

`decide()` turns the Hiring Fit Score into one of {", ".join(f"`{o}`" for o in facts["outcomes"])}. The score sets a base band (selected at or above {facts['selected_threshold']:g}, hold at or above {facts['hold_threshold']:g}, otherwise rejected), then **rules only ever move an outcome toward human review, never toward rejection**:

| Rule | Condition | Effect |
|---|---|---|
| R1 | evidence incomplete | hold (pending evidence) |
| R2 | a skill round below 40 | blocks selected |
| R3 | integrity tag medium or high | blocks selected |
| R4 | borderline score (within {facts['borderline_margin']:g} of a threshold), rounds disagree (spread of {facts['disagreement_spread']:g} or more), a round asked for review, or an ATS zone other than shortlist | blocks selected |
| R5 | selection confidence below 55 | blocks selected |
| R6 | rejection confidence below 50 | rejected becomes hold |
| R7 | any rejection | always needs a named person; never applied automatically |

**Confidence** (0 to 100) measures how robust the evidence behind the band is: margin from the nearest threshold 35 %, evidence coverage 25 %, agreement between rounds 20 %, stability when any one round is left out 20 %, multiplied by a risk multiplier and capped at 60 while any round is missing. It is **not** a probability of a good hire and is not calibrated.

Risk factors: an integrity tag lowers confidence and blocks selection; behaviour signals (latency spikes, uneven pacing) only lower confidence. Verbal hesitation is shown but deliberately **not used**, because it penalises nervous and non-native speakers. The candidate-facing notice never contains scores, risk factors or the word integrity.

---

## 6. Data models

### 6.1 Request and response models

The API schemas (24 JSON Schemas) are in `schemas/integration_api_schemas.json`. Requests are strict (unknown fields refused); responses allow extra fields so a new field does not break a client. The ATS, resume and job models:

| Model | File | Key fields |
|---|---|---|
| Resume | `schemas/resume_schema.json` | candidateId, name, contact, currentDesignation, totalExperienceYears, summary, skills, experience, education, certifications |
| Job description | `schemas/job_description_schema.json` | jobId, jobTitle, department, location, employmentType, experienceRequired, requiredSkills, niceToHaveSkills, educationRequired, responsibilities, salaryRange |
| ATS request and result | `schemas/ats_api_schemas.json`, `schemas/integration_api_schemas.json` | see section 4 |

The resume-parsing API returns text, skills, experience, education and certifications but **no name, email or phone** (Day 59 decision D3): no engine needs them, and the audit log forbids them. The Day 2 schema, which requires them, is therefore not the API's output contract.

### 6.2 Screening transcript

Two tables (`schemas/transcript_schema.sql`, executed against SQLite in the Day 23 demo; portable SQL):

| Table | One row per | Key columns |
|---|---|---|
| `call_sessions` | screening call | call_id, candidate_id, job_id, started_at, ended_at, status (`in_progress`, `completed`, `dropped`, `failed`), language |
| `transcript_turns` | question and answer | turn_id, call_id, candidate_id, job_id, question_id, turn_index, question_text, raw_transcript, asr_confidence (0 to 1), expected_answer_type, normalized_value, normalization_status (`ok`, `partial`, `needs_review`, `not_applicable`) |

`candidate_id` and `job_id` are denormalised on purpose. The Python model is in `parsers/transcript_schema.py`.

### 6.3 Audit entries

The audit log (`parsers/audit_trail.py`) is append-only and hash-chained, so one edited entry is detected on reload. Entries are typed (score, decision, access, consent). An entry may hold ids, scores, versions and codes; it **refuses** any payload key from the forbidden list (name, email, phone, resume text, transcript, answers, audio, video, protected attributes and similar) and any string over {200} characters. It refuses to record an automated rejection. Day 61 added a decision recorder that logs an *inputs* entry and a *result* entry per decision so a decision can be replayed.

### 6.4 Roles, resources and data retention

Roles: {", ".join(f"`{r}`" for r in facts["roles"])}. Resources: {", ".join(f"`{r}`" for r in facts["resource_types"])}. Access is deny-by-default and every decision names the rule that made it. Recruiters and company admins see the paid resources ({", ".join(f"`{r}`" for r in facts["paid_types"])}) only when the unlock flag is set. The service role can append to the audit log but never edit or delete it, and can never confirm a rejection.

Retention rules (proposed defaults for a lawyer to confirm, not legal advice):

{table(["Data category", "Kept", "Then", "Counted from"], ret_rows)}

---

## 7. Workflows

### 7.1 The candidate journey

![Candidate journey](diagrams/day62_candidate_workflow.png)

The order the real engines run in (`parsers/pipeline_simulation.py` runs it end to end; the Day 56 simulation ran 8 scripted candidates from file to report with no hand-built hand-off).

### 7.2 A screening call

Question bank, then for each turn: speech-to-text result (a mock provider today) is cleaned, the flow engine decides the action (ask, clarify, retry on silence, advance, end), the answer is understood and scored, and at the end the call is scored for consistency and a report is written. Poor audio and language mismatch are handled by `edge_case_handler`; a crash anywhere returns a safe result.

### 7.3 A decision, with a human in the loop

1. The backend collects the round scores (and the ATS zone) and calls `recommend_decision`.
2. The service returns the outcome, the confidence, the reasons and the flags.
3. `rejected` always carries `human_confirmation_required: true` and `automated_action: none`; the candidate sees "under review" until a named person confirms.
4. The backend saves the result and appends the decision-audit entries; a recruiter override is recorded with the reviewer and a mandatory note.

---

## 8. Setup and deployment

### 8.1 Setup on a developer machine

Prerequisites: Python 3.11 (the version the project's virtual environment uses; 3.12 also runs the examples in this handbook, with the float-sum difference noted in section 9), and Git.

{code(HB_SETUP, 'bash')}

**requirements.txt fix (Day 62).** Until Day 62 the file did not list `scikit-learn` (the TF-IDF matcher), `pdfplumber` and `python-docx` (resume reading), although the code imports them; a fresh install would fail at the first ATS score or file read. They are now listed. `numpy` and `scipy` come with scikit-learn.

### 8.2 Configuration

Settings come from environment variables (`utils/config.py`, `.env.example`); never put secrets in source control.

{table(["Variable", "Default", "Meaning"], [
    ("`ZECPATH_ENV`", "development", "development, staging or production (DEBUG is on only in development)"),
    ("`ZECPATH_SERVICE_NAME`", "unnamed-service", "name used in logs and version tags"),
    ("`ZECPATH_MODEL_VERSION`", "v0.1.0", "model version stamped on every response"),
    ("`ZECPATH_DATABASE_URL`", "sqlite:///data/zecpath.db", "placeholder; the AI layer itself holds no database"),
    ("`ZECPATH_MEDIA_PATH`", "data/media", "placeholder for media storage"),
    ("`ZECPATH_QUEUE_URL`", "(empty)", "placeholder for the job queue"),
    ("`ZECPATH_WEBHOOK_URL`", "(empty)", "placeholder for webhook callbacks"),
    ("`ZECPATH_CACHE`", "on", "set to `off` to disable every cache (Day 60)"),
    ("`ZECPATH_BATCH_WORKERS`", "1", "worker processes for batch ATS scoring (Day 60)"),
])}

### 8.3 Run a service locally

{code(HB_RUN_SERVICE, 'bash')}

Logs go to the console and to `logs/zecpath_ai.log` (rotated at 5 MB, three backups kept). Every `run_dayNN_*_demo.py` script reproduces a day's results and writes its own log into `logs/`.

### 8.4 Deployment (proposed; nothing is deployed yet)

There is no gateway, queue, load balancer, autoscaler or cluster in this project. The Day 59 and Day 60 designs say what to build, and these are the decisions they ask for:

- **Two tiers first** (Day 60): a *sync tier* (ATS, screening, interview, decision) behind a layer-7 load balancer using least-outstanding-requests, and an *async tier* (resume parsing, batch scoring) fed by one shared queue with competing consumers. In a model of the design, separating slow work from quick work cut the 99th-percentile latency of quick requests from 64-453 ms to about 6 ms at the same worker count.
- **One worker process per core;** scale by processes and replicas, not threads (measured: eight threads gave no more throughput than one).
- **Warm up before serving:** a worker reports ready only after `utils.warmup.warm_up()` (measured: the first request on a cold worker took about 1.2 s against about 4 ms).
- **Stateless workers:** no session affinity and no shared database; the only shared state is the idempotency store for job creation.
- **Memory per worker (measured):** about 154 MB if it scores resumes (scikit-learn, NumPy, SciPy), 41 MB if it parses files, 19 MB if it only scores decisions, interviews or screening. A starting container recipe is in the architecture document; it has **not** been built or run.

---

## 9. Quality, performance and operations

### 9.1 Tests

{tests['functions']:,} test functions in {tests['files']} files under `tests/`, one file per module, plain `pytest`. The Day 61 full regression: 2,017 passed, 6 skipped. Run `pytest --cov=. --cov-report=term-missing` for coverage.

**Python 3.11 and 3.12 differ in one place.** Python 3.12 made `sum()` on floats more exact, which moves a few HR scores by 0.1 at rounding boundaries. The Day 60 golden test therefore has two golden files and reads the one that matches the Python it runs on (`tests/golden/make_day60_golden.py` explains why). Never regenerate a golden file from optimised code: that compares the code with itself.

### 9.2 Performance (Day 60, measured on one shared 1-CPU machine; trust the ratios, not the milliseconds)

ATS scoring about 1.4 to 1.7 times faster, screening and HR scoring about 1.6 to 1.7 times, a repeated resume parse about 150 times; one application's compute is about 22 ms. Every answer is unchanged (golden file). Caches are keyed by content, bounded, thread-safe, never cache errors and can be switched off.

### 9.3 Observability (Day 61, designed and prototyped)

One JSON log line per event in three kinds (`api_request`, `model_output`, `error`), sharing a request id; fields are allowlisted and numbers-and-codes only. The plan has a metric catalogue, SLOs, 16 alert rules (pages only for four conditions), five dashboards with 27 panels, and a decision-audit recorder with replay. A log shipper, metrics server, alert manager and dashboard tool do **not** exist.

### 9.4 Stability tooling

`stability_checks` feeds awkward inputs (empty, huge, unicode, NaN, contradictory) into every public engine; `consistency_audit` checks invariants (raising a round score never lowers the Hiring Fit); `evaluation_harness` is the single tested confusion-matrix tool; `pipeline_simulation` runs a candidate end to end.

---

## 10. Governance and security

| Area | What is built (logic and tests) | What is missing |
|---|---|---|
| Audit | Hash-chained log, typed entries, forbidden-content refusal, decision recorder with replay | Durable storage, export pipeline |
| Retention | Per-category rules, due-action calculation, legal hold | A scheduler that executes deletions |
| Consent | Default-deny registry, per purpose, versioned, withdrawable; withdrawal triggers deletions | Real consent capture screens |
| Access | Role matrix, six contextual rules, deny by default, paid-content unlock | Tenant isolation for the service role (gap G3) |
| Storage | Six-store plan, 12 checked invariants | The stores themselves |
| Privacy in text | Resume masking (Day 15), transcript scrubbing (Day 43), no personal content in logs (Day 61) | Review by a lawyer; a bias audit on real data |

**Known gaps from the Day 59 access check (G1 to G3).** The role matrix lets the service read a resume but not write one and has no resource type for parsed fields (G1); job descriptions are not a resource type and the storage plan has no job store (G2); tenant isolation does not apply to the service role, so the token must carry the tenant and a batch must never mix tenants (G3). This is an engineering design, not legal advice.

---

## 11. Known limits and open items

**Mocked or missing, and what real use needs** (consolidated from the Day 32 handover and later days):

| Area | State | Needed |
|---|---|---|
| Speech-to-text | A mock provider behind an interface; tests build the results by hand | A real STT provider with genuine confidence scores and language tags |
| Voice calling and speech | Nothing places a call or speaks | A telephony and text-to-speech provider |
| Intent, sentiment, hesitation | Keyword and pattern rules; a small hand-picked lexicon | Trained models and validated lexicons |
| Languages | English only below the STT layer | Per-language lexicons and resources (Malayalam, Hindi, Tamil are in the PRD) |
| Location | No gazetteer: a bare place name reads as vague | A places database |
| Gaze, head movement, facial analysis | Deliberately not built (biometric, no consent infrastructure) | Legal review, consent, fairness review |
| External voice, looking away, phone use | Listed as "not implemented" in every integrity report | An audio and camera pipeline, with the same reviews |
| Running candidate code | Never done; only results and static analysis | A sandbox (container or microVM, no network, limits) |
| Weights and thresholds | Reasoned, not calibrated | Labelled hiring outcomes and a calibration study |
| Human-vs-AI agreement | 12 labelled ATS pairs only; none for the interview rounds | Real recruiter ratings |
| Gateway, queue, job store, identity | Designed (Day 59), not built | Build or choose |
| Compliance | Design and logic only (Day 43: retention and consent were "not ready" before Day 55) | Legal review; enforcement |

The Day 56 simulation, Day 57 stabilisation and Day 58 roadmap documents list the individual defects found and the prioritised improvements; the roadmap data is in `data/roadmap/day58_feature_backlog.json`.

---

## 12. Where to go next

- **New developer:** read `docs/day62_developer_onboarding_guide.md`, then `docs/CODE_STANDARDS.md`.
- **Architecture detail:** `docs/day62_system_architecture.md`.
- **Why a number is what it is:** the day's own document (appendix B) and the module docstring.

---

## Appendix A. Glossary

{table(["Term", "Meaning"], [
    ("ATS", "Applicant Tracking System: here, the resume-versus-job scoring engine."),
    ("Zone", "The ATS outcome: shortlist, review or reject."),
    ("Round", "One stage of evidence: ATS, screening, HR interview, technical interview, machine test."),
    ("Hiring Fit Score", "The 0 to 100 combination of all applicable rounds."),
    ("Provisional", "A score computed while a needed round is missing; not comparable with a complete one."),
    ("Envelope", "The fixed response shape every service returns (success or error)."),
    ("Stateless", "The service keeps nothing between requests; any worker can serve any request."),
    ("Golden file", "Recorded outputs of the code before a change, used to prove the change did not alter any answer."),
    ("Idempotency key", "A caller-chosen key that makes retrying a job creation safe."),
    ("Hash chain", "Each audit entry includes the hash of the previous one, so any edit is detectable."),
    ("Human confirmation", "A named person records a decision; required for every rejection."),
    ("STT", "Speech-to-text."),
    ("PRD phase", "One of the 100 numbered phases in the product requirements document."),
])}

## Appendix B. Document index

Every day's work has its own document in `docs/`.

{doc_index()}
"""


# ------------------------------------------------------------------------------------------------------------ architecture
def build_architecture(facts: Dict[str, Any]) -> str:
    return f"""# Zecpath AI: System Architecture

Zecpath: AI Job Portal | System architecture documentation | Built {AS_OF} (Day 62)

**Status words.** *Built* = code and tests exist. *Designed* = specified in code or a document, nothing enforces it yet. *Proposed* = a starting point to tune. *Not built* = absent. Numbers are read from the code when this document is generated.

## 1. Purpose and scope

The AI layer turns raw hiring inputs (a resume file, a job description, call turns, interview answers, execution results) into scores, explanations and a **recommendation for a person to act on**. It is the intelligence component of Zecpath. It is deliberately **not** the platform: accounts, scheduling, telephony, video, email, payments and the database belong to the backend.

**Goals the architecture serves:** explainable scores; no automated rejection; no personal content in logs; consistent contracts between services; scaling by adding replicas; the ability to change a model without changing an answer unnoticed.

**Constraints it accepts:** no trained models (no labelled outcome data exists), no real speech or video pipeline, no deployed infrastructure.

## 2. Context

![Where the AI layer sits](diagrams/day62_architecture.png)

| Neighbour | Direction | Contract |
|---|---|---|
| Zecpath backend | calls the AI layer; reads inputs; saves results and audit entries | Day 59 operations (`parse_resume`, `score_ats`, `score_ats_batch`, `score_screening`, `score_interview`, `recommend_decision`, `get_job`, `cancel_job`, `health`) |
| Speech-to-text provider | feeds call turns (text and a confidence) | `RawSTTResult` (a mock provider exists) |
| Voice / telephony provider | places calls | **not integrated**: the AI layer scores a conversation that has happened |
| Recruiters and candidates | see results through the backend | recommendation envelope, candidate-facing notice text |
| Auditors | read the audit log | hash-chained entries, replay |

## 3. Building blocks

| Block | Where | Responsibility |
|---|---|---|
| Service boundary | `utils/base_service.py` | `run()` validation, envelopes, error codes, JSON safety |
| ATS service and resume parsing | `ats_engine/` | resume x job score and zone; PDF/DOCX reading; batch scoring (process-parallel) |
| Screening service | `screening_ai/` | scores a call from turns |
| Interview service | `interview_ai/` | HR and technical answer scoring |
| Decision service | `scoring/` | Hiring Fit Score and recommendation |
| Engines | `parsers/` | all analysis logic (see the handbook's module reference) |
| Governance | `parsers/audit_trail.py`, `data_governance.py`, `access_control.py`, `secure_storage_plan.py`, `governance_framework.py`, `decision_audit.py` | audit, retention, consent, access, storage plan |
| Integration contract | `parsers/integration_contract.py`, `api/`, `schemas/` | operations, schemas, OpenAPI, error and retry rules |
| Observability | `parsers/observability.py`, `observability_plan.py` | structured logs, metrics, alert rules, dashboards |
| Performance | `utils/perf.py`, `utils/warmup.py`, `ats_engine/parallel.py` | bounded caches, warm-up, parallel batches |

Services are **independent**: no service imports another. Engines are shared libraries.

## 4. The request path

![One API call](diagrams/day62_request_lifecycle.png)

1. The caller sends a request with a scoped token (designed). The gateway checks the token and validates the body against the operation's JSON Schema, answering in the services' own error codes (designed).
2. `run(payload)` checks the payload is an object and calls `process`.
3. `process` reads fields with typed helpers (`_get_text`, `_get_list`, `_get_choice`, `_get_score`), which raise `ServiceInputError(code, message, field)`.
4. The engine computes the result; `to_json_safe` normalises it.
5. The service returns `success` or `error`. An unexpected exception becomes `internal_error`; the trace is logged, never returned.
6. An observer (prototype) records a log event of numbers and codes; the **backend** writes the audit entry. The AI layer never writes to a store.

## 5. Data flow across rounds

![Candidate journey](diagrams/day62_candidate_workflow.png)

Data moves as small dictionaries of scores and codes between rounds. The raw inputs (resume text, answers, transcripts) are read by the service that scores them and are never copied into logs or audit entries. Stores named by the Day 59 plan: `resume_store`, `job_store`, `transcript_store`, `report_store`, `audit_store`.

| Operation | Reads | Writes |
|---|---|---|
| `parse_resume` | resume file | parsed fields, audit entry |
| `score_ats`, `score_ats_batch` | parsed resume, job description | score, audit entry |
| `score_screening` | transcript turns | score, audit entry |
| `score_interview` | candidate answers | score, audit entry |
| `recommend_decision` | round scores | decision, audit entry |

## 6. Scoring architecture

![How a score becomes a recommendation](diagrams/day62_scoring_flow.png)

Each round has its own engine and 0 to 100 score; `cross_round_aggregation_engine` applies role weights (technical: {weights_line(facts['round_weights']['technical'])}; non-technical: {weights_line({k: v for k, v in facts['round_weights']['non_technical'].items() if v})}), the fresher adjustment and the missing-round rules; `final_recommendation_engine` applies the rule layer and confidence. Details and every weight are in the handbook, section 5.

## 7. Cross-cutting concerns

### 7.1 Errors
One envelope, a closed set of codes, `field` names the input at fault, `internal_error` hides internals. Gateway codes (`unauthenticated`, `forbidden`, `not_found`, `conflict`, `idempotency_conflict`, `rate_limited`, `service_unavailable`, `timeout`) are separate and carry retry advice.

### 7.2 Security (designed)
Scopes per operation, signed service tokens that carry tenant and pseudonymous actor, deny-by-default access control, paid-content unlock, TLS and encryption at rest through the storage plan. Known gaps G1 to G3 are listed in the handbook, section 10.

### 7.3 Privacy and fairness
Personal fields masked before scoring; demographic disclosures scrubbed from transcripts; verbal hesitation not used in decisions; logs and audit entries hold ids, scores and codes only.

### 7.4 Observability (designed, prototyped)
Three event kinds with a shared request id, a metrics registry with a label cap, 16 alert rules, five dashboards, a decision-audit recorder with replay.

### 7.5 Performance and scaling
Stateless workers; one process per core; warm-up before readiness; bounded content-keyed caches; process-parallel batches (`ZECPATH_BATCH_WORKERS`). Measured: scoring is cheap (about 22 ms of compute per application), so scale is about shape (redundancy, isolating slow from quick work, absorbing bursts), not raw size.

## 8. Deployment view (proposed)

| Tier | Contents | Balancing | Scaling signal |
|---|---|---|---|
| Sync | ATS, screening, interview, decision workers | layer-7, least outstanding requests | utilisation and p95 latency |
| Async | resume parsing and batch scoring workers | one shared queue, competing consumers | queue age |
| Gateway | authentication, schema checks, idempotency | n/a | request rate |
| State | job store and idempotency store (the only shared state) | n/a | n/a |

A worker is ready only after warm-up. Memory per worker: about 154 MB if it scores resumes, 41 MB if it parses files, 19 MB otherwise (measured, Day 60).

**Container recipe (not built, not run):**

{code(DOCKERFILE, 'dockerfile')}

## 9. Key design decisions

| # | Decision | Why | Day |
|---|---|---|---|
| 1 | One `run()` boundary that never raises | callers must never see internals or crash | 57 |
| 2 | Stateless AI layer | safe retries, one writer of the audit log, easy scaling | 59 |
| 3 | Rule-based scoring with visible components | no training data; explainability | 13, 26, 37, 47 |
| 4 | Missing evidence is never zero | silently punishing a candidate for a round that has not happened is unfair | 13, 51, 57 |
| 5 | Rejection is a recommendation | the costly, hard-to-reverse error is a wrongful rejection | 41, 52 |
| 6 | No camera or audio analysis | biometric data without consent infrastructure or fairness review | 48, 49 |
| 7 | Never run candidate code | needs a real sandbox; `exec()` is not one | 50 |
| 8 | Allowlisted logging | logs are an uncontrolled copy of data | 61 |
| 9 | Processes, not threads, for parallelism | pure-Python CPU work; measured | 60 |
| 10 | Golden files for optimisation | prove answers did not change | 60 |

## 10. Risks and open decisions

Choose the gateway, queue, identity provider, log shipper, metrics store, alert manager and dashboard tool; build the job store; resolve gaps G1 to G3; obtain labelled outcomes to calibrate weights; add a real STT and voice provider; commission a legal review and a bias audit before real use. Each is traced to the day that raised it in the handbook (section 11).
"""


# ------------------------------------------------------------------------------------------------------------ onboarding
def build_onboarding(facts: Dict[str, Any]) -> str:
    tests = di.count_tests()
    return f"""# Zecpath AI: Developer Onboarding Guide

Zecpath: AI Job Portal | For developers joining the AI layer | Built {AS_OF} (Day 62)

Read this first. It gets you from a clean machine to a first change in a day. The full reference is the **Technical Handbook** (`docs/day62_zecpath_ai_technical_handbook.md`); the picture is in the **System Architecture** (`docs/day62_system_architecture.md`).

## 1. What you are joining

A Python codebase of small, stateless AI services that score resumes, screening calls, interviews and machine tests and recommend a hiring decision for a person to act on. About {len(di.python_modules())} Python files and {tests['functions']:,} test functions. Almost all logic is rule-based and deterministic, with reasoned (not calibrated) weights. Nothing is deployed; there is no gateway, database or queue here.

## 2. Your first day

| Step | Do this | Time |
|---|---|---|
| 1 | Read `README.md` and `docs/CODE_STANDARDS.md` | 20 min |
| 2 | Read handbook sections 1 and 2 (overview, architecture) | 30 min |
| 3 | Set up (section 3 below) and run the sample | 30 min |
| 4 | Read `utils/base_service.py` and `ats_engine/service.py` (170 lines in total) | 20 min |
| 5 | Run one day's demo and read its document, for example Day 56 (`run_day56_full_system_simulation.py`, `docs/day56_full_system_simulation.md`) | 40 min |
| 6 | Read the handbook's scoring section (5) and the glossary | 30 min |
| 7 | Pick a starter task (section 9) | rest of day |

## 3. Set up

Prerequisites: Python 3.11, Git.

{code(ONB_SETUP, 'bash')}

Check it works:

{code(ONB_CHECK, 'bash')}

If `pytest` is not available (some locked-down machines), `regression_runner.py` runs test modules without it; edit its module list at the bottom.

**Watch for these on a new machine**

- `requirements.txt` now lists scikit-learn, pdfplumber and python-docx (it did not before Day 62); if an import fails, reinstall.
- **Python 3.12 gives HR scores that differ by 0.1** from 3.11 at rounding boundaries (a float `sum()` change). The golden test handles both; do not "fix" a 0.1 difference.
- `venv/`, logs and real data are gitignored; do not commit them.

## 4. A tour of the repository

{code(ONB_TREE)}

To find a module, use the module reference in the handbook (section 3): it lists every file with what it does and the PRD phase it serves.

## 5. Ten ideas to hold in your head

1. **Call `run()`, never `process()`.** `run()` never raises and always returns an envelope with `status` of `success` or `error`.
2. **Services are stateless and never touch a database.** The backend saves results.
3. **Services never import each other.** Engines in `parsers/` are shared libraries.
4. **Every score shows its working:** components, weights, contributions, reasons.
5. **Missing is not zero.** A missing section redistributes weight; a missing round makes the result provisional.
6. **A rejection is only a recommendation.** Never write code that rejects automatically; `human_confirmation_required` must be true.
7. **No personal content in logs or audit entries** (text, answers, names, emails, transcripts). Log numbers and codes.
8. **Do not claim a capability that does not exist.** If a signal cannot be observed, say "not implemented" in the output, as the integrity report does.
9. **Weights are reasoned, not calibrated.** Say so when you change one.
10. **Change behaviour deliberately.** A test that fails after a scoring change is the system working; read why before touching the test.

## 6. Follow one request

`ATSService().run({{"resume_text": ..., "job_description": ...}})`

1. `BaseAIService.run` checks the payload is a dictionary and calls `process`.
2. `ATSService.process` reads the fields (`_get_text`, `_get_list`) and picks the mode: with a `job_description` it is the real engine (`scoring_mode: ats_engine`); with only `job_requirements` it is the **deprecated** keyword-coverage mode, which is **not comparable** with an engine score.
3. It normalises resume headings (a resume headed "Technical Skills" must not score as having none), fits TF-IDF on exactly this resume and job description, and calls `score_candidate`.
4. The result carries `ats_score`, `zone` and the four components; `to_json_safe` makes it JSON-safe.
5. Any bad input raised as `ServiceInputError` becomes an error envelope with `code` and `field`.

## 7. How work is done here

Each day's task produces the same set of things. Follow the pattern.

| Piece | Naming | Notes |
|---|---|---|
| Module | `parsers/<topic>.py` (or a service folder) | starts with a docstring: what it implements, input contract, output contract, and what it does **not** do |
| Tests | `tests/test_<module>.py` | one file per module; a normal case and an edge case per function |
| Demo | `run_dayNN_<topic>_demo.py` | reproduces the day's numbers; writes `logs/dayNN_*.log` and `data/results/*.json` |
| Document | `docs/dayNN_<topic>.md` | separates what is built, measured, proposed and not built |
| Regression | run the full suite before you finish | record the result in the day's document |

**Style** (`docs/CODE_STANDARDS.md`): PEP 8, `black` and `flake8` (maximum line length 100), type hints on signatures, `snake_case` names, `PascalCase` classes, `UPPER_SNAKE_CASE` constants, `get_logger(__name__)` instead of `print`, commit messages as `<area>: <short description>`.

## 8. Recipes

### 8.1 Add a new service
1. Create the folder with `__init__.py` and `service.py`.
2. Subclass `BaseAIService`, implement `process()`, return `self._base_response()` plus your fields.
3. Raise `ServiceInputError(code, message, field)` for bad input; use the typed helpers for fields.
4. Write `tests/test_<service>.py`, and add the service to the contract tests.
5. Add the operation to `parsers/integration_contract.py`, then run `python run_day59_integration_demo.py` to regenerate `schemas/integration_api_schemas.json` and `api/integration_openapi.yaml`. A test fails if those files differ from what the code generates.
6. Add the new modules to `parsers/documentation_index.py` (`MODULE_CATALOGUE`), or the Day 62 test fails.

### 8.2 Change a weight or threshold
1. Find the constant (the handbook's scoring section names the module; the numbers are read from the code).
2. Change it, and expect tests and the golden test to fail: they pin behaviour on purpose.
3. Decide whether the new answers are right. If yes, update the tests that pin the old values and say why in the day's document. **Never regenerate the golden files from changed code**: they were generated from the pre-optimisation code so that an optimisation can be proven not to change answers. A deliberate behaviour change needs a new, clearly labelled golden file.
4. Say in the document that the number is reasoned, not calibrated.
5. Re-run `python run_day62_handbook.py` so the handbook shows the new value.

### 8.3 Add a skill or a question
Skills: add to `parsers/skill_dictionary.py` (grouped by domain, with aliases), then run `tests/test_skill_extractor.py`. Questions: add to the relevant bank (`screening_question_bank`, `hr_interview_question_bank`, `technical_interview_question_bank`) with its category and expected key concepts, then run that bank's test file.

### 8.4 Debug a request
1. Reproduce with `Service().run(payload)` and read `status` and `error`.
2. `error.field` names the input at fault; `internal_error` means a bug: read `logs/zecpath_ai.log` for the full trace.
3. For a surprising score, look at the components, weights and warnings in the response before reading code.
4. Use `parsers/stability_checks.py` patterns to turn the failing input into a permanent edge-case test.

## 9. Pitfalls found the hard way

| Pitfall | What happens | Source |
|---|---|---|
| Interview answers are matched **in order** to the questions the service asks | a good answer to a different question scores 0. For a technical interview the first question is "tell me about your technical background", so an answer about React internals sent first scores 0. Send answers in the order the questions are asked | `interview_ai/service.py` |
| Extra answers beyond the question count | ignored, with a warning | `interview_ai/service.py` |
| Keyword-coverage mode of the ATS | looks like a score but is only the percentage of keywords found | `ats_engine/service.py` |
| Resume with unusual section headings | skills invisible; the readiness check tells a candidate when the system cannot read their resume | Day 57, Day 58 |
| A score of 0.0 from an engine | may mean "nothing to score", not a real zero; the aggregation reads the evidence and reports the round as missing | Day 51 |
| Technical roles with no machine test | never `selected` or `rejected` on partial evidence | Day 57 |
| `behavior_score` and `communication_score` keys | legacy: `behavior_score` is ignored with a warning, `communication_score` is an alias for `hr_interview_score` | `scoring/service.py` |
| Python 3.12 vs 3.11 | HR scores can differ by 0.1 | Day 60 |
| Missing install lines | fixed in Day 62 | `requirements.txt` |

## 10. Starter tasks

1. Run `run_day56_full_system_simulation.py` and read the "inconsistencies found" section of its document.
2. Add an edge-case test for an input you think could break an engine (see `tests/test_edge_case_sweep.py`).
3. Pick a limit from the handbook's section 11 and read its day's document to see how it was found.
4. Fix a documentation gap: if a module's docstring is missing a contract line, add it.

## 11. Rules of the road (checklist before you commit)

- [ ] Module docstring states what it implements, its input contract, its output contract and its limits
- [ ] Type hints; `black` and `flake8` clean
- [ ] No `print`; logging through `get_logger`
- [ ] No personal content in any log or audit entry
- [ ] No service imports another service
- [ ] A test file for the module, normal and edge cases
- [ ] Full test suite passes; result recorded in the day's document
- [ ] Any new weight or threshold labelled as reasoned or calibrated
- [ ] `parsers/documentation_index.py` updated for a new module; `python run_day62_handbook.py` re-run
- [ ] Commit message `<area>: <short description>`

## 12. Glossary

See the handbook, appendix A. The most-used words: *ATS*, *zone*, *round*, *Hiring Fit Score*, *provisional*, *envelope*, *stateless*, *golden file*, *human confirmation*.
"""


# ------------------------------------------------------------------------------------------------------------ main
def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    facts = di.live_facts()
    ex = run_examples()
    handbook = build_handbook(facts, ex)
    write(HANDBOOK, handbook)
    write(ARCHITECTURE, build_architecture(facts))
    write(ONBOARDING, build_onboarding(facts))
    tests = di.count_tests()
    report = {
        "as_of": AS_OF,
        "python_files": len(di.python_modules()),
        "catalogued_modules": len(di.MODULE_CATALOGUE),
        "uncatalogued": di.uncatalogued(),
        "stale_entries": di.stale_entries(),
        "test_files": tests["files"],
        "test_functions": tests["functions"],
        "docs_in_repo": len(list(DOCS.glob("*.md"))),
        "prd_groups": len(di.PRD_COVERAGE),
        "handbook_words": len(handbook.split()),
        "diagrams": DIAGRAMS,
    }
    write(REPORT, json.dumps(report, indent=2))
    for p in (HANDBOOK, ARCHITECTURE, ONBOARDING):
        print(f"wrote {p.relative_to(ROOT)}  ({len(p.read_text(encoding='utf-8').split())} words)")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
