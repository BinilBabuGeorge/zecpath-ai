from parsers.speech_to_text import (
    RawSTTResult, CleanedTranscript, CleanStatus,
    MockSTTProvider, clean_transcript,
)
from run_day24_stt_accuracy_report import word_error_rate, GROUND_TRUTH_SENTENCES, PROFILES


# ---------------------------------------------------------------------------
# MockSTTProvider -- deterministic, clearly-labeled simulation
# ---------------------------------------------------------------------------

def test_mock_provider_is_deterministic_for_same_seed_and_inputs():
    p1 = MockSTTProvider(seed=5)
    p2 = MockSTTProvider(seed=5)
    r1 = p1.simulate("I have three years of experience.", accent="indian_en", noise_level=0.5)
    r2 = p2.simulate("I have three years of experience.", accent="indian_en", noise_level=0.5)
    assert r1.text == r2.text
    assert r1.confidence == r2.confidence


def test_mock_provider_zero_noise_preserves_text_and_full_confidence():
    p = MockSTTProvider(seed=1)
    r = p.simulate("Hello there.", accent="clear", noise_level=0.0)
    assert r.text == "Hello there."
    assert r.confidence == 1.0


def test_mock_provider_accent_substitution_is_word_boundary_safe():
    # "years" -> "yours" substitution must not corrupt "yearly", which
    # merely contains "year" as a substring, not the whole word "years".
    p = MockSTTProvider(seed=1)
    r = p.simulate("I get a yearly bonus after three years.", accent="indian_en", noise_level=0.0)
    assert "yearly" in r.text
    assert "yours" in r.text  # "years" (the standalone word) was substituted


def test_mock_provider_confidence_decreases_with_noise_level():
    p = MockSTTProvider(seed=1)
    low = p.simulate("test sentence here", accent="clear", noise_level=0.1)
    high = p.simulate("test sentence here", accent="clear", noise_level=0.8)
    assert high.confidence < low.confidence


def test_mock_provider_high_noise_can_produce_silence():
    p = MockSTTProvider(seed=1)
    found_silent = any(
        p.simulate("some sentence", accent="clear", noise_level=0.99).is_silent
        for _ in range(20)
    )
    # not asserting every call is silent (it's probabilistic) -- just that
    # the mechanism can actually fire within a reasonable number of tries
    assert found_silent


# ---------------------------------------------------------------------------
# clean_transcript -- filler word removal (word-boundary safe)
# ---------------------------------------------------------------------------

def test_filler_words_removed():
    result = clean_transcript(RawSTTResult(text="um so I have uh three years", confidence=0.9))
    assert "um" not in result.text.lower().split()
    assert "uh" not in result.text.lower().split()
    assert result.had_filler_words is True


def test_filler_word_removal_is_word_boundary_safe():
    # "umbrella" contains "um" as a substring but is a real word --
    # must not be stripped or mangled.
    result = clean_transcript(RawSTTResult(text="I sell umbrellas for a living", confidence=0.9))
    assert "umbrella" in result.text.lower()


def test_filler_phrases_removed():
    result = clean_transcript(RawSTTResult(text="I mean I have you know good experience", confidence=0.9))
    assert "you know" not in result.text.lower()
    assert "i mean" not in result.text.lower()


def test_no_filler_words_leaves_had_filler_words_false():
    result = clean_transcript(RawSTTResult(text="I have three years of experience.", confidence=0.9))
    assert result.had_filler_words is False


# ---------------------------------------------------------------------------
# clean_transcript -- self-correction / interrupted speech
# ---------------------------------------------------------------------------

def test_self_correction_keeps_only_final_statement():
    result = clean_transcript(RawSTTResult(text="I have three years— no wait, four years of experience", confidence=0.9))
    assert "three" not in result.text.lower()
    assert "four" in result.text.lower()
    assert result.status == CleanStatus.SELF_CORRECTED
    assert result.had_self_correction is True


def test_self_correction_uses_the_last_marker_not_the_first():
    text = "I studied at ABC college— no wait, XYZ college— actually no, I mean ABC College again"
    result = clean_transcript(RawSTTResult(text=text, confidence=0.9))
    assert "ABC College again" in result.text or "abc college again" in result.text.lower()


def test_no_correction_marker_leaves_had_self_correction_false():
    result = clean_transcript(RawSTTResult(text="I have three years of experience.", confidence=0.9))
    assert result.had_self_correction is False
    assert result.status != CleanStatus.SELF_CORRECTED


