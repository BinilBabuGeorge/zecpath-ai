"""Day 57 -- regression tests for each defect found and fixed. Each test names the behaviour BEFORE the fix."""
import math
import os
import tempfile
from datetime import date
from types import SimpleNamespace as NS

import pytest
from docx import Document

from parsers import experience_parser
from parsers.answer_intent_engine import AnswerQuality, understand_answer
from parsers.cross_round_aggregation_engine import RoundResult, ats_zone_of, compute_cross_round_score, zone_review_reasons
from parsers.edge_case_handler import _MAX_CONSECUTIVE_SILENT_TURNS, RobustConversationController
from parsers.experience_parser import compute_total_experience, parse_experience, reference_date, today
from parsers.final_recommendation_engine import DecisionOutcome, HoldKind, decide
from parsers.hr_interview_question_bank import ExperienceLevel, InterviewSession, RoleType
from parsers.hr_interview_scoring_engine import score_hr_interview
from parsers.resume_extractor import ResumeUploadError, extract_resume, normalize_section_headings
from parsers.screening_pipeline import run_screening_call
from parsers.screening_question_bank import CATEGORIES
from parsers.section_extractor import extract_jd_sections, extract_resume_sections
from parsers.speech_to_text import RawSTTResult
from parsers.technical_interview_question_bank import TechnicalDomain, TechnicalInterviewSession, experience_years_to_tier
from parsers.technical_skill_scoring_engine import build_technical_evaluation_report, evaluate_technical_answer, looks_like_keyword_list

T = lambda text, conf=0.9, silent=False: RawSTTResult(text=text, confidence=conf, is_silent=silent)


def years(text, as_of=None):
    with reference_date(as_of):
        s = compute_total_experience(parse_experience("Experience:\n" + text))
    return s


# ======================================================================= experience parsing
def test_year_only_ranges_are_counted_not_dropped():           # before: "(2019 - 2022)" matched nothing -> 0.0 years
    assert years("- Engineer, Acme (2019 - 2022)\n").total_years == 3.0


def test_a_job_inside_one_bare_year_is_credited_half_a_year():
    assert years("- Engineer, Acme (2020 - 2020)\n").total_years == 0.5


@pytest.mark.parametrize("line", ["- A, X (Jan 2020 to Jan 2021)", "- A, X (Jan 2020 \u2014 Jan 2021)", "- A, X (Jan 2020 \u2013 Jan 2021)", "- A, X (Jan 2020 - Jan 2021)"])
def test_separators_to_em_dash_en_dash_and_hyphen(line):
    assert years(line + "\n").total_years == 1.1


@pytest.mark.parametrize("word", ["Present", "Current", "Ongoing", "Now", "Till date", "Till now"])
def test_present_synonyms(word):
    assert years(f"- A, X (Jan 2025 - {word})\n", date(2026, 1, 1)).total_years == 1.1


def test_end_before_start_is_left_out_with_a_warning():        # before: -1.1 years
    s = years("- Engineer, Acme (Mar 2024 - Jan 2023)\n")
    assert s.total_years == 0.0 and any("end date is before" in w for w in s.warnings)


def test_a_future_job_is_left_out_not_counted_as_negative_time():   # before: -4.1 years
    s = years("- Engineer, Acme (Jan 2031 - Present)\n", date(2026, 10, 30))
    assert s.total_years == 0.0 and any("future" in w for w in s.warnings)


def test_an_implausible_career_is_left_out():                    # before: 126.9 years
    s = years("- Engineer, Acme (Jan 1900 - Present)\n", date(2026, 10, 30))
    assert s.total_years == 0.0 and any("60 years" in w for w in s.warnings)


def test_a_job_ending_in_the_future_is_capped_at_today():
    assert years("- A, X (Jan 2026 - Dec 2030)\n", date(2026, 6, 1)).total_years == 0.5


def test_a_date_slot_that_is_not_a_date_does_not_abort_the_resume():
    s = years("- Engineer, Acme (Foo 2020 - Bar 2021)\n- Dev, Beta (Jan 2020 - Jan 2021)\n")
    assert s.total_years == 1.1


def test_valid_entries_are_unchanged_and_overlaps_still_counted_once():
    s = years("- A, X (Jan 2020 - Jan 2022)\n- B, Y (Jan 2020 - Jan 2022)\n")
    assert s.total_years == 2.1 and s.warnings == []


def test_present_follows_the_reference_date_and_the_pin_is_restored():   # Day 56 finding F4
    line = "- E, A (Jan 2024 - Present)\n"
    assert years(line, date(2025, 1, 1)).total_years < years(line, date(2026, 1, 1)).total_years
    assert experience_parser._REFERENCE_DATE is None and today() == date.today()


