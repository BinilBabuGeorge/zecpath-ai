import json
import threading
from pathlib import Path

import pytest
from sklearn.metrics.pairwise import cosine_similarity

from parsers.answer_intent_engine import (
    AnswerQuality,
    _NON_PLACE_TOKENS,
    _looks_like_place_name,
    _score_categories,
    classify_intent,
    understand_answer,
)
from parsers.evaluation_harness import compare_runs, evaluate_predictions
from parsers.semantic_matcher import EMBED_CACHE_SIZE, SemanticMatcher, normalize_for_embedding

BENCHMARK = Path("data/ground_truth_screening/day54_intent_benchmark.json")
BEFORE = Path("data/ground_truth_screening/day54_intent_baseline_before.json")


def quality(text, category):
    return understand_answer(text, expected_category=category).quality


# ---------------------------------------------------------------------------
# The frozen benchmark: before / after, fixed / broken
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def benchmark():
    return json.load(open(BENCHMARK, encoding="utf-8"))["cases"]


@pytest.fixture(scope="module")
def runs(benchmark):
    truth = {c["id"]: c["human_expected_quality"] for c in benchmark}
    before = {b["id"]: b["predicted"] for b in json.load(open(BEFORE, encoding="utf-8"))["predictions"]}
    after = {c["id"]: understand_answer(c["text"], expected_category=c["category"]).quality.value for c in benchmark}
    return truth, before, after


def test_the_benchmark_and_its_before_snapshot_cover_the_same_cases(benchmark, runs):
    truth, before, after = runs
    assert len(benchmark) == 52 and set(truth) == set(before) == set(after)


def test_the_frozen_before_snapshot_records_the_unmodified_engine(runs):
    truth, before, _ = runs
    assert evaluate_predictions([truth[k] for k in truth], [before[k] for k in truth]).correct == 25         # 48.1%


def test_after_the_refinement_49_of_52_cases_are_correct(runs):
    truth, _, after = runs
    r = evaluate_predictions(list(truth.values()), [after[k] for k in truth], ids=list(truth))
    assert r.correct == 49 and r.accuracy_ci[0] > 0.84


def test_the_refinement_fixes_25_cases_and_newly_breaks_exactly_one_the_documented_tradeoff(runs):
    """The headline gain is net +24, but 'net' hides a regression: 25 cases fixed, 1 newly broken. The one is
    'Banana' for a location question -- without a gazetteer a nonsense word cannot be told from an unfamiliar town.
    It is documented, accepted, and pinned here so it can never grow silently."""
    c = compare_runs(*runs)
    assert len(c.fixed) == 25 and c.newly_broken == ["l25"] and c.net_change == 24
    assert c.still_wrong == ["e15", "e16"]


def test_all_16_negative_cases_stay_correct_so_the_fix_did_not_just_accept_everything(benchmark, runs):
    _, _, after = runs
    negatives = [c for c in benchmark if c["group"].startswith("negative_")]
    assert len(negatives) == 17 and all(after[c["id"]] == c["human_expected_quality"] for c in negatives)


def test_the_three_remaining_errors_are_exactly_the_documented_ones(benchmark, runs):
    truth, _, after = runs
    wrong = {c["id"]: c["group"] for c in benchmark if after[c["id"]] != truth[c["id"]]}
    assert wrong == {"e15": "hard_known_remaining", "e16": "hard_known_remaining", "l25": "known_tradeoff"}


def test_the_label_revision_is_recorded_in_the_benchmark_file():
    d = json.load(open(BENCHMARK, encoding="utf-8"))
    assert d["revisions"][0]["case"] == "l08" and "labelling error" in d["revisions"][0]["reason"]


# ---------------------------------------------------------------------------
# Education: degree abbreviations
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["B.Sc IT", "M.Sc Physics", "B.Com", "M.Com Finance", "MBA", "BCA", "MCA", "BBA", "PhD", "Ph.D",
                                   "B.E. ECE", "M.Tech CSE", "MBBS", "LLB", "B.Pharm", "bsc", "HSC", "SSC"])
def test_degree_abbreviations_are_now_recognised(text):
    assert quality(text, "education") == AnswerQuality.OK


def test_the_two_answers_day_32_documented_as_false_rejections_are_fixed():
    assert quality("B.Sc IT", "education") == AnswerQuality.OK


