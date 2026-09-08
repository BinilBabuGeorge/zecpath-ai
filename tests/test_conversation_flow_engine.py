from parsers.conversation_flow_engine import (
    ConversationFlowController, FlowAction, detect_confusion, detect_repeated_answer,
)


def _controller(categories=None):
    return ConversationFlowController(categories=categories or ["introduction", "experience", "salary"])


# ---------------------------------------------------------------------------
# detect_confusion
# ---------------------------------------------------------------------------

def test_confusion_phrase_detected():
    assert detect_confusion("Sorry, what do you mean by that?")


def test_confusion_not_detected_in_normal_answer():
    assert not detect_confusion("I have three years of experience with React.")


def test_confusion_variants_detected():
    for phrase in ["can you repeat that", "I don't understand the question", "come again?", "pardon"]:
        assert detect_confusion(phrase), phrase


# ---------------------------------------------------------------------------
# detect_repeated_answer
# ---------------------------------------------------------------------------

def test_identical_answer_detected_as_repeated():
    assert detect_repeated_answer("I have three years of experience with React.",
                                   ["I have three years of experience with React."])


def test_high_overlap_answer_detected_as_repeated():
    assert detect_repeated_answer("three years of experience with React and Node",
                                   ["I have three years of experience with React and Node."])


def test_different_answer_not_flagged_as_repeated():
    assert not detect_repeated_answer("My notice period is two weeks.",
                                       ["I have three years of experience with React."])


def test_empty_text_never_flagged_as_repeated():
    assert not detect_repeated_answer("", ["I have three years of experience."])


# ---------------------------------------------------------------------------
# Silence handling
# ---------------------------------------------------------------------------

def test_first_silence_retries_same_category():
    c = _controller()
    action = c.process_turn("", is_silent=True)
    assert action.action_type == FlowAction.RETRY_SILENCE
    assert c.current_category == "introduction"


def test_second_silence_falls_back():
    c = _controller()
    c.process_turn("", is_silent=True)
    action = c.process_turn("", is_silent=True)
    assert action.action_type == FlowAction.ASK_FALLBACK
    assert c.current_category == "introduction"


def test_third_silence_polite_skips_and_advances():
    c = _controller()
    c.process_turn("", is_silent=True)
    c.process_turn("", is_silent=True)
    action = c.process_turn("", is_silent=True)
    assert action.action_type == FlowAction.POLITE_SKIP
    assert c.current_category == "experience"


# ---------------------------------------------------------------------------
# Confusion handling
# ---------------------------------------------------------------------------

def test_confusion_clarifies_same_category():
    c = _controller()
    action = c.process_turn("Sorry, what do you mean?")
    assert action.action_type == FlowAction.CLARIFY_CONFUSION
    assert c.current_category == "introduction"


def test_repeated_confusion_eventually_skips():
    c = _controller()
    c.process_turn("Sorry, what do you mean?")
    action = c.process_turn("Can you repeat that?")
    assert action.action_type == FlowAction.POLITE_SKIP
    assert c.current_category == "experience"


# ---------------------------------------------------------------------------
# Off-topic handling
# ---------------------------------------------------------------------------

def test_off_topic_redirects_same_category():
    c = _controller(categories=["location", "salary"])
    action = c.process_turn("My current CTC is twelve lakhs.")  # location expected, salary content
    assert action.action_type == FlowAction.REDIRECT_OFF_TOPIC
    assert c.current_category == "location"


def test_off_topic_twice_polite_skips():
    c = _controller(categories=["location", "salary"])
    c.process_turn("My current CTC is twelve lakhs.")
    action = c.process_turn("My CTC expectation is fifteen lakhs.")
    assert action.action_type == FlowAction.POLITE_SKIP
    assert c.current_category == "salary"


# ---------------------------------------------------------------------------
# Vague handling
# ---------------------------------------------------------------------------

def test_vague_answer_asks_fallback():
    c = _controller(categories=["salary"])
    action = c.process_turn("I'm not sure, maybe.")
    assert action.action_type == FlowAction.ASK_FALLBACK


def test_vague_twice_polite_skips():
    c = _controller(categories=["salary"])
    c.process_turn("I'm not sure, maybe.")
    action = c.process_turn("I don't know, maybe.")
    assert action.action_type == FlowAction.POLITE_SKIP
    assert c.is_call_complete


# ---------------------------------------------------------------------------
# Repeated-answer handling
# ---------------------------------------------------------------------------

def test_repeated_answer_acknowledged_and_advances():
    c = _controller(categories=["introduction", "experience"])
    c.process_turn("Hi, I'm a developer based in Pune with a background in web development.")
    action = c.process_turn("Hi, I'm a developer based in Pune with a background in web development.")
    assert action.action_type == FlowAction.ACKNOWLEDGE_REPEATED
    assert c.is_call_complete


# ---------------------------------------------------------------------------
# OK / thin-answer follow-up handling
# ---------------------------------------------------------------------------

def test_thin_ok_answer_triggers_follow_up():
    c = _controller(categories=["experience"])
    action = c.process_turn("About four years of experience.")
    assert action.action_type == FlowAction.ASK_FOLLOW_UP
    assert c.current_category == "experience"


def test_follow_up_only_triggered_once_per_category():
    c = _controller(categories=["experience"])
    c.process_turn("About four years of experience.")
    action = c.process_turn("Yes okay that's right.")
    assert action.action_type == FlowAction.ADVANCE
    assert c.is_call_complete


def test_substantial_ok_answer_advances_directly():
    c = _controller(categories=["introduction", "experience"])
    action = c.process_turn("Hi, I'm a developer with three years of experience working on React and Node.js projects.")
    assert action.action_type == FlowAction.ADVANCE
    assert c.current_category == "experience"


# ---------------------------------------------------------------------------
# Call completion
# ---------------------------------------------------------------------------

def test_call_completes_after_last_category():
    c = _controller(categories=["introduction"])
    c.process_turn("Hi, I'm a developer with three years of experience.")
    assert c.is_call_complete
    assert c.current_category is None


def test_process_turn_after_completion_returns_end_call():
    c = _controller(categories=["introduction"])
    c.process_turn("Hi, I'm a developer with three years of experience.")
    action = c.process_turn("hello?")
    assert action.action_type == FlowAction.END_CALL


def test_action_log_records_every_turn():
    c = _controller(categories=["introduction"])
    c.process_turn("", is_silent=True)
    c.process_turn("Hi, I'm a developer with three years of experience.")
    assert len(c.action_log) == 2


def test_to_dict_round_trips_expected_keys():
    c = _controller(categories=["introduction"])
    action = c.process_turn("Hi, I'm a developer with three years of experience.")
    d = action.to_dict()
    for key in ["action_type", "message", "category", "attempt_number", "reason", "quality"]:
        assert key in d


def test_default_categories_match_day22_category_bank():
    from parsers.screening_question_bank import CATEGORIES
    c = ConversationFlowController()
    assert c.categories == CATEGORIES