def test_reference_date_restores_even_when_the_block_raises():
    with pytest.raises(RuntimeError):
        with reference_date(date(2020, 1, 1)):
            raise RuntimeError("boom")
    assert experience_parser._REFERENCE_DATE is None


# =============================================================================== upload
def _file(name, data=b""):
    p = os.path.join(tempfile.mkdtemp(), name)
    open(p, "wb").write(data)
    return p


@pytest.mark.parametrize("name,data,code", [("a.txt", b"x", "unsupported_type"), ("a.doc", b"\xd0\xcf", "unsupported_type"), ("a.pdf", b"not a pdf", "corrupt_file"),
                                            ("b.docx", b"garbage", "corrupt_file"), ("c.docx", b"", "empty_file")])
def test_upload_failures_are_one_typed_error_with_a_code(name, data, code):
    with pytest.raises(ResumeUploadError) as e:
        extract_resume(_file(name, data))
    assert e.value.code == code and isinstance(e.value, ValueError)         # still a ValueError for older callers


def test_missing_file_is_typed_and_doc_gets_a_helpful_hint():
    with pytest.raises(ResumeUploadError) as e:
        extract_resume("/nonexistent/x.docx")
    assert e.value.code == "file_not_found"
    with pytest.raises(ResumeUploadError) as e:
        extract_resume(_file("old.doc", b"\xd0\xcf"))
    assert "DOCX or PDF" in str(e.value)


def test_blank_docx_reads_but_reports_no_text():
    p = os.path.join(tempfile.mkdtemp(), "blank.docx"); Document().save(p)
    assert extract_resume(p).has_text is False


# ====================================================================== section headings
@pytest.mark.parametrize("head", ["Technical Skills", "TECHNICAL SKILLS:", "Key Skills", "Core Competencies", "Tech Stack", "Skills & Tools"])
def test_resume_skill_heading_synonyms_are_recognised(head):      # before: all of these -> skills section empty -> score 14.9 vs 50.7
    assert "React" in extract_resume_sections(f"Summary:\nDev.\n{head}\nReact, Node\nExperience:\n- A, B (Jan 2020 - Jan 2021)\n")["skills"]


@pytest.mark.parametrize("head", ["Work Experience", "PROFESSIONAL EXPERIENCE", "Employment History"])
def test_resume_experience_heading_synonyms_are_recognised(head):
    assert "Acme" in extract_resume_sections(f"Skills:\nReact\n{head}\n- Dev, Acme (Jan 2020 - Jan 2021)\n")["experience"]


@pytest.mark.parametrize("head", ["Requirements:", "Must Have", "Key Requirements", "What we're looking for"])
def test_jd_requirement_heading_synonyms_are_recognised(head):
    assert "MongoDB" in extract_jd_sections(f"About the Role:\nx\n{head}\n- MongoDB\n- React\n")["skills"]


def test_nice_to_have_and_key_responsibilities_map_to_the_jd_sections():
    s = extract_jd_sections("Requirements:\n- React\nNice to Have\n- Docker\nKey Responsibilities\n- Build APIs\n")
    assert "Docker" in s["skills"] and "Build APIs" in s["experience"]


def test_a_phrase_inside_a_sentence_is_never_treated_as_a_heading():
    text = "I have technical skills in React\nTechnologies\nReact"
    out = normalize_section_headings(text)
    assert out.splitlines()[0] == "I have technical skills in React" and out.splitlines()[1] == "Skills:"


def test_heading_normalisation_is_idempotent():
    once = normalize_section_headings("Technical Skills\nReact\nWork Experience\n- A")
    assert normalize_section_headings(once) == once


# ======================================================================= conversation
def test_a_dead_line_ends_the_call_after_the_silence_limit():       # before: walked through ~21 prompts, never ended
    ctl = RobustConversationController(categories=list(CATEGORIES))
    for i in range(_MAX_CONSECUTIVE_SILENT_TURNS):
        ctl.process_turn(T("", 0.0, True))
    assert ctl.call_ended_early and ctl.is_call_complete


def test_speech_resets_the_silence_counter():
    ctl = RobustConversationController(categories=list(CATEGORIES))
    for _ in range(_MAX_CONSECUTIVE_SILENT_TURNS - 1):
        ctl.process_turn(T("", 0.0, True))
    ctl.process_turn(T("I am Ananya, a developer based in Bengaluru."))
    for _ in range(_MAX_CONSECUTIVE_SILENT_TURNS - 1):
        ctl.process_turn(T("", 0.0, True))
    assert not ctl.call_ended_early