@pytest.mark.parametrize("text", ["I will be available", "Ma'am yes", "I am here", "ba da bing", "combat", "absc"])
def test_ordinary_words_do_not_trigger_the_education_vocabulary(text):
    assert _score_categories(text).get("education", 0.0) == 0.0


def test_ambiguous_undotted_abbreviations_are_deliberately_not_added():
    assert quality("BE Mechanical", "education") == AnswerQuality.VAGUE                  # 'be' is an English word
    assert quality("B.A English", "education") == AnswerQuality.VAGUE                    # 'ba' is too ambiguous


def test_degree_words_now_steer_intent_classification_for_longer_answers():
    assert classify_intent("I completed my MBA from a good institute").intent.value == "education"


@pytest.mark.parametrize("text", ["Not sure", "Whatever", "Hmm", "maybe a degree"])
def test_non_answers_to_an_education_question_stay_vague(text):
    assert quality(text, "education") == AnswerQuality.VAGUE


def test_a_salary_answer_to_an_education_question_is_still_off_topic():
    assert quality("Ten lakhs", "education") == AnswerQuality.OFF_TOPIC


# ---------------------------------------------------------------------------
# Location: bare place names, without a gazetteer
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["Chennai", "Kochi", "Bangalore", "Thiruvananthapuram", "Pune, Maharashtra", "Navi Mumbai", "Delhi NCR",
                                   "Thrissur Kerala", "kochi", "CHENNAI", "Bengaluru"])
def test_bare_place_names_are_accepted_for_a_location_question(text):
    assert quality(text, "location") == AnswerQuality.OK


def test_the_rule_treats_every_place_name_alike_so_small_towns_are_not_penalised():
    assert quality("Chennai", "location") == quality("Kottayam", "location") == quality("Mannarkkad", "location") == AnswerQuality.OK


@pytest.mark.parametrize("text", ["Maybe", "Not sure", "I don't know", "Depends", "Hmm", "No idea", "Whatever", "Skip", "Pass", "Later", "None", "Nothing"])
def test_non_answers_to_a_location_question_stay_vague(text):
    assert quality(text, "location") == AnswerQuality.VAGUE


@pytest.mark.parametrize("text", ["Remote", "Hybrid", "Onsite", "On-site", "WFH", "Anywhere", "Flexible", "Office"])
def test_work_mode_words_are_not_a_location(text):
    # Day 30 decided this deliberately; its tests pin it. The first draft of the Day 54 rule got it wrong.
    assert quality(text, "location") == AnswerQuality.VAGUE


def test_the_place_rule_applies_only_to_location_questions():
    for category in ("experience", "salary", "notice_period", "skills", "education", "introduction"):
        assert quality("Chennai", category) in (AnswerQuality.VAGUE, AnswerQuality.OFF_TOPIC)


def test_a_wrong_category_answer_to_a_location_question_is_still_off_topic():
    assert quality("Ten lakhs", "location") == AnswerQuality.OFF_TOPIC


def test_a_silent_or_empty_location_answer_is_missing_not_a_place():
    assert quality("", "location") == AnswerQuality.MISSING


def test_the_documented_tradeoff_a_nonsense_word_passes_for_location():
    assert quality("Banana", "location") == AnswerQuality.OK


def test_place_shape_requires_letters_and_at_most_three_tokens():
    assert _looks_like_place_name("pune")
    assert _looks_like_place_name("navi mumbai")
    assert _looks_like_place_name("st. john's")
    assert not _looks_like_place_name("pune 411001")
    assert not _looks_like_place_name("a b c d")
    assert not _looks_like_place_name("")
    assert not _looks_like_place_name("12")


def test_the_stoplist_contains_no_real_place_names():
    assert not {"chennai", "kochi", "pune", "delhi", "mumbai", "bangalore", "hyderabad", "kolkata"} & _NON_PLACE_TOKENS


def test_existing_confident_short_answers_are_unaffected():
    for text, category in (("Thirty days", "notice_period"), ("Five years", "experience"), ("Immediately", "notice_period"), ("12 LPA", "salary")):
        assert quality(text, category) == AnswerQuality.OK


# ---------------------------------------------------------------------------
# The optimised SemanticMatcher: exactly equivalent to sklearn's cosine, and faster
# ---------------------------------------------------------------------------

