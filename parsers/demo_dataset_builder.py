"""
Demo dataset builder (Day 63): turns the personas into the files of `data/demo_dataset/`

    python run_day63_demo_dataset.py        (builds the dataset, then runs the end-to-end environment on it)

WHAT IT WRITES (all under data/demo_dataset/, all synthetic; see demo_dataset_content.py):
  jobs/                     6 job descriptions (text) and jobs.json (the structured list)
  resumes/                  30 resumes as the files the real upload path accepts (DOCX or PDF)
  resumes_text/             the same 30 resumes as plain text, for reading
  edge_files/               4 files the upload path must refuse politely (corrupt, empty, legacy .doc, unsupported type)
  candidates.json           one record per candidate: scenario, job, resume file, the author's EXPECTED outcome and why
  responses/                screening, HR and technical answers (what each candidate says)
  machine_test/             the two tasks and each candidate's attempts (code snapshots and execution results)
  integrity/                browser events (tab and focus changes) for the candidates who have any
  manifest.json             counts and the checksums of the text resumes

NO SIMULATED SCORES ARE WRITTEN HERE. The ATS results, screening scores, interview scores and decisions come from running the REAL engines
on these files (`parsers/demo_environment.py`). This module only writes INPUTS.

MACHINE-TEST RESULTS ARE REAL EXECUTIONS OF THE AUTHOR'S OWN CODE. Each candidate's code snapshots (authored by us, in five qualities from
strong to broken) are executed here against the task's test cases, so "case passed / failed" is the code's real behaviour. The runtimes are
fixed multiples of a reference runtime (not measured), so the dataset is identical on every machine. The scoring engine itself never runs
candidate code (Day 50); this builder runs only code written for this dataset.

Input contract:  none (reads demo_dataset_content / demo_dataset_answers).
Output contract: files on disk and a summary dict returned by build_dataset().
"""

from __future__ import annotations

import copy
import hashlib
import json
import textwrap
import zlib
from pathlib import Path
from typing import Any, Dict, List, Tuple

from parsers import demo_dataset_answers as ans
from parsers.demo_dataset_content import AS_OF_ISO, JOBS, PERSONAS

ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = ROOT / "data" / "demo_dataset"
JOB_BY_ID = {j["id"]: j for j in JOBS}


# --------------------------------------------------------------------------------------------------------------------------- resumes
def _slug(text: str) -> str:
    return "".join(c.lower() if c.isalnum() else "_" for c in text).strip("_")


def _email(p: Dict[str, Any]) -> str:
    parts = [_slug(x) for x in p["name"].split()]
    return f"{parts[0]}.{parts[-1]}@example.com"


def _phone(p: Dict[str, Any]) -> str:
    return "+91-90000-%05d" % (2000 + int(p["id"].split("-")[1]))


def _experience_lines(p: Dict[str, Any]) -> List[str]:
    lines = []
    for title, company, start, end, what in p["experience"]:
        lines.append(f"- {title}, {company} ({start} - {end or 'Present'})")
        lines.append(f"  {what}")
    return lines


def render_resume_text(p: Dict[str, Any]) -> str:
    """The resume as text, in the persona's layout style."""
    style = p["style"]
    head = [f"Name: {p['name']}"]
    if style == "bias_header":
        head += ["Gender: Male", "Date of Birth: 3 March 2001", "Marital Status: Single", "Religion: Hindu", "Nationality: Indian",
                 "Father's Name: Mahesh Bhandari", "Photo: attached"]
    head += [f"Designation: {p['designation']}", f"Location: {p['city']}, India", f"Email: {_email(p)}", f"Phone: {_phone(p)}"]
    edu = [f"- {d}, {inst}, {yr}" for d, inst, yr in p["education"]]
    if style in ("no_headings", "typos"):
        body = [f"{p['summary']}", ""]
        body.append("Technologies I work with: " + ", ".join(p["skills"]) + ".")
        body.append("")
        for title, company, start, end, what in p["experience"]:
            body.append(f"{title} at {company} from {start} to {end or 'now'}. {what}")
        body.append("")
        body += [f"Studied {d} at {inst} ({yr})." for d, inst, yr in p["education"]]
        body += [f"Certified: {c}." for c in p["certs"]]
        return "\n".join(head + [""] + body) + "\n"
    out = list(head) + [""]
    if style != "minimal":
        out += ["Summary:", p["summary"], ""]
    out.append("Skills: " + ", ".join(p["skills"]))
    if style == "stuffed":
        out += ["Technologies: " + ", ".join(p["skills"]), "Keywords: " + ", ".join(p["skills"]), ""]
    else:
        out.append("")
    out += ["Experience:"] + _experience_lines(p) + ["", "Education:"] + edu
    if p["certs"]:
        out += ["", "Certifications:"] + [f"- {c}" for c in p["certs"]]
    return "\n".join(out) + "\n"


