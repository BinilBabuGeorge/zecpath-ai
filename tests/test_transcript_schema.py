import json
import sqlite3
from pathlib import Path

import pytest

from parsers.transcript_schema import (
    CallSession, TranscriptTurn, NormalizedAnswer,
    CallStatus, NormalizationStatus,
    new_call_id, new_turn_id, utc_now_iso, normalize_answer,
)

SCHEMA_PATH = Path("schemas/transcript_schema.sql")


# ---------------------------------------------------------------------------
# ID / timestamp helpers
# ---------------------------------------------------------------------------

def test_new_call_id_has_expected_prefix_and_length():
    cid = new_call_id()
    assert cid.startswith("call_")
    assert len(cid) == len("call_") + 12


def test_new_call_id_is_unique_across_calls():
    assert new_call_id() != new_call_id()


def test_new_turn_id_embeds_call_id_and_zero_padded_index():
    call_id = "call_abc123"
    assert new_turn_id(call_id, 0) == "call_abc123-t000"
    assert new_turn_id(call_id, 7) == "call_abc123-t007"
    assert new_turn_id(call_id, 42) == "call_abc123-t042"


def test_utc_now_iso_produces_parseable_iso_timestamp():
    from datetime import datetime
    ts = utc_now_iso()
    parsed = datetime.fromisoformat(ts)
    assert parsed.tzinfo is not None  # timezone-aware, not naive


# ---------------------------------------------------------------------------
# normalize_answer -- empty / low-confidence gating
# ---------------------------------------------------------------------------

def test_empty_transcript_needs_review():
    result = normalize_answer("", "number", 0.9)
    assert result.status == NormalizationStatus.NEEDS_REVIEW
    assert result.value is None


def test_whitespace_only_transcript_needs_review():
    result = normalize_answer("   ", "yes_no", 0.9)
    assert result.status == NormalizationStatus.NEEDS_REVIEW


def test_low_confidence_forces_needs_review_even_when_parseable():
    # "three years" would parse cleanly as 3.0 at high confidence --
    # low confidence must override that regardless.
    result = normalize_answer("three years", "number", 0.40)
    assert result.status == NormalizationStatus.NEEDS_REVIEW
    assert result.value is None
    assert "confidence" in result.note.lower()


def test_confidence_exactly_at_threshold_is_not_gated():
    from parsers.transcript_schema import _LOW_CONFIDENCE_THRESHOLD
    result = normalize_answer("three", "number", _LOW_CONFIDENCE_THRESHOLD)
    assert result.status != NormalizationStatus.NEEDS_REVIEW or result.value is not None


# ---------------------------------------------------------------------------
# normalize_answer -- free_text / list (no coercion)
# ---------------------------------------------------------------------------

def test_free_text_passes_through_unchanged():
    text = "I mostly worked on backend services using Django."
    result = normalize_answer(text, "free_text", 0.9)
    assert result.value == text
    assert result.status == NormalizationStatus.NOT_APPLICABLE


def test_list_type_also_passes_through_unchanged():
    text = "Python, Django, PostgreSQL"
    result = normalize_answer(text, "list", 0.9)
    assert result.value == text
    assert result.status == NormalizationStatus.NOT_APPLICABLE


# ---------------------------------------------------------------------------
# normalize_answer -- yes_no
# ---------------------------------------------------------------------------

def test_yes_phrases_normalize_to_true():
    for phrase in ["yes", "Yeah definitely", "sure thing", "of course I can"]:
        result = normalize_answer(phrase, "yes_no", 0.9)
        assert result.value is True, f"failed for: {phrase}"
        assert result.status == NormalizationStatus.OK


def test_no_phrases_normalize_to_false():
    for phrase in ["no", "nope, never", "not really", "not at all"]:
        result = normalize_answer(phrase, "yes_no", 0.9)
        assert result.value is False, f"failed for: {phrase}"
        assert result.status == NormalizationStatus.OK


