"""
Day 23 demo: Day 22's questions -> a synthetic voice call transcript ->
normalized structured data -> real SQLite storage.

IMPORTANT: nothing in this project performs real speech-to-text. The
"candidate answers" below are hand-written, clearly-labeled SYNTHETIC
transcripts standing in for what an ASR system would produce -- they
exist to exercise and validate the schema and normalization logic
against realistic phrasing (including messy, low-confidence, and
ambiguous cases), not to claim a working voice pipeline exists.
"""

import json
import logging
import sqlite3
from pathlib import Path

from parsers.semantic_matcher import SemanticMatcher
from parsers.ats_scoring_engine import score_candidate
from parsers.screening_question_bank import generate_screening_questions
from parsers.transcript_schema import (
    CallSession, TranscriptTurn, CallStatus,
    new_call_id, new_turn_id, utc_now_iso, normalize_answer,
)

RESUME_DIR = Path("data/samples/resumes")
JD_DIR = Path("data/samples/jds")
SCHEMA_PATH = Path("schemas/transcript_schema.sql")
OUT_DIR = Path("data/results")
LOG_DIR = Path("logs")

OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "day23_transcript_run.log", mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("day23")

# Synthetic candidate answers, matched by question category/source to
# what generate_screening_questions() actually produces for
# resume_01_mern_developer vs jd_01_mern_developer. Deliberately
# includes a mix of clean, messy, and low-confidence cases.
SYNTHETIC_ANSWERS = {
    "introduction": ("Hi, I'm a full stack developer with about three years of experience, mostly working on React and Node.js projects.", 0.93),
    "education": ("I did my B.Tech in Computer Science from a college in Bengaluru.", 0.88),
    "experience": ("Sure -- I've been working professionally for around three years now, starting as a junior developer and now as a software engineer.", 0.91),
    "location": ("I'm currently based in Bengaluru and I'm fine with hybrid work.", 0.95),
    "salary": ("My current CTC is about eleven lakhs and I'm expecting somewhere in the twelve to fourteen range.", 0.40),  # deliberately low confidence -- noisy line
    "notice_period": ("I can join immediately, I'm not serving notice right now.", 0.97),
}
SYNTHETIC_SKILL_ANSWER = ("Yeah, I've used Docker quite a bit for containerizing our services.", 0.85)
SYNTHETIC_FOLLOWUP_ANSWER = ("Um, not really, I haven't worked with that one.", 0.62)


def run():
    resume_files = sorted(RESUME_DIR.glob("*.txt"))
    jd_files = sorted(JD_DIR.glob("*.txt"))
    corpus = [f.read_text() for f in resume_files + jd_files]
    matcher = SemanticMatcher(corpus)
    logger.info("Fitted semantic matcher on %d documents", len(corpus))
    logger.info("=" * 90)

    candidate_id = "resume_01_mern_developer"
    job_id = "jd_01_mern_developer"
    resume_text = (RESUME_DIR / f"{candidate_id}.txt").read_text()
    jd_text = (JD_DIR / f"{job_id}.txt").read_text()
    ats_result = score_candidate(resume_text, jd_text, matcher)

    questions = generate_screening_questions(jd_text, job_id, resume_text=resume_text, ats_result=ats_result)
    logger.info("Generated %d questions for %s vs %s (%d ATS-driven follow-ups)",
                len(questions), candidate_id, job_id, sum(1 for q in questions if q.source == "ats_followup"))
    logger.info("-" * 90)

    call = CallSession(
        call_id=new_call_id(), candidate_id=candidate_id, job_id=job_id,
        started_at=utc_now_iso(), status=CallStatus.IN_PROGRESS,
    )

    for i, q in enumerate(questions):
        if q.category in SYNTHETIC_ANSWERS:
            raw_text, confidence = SYNTHETIC_ANSWERS[q.category]
        elif q.source == "ats_followup":
            raw_text, confidence = SYNTHETIC_FOLLOWUP_ANSWER
        else:
            raw_text, confidence = SYNTHETIC_SKILL_ANSWER

        normalized = normalize_answer(raw_text, q.expected_answer_type, confidence)
        turn = TranscriptTurn(
            turn_id=new_turn_id(call.call_id, i), call_id=call.call_id,
            candidate_id=candidate_id, job_id=job_id, question_id=q.id,
            turn_index=i, question_text=q.text, raw_transcript=raw_text,
            asr_confidence=confidence, timestamp=utc_now_iso(),
            expected_answer_type=q.expected_answer_type, normalized=normalized,
        )
        call.turns.append(turn)
        logger.info("[%s] Q: %s", q.category, q.text)
        logger.info("       A (raw, conf=%.2f): %s", confidence, raw_text)
        logger.info("       -> normalized: value=%r status=%s%s",
                     normalized.value, normalized.status.value,
                     f" ({normalized.note})" if normalized.note else "")

    call.status = CallStatus.COMPLETED
    call.ended_at = utc_now_iso()

    logger.info("-" * 90)
    review_turns = call.turns_needing_review()
    logger.info("Call complete. %d/%d turns need human review: %s",
                len(review_turns), len(call.turns), [t.question_id for t in review_turns])

    # --- Prove the DDL is real by actually storing this call in SQLite ---
    logger.info("-" * 90)
    logger.info("Storing call in an in-memory SQLite database using schemas/transcript_schema.sql ...")
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_PATH.read_text())
    conn.execute(
        "INSERT INTO call_sessions (call_id, candidate_id, job_id, started_at, ended_at, status, language) VALUES (?,?,?,?,?,?,?)",
        (call.call_id, call.candidate_id, call.job_id, call.started_at, call.ended_at, call.status.value, call.language),
    )
    for t in call.turns:
        conn.execute(
            """INSERT INTO transcript_turns
               (turn_id, call_id, candidate_id, job_id, question_id, turn_index, question_text,
                raw_transcript, asr_confidence, timestamp, expected_answer_type,
                normalized_value, normalization_status, normalization_note)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (t.turn_id, t.call_id, t.candidate_id, t.job_id, t.question_id, t.turn_index, t.question_text,
             t.raw_transcript, t.asr_confidence, t.timestamp, t.expected_answer_type,
             json.dumps(t.normalized.value), t.normalized.status.value, t.normalized.note),
        )
    conn.commit()

    row_count = conn.execute("SELECT COUNT(*) FROM transcript_turns WHERE call_id=?", (call.call_id,)).fetchone()[0]
    review_count = conn.execute(
        "SELECT COUNT(*) FROM transcript_turns WHERE call_id=? AND normalization_status='needs_review'", (call.call_id,)
    ).fetchone()[0]
    logger.info("Stored %d turns in SQLite; %d flagged needs_review via a real SQL query (not Python re-filtering).", row_count, review_count)
    conn.close()

    out_path = OUT_DIR / "day23_sample_call_session.json"
    out_path.write_text(json.dumps(call.to_dict(), indent=2), encoding="utf-8")
    logger.info("Full call session written to %s", out_path)


if __name__ == "__main__":
    run()