def write_docx(text: str, path: Path) -> None:
    from datetime import datetime
    from docx import Document

    if path.exists():                                            # keep the existing file when its words are unchanged (DOCX bytes carry timestamps)
        try:
            if [para.text for para in Document(str(path)).paragraphs] == text.splitlines():
                return
        except Exception:                                        # an unreadable file is simply rewritten
            pass
    doc = Document()
    for line in text.splitlines():
        doc.add_paragraph(line)
    stamp = datetime(2026, 11, 21, 9, 0, 0)
    props = doc.core_properties
    props.author, props.last_modified_by, props.created, props.modified, props.title = "Demo dataset (synthetic)", "Demo dataset (synthetic)", stamp, stamp, "Resume"
    doc.save(str(path))


def _pdf_escape(line: str) -> bytes:
    return line.encode("latin-1", "replace").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def write_pdf(text: str, path: Path) -> None:
    """A small dependency-free PDF writer (Helvetica 10 pt, A4, text only). Deterministic bytes; real PDF text extraction reads it back."""
    wrapped: List[str] = []
    for raw in text.splitlines():
        wrapped += textwrap.wrap(raw, 92, subsequent_indent="  ") or [""]
    per_page = 58
    pages = [wrapped[i:i + per_page] for i in range(0, len(wrapped), per_page)] or [[]]
    objects: List[bytes] = []
    n_pages = len(pages)
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(n_pages))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for i, lines in enumerate(pages):
        content_id = 5 + 2 * i
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>".encode())
        stream = b"BT /F1 10 Tf 14 TL 40 800 Td\n" + b"".join(b"(" + _pdf_escape(line) + b") Tj T*\n" for line in lines) + b"ET"
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))


# --------------------------------------------------------------------------------------------------------------------------- machine test
def execute_cases(code: str, function: str, cases: List[Tuple[str, bool, List[Any], Any]]) -> Tuple[bool, List[Tuple[str, bool]], str]:
    """Really run an authored solution against the task's cases. Returns (compile_error, [(case_id, passed)], stderr_text)."""
    try:
        compiled = compile(code, "solution.py", "exec")
    except SyntaxError as exc:
        return True, [], f"SyntaxError: {exc.msg} (solution.py, line {exc.lineno})"
    namespace: Dict[str, Any] = {}
    try:
        exec(compiled, namespace)                                # authored dataset code only: never a candidate's code
    except Exception as exc:                                    # pragma: no cover - authored code defines functions only
        return True, [], f"{type(exc).__name__}: {exc}"
    results = []
    first_error = ""
    for case_id, _visible, args, expected in cases:
        try:
            got = namespace[function](*copy.deepcopy(args))
            results.append((case_id, got == expected))
        except Exception as exc:
            results.append((case_id, False))
            first_error = first_error or f"{type(exc).__name__}: {exc}"
    return False, results, first_error


def _jitter(candidate_id: str, salt: str) -> float:
    """A fixed pseudo-random number in [0, 1) from the ids, so the dataset is identical on every machine."""
    return (zlib.crc32(f"{candidate_id}:{salt}".encode()) % 1000) / 1000.0