def test_empty_text_counts_as_silence_too():
    ctl = RobustConversationController(categories=list(CATEGORIES))
    for _ in range(_MAX_CONSECUTIVE_SILENT_TURNS):
        ctl.process_turn(T("   ", 0.9))
    assert ctl.call_ended_early


@pytest.mark.parametrize("cat", ["introduction", "skills", "location"])
def test_digits_alone_are_not_an_answer_to_a_question_that_wants_words(cat):   # before: digits counted as concrete for every question
    assert understand_answer("12345 67890", cat).quality in (AnswerQuality.VAGUE, AnswerQuality.OFF_TOPIC)


@pytest.mark.parametrize("cat,text", [("salary", "1200000"), ("notice_period", "30"), ("experience", "5")])
def test_digits_alone_are_fine_where_a_number_is_the_answer(cat, text):
    assert understand_answer(text, cat).quality is AnswerQuality.OK


def test_a_digit_string_call_no_longer_scores_like_a_real_one():     # before: 60.7
    c = run_screening_call([T("12345 67890") for _ in range(8)], candidate_id="x", job_role="r")
    assert c.scoring_result.total_score < 50


def test_a_rich_self_introduction_is_not_off_topic():                # before: off_topic, re-asked
    for text in ["Hi, I'm Ananya Rao, a MERN stack developer based in Bengaluru.", "My name is Arjun and I work at Infosys as a tech lead.",
                 "I am Priya, a sales executive with a BBA from Delhi University."]:
        assert understand_answer(text, "introduction").quality is AnswerQuality.OK, text


def test_a_vague_introduction_is_still_vague():
    assert understand_answer("hmm", "introduction").quality is not AnswerQuality.OK


def test_an_introduction_marker_does_not_excuse_an_off_topic_answer_to_another_question():
    assert understand_answer("I am based in Delhi and my name is Priya", "salary").quality is AnswerQuality.OFF_TOPIC


def test_unknown_screening_categories_are_refused_up_front():       # before: silently accepted, swallowed mid-call
    with pytest.raises(ValueError, match="Unknown screening categories"):
        run_screening_call([T("hi")], categories=["hobby"], candidate_id="x", job_role="r")
    assert run_screening_call([T("I expect 12 lakhs")], categories=["salary"], candidate_id="x", job_role="r") is not None


# =========================================================================== HR scoring
def _hr(answers):
    s = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)
    for a in answers:
        s.submit_response(a)
    return score_hr_interview(s)


GOOD = "I work well in teams and communicate clearly; on my last project I led a migration and mentored two juniors."


def test_content_free_answers_no_longer_score_in_the_selection_band():   # before: six "yes" -> 73.3
    r = _hr(["yes"] * 6)
    assert r.overall_hr_score < 50
    assert sum(b.non_substantive for b in r.answer_breakdowns) == 5            # the 6th is the availability question, exempt by design


def test_good_answers_are_unchanged_by_the_gate():
    r = _hr([GOOD] * 6)
    assert r.overall_hr_score > 70 and not any(b.non_substantive for b in r.answer_breakdowns)


def test_the_gap_between_yes_and_a_real_answer_is_now_large():
    assert _hr([GOOD] * 6).overall_hr_score - _hr(["yes"] * 6).overall_hr_score > 30      # before: 3 points


def test_availability_answers_may_be_one_word():
    r = _hr(["I like working in teams and learning new things every day."] * 5 + ["Immediately."])
    assert not r.answer_breakdowns[-1].non_substantive


def test_a_non_text_answer_is_refused():                          # before: None stored silently
    s = InterviewSession.start(ExperienceLevel.EXPERIENCED, RoleType.TECHNICAL)
    with pytest.raises(TypeError):
        s.submit_response(None)
    with pytest.raises(TypeError):
        TechnicalInterviewSession.start("mern", 3).submit_response(42)


def test_breakdown_reports_the_non_substantive_flag():
    assert "non_substantive" in _hr(["yes"] * 6).answer_breakdowns[0].to_dict()


# ===================================================================== technical scoring
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_experience_is_refused(bad):                   # before: NaN fell through to ADVANCED
    with pytest.raises(ValueError):
        experience_years_to_tier(bad)


@pytest.mark.parametrize("bad", ["3", True, None, [3]])
def test_non_numeric_experience_is_refused(bad):
    with pytest.raises(TypeError):
        experience_years_to_tier(bad)