def test_ambiguous_yes_no_needs_review():
    result = normalize_answer("maybe, I'm not totally sure", "yes_no", 0.9)
    assert result.status == NormalizationStatus.NEEDS_REVIEW
    assert result.value is None


# ---------------------------------------------------------------------------
# normalize_answer -- number (including the documented "a"/"an" bug fix)
# ---------------------------------------------------------------------------

def test_digit_number_extracted_directly():
    result = normalize_answer("I have 5 years", "number", 0.9)
    assert result.value == 5.0
    assert result.status == NormalizationStatus.OK


def test_decimal_number_extracted():
    result = normalize_answer("about 3.5 years total", "number", 0.9)
    assert result.value == 3.5


def test_comma_formatted_number_extracted():
    result = normalize_answer("around 8,00,000 per year", "number", 0.9)
    assert result.value == 800000.0


def test_word_number_extracted_when_no_digits_present():
    result = normalize_answer("three years of experience", "number", 0.9)
    assert result.value == 3.0
    assert result.status == NormalizationStatus.OK


def test_approximate_word_couple_extracted():
    result = normalize_answer("a couple of years", "number", 0.9)
    assert result.value == 2.0


def test_article_a_does_not_false_positive_as_one():
    # Regression test for a real bug found and fixed during Day 23:
    # an earlier version treated "a"/"an" as number words, which
    # incorrectly extracted 1.0 from ordinary filler speech with no
    # numeric content at all.
    result = normalize_answer("quite a while actually", "number", 0.9)
    assert result.value is None
    assert result.status == NormalizationStatus.NEEDS_REVIEW


def test_compound_number_words_are_a_documented_gap_not_a_wrong_guess():
    # "twenty-three" is NOT handled -- must fall through to NEEDS_REVIEW,
    # never silently guess a wrong number.
    result = normalize_answer("twenty-three years old", "number", 0.9)
    assert result.status == NormalizationStatus.NEEDS_REVIEW
    assert result.value is None


def test_no_number_found_needs_review():
    result = normalize_answer("quite a long time honestly", "number", 0.9)
    assert result.status == NormalizationStatus.NEEDS_REVIEW


# ---------------------------------------------------------------------------
# normalize_answer -- duration (structured, not collapsed to a bare number)
# ---------------------------------------------------------------------------

def test_immediate_availability_phrases():
    for phrase in ["I can join immediately", "no notice required", "I can join now"]:
        result = normalize_answer(phrase, "duration", 0.9)
        assert result.value == {"amount": 0, "unit": "days", "immediate": True}
        assert result.status == NormalizationStatus.OK


def test_numeric_duration_with_unit():
    result = normalize_answer("I need about 2 months notice", "duration", 0.9)
    assert result.value == {"amount": 2.0, "unit": "months", "immediate": False}


def test_word_number_duration():
    result = normalize_answer("three weeks notice period", "duration", 0.9)
    assert result.value == {"amount": 3, "unit": "weeks", "immediate": False}


def test_duration_amount_and_unit_kept_separate_not_collapsed():
    # "2 weeks" and "2 months" must be distinguishable -- collapsing to a
    # bare "2" would destroy exactly the distinction that matters for a
    # notice-period decision.
    weeks = normalize_answer("2 weeks", "duration", 0.9)
    months = normalize_answer("2 months", "duration", 0.9)
    assert weeks.value["unit"] == "weeks"
    assert months.value["unit"] == "months"
    assert weeks.value != months.value


def test_no_duration_found_needs_review():
    result = normalize_answer("I'm really not sure to be honest", "duration", 0.9)
    assert result.status == NormalizationStatus.NEEDS_REVIEW


# ---------------------------------------------------------------------------
# normalize_answer -- unknown type
# ---------------------------------------------------------------------------

def test_unknown_answer_type_needs_review_with_note():
    result = normalize_answer("some text", "date", 0.9)
    assert result.status == NormalizationStatus.NEEDS_REVIEW
    assert "date" in result.note