def build_attempt(candidate_id: str, task: Dict[str, Any], variant: str) -> Dict[str, Any]:
    """One candidate's attempt at one task: snapshots, runs (with real pass/fail results) and the finishing time."""
    shape = ans.SHAPES[variant]
    limit = float(task["time_limit_seconds"])
    finish = round(min(shape["finish"], 0.99) * limit, 1)
    steps = shape["path"]
    times = [round(0.10 * limit, 1)] + [round((0.10 + (shape["finish"] - 0.10) * k / (len(steps) - 1)) * limit, 1) for k in range(1, len(steps))]
    times[-1] = finish
    snapshots, runs = [], []
    for index, (step, at) in enumerate(zip(steps, times)):
        code = ans.STUB[task["task_id"]] if step == "stub" else ans.CODE[task["task_id"]][step]
        trigger = "interval" if index == 0 else ("submit" if index == len(steps) - 1 else "run")
        snapshots.append({"timestamp": at, "code": code, "trigger": trigger})
        if index == 0:
            continue
        compile_error, results, error_text = execute_cases(code, task["function"], task["cases"])
        base = task["reference_runtime_ms"] * shape["runtime"]
        run: Dict[str, Any] = {"timestamp": round(at + 4.0, 1), "compile_error": compile_error, "stdout_tail": "", "stderr_tail": error_text, "results": []}
        for case_id, passed in results:
            run["results"].append({"case_id": case_id, "passed": passed, "runtime_ms": round(base * (0.9 + 0.2 * _jitter(candidate_id, case_id)), 2), "timed_out": False})
        runs.append(run)
    return {"snapshots": snapshots, "runs": runs, "submitted_at": finish}


# --------------------------------------------------------------------------------------------------------------------------- the build
def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def derive_tier_and_questions(p: Dict[str, Any], domain: str) -> Tuple[str, List[str]]:
    """The tier the real question bank assigns (from the years the resume parser finds) and the suffixes of its three tier questions."""
    from parsers import experience_parser
    from parsers.pipeline_simulation import frozen_today
    from parsers.technical_interview_question_bank import TechnicalDomain, TechnicalInterviewSession
    from datetime import date

    text = render_resume_text(p)
    with frozen_today(date.fromisoformat(AS_OF_ISO)):
        years = experience_parser.compute_total_experience(experience_parser.parse_experience(text)).total_years
    session = TechnicalInterviewSession.start(TechnicalDomain(domain), years)
    suffixes = [state.question.question_id.split("-")[-1] for state in session.questions[2:]]
    return session.tier.value, suffixes


