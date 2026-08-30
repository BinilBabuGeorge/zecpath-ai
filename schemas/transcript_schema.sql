-- Day 23: Database schema for screening interactions (voice transcript storage)
--
-- Two tables, matching the two granularities in transcript_schema.py:
--   call_sessions  -- one row per screening call
--   transcript_turns -- one row per question/answer exchange within a call
--
-- Verified: this file is proven executable, not just typed SQL text --
-- see run_day23_transcript_demo.py, which actually CREATEs these tables
-- in an in-memory SQLite database and inserts real rows before this
-- schema is considered "done."
--
-- Portable subset of SQL used deliberately (works in SQLite as shipped
-- here; adapt CHECK/TEXT/REAL types for Postgres/MySQL as needed --
-- e.g. TEXT -> VARCHAR, REAL -> FLOAT/DOUBLE PRECISION, and SQLite's
-- permissive typing would become explicit column types elsewhere).

CREATE TABLE IF NOT EXISTS call_sessions (
    call_id         TEXT PRIMARY KEY,
    candidate_id    TEXT NOT NULL,
    job_id          TEXT NOT NULL,
    started_at      TEXT NOT NULL,      -- ISO 8601 UTC
    ended_at        TEXT,               -- NULL while in_progress
    status          TEXT NOT NULL CHECK (status IN ('in_progress', 'completed', 'dropped', 'failed')),
    language        TEXT NOT NULL DEFAULT 'en'
);

CREATE INDEX IF NOT EXISTS idx_call_sessions_candidate ON call_sessions(candidate_id);
CREATE INDEX IF NOT EXISTS idx_call_sessions_job ON call_sessions(job_id);

CREATE TABLE IF NOT EXISTS transcript_turns (
    turn_id                 TEXT PRIMARY KEY,
    call_id                 TEXT NOT NULL REFERENCES call_sessions(call_id),
    candidate_id            TEXT NOT NULL,     -- denormalized on purpose -- see docs, "why denormalize"
    job_id                  TEXT NOT NULL,     -- denormalized on purpose
    question_id             TEXT NOT NULL,     -- matches screening_question_bank.ScreeningQuestion.id
    turn_index              INTEGER NOT NULL,
    question_text           TEXT NOT NULL,
    raw_transcript          TEXT NOT NULL,
    asr_confidence          REAL NOT NULL CHECK (asr_confidence >= 0.0 AND asr_confidence <= 1.0),
    timestamp               TEXT NOT NULL,     -- ISO 8601 UTC
    expected_answer_type    TEXT NOT NULL CHECK (expected_answer_type IN ('free_text', 'number', 'duration', 'yes_no', 'list')),
    normalized_value        TEXT,              -- JSON-encoded; type varies by expected_answer_type
    normalization_status    TEXT CHECK (normalization_status IN ('ok', 'partial', 'needs_review', 'not_applicable')),
    normalization_note      TEXT,
    UNIQUE (call_id, turn_index)
);

CREATE INDEX IF NOT EXISTS idx_transcript_turns_call ON transcript_turns(call_id);
CREATE INDEX IF NOT EXISTS idx_transcript_turns_candidate ON transcript_turns(candidate_id);
CREATE INDEX IF NOT EXISTS idx_transcript_turns_needs_review ON transcript_turns(normalization_status)
    WHERE normalization_status = 'needs_review';
