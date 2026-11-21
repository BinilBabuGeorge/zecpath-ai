"""
Documentation index (Day 62): the module catalogue, the PRD coverage map and the live numbers behind the handbook

WHAT THIS DAY BUILDS. Day 62 asks for one structured technical handbook for the whole AI system. A handbook written by hand goes
stale the first time a weight or a module changes, so this module keeps the parts that CAN be checked as data, and
`run_day62_handbook.py` writes the documents from it:

  1. MODULE_CATALOGUE  one entry per Python module (layer, what it does, which PRD phases it serves). A test fails if a module
                       exists that is not listed here, or a listed module no longer exists, so the handbook cannot silently miss
                       a new file.
  2. PRD_COVERAGE      for every PRD phase group: what this repository implements, what it only designs, and what it does not do.
  3. live_facts()      the weights, thresholds, retention periods, API operations and error rules, READ FROM THE CODE at the time the
                       handbook is built. They are never typed a second time, so the handbook cannot disagree with the code, and a
                       test compares the written document with these values.

Input contract:  none (reads the source tree and imports the engines).
Output contract: plain dicts, lists and strings; no file is written here.

WHAT IT IS NOT. Layer assignment and the one-line purposes are written by hand (an author's judgement, checked only for presence).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent

# Layer ids, in reading order, with the title used in the handbook.
LAYERS: Dict[str, str] = {
    "A": "Foundation (shared code every service uses)",
    "B": "Resume and job-description understanding",
    "C": "ATS scoring, ranking and eligibility",
    "D": "Voice screening call",
    "E": "HR interview",
    "F": "Technical interview, machine test, behaviour and integrity",
    "G": "Aggregation, final recommendation and reporting",
    "H": "Governance, audit and security",
    "I": "Integration, operations and quality tooling",
    "S": "Services (the stable API boundary)",
}

# path -> (layer, what it does, PRD phases it serves or "-")
MODULE_CATALOGUE: Dict[str, Tuple[str, str, str]] = {
    # ---- S: services -------------------------------------------------------------------------------------------------------
    "ats_engine/service.py": ("S", "ATSService: scores one resume against one job description; returns score, zone and components.", "2"),
    "ats_engine/batch_service.py": ("S", "ATSBatchService: one job description, many resumes, one independent result per candidate.", "2"),
    "ats_engine/parallel.py": ("S", "Process-based parallel batch scoring (threads cannot speed up pure-Python CPU work).", "2"),
    "ats_engine/resume_parsing_service.py": ("S", "ResumeParsingService: reads a PDF/DOCX and returns text, skills, experience, education; no name, email or phone.", "1, 2"),
    "screening_ai/service.py": ("S", "ScreeningService: scores a screening-call conversation that has already happened.", "5"),
    "interview_ai/service.py": ("S", "InterviewIntelligenceService: scores HR and technical interview answers.", "15, 16, 37-40"),
    "scoring/service.py": ("S", "DecisionScoringService: combines round scores into a hiring-fit score and a recommendation.", "20, 45, 70, 71"),
    # ---- A: foundation -----------------------------------------------------------------------------------------------------
    "utils/base_service.py": ("A", "BaseAIService: the run() boundary that never raises, the response envelope and the error codes.", "-"),
    "utils/config.py": ("A", "Environment-driven settings (ZECPATH_ENV, service name, model version, placeholders for storage and queue).", "-"),
    "utils/logger.py": ("A", "get_logger(): console plus rotating file log in logs/zecpath_ai.log.", "-"),
    "utils/perf.py": ("A", "BoundedLRU cache and the switch (ZECPATH_CACHE) used by every Day 60 optimisation.", "-"),
    "utils/warmup.py": ("A", "Loads the heavy parts once at start so the first request is not slow.", "-"),
    # ---- B: resume and JD understanding --------------------------------------------------------------------------------------
    "parsers/resume_extractor.py": ("B", "Reads a PDF or DOCX file, returns clean text; refuses empty, corrupt or unsupported files.", "1, 2"),
    "parsers/resume_parser.py": ("B", "Thin shared entry point to the resume extraction helpers.", "2"),
    "parsers/section_classifier.py": ("B", "Tags each resume line with its section (skills, experience, education ...).", "2"),
    "parsers/section_extractor.py": ("B", "Pulls the skills / experience / responsibilities blocks out of resume and JD text.", "2"),
    "parsers/skill_dictionary.py": ("B", "Master skill list grouped by domain (tech, business, creative) with aliases.", "2"),
    "parsers/skill_extractor.py": ("B", "Finds skills in resume or JD text using the dictionary.", "2"),
    "parsers/experience_parser.py": ("B", "Parses the experience section into dated entries and total years.", "2"),
    "parsers/experience_relevance.py": ("B", "Scores how relevant the work history is to the target job title.", "2"),
    "parsers/education_dictionary.py": ("B", "Degree and certification vocabularies.", "2"),
    "parsers/education_parser.py": ("B", "Parses degrees and certifications from the education section.", "2"),
    "parsers/education_relevance.py": ("B", "Scores how well the education fits the target level.", "2"),
    "parsers/jd_parser.py": ("B", "Turns a raw job description into required skills, experience and responsibilities.", "1, 2"),
    "parsers/semantic_matcher.py": ("B", "TF-IDF cosine similarity between resume and job description (not a neural model).", "2"),
    "parsers/fairness_engine.py": ("B", "Normalises resume text, masks personal fields, damps keyword stuffing, reports bias indicators.", "2"),
    # ---- C: ATS scoring ---------------------------------------------------------------------------------------------------
    "parsers/ats_scoring_engine.py": ("C", "The ATS formula: four weighted components, weight redistribution when a section is missing.", "2"),
    "parsers/ranking_engine.py": ("C", "Ranks candidates and assigns the shortlist / review / reject zone with per-category cutoffs.", "2, 3"),
    "parsers/eligibility_engine.py": ("C", "Hard gates first (mandatory skills, experience floor), then the zone: who may receive a screening call.", "3"),
    "parsers/scoring_calibration.py": ("C", "Opt-in alignment of the ATS score to the common scale (the aggregate still defaults to the raw score).", "70"),
    "parsers/resume_readiness.py": ("C", "Prototype: tells a candidate whether the system can read their resume.", "-"),
    # ---- D: screening call ------------------------------------------------------------------------------------------------
    "parsers/screening_question_bank.py": ("D", "The screening questions (introduction, education, experience, skills, location, notice period, salary).", "5"),
    "parsers/transcript_schema.py": ("D", "Data model of a call: CallSession, TranscriptTurn, NormalizedAnswer; matches schemas/transcript_schema.sql.", "5"),
    "parsers/speech_to_text.py": ("D", "Speech-to-text provider interface and transcript cleaning (a mock provider; no real STT yet).", "5"),
    "parsers/answer_intent_engine.py": ("D", "Understands an answer: which category it addresses, quality, extracted value (rule-based).", "5"),
    "parsers/screening_scoring_engine.py": ("D", "Scores a call on clarity, relevance, completeness and consistency.", "5"),
    "parsers/confidence_sentiment_engine.py": ("D", "Text signals: hesitation, sentiment and confidence cues.", "5, 16"),
    "parsers/screening_report_generator.py": ("D", "Turns a scored call into a recruiter-readable screening report.", "5"),
    "parsers/conversation_flow_engine.py": ("D", "State machine for the call: ask, re-ask, clarify, end; fixed message templates.", "5"),
    "parsers/edge_case_handler.py": ("D", "Poor audio, language mismatch and crash safety for the call flow.", "5"),
    "parsers/screening_pipeline.py": ("D", "Runs the whole screening chain start to finish: run_screening_call().", "5"),
    # ---- E: HR interview --------------------------------------------------------------------------------------------------
    "parsers/hr_interview_question_bank.py": ("E", "HR question bank by role type and experience level; InterviewSession state.", "15"),
    "parsers/hr_followup_engine.py": ("E", "Decides when a follow-up is needed and what kind.", "15"),
    "parsers/communication_skill_engine.py": ("E", "Per-answer communication score: fluency, grammar, vocabulary, structure (text only).", "16"),
    "parsers/confidence_stress_engine.py": ("E", "Per-answer confidence and stress indicators from text.", "16, 18"),
    "parsers/hr_interview_scoring_engine.py": ("E", "HR score: relevance 35%, communication 25%, confidence 25%, consistency 15%.", "16, 20"),
    "parsers/aptitude_logic_engine.py": ("E", "Logic puzzles and situational-judgement questions with scoring.", "17"),
    "parsers/interview_summary_generator.py": ("E", "Strengths, weaknesses, culture-fit indicators, risk flags and a narrative.", "24"),
    "parsers/hr_interview_simulation.py": ("E", "Scripted HR interviews to validate the whole HR chain.", "-"),
    "parsers/hr_interview_finalization.py": ("E", "HR interview wrap-up: demo and readiness checks.", "-"),
    "parsers/unified_scoring_engine.py": ("E", "Day 41 three-round score (ATS, screening, HR); kept; the five-round engine extends it.", "20"),
    "parsers/transcript_demographic_scrubber.py": ("E", "Removes volunteered demographic disclosures from answers before storage or scoring.", "25"),
    # ---- F: technical, machine test, behaviour, integrity ---------------------------------------------------------------------
    "parsers/technical_interview_question_bank.py": ("F", "Technical questions by domain and experience tier; TechnicalInterviewSession.", "37, 38"),
    "parsers/technical_skill_scoring_engine.py": ("F", "Technical score: accuracy 40%, depth 20%, reasoning 20%, real-world 20%.", "40, 44"),
    "parsers/behavioral_signal_engine.py": ("F", "Non-invasive behaviour signals from timing and text; no camera analysis.", "18, 41"),
    "parsers/integrity_detection_engine.py": ("F", "Integrity tag from tab-switch and focus-loss events; unobservable signals are listed as not implemented.", "19, 42"),
    "parsers/machine_test_evaluation_engine.py": ("F", "Scores machine-test attempts from execution results and static code analysis; never runs candidate code.", "62-69"),
    # ---- G: aggregation, decision, reporting ----------------------------------------------------------------------------------
    "parsers/cross_round_aggregation_engine.py": ("G", "Five-round Hiring Fit Score with role weights, fresher adjustment, sensitivity and flags.", "70"),
    "parsers/final_recommendation_engine.py": ("G", "Selected / hold_review / rejected with confidence and rule trace; a rejection is never automatic.", "45, 71"),
    "parsers/hiring_report_generator.py": ("G", "One recruiter-facing report from all round results.", "24, 47, 49"),
    # ---- H: governance ------------------------------------------------------------------------------------------------------
    "parsers/audit_trail.py": ("H", "Append-only hash-chained audit log; refuses personal content and automated rejections.", "25, 50"),
    "parsers/data_governance.py": ("H", "Retention rules per data category and the consent registry (default deny).", "25, 50"),
    "parsers/access_control.py": ("H", "Role matrix and contextual rules, deny by default; paid-content unlock flag.", "23, 25, 48"),
    "parsers/secure_storage_plan.py": ("H", "Six-store storage plan and 12 invariants it is checked against.", "22, 43"),
    "parsers/governance_framework.py": ("H", "One call that applies access, consent, retention and audit in order.", "25, 50"),
    "parsers/decision_audit.py": ("H", "Decision-audit recorder: inputs entry, result entry, replay and completeness check.", "25, 50"),
    # ---- I: integration, operations, quality ---------------------------------------------------------------------------------
    "parsers/integration_contract.py": ("I", "API catalogue, JSON Schemas, OpenAPI, error rules, retry and idempotency logic.", "-"),
    "parsers/observability.py": ("I", "Structured logger with allowlist and privacy guard, metrics registry, service observer.", "9, 10"),
    "parsers/observability_plan.py": ("I", "Metric catalogue, SLOs, alert rules and engine, dashboard definitions.", "9, 10"),
    "parsers/scaling_model.py": ("I", "Queueing and capacity model used by the scalability strategy.", "-"),
    "parsers/pipeline_simulation.py": ("I", "Runs a candidate through the real engines from file to report.", "-"),
    "parsers/stability_checks.py": ("I", "Edge-case sweep and output sanity checks over every public engine.", "-"),
    "parsers/consistency_audit.py": ("I", "Property checks that the aggregate, decision and ATS alignment must satisfy.", "-"),
    "parsers/evaluation_harness.py": ("I", "The one tested confusion-matrix and threshold-analysis tool.", "-"),
    "parsers/roadmap_planner.py": ("I", "Keeps the Day 58 roadmap data consistent and ordered.", "-"),
    "parsers/documentation_index.py": ("I", "Module catalogue, PRD coverage map and live numbers the handbook is generated from.", "-"),
}

# (PRD phase group, status, what the repository holds, what is not here)
PRD_COVERAGE: List[Tuple[str, str, str, str]] = [
    ("1  Job portal foundation", "Partly", "Resume file reading (PDF, DOCX) and job-description parsing.",
     "Company registration, dashboards, job posting UI, candidate accounts, DOC files: backend and frontend work."),
    ("2  AI ATS", "Built", "Parsing, four-component scoring, ranking, zones, fairness masking, batch scoring.",
     "A trained model: scoring is rule-based and TF-IDF, with reasoned (not calibrated) weights."),
    ("3  Eligibility and call trigger", "Partly", "Eligibility engine: hard gates, then zone.",
     "Call windows, retries, scheduling: backend work."),
    ("4  AI voice calling", "Not built", "Nothing places a call. Speech-to-text is a mock provider behind an interface.",
     "Telephony (for example Twilio), text-to-speech, voice and language selection."),
    ("5  Screening conversation", "Built", "Question bank, flow state machine, answer understanding, scoring, report.",
     "Generated speech and real audio; answers arrive as text turns."),
    ("6-8  Scheduling, reminders, notifications", "Not here", "-", "Backend, calendar and messaging integration."),
    ("9  Recruiter dashboard and analytics", "Designed", "Hiring report generator; observability dashboard definitions.", "Any user interface."),
    ("10  Admin, security, compliance", "Designed", "Audit log, retention, consent, access rules, storage plan: logic and tests.",
     "Enforcement infrastructure: database, key service, login, intake screens."),
    ("11-13  Video infrastructure, camera checks, instructions", "Not built", "-", "Browser and WebRTC client work."),
    ("14  Voice personality and cloning", "Not built", "-", "Voice provider; consent infrastructure."),
    ("15-17  HR questions, communication, aptitude", "Built", "Question bank, follow-ups, text-based communication scoring, aptitude engine.",
     "Audio features (pace, tone) need an audio pipeline."),
    ("18  Facial expression and behaviour", "Replaced", "Non-invasive timing and text signals (Day 48).",
     "Gaze, head movement and facial analysis were deliberately not built (biometric, no consent infrastructure)."),
    ("19  Malpractice and integrity", "Partly", "Tab-switch and focus-loss events.",
     "External voice, looking away and phone use are listed as not implemented in every report."),
    ("20-21  Scoring, decision, selection mail", "Partly", "Scoring and decision engines; candidate-facing notice text.", "Sending mail."),
    ("22  Recording and secure storage", "Designed", "Storage plan with checked invariants.", "The storage itself."),
    ("23-24  Paid access, recruiter review", "Partly", "Paid-content unlock rule in access control; summary and report generators.", "Payments and the review UI."),
    ("25  Compliance and consent", "Designed", "Consent registry, retention rules, audit trail.", "Legal review; real consent capture."),
    ("26-50  Second round and technical interview", "Partly", "Technical question bank, scoring, aggregation, final recommendation, report.",
     "Calls, emails, video, interviewer voice."),
    ("51-75  Machine test", "Partly", "Evaluation of execution results and static code analysis.",
     "A sandboxed runner, live editor and screen recording."),
    ("76-90  Final round and salary negotiation", "Not built", "-", "Negotiation engine, market benchmarks, final interview."),
    ("91-100  Offer and onboarding", "Not built", "-", "Offer letters, acceptance tracking."),
]


def python_modules() -> List[str]:
    """Every Python module of the AI layer (services, utils, parsers), as repo-relative paths."""
    found: List[str] = []
    for folder in ("ats_engine", "screening_ai", "interview_ai", "scoring", "utils", "parsers"):
        for path in sorted((ROOT / folder).glob("*.py")):
            if path.name != "__init__.py":
                found.append(f"{folder}/{path.name}")
    return found


def line_count(rel_path: str) -> int:
    """Number of lines in a module."""
    return len((ROOT / rel_path).read_text(encoding="utf-8", errors="ignore").splitlines())


def uncatalogued() -> List[str]:
    """Modules on disk with no catalogue entry."""
    return [m for m in python_modules() if m not in MODULE_CATALOGUE]


def stale_entries() -> List[str]:
    """Catalogue entries whose file no longer exists."""
    return [m for m in MODULE_CATALOGUE if not (ROOT / m).exists()]


def module_docstring_head(rel_path: str) -> str:
    """The first line of a module's docstring (used to point a reader at the source of truth)."""
    tree = ast.parse((ROOT / rel_path).read_text(encoding="utf-8", errors="ignore"))
    return (ast.get_docstring(tree) or "").strip().split("\n")[0]