CORPUS = [
    "Python developer with Flask and SQL experience building REST APIs and microservices on AWS.",
    "Senior Java backend engineer, Spring Boot, Kafka, distributed systems and team leadership.",
    "React and Node.js full stack developer with MongoDB, Express, TypeScript and CI/CD pipelines.",
    "Sales executive with five years in B2B enterprise sales, CRM, lead generation and client relationships.",
    "UI UX designer skilled in Figma, user research, wireframes and design systems.",
    "Machine learning engineer: scikit-learn, TensorFlow, feature engineering and model deployment.",
    "the and of to a",
    "",
    "zzzz qqqq xxxx",
    "Python Python Python Flask Flask SQL",
]


@pytest.fixture(scope="module")
def matcher():
    return SemanticMatcher(CORPUS)


def reference_similarity(m, a, b):
    """The pre-Day 54 implementation, verbatim."""
    return round(float(cosine_similarity(m.vectorizer.transform([normalize_for_embedding(a)]), m.vectorizer.transform([normalize_for_embedding(b)]))[0][0]), 4)


def test_every_ordered_pair_matches_sklearns_cosine_exactly(matcher):
    for a in CORPUS:
        for b in CORPUS:
            assert matcher.similarity(a, b) == reference_similarity(matcher, a, b)


def test_degenerate_texts_score_zero_exactly_as_before(matcher):
    for degenerate in ("", "the and of to a", "zzzz qqqq xxxx"):
        assert matcher.similarity(degenerate, CORPUS[0]) == reference_similarity(matcher, degenerate, CORPUS[0])


def test_identical_text_scores_one_and_similarity_is_symmetric(matcher):
    assert matcher.similarity(CORPUS[0], CORPUS[0]) == 1.0
    assert matcher.similarity(CORPUS[0], CORPUS[1]) == matcher.similarity(CORPUS[1], CORPUS[0])


def test_repeated_texts_are_served_from_the_cache():
    m = SemanticMatcher(CORPUS)
    m.similarity(CORPUS[0], CORPUS[1])
    misses = m.cache_misses
    m.similarity(CORPUS[0], CORPUS[2])                     # CORPUS[0] again: a hit
    assert m.cache_misses == misses + 1 and m.cache_hits >= 1


def test_the_cache_is_bounded():
    m = SemanticMatcher(CORPUS, cache_size=3)
    for text in CORPUS:
        m.embed(text)
    assert len(m._cache) == 3 and m.cache_misses == len(CORPUS)


def test_the_cache_evicts_the_least_recently_used_text():
    m = SemanticMatcher(CORPUS, cache_size=2)
    m.embed("a one"), m.embed("b two"), m.embed("a one"), m.embed("c three")        # "b two" is now the oldest
    assert "a one" in m._cache and "c three" in m._cache and "b two" not in m._cache


def test_a_cache_size_of_zero_disables_caching_without_changing_results(matcher):
    uncached = SemanticMatcher(CORPUS, cache_size=0)
    for a, b in ((CORPUS[0], CORPUS[1]), (CORPUS[2], CORPUS[2]), (CORPUS[3], CORPUS[7])):
        assert uncached.similarity(a, b) == matcher.similarity(a, b)
    assert uncached.cache_hits == 0 and len(uncached._cache) == 0


def test_the_cached_vector_is_the_same_object_and_is_not_mutated_by_similarity():
    m = SemanticMatcher(CORPUS)
    first = m.embed(CORPUS[0])
    snapshot = first.toarray().copy()
    m.similarity(CORPUS[0], CORPUS[1])
    assert m.embed(CORPUS[0]) is first and (first.toarray() == snapshot).all()


def test_concurrent_use_gives_the_same_scores():
    m = SemanticMatcher(CORPUS, cache_size=4)
    expected = {(i, j): reference_similarity(m, CORPUS[i], CORPUS[j]) for i in range(len(CORPUS)) for j in range(len(CORPUS))}
    failures = []

    def worker():
        for (i, j), want in expected.items():
            if m.similarity(CORPUS[i], CORPUS[j]) != want:
                failures.append((i, j))

    threads = [threading.Thread(target=worker) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert failures == []


def test_default_cache_size_is_documented_and_positive():
    assert EMBED_CACHE_SIZE == 1024 and SemanticMatcher(CORPUS)._cache_size == 1024