# ---------------------------------------------------------------------------
# Dataclass structure / to_dict / turns_needing_review
# ---------------------------------------------------------------------------

def test_normalized_answer_to_dict_serializes_enum_as_string():
    ans = NormalizedAnswer(value=3.0, status=NormalizationStatus.OK, raw_text="three years")
    d = ans.to_dict()
    assert d["status"] == "ok"
    assert isinstance(d["status"], str)


def test_transcript_turn_to_dict_includes_normalized_when_present():
    ans = NormalizedAnswer(value=True, status=NormalizationStatus.OK, raw_text="yes")
    turn = TranscriptTurn(
        turn_id="t1", call_id="c1", candidate_id="cand1", job_id="job1",
        question_id="q1", turn_index=0, question_text="Are you available?",
        raw_transcript="yes", asr_confidence=0.9, timestamp=utc_now_iso(),
        expected_answer_type="yes_no", normalized=ans,
    )
    d = turn.to_dict()
    assert d["normalized"]["status"] == "ok"


def test_call_session_turns_needing_review_filters_correctly():
    ok_ans = NormalizedAnswer(value=1.0, status=NormalizationStatus.OK, raw_text="one")
    review_ans = NormalizedAnswer(value=None, status=NormalizationStatus.NEEDS_REVIEW, raw_text="uh")

    def make_turn(tid, ans):
        return TranscriptTurn(
            turn_id=tid, call_id="c1", candidate_id="cand1", job_id="job1",
            question_id=tid, turn_index=0, question_text="Q", raw_transcript="A",
            asr_confidence=0.9, timestamp=utc_now_iso(), expected_answer_type="number", normalized=ans,
        )

    call = CallSession(call_id="c1", candidate_id="cand1", job_id="job1", started_at=utc_now_iso())
    call.turns = [make_turn("t1", ok_ans), make_turn("t2", review_ans), make_turn("t3", ok_ans)]
    review = call.turns_needing_review()
    assert len(review) == 1
    assert review[0].turn_id == "t2"


def test_call_session_to_dict_serializes_status_enum():
    call = CallSession(call_id="c1", candidate_id="cand1", job_id="job1",
                        started_at=utc_now_iso(), status=CallStatus.COMPLETED)
    d = call.to_dict()
    assert d["status"] == "completed"
    assert isinstance(d["status"], str)


# ---------------------------------------------------------------------------
# SQL DDL -- proven executable, constraints proven to actually fire
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_PATH.read_text())
    yield conn
    conn.close()