def count_tests() -> Dict[str, int]:
    """Test files and test functions found by reading tests/ (no test is run)."""
    files = sorted((ROOT / "tests").glob("test_*.py"))
    total = 0
    for f in files:
        total += sum(1 for line in f.read_text(encoding="utf-8", errors="ignore").splitlines() if line.lstrip().startswith("def test_"))
    return {"files": len(files), "functions": total}


def live_facts() -> Dict[str, Any]:
    """Weights, thresholds, retention, API and error rules read from the engines at call time."""
    from parsers import access_control, data_governance, integration_contract, ranking_engine
    from parsers import cross_round_aggregation_engine as agg
    from parsers import final_recommendation_engine as fin
    from parsers import hr_interview_scoring_engine as hr
    from parsers import technical_skill_scoring_engine as tech
    from parsers.ats_scoring_engine import WEIGHT_PROFILES
    from utils.base_service import API_VERSION, MAX_ITEMS, MAX_TEXT_CHARS

    hr_w = hr.WeightConfig()
    return {
        "ats_weights": {k: dict(v) for k, v in WEIGHT_PROFILES.items()},
        "ats_thresholds_default": dict(ranking_engine.DEFAULT_THRESHOLDS),
        "ats_thresholds_category": {k: dict(v) for k, v in ranking_engine.CATEGORY_THRESHOLDS.items()},
        "round_weights": {r.value: dict(w) for r, w in agg.ROLE_WEIGHT_PROFILES.items()},
        "fresher_multipliers": {lvl.value: dict(m) for lvl, m in agg.EXPERIENCE_MULTIPLIERS.items()},
        "selected_threshold": agg.SELECTED_THRESHOLD,
        "hold_threshold": agg.HOLD_THRESHOLD,
        "borderline_margin": agg.BORDERLINE_MARGIN,
        "disagreement_spread": agg.DISAGREEMENT_SPREAD,
        "hr_weights": {"relevance": hr_w.relevance, "communication": hr_w.communication, "confidence": hr_w.confidence, "consistency": hr_w.consistency},
        "technical_weights": {"accuracy": tech._ACCURACY_WEIGHT, "depth": tech._DEPTH_WEIGHT, "logical_reasoning": tech._LOGICAL_REASONING_WEIGHT,
                              "real_world": tech._REAL_WORLD_WEIGHT},
        "machine_test_weights": {k: dict(v) for k, v in __import__("parsers.machine_test_evaluation_engine", fromlist=["x"]).TYPE_WEIGHTS.items()},
        "retention": [(r.category.value, r.days, r.action.value, r.trigger.value) for r in data_governance.DEFAULT_RULES],
        "operations": [(o.op_id, o.method, f"{integration_contract.API_PREFIX}{o.path}", o.mode.value, o.scope or "none", o.timeout_s,
                        o.implementation or "(gateway, planned)") for o in integration_contract.OPERATIONS],
        "error_rules": [(e.code, e.http_status, e.source, e.max_retries) for e in integration_contract.ERROR_RULES.values()],
        "job_states": list(integration_contract.JOB_STATES),
        "roles": [r.value for r in access_control.Role],
        "resource_types": [r.value for r in access_control.ResourceType],
        "paid_types": sorted(t.value for t in access_control.PAID_TYPES),
        "api_version": API_VERSION,
        "max_text_chars": MAX_TEXT_CHARS,
        "max_items": MAX_ITEMS,
        "outcomes": [o.value for o in fin.DecisionOutcome],
    }