def test_unknown_domain_is_a_clear_error_and_strings_are_accepted():   # before: KeyError: 'cobol'
    with pytest.raises(ValueError, match="Valid domains"):
        TechnicalInterviewSession.start("cobol", 3)
    assert TechnicalInterviewSession.start("mern", 3).domain is TechnicalDomain.MERN


def test_keyword_list_detection():
    assert looks_like_keyword_list("event loop libuv thread pool task queue timers phase poll phase microtask callbacks")
    assert not looks_like_keyword_list("Node runs your code on one thread and hands slow work to the system so it never waits.")
    assert not looks_like_keyword_list("short answer")
    assert not looks_like_keyword_list("")


def test_a_keyword_list_keeps_only_part_of_its_credit():
    s = TechnicalInterviewSession.start(TechnicalDomain.MERN, 3)
    q = next(x for x in s.questions if x.phase.value == "conceptual").question
    listy = "event loop libuv thread pool task queue timers phase poll phase microtask callbacks non-blocking single-threaded"
    prose = "The event loop is single-threaded and non-blocking, and libuv uses a thread pool so that the task queue, timers phase and poll phase keep moving."
    a = evaluate_technical_answer(listy, q.question_id, "mern", s.tier, [])
    b = evaluate_technical_answer(prose, q.question_id, "mern", s.tier, [])
    assert a.keyword_list and not b.keyword_list and a.overall_technical_score < b.overall_technical_score
    assert a.to_dict()["keyword_list"] is True


# ============================================================ ATS zone in the decision (finding F1)
def _round_set(ats_reasons):
    return [RoundResult("ats", 70, review_reasons=ats_reasons), RoundResult("screening", 90), RoundResult("hr_interview", 90)]


def test_a_non_shortlist_ats_zone_blocks_selection_with_a_reason():     # before: 69.0 raw / 74.5 aligned -> SELECTED
    free = decide(compute_cross_round_score(_round_set([]), RoleType.NON_TECHNICAL, ExperienceLevel.EXPERIENCED, "c"))
    blocked = decide(compute_cross_round_score(_round_set(zone_review_reasons("reject")), RoleType.NON_TECHNICAL, ExperienceLevel.EXPERIENCED, "c"))
    assert free.outcome is DecisionOutcome.SELECTED
    assert blocked.outcome is DecisionOutcome.HOLD_REVIEW and blocked.hold_kind is HoldKind.SELECTION_BLOCKED
    assert any("ATS zone is REJECT" in r for r in blocked.reasons)


def test_zone_review_reasons():
    assert zone_review_reasons("shortlist") == [] and "REVIEW" in zone_review_reasons("review")[0] and "REJECT" in zone_review_reasons("reject")[0]


def _ats(score, skill_available, skill_score=0.0, category="default"):
    return NS(overall_score=score, role_category=category,
              components=[NS(name="skill_match", score=skill_score, available=skill_available), NS(name="semantic", score=score, available=True)])


def test_a_reject_needs_skill_evidence():                         # before: an unparseable JD -> REJECT
    assert ats_zone_of(_ats(5.0, skill_available=False)) == "review"
    assert ats_zone_of(_ats(5.0, skill_available=True, skill_score=5.0)) == "reject"
    assert ats_zone_of(_ats(60.0, skill_available=True, skill_score=80.0)) == "shortlist"


# ===================================================================== eligibility (call trigger)
def test_an_unparseable_job_description_sends_the_candidate_to_review_not_rejection():     # before: REJECTED
    from pathlib import Path
    from parsers.ats_scoring_engine import score_candidate
    from parsers.eligibility_engine import EligibilityRules, evaluate_eligibility
    from parsers.pipeline_simulation import build_matcher
    s = Path("data/samples")
    resume = (s / "resumes/resume_01_mern_developer.txt").read_text(encoding="utf-8")
    result = score_candidate(resume, "We need a developer with React and Node experience for our product team.", build_matcher(s))
    assert evaluate_eligibility("c1", resume, result, EligibilityRules(job_id="j")).tag == "REVIEW"
    # a very low score with no comparable skills would be classified REJECT on the score alone -- this is the case that needs the cap
    sparse = score_candidate("Skills:\nReact", "We need a developer with React and Node experience for our product team.", build_matcher(s))
    assert sparse.overall_score < 20
    assert evaluate_eligibility("c2", "Skills:\nReact", sparse, EligibilityRules(job_id="j")).tag == "REVIEW"
    structured = score_candidate(resume, (s / "jds/jd_01_mern_developer.txt").read_text(encoding="utf-8"), build_matcher(s))
    assert evaluate_eligibility("c1", resume, structured, EligibilityRules(job_id="j")).tag == "ELIGIBLE"