def build_dataset(out_dir: Path = DATASET_DIR) -> Dict[str, Any]:
    """Write every file of the dataset and return a summary."""
    for sub in ("jobs", "resumes", "resumes_text", "edge_files", "responses", "machine_test", "integrity"):
        (out_dir / sub).mkdir(parents=True, exist_ok=True)

    jobs_json = []
    for job in JOBS:
        name = f"{job['id']}_{job['slug']}.txt"
        (out_dir / "jobs" / name).write_text(job["text"], encoding="utf-8")
        jobs_json.append({k: job[k] for k in ("id", "slug", "title", "role_type", "domain")} | {"file": f"jobs/{name}"})
    _write_json(out_dir / "jobs" / "jobs.json", jobs_json)

    candidates, screening, hr, technical, machine, integrity = [], {}, {}, {}, {}, {}
    checksums: Dict[str, str] = {}
    for p in PERSONAS:
        job = JOB_BY_ID[p["job"]]
        stem = f"{p['id']}_{_slug(p['name'])}"
        text = render_resume_text(p)
        (out_dir / "resumes_text" / f"{stem}.txt").write_text(text, encoding="utf-8")
        resume_name = f"{stem}.{p['fmt']}"
        (write_docx if p["fmt"] == "docx" else write_pdf)(text, out_dir / "resumes" / resume_name)
        checksums[f"resumes_text/{stem}.txt"] = hashlib.sha256(text.encode("utf-8")).hexdigest()

        turns, reask = ans.screening_answers(p)
        screening[p["id"]] = {"answers": [{"category": c, "text": t["text"], "confidence": t["confidence"]} for c, t in zip(ans.SCREENING_ORDER, turns)], "reask": reask}
        hr[p["id"]] = {"level": p["hr"], "answers": [{"question": q, "text": t} for q, t in zip(ans.HR_QUESTIONS, ans.hr_answers(p))]}

        record = {"id": p["id"], "name": p["name"], "job_id": p["job"], "job_title": job["title"], "role_type": job["role_type"], "domain": job["domain"],
                  "scenario": p["scenario"], "resume_file": f"resumes/{resume_name}", "resume_format": p["fmt"], "resume_style": p["style"],
                  "resume_quality": p["resume_quality"], "years_on_resume": p["years"], "years_claimed_in_call": p.get("claims_years"),
                  "answer_levels": {"screening": p["scr"], "hr": p["hr"], "technical": p.get("tech"), "machine_test": list(p["mt"]) if p.get("mt") else None},
                  "expected_outcomes": p["expected"], "expected_rationale": p["rationale"]}
        if job["role_type"] == "technical":
            tier, suffixes = derive_tier_and_questions(p, job["domain"])
            if (job["domain"], tier) not in ans.TECH_BANK:
                raise ValueError(f"{p['id']}: no technical answer bank for {job['domain']}/{tier}; change the persona's years or add a bank")
            technical[p["id"]] = {"domain": job["domain"], "tier": tier, "level": p["tech"],
                                  "answers": ans.technical_answers(p, job["domain"], tier, suffixes)}
            record["technical_tier"] = tier
            attempts = {t["task_id"]: build_attempt(p["id"], t, variant) for t, variant in zip(ans.TASKS, p["mt"])}
            machine[p["id"]] = attempts
            if p.get("integrity_events"):
                integrity[p["id"]] = [{"event_type": kind, "timestamp": at} for kind, at in p["integrity_events"]]
        candidates.append(record)

    edge = out_dir / "edge_files"
    (edge / "corrupt_resume.pdf").write_bytes(b"%PDF-1.4\n\x00\x01\x02 this is not a real pdf body \xff\xfe")
    (edge / "empty_resume.docx").write_bytes(b"")
    (edge / "legacy_resume.doc").write_text("Name: Legacy Format\nSkills: Excel\n", encoding="utf-8")
    (edge / "resume_photo_scan.jpg").write_bytes(b"\xff\xd8\xff\xe0 not an image, stands in for a scanned photo of a resume")

    tasks = [{**{k: t[k] for k in ("task_id", "task_type", "title", "difficulty", "time_limit_seconds", "function", "reference_runtime_ms")},
              "language": "python", "cases": [{"case_id": c[0], "visible": c[1], "args": c[2], "expected": c[3]} for c in t["cases"]]} for t in ans.TASKS]
    _write_json(out_dir / "candidates.json", {"_note": NOTE, "as_of": AS_OF_ISO, "candidates": candidates})
    _write_json(out_dir / "responses" / "screening_responses.json", screening)
    _write_json(out_dir / "responses" / "hr_responses.json", hr)
    _write_json(out_dir / "responses" / "technical_responses.json", technical)
    _write_json(out_dir / "machine_test" / "tasks.json", tasks)
    _write_json(out_dir / "machine_test" / "submissions.json", machine)
    _write_json(out_dir / "integrity" / "browser_events.json", integrity)
    summary = {"as_of": AS_OF_ISO, "jobs": len(JOBS), "candidates": len(candidates), "technical_candidates": len(technical),
               "resumes_docx": sum(1 for p in PERSONAS if p["fmt"] == "docx"), "resumes_pdf": sum(1 for p in PERSONAS if p["fmt"] == "pdf"),
               "edge_files": 4, "machine_test_tasks": len(tasks), "machine_test_attempts": sum(len(v) for v in machine.values()),
               "integrity_event_sets": len(integrity)}
    _write_json(out_dir / "manifest.json", {"_note": NOTE, "summary": summary, "resume_text_sha256": checksums})
    return summary


NOTE = ("SYNTHETIC DEMO DATA. Every name, employer, institute, e-mail and phone number is invented; any match with a real person or company is a "
        "coincidence. 'expected_outcomes' are the AUTHOR'S design intent, written before the pipeline was run; they are not human judgement. "
        "No scores are stored here: scores come from running the real engines on these inputs (parsers/demo_environment.py).")
