"""
Day 30 tests -- covers the false-rejection fix to
parsers.answer_intent_engine._is_vague(), found and fixed during Day 30
testing. See docs/day30_screening_system_testing_optimization.md and
data/ground_truth_screening/day30_manual_review.json for the full
evidence this fix is based on.
"""

from parsers.answer_intent_engine import understand_answer, AnswerQuality


def _quality(text, category):
    return understand_answer(text, expected_category=category).quality


# ---------------------------------------------------------------------------
# The false rejections this day fixed -- each verified against the
# real ground truth case in day30_manual_review.json
# ---------------------------------------------------------------------------

def test_digit_short_answer_no_longer_vague():
    assert _quality("5 years", "experience") == AnswerQuality.OK


def test_word_number_short_answer_no_longer_vague():
    assert _quality("Two years", "experience") == AnswerQuality.OK


def test_immediately_no_longer_vague():
    assert _quality("Immediately", "notice_period") == AnswerQuality.OK


def test_salary_with_lakhs_keyword_no_longer_vague():
    assert _quality("Ten lakhs", "salary") == AnswerQuality.OK


def test_education_with_degree_keyword_no_longer_vague():
    assert _quality("B.Tech CSE", "education") == AnswerQuality.OK


def test_broad_number_word_thirty_no_longer_vague():
    assert _quality("Thirty days", "notice_period") == AnswerQuality.OK


def test_single_recognized_skill_no_longer_vague():
    assert _quality("Docker", "skills") == AnswerQuality.OK


def test_bare_digit_no_longer_vague():
    assert _quality("8", "salary") == AnswerQuality.OK


def test_no_notice_period_still_ok_unaffected_by_fix():
    # Was already correct before Day 30 (3 words, escapes the
    # short-answer heuristic entirely) -- confirms the fix didn't
    # touch behavior that was already right.
    assert _quality("No notice period", "notice_period") == AnswerQuality.OK


# ---------------------------------------------------------------------------
# Genuine hedges must still be caught -- the fix must not overcorrect
# into accepting real non-answers
# ---------------------------------------------------------------------------

def test_maybe_still_vague():
    assert _quality("maybe", "salary") == AnswerQuality.VAGUE


def test_not_sure_still_vague():
    assert _quality("not sure", "experience") == AnswerQuality.VAGUE


def test_dunno_still_vague():
    assert _quality("dunno", "salary") == AnswerQuality.VAGUE


def test_longer_hedge_still_vague():
    assert _quality("I'm not really sure, maybe around that range I guess.", "salary") == AnswerQuality.VAGUE


# ---------------------------------------------------------------------------
# The overcorrection this day found and reverted -- "remote"/"hybrid"/
# "onsite" don't correspond to any of Day 22's 7 categories, so they
# must NOT be treated as universally confident
# ---------------------------------------------------------------------------

def test_remote_alone_still_vague_not_overcorrected():
    assert _quality("Remote", "notice_period") == AnswerQuality.VAGUE


def test_hybrid_alone_still_vague_not_overcorrected():
    assert _quality("Hybrid", "location") == AnswerQuality.VAGUE


def test_onsite_alone_still_vague_not_overcorrected():
    assert _quality("Onsite", "location") == AnswerQuality.VAGUE


# ---------------------------------------------------------------------------
# The one honestly-documented remaining gap -- a bare place name has
# no digit, number-word, category-keyword hit, or confident-word
# match, so it is still (correctly, per this project's stated scope)
# flagged vague without a location gazetteer this project doesn't have
# ---------------------------------------------------------------------------

def test_bare_city_name_still_vague_documented_gap():
    assert _quality("Bengaluru", "location") == AnswerQuality.VAGUE


# ---------------------------------------------------------------------------
# Sanity: substantial answers and other quality types unaffected
# ---------------------------------------------------------------------------

def test_substantial_answer_unaffected():
    text = "Hi, I'm a full stack developer with about three years of experience, mostly working on React and Node.js."
    assert _quality(text, "introduction") == AnswerQuality.OK


def test_off_topic_detection_unaffected():
    assert _quality("My current CTC is around twelve lakhs.", "location") == AnswerQuality.OFF_TOPIC


def test_missing_detection_unaffected():
    assert understand_answer("", expected_category="experience", is_silent=True).quality == AnswerQuality.MISSING


def test_yes_no_short_answers_still_not_vague():
    assert _quality("yes", "notice_period") == AnswerQuality.OK
    assert _quality("no", "notice_period") == AnswerQuality.OK