# ---------------------------------------------------------------------------
# clean_transcript -- partial / cutoff answers
# ---------------------------------------------------------------------------

def test_trailing_connector_word_flagged_as_partial():
    result = clean_transcript(RawSTTResult(text="my notice period is two weeks and", confidence=0.9))
    assert result.status == CleanStatus.PARTIAL_ANSWER
    assert len(result.notes) > 0


def test_complete_sentence_not_flagged_as_partial():
    result = clean_transcript(RawSTTResult(text="my notice period is two weeks.", confidence=0.9))
    assert result.status != CleanStatus.PARTIAL_ANSWER


# ---------------------------------------------------------------------------
# clean_transcript -- silence detection
# ---------------------------------------------------------------------------

def test_is_silent_flag_produces_silent_status():
    result = clean_transcript(RawSTTResult(text="", confidence=0.0, is_silent=True))
    assert result.status == CleanStatus.SILENT
    assert result.text == ""


def test_empty_text_without_silent_flag_still_treated_as_silent():
    # empty/whitespace-only text has nothing to clean regardless of the
    # is_silent flag's value -- there's no speech content either way.
    result = clean_transcript(RawSTTResult(text="   ", confidence=0.5, is_silent=False))
    assert result.status == CleanStatus.SILENT


def test_silent_result_has_explanatory_note():
    result = clean_transcript(RawSTTResult(text="", confidence=0.0, is_silent=True))
    assert len(result.notes) > 0
    assert "no speech" in result.notes[0].lower()


# ---------------------------------------------------------------------------
# clean_transcript -- punctuation and case
# ---------------------------------------------------------------------------

def test_sentence_capitalized_and_terminal_punctuation_added():
    result = clean_transcript(RawSTTResult(text="i can join immediately", confidence=0.9))
    assert result.text[0] == "I" or result.text.startswith("I ")
    assert result.text.endswith(".")


def test_standalone_i_capitalized():
    result = clean_transcript(RawSTTResult(text="yes i think i can do that", confidence=0.9))
    words = result.text.split()
    assert "I" in words
    assert "i" not in [w.strip(".,") for w in words]


def test_double_spaces_collapsed():
    result = clean_transcript(RawSTTResult(text="I have   three    years", confidence=0.9))
    assert "  " not in result.text


def test_already_well_formed_text_passes_through_cleanly():
    result = clean_transcript(RawSTTResult(text="I have three years of experience.", confidence=0.9))
    assert result.status == CleanStatus.OK
    assert result.text == "I have three years of experience."


# ---------------------------------------------------------------------------
# word_error_rate -- a standard, real metric
# ---------------------------------------------------------------------------

def test_wer_identical_strings_is_zero():
    assert word_error_rate("hello world", "hello world") == 0.0


def test_wer_single_word_substitution():
    # 1 substitution out of 2 reference words = 0.5
    assert word_error_rate("hello world", "hello there") == 0.5


def test_wer_case_insensitive():
    assert word_error_rate("Hello World", "hello world") == 0.0


def test_wer_empty_reference_and_hypothesis_is_zero():
    assert word_error_rate("", "") == 0.0


def test_wer_empty_reference_nonempty_hypothesis_is_one():
    assert word_error_rate("", "some words here") == 1.0


def test_wer_deletion_counted_correctly():
    # reference has 3 words, hypothesis drops the last one -> 1 deletion / 3
    assert word_error_rate("one two three", "one two") == 1 / 3


# ---------------------------------------------------------------------------
# Cross-cutting guarantee: cleaning never makes WER worse than raw
# ---------------------------------------------------------------------------

def test_cleaning_never_increases_wer_across_all_simulated_profiles():
    provider = MockSTTProvider(seed=123)
    for accent, noise in PROFILES:
        for gt in GROUND_TRUTH_SENTENCES:
            raw = provider.simulate(gt, accent=accent, noise_level=noise)
            cleaned = clean_transcript(raw)
            raw_wer = word_error_rate(gt, raw.text)
            cleaned_wer = word_error_rate(gt, cleaned.text)
            assert cleaned_wer <= raw_wer + 1e-9, (
                f"cleaning made WER worse for accent={accent} noise={noise}: "
                f"raw_wer={raw_wer:.3f} cleaned_wer={cleaned_wer:.3f}"
            )