def test_schema_creates_both_tables(db_conn):
    tables = {row[0] for row in db_conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "call_sessions" in tables
    assert "transcript_turns" in tables


def test_valid_call_session_insert_succeeds(db_conn):
    db_conn.execute(
        "INSERT INTO call_sessions (call_id, candidate_id, job_id, started_at, status, language) VALUES (?,?,?,?,?,?)",
        ("c1", "cand1", "job1", utc_now_iso(), "in_progress", "en"),
    )
    db_conn.commit()
    count = db_conn.execute("SELECT COUNT(*) FROM call_sessions").fetchone()[0]
    assert count == 1


def test_invalid_status_value_rejected_by_check_constraint(db_conn):
    with pytest.raises(sqlite3.IntegrityError):
        db_conn.execute(
            "INSERT INTO call_sessions (call_id, candidate_id, job_id, started_at, status) VALUES (?,?,?,?,?)",
            ("c1", "cand1", "job1", utc_now_iso(), "not_a_real_status"),
        )


def test_asr_confidence_out_of_range_rejected_by_check_constraint(db_conn):
    db_conn.execute(
        "INSERT INTO call_sessions (call_id, candidate_id, job_id, started_at, status) VALUES (?,?,?,?,?)",
        ("c1", "cand1", "job1", utc_now_iso(), "completed"),
    )
    with pytest.raises(sqlite3.IntegrityError):
        db_conn.execute(
            """INSERT INTO transcript_turns
               (turn_id, call_id, candidate_id, job_id, question_id, turn_index, question_text,
                raw_transcript, asr_confidence, timestamp, expected_answer_type)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            ("t1", "c1", "cand1", "job1", "q1", 0, "Q?", "A.", 1.5, utc_now_iso(), "free_text"),
        )


def test_duplicate_turn_index_within_call_rejected(db_conn):
    db_conn.execute(
        "INSERT INTO call_sessions (call_id, candidate_id, job_id, started_at, status) VALUES (?,?,?,?,?)",
        ("c1", "cand1", "job1", utc_now_iso(), "completed"),
    )
    args = ("c1", "cand1", "job1", "q1", 0, "Q?", "A.", 0.9, utc_now_iso(), "free_text")
    db_conn.execute(
        """INSERT INTO transcript_turns
           (call_id, candidate_id, job_id, question_id, turn_index, question_text,
            raw_transcript, asr_confidence, timestamp, expected_answer_type, turn_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        args + ("t1",),
    )
    with pytest.raises(sqlite3.IntegrityError):
        db_conn.execute(
            """INSERT INTO transcript_turns
               (call_id, candidate_id, job_id, question_id, turn_index, question_text,
                raw_transcript, asr_confidence, timestamp, expected_answer_type, turn_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            args + ("t2",),  # same call_id + turn_index=0, different turn_id
        )


def test_needs_review_partial_index_query_works(db_conn):
    db_conn.execute(
        "INSERT INTO call_sessions (call_id, candidate_id, job_id, started_at, status) VALUES (?,?,?,?,?)",
        ("c1", "cand1", "job1", utc_now_iso(), "completed"),
    )
    rows = [
        ("t1", "c1", "cand1", "job1", "q1", 0, "Q1", "A1", 0.9, utc_now_iso(), "number", "3.0", "ok"),
        ("t2", "c1", "cand1", "job1", "q2", 1, "Q2", "A2", 0.4, utc_now_iso(), "number", None, "needs_review"),
    ]
    for r in rows:
        db_conn.execute(
            """INSERT INTO transcript_turns
               (turn_id, call_id, candidate_id, job_id, question_id, turn_index, question_text,
                raw_transcript, asr_confidence, timestamp, expected_answer_type, normalized_value, normalization_status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            r,
        )
    db_conn.commit()
    review_count = db_conn.execute(
        "SELECT COUNT(*) FROM transcript_turns WHERE normalization_status='needs_review'"
    ).fetchone()[0]
    assert review_count == 1


# ---------------------------------------------------------------------------
# JSON Schema conformance -- a real CallSession's to_dict() output must
# validate against schemas/transcript_schema.json
# ---------------------------------------------------------------------------

def test_real_call_session_conforms_to_json_schema():
    schema_defs = json.loads(Path("schemas/transcript_schema.json").read_text())["$defs"]

    ans = NormalizedAnswer(value=2.0, status=NormalizationStatus.OK, raw_text="two years")
    turn = TranscriptTurn(
        turn_id="t1", call_id="c1", candidate_id="cand1", job_id="job1",
        question_id="q1", turn_index=0, question_text="How many years?",
        raw_transcript="two years", asr_confidence=0.9, timestamp=utc_now_iso(),
        expected_answer_type="number", normalized=ans,
    )
    call = CallSession(call_id="c1", candidate_id="cand1", job_id="job1",
                        started_at=utc_now_iso(), status=CallStatus.COMPLETED, turns=[turn])
    data = call.to_dict()

    call_schema = schema_defs["CallSession"]
    for field_name in call_schema["required"]:
        assert field_name in data
    assert data["status"] in call_schema["properties"]["status"]["enum"]
    turn_data = data["turns"][0]
    for field_name in schema_defs["TranscriptTurn"]["required"]:
        assert field_name in turn_data
