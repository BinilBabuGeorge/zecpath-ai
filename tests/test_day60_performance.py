"""
Day 60 tests: speed-ups must not change answers, and the caches must be bounded and safe.

  * test_golden_*          the optimized code reproduces, exactly, what the PRE-optimization code returned (tests/golden/).
  * test_fuzzy_*           the length-window and memo in the skill extractor give difflib's own answer on 20,000 generated fragments.
  * test_embed_many_*      one batched TF-IDF call gives the same vectors and scores as one call per text.
  * test_cache_*           BoundedLRU: bounded, least-recently-used eviction, thread-safe, switchable off, no stale or shared results.
  * test_warmup_*          warm-up works for every component, leaves caches empty, restores logging.
  * test_parallel_*        worker processes give the sequential answers; a failing pool falls back instead of failing the batch.
  * test_lazy_*            services that do not score resumes no longer load scikit-learn.
  * test_scaling_*         the capacity arithmetic and the load-balancing simulator (itself checked against queueing theory).
  * test_benchmark_*       the recorded before/after benchmark runs show identical result fingerprints.
"""

import difflib
import glob
import json
import logging
import math
import os
import random
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from ats_engine.batch_service import ATSBatchService
from ats_engine.resume_parsing_service import ResumeParsingService, _PARSE_CACHE
from ats_engine.service import ATSService
from parsers import scaling_model as sm
from parsers import skill_extractor as se
from parsers.semantic_matcher import SemanticMatcher, compare_resume_to_jd
from utils import perf
from utils.perf import BoundedLRU

ROOT = Path(__file__).resolve().parent.parent
# Python 3.12 made sum() on floats more exact, which moves a few HR scores by 0.1 at rounding boundaries (see tests/golden/make_day60_golden.py).
# The untouched Day 59 code does this too. So there are two golden files, both generated from the PRE-optimization code, and the test uses
# the one that matches the Python it runs on.
GOLDEN_MAIN = json.loads((ROOT / "tests/golden/day60_golden_outputs.json").read_text(encoding="utf-8"))
GOLDEN_LEGACY = json.loads((ROOT / "tests/golden/day60_golden_outputs_py311sum.json").read_text(encoding="utf-8"))
GOLDEN = GOLDEN_MAIN if sys.version_info >= (3, 12) else GOLDEN_LEGACY
AS_OF = GOLDEN["as_of"]


def _pre_312_sum(iterable, start=0):
    """sum() as it behaved before Python 3.12: plain left-to-right addition."""
    total = start
    for x in iterable:
        total = total + x
    return total


def _texts(folder, pattern):
    return [Path(p).read_text(encoding="utf-8") for p in sorted(glob.glob(str(ROOT / folder / pattern)))]


JDS = _texts("data/samples/jds", "*.txt")
RESUMES = _texts("data/samples/resumes", "*.txt")


def _h(obj):
    import hashlib
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:20]


def _plain(x):
    from dataclasses import asdict, is_dataclass
    return asdict(x) if is_dataclass(x) else x


@pytest.fixture(autouse=True)
def _fresh_caches():
    perf.clear_all_caches()
    yield
    perf.clear_all_caches()


# ---------------------------------------------------------------------------------------------------- golden: same answers
def test_golden_ats_scores_are_identical_for_every_resume_and_job():
    assert GOLDEN["ats_n"] == {"jds": len(JDS), "resumes": len(RESUMES)}
    got = [ATSService().run({"resume_text": r, "job_description": j}) for j in JDS for r in RESUMES]
    assert got == GOLDEN["ats_pairs"]


def test_golden_ats_scores_are_identical_with_caches_warm_and_with_caches_off(monkeypatch):
    warm = [ATSService().run({"resume_text": r, "job_description": j}) for j in JDS for r in RESUMES]      # fills the caches
    again = [ATSService().run({"resume_text": r, "job_description": j}) for j in JDS for r in RESUMES]     # served from them
    assert warm == again == GOLDEN["ats_pairs"]
    monkeypatch.setenv("ZECPATH_CACHE", "off")
    off = [ATSService().run({"resume_text": r, "job_description": j}) for j in JDS for r in RESUMES]
    assert off == GOLDEN["ats_pairs"]


def test_golden_batch_result_is_identical_and_equals_single_requests():
    body = {"job_description": JDS[0], "candidates": [{"candidate_id": f"C{i:02d}", "resume_text": r} for i, r in enumerate(RESUMES)]}
    got = ATSBatchService().run(body)
    assert got == GOLDEN["ats_batch"]
    for item, resume in zip(got["results"], RESUMES):
        assert item["outcome"] == ATSService().run({"resume_text": resume, "job_description": JDS[0]})


def test_golden_resume_parsing_is_identical_for_every_sample_file():
    files = sorted(glob.glob(str(ROOT / "data/raw_resumes/docx/*.docx")) + glob.glob(str(ROOT / "data/raw_resumes/pdf/*.pdf")))
    assert len(files) == len(GOLDEN["parse_hashes"]) >= 20
    for p in files:
        out = ResumeParsingService(resolver=lambda ref, p=p: p).run({"candidate_id": "C1", "file_ref": Path(p).name, "file_type": Path(p).suffix.lstrip("."), "as_of_date": AS_OF})
        assert _h(out) == GOLDEN["parse_hashes"][Path(p).name], Path(p).name


SKILL_TEXTS = RESUMES + JDS + ["Skills: Reactjs, Node js, mongo db, comunication, Pythn, Javscript, Dockr, Kubernetes, AWSS, postgress", "x, yy, zzz, " * 120,
                               "Skills: MERN stack, full stack, data science, power bi, tableau", "", "no skills listed here at all"]


def test_golden_skill_extraction_is_identical_first_call_and_repeat():
    assert [_h([_plain(s) for s in se.extract_skills(t)]) for t in SKILL_TEXTS] == GOLDEN["skills"]
    assert [_h([_plain(s) for s in se.extract_skills(t)]) for t in SKILL_TEXTS] == GOLDEN["skills_repeat"] == GOLDEN["skills"]


def _answers():
    sys.path.insert(0, str(ROOT / "tests/golden"))
    from make_day60_golden import answer_corpus
    return answer_corpus()


def test_golden_phrase_engines_are_identical_on_240_answers():
    from parsers import communication_skill_engine as cse, confidence_sentiment_engine as csent, conversation_flow_engine as cfe
    from parsers import hr_followup_engine as hfe, transcript_schema as ts
    from parsers.answer_intent_engine import _is_vague
    answers = _answers()
    assert len(answers) == GOLDEN["answer_corpus_size"] == 240
    g = GOLDEN["phrase_engines"]
    assert [_h(_plain(cse.assess_grammar(a))) for a in answers] == g["assess_grammar"]
    assert [_h(_plain(cse.assess_fluency(a))) for a in answers] == g["assess_fluency"]
    assert [_h(_plain(cse.assess_structure(a))) for a in answers] == g["assess_structure"]
    assert [_h(_plain(csent.detect_hesitation(a))) for a in answers] == g["detect_hesitation"]
    assert [_h(_plain(csent.detect_uncertainty(a))) for a in answers] == g["detect_uncertainty"]
    assert [cfe.detect_confusion(a) for a in answers] == g["detect_confusion"]
    assert [hfe.is_vague_behavioral_answer(a) for a in answers] == g["is_vague_behavioral_answer"]
    assert [ts._extract_yes_no(a) for a in answers] == g["extract_yes_no"]
    assert [_is_vague(a) for a in answers] == g["is_vague"]
    # the corpus must exercise both outcomes of each yes/no check, or the comparison proves little
    for name in ("detect_confusion", "is_vague_behavioral_answer", "is_vague"):
        assert True in g[name] and False in g[name], name


def _check_services_against(golden):
    from interview_ai.service import InterviewIntelligenceService
    from scoring.service import DecisionScoringService
    from screening_ai.service import ScreeningService
    answers = _answers()
    assert [ScreeningService().run({"candidate_id": "C1", "turns": [{"text": a, "confidence": 0.9} for a in answers[i:i + 7]]}) for i in range(0, 70, 7)] == golden["screening"]
    assert [InterviewIntelligenceService().run({"interview_type": "hr", "answers": answers[i:i + 4]}) for i in range(0, 80, 4)] == golden["interview_hr"]
    combos = [("mern", 1), ("mern", 4), ("java", 2), ("devops", 6), ("mern", 0), ("java", 9)] * 3
    assert [InterviewIntelligenceService().run({"interview_type": "technical", "domain": d, "experience_years": y, "answers": answers[i:i + 3]})
            for i, (d, y) in enumerate(combos)] == golden["interview_technical"]
    assert [DecisionScoringService().run({"candidate_id": "C1", "ats_score": a, "screening_score": s, "hr_interview_score": hr, "technical_score": t})
            for a, s, hr, t in [(70, 75, 80, 60), (30, 40, 50, 20), (90, 90, 90, 90), (55, 60, None, None), (45, 80, 80, 80)]] == golden["decision"]


def test_golden_services_screening_interview_decision_are_identical():
    _check_services_against(GOLDEN)


def test_golden_services_are_identical_under_pre_python_312_sum_semantics(monkeypatch):
    """Runs on every Python: with sum() made to behave like Python 3.11 and earlier, the optimized code must reproduce the golden file
    generated the same way from the old code. Together with the test above this covers both float-sum behaviours."""
    import builtins
    monkeypatch.setattr(builtins, "sum", _pre_312_sum)
    _check_services_against(GOLDEN_LEGACY)


def test_finding_the_two_golden_files_differ_only_by_the_python_312_float_sum():
    """Why there are two golden files: the HR score of two cases (and in one of them the communication score) moves by 0.1 because the unchanged code averages with sum(), and
    (88.2 + 25.9 + 66.8 + 92.9) / 4 is 68.45 with the new sum() and 68.44999999999999 with the old, a rounding boundary."""
    assert GOLDEN_MAIN["legacy_sum"] is False and GOLDEN_LEGACY["legacy_sum"] is True
    differing = [k for k in GOLDEN_MAIN if GOLDEN_MAIN[k] != GOLDEN_LEGACY[k] and k not in ("legacy_sum", "generated_with_python")]
    assert differing == ["interview_hr"]
    cases = [i for i, (a, b) in enumerate(zip(GOLDEN_MAIN["interview_hr"], GOLDEN_LEGACY["interview_hr"])) if a != b]
    assert cases == [10, 11]
    for i in cases:
        a, b = GOLDEN_MAIN["interview_hr"][i], GOLDEN_LEGACY["interview_hr"][i]
        moved = [k for k in a if a[k] != b[k]]
        assert "hr_score" in moved and set(moved) <= {"hr_score", "communication_score", "relevance_score", "confidence_score"}
        for k in moved:                                    # only rounded scores move, each by exactly one rounding step (0.1)
            assert abs(a[k] - b[k]) == pytest.approx(0.1, abs=1e-9), (i, k)
    assert GOLDEN_MAIN["interview_hr"][10]["hr_score"] == 68.5 and GOLDEN_LEGACY["interview_hr"][10]["hr_score"] == 68.4
    assert round(_pre_312_sum([88.2, 25.9, 66.8, 92.9]) / 4, 1) == 68.4


# ---------------------------------------------------------------------------------------------------- fuzzy equivalence
def _fragments(n=20_000, seed=7):
    rng = random.Random(seed)
    terms = se._ALL_KNOWN_TERMS
    alphabet = "abcdefghijklmnopqrstuvwxyz .+#"
    out = []
    for _ in range(n):
        kind = rng.random()
        if kind < 0.45:                                    # a real term with 1-3 edits (typo-like, often near the cutoff)
            t = list(rng.choice(terms))
            for _ in range(rng.randint(1, 3)):
                op, pos = rng.choice("sdi"), rng.randrange(max(1, len(t)))
                if op == "s" and t:
                    t[pos % len(t)] = rng.choice(alphabet)
                elif op == "d" and len(t) > 1:
                    del t[pos % len(t)]
                else:
                    t.insert(pos, rng.choice(alphabet))
            out.append("".join(t))
        elif kind < 0.7:
            out.append("".join(rng.choice(alphabet) for _ in range(rng.randint(1, 40))))
        else:
            out.append(rng.choice(terms)[: rng.randint(1, 20)] + rng.choice(["", "s", "ing", " dev"]))
    return [f for f in out if f]


def test_fuzzy_memo_and_length_window_match_difflib_exactly_on_20000_fragments():
    frags = _fragments()
    mismatches = []
    matched = 0
    for f in frags:
        expected = difflib.get_close_matches(f, se._ALL_KNOWN_TERMS, n=1, cutoff=se.FUZZY_MATCH_THRESHOLD)
        expected = expected[0] if expected else None
        matched += expected is not None
        if se._closest_known_term(f) != expected:
            mismatches.append((f, expected, se._closest_known_term(f)))
    assert not mismatches, mismatches[:5]
    assert 1000 < matched < len(frags) - 1000, "the generated fragments must include both matches and non-matches"


def test_fuzzy_cache_off_gives_the_same_answers(monkeypatch):
    frags = _fragments(2000, seed=11)
    on = [se._closest_known_term(f) for f in frags]
    monkeypatch.setenv("ZECPATH_CACHE", "off")
    assert [se._closest_known_term(f) for f in frags] == on


def test_fuzzy_window_never_hides_a_term_difflib_would_have_returned():
    """The window is exactly difflib's own first filter, so for every length the excluded terms could not have passed it."""
    for length in range(1, 65):
        window = set(se._TERMS_BY_FRAGMENT_LENGTH[length])
        for t in se._ALL_KNOWN_TERMS:
            passes = 2.0 * min(length, len(t)) / (length + len(t)) >= se.FUZZY_MATCH_THRESHOLD
            assert (t in window) == passes


def test_extract_skills_returns_independent_copies():
    text = "Skills: React, Node.js, MongoDB"
    first = se.extract_skills(text)
    assert first
    first[0].mentions.append("tampered")
    first[0].name = "Changed"
    first.pop()
    second = se.extract_skills(text)
    assert all("tampered" not in s.mentions and s.name != "Changed" for s in second)
    assert len(second) == len(se.extract_skills(text))


# ---------------------------------------------------------------------------------------------------- embed_many
def test_embed_many_vectors_equal_one_at_a_time_vectors_array_by_array():
    import numpy as np
    a, b = SemanticMatcher(RESUMES[:2]), SemanticMatcher(RESUMES[:2])
    texts = RESUMES[:8] + ["", " ", RESUMES[0]]            # includes empty text and a duplicate
    many, single = a.embed_many(texts), [b.embed(t) for t in texts]
    for x, y in zip(many, single):
        assert np.array_equal(x.indptr, y.indptr) and np.array_equal(x.indices, y.indices) and np.array_equal(x.data, y.data)


def test_embed_many_uses_and_fills_the_cache_and_batches_misses_into_one_call():
    m = SemanticMatcher(RESUMES[:2])
    calls = []
    real = m.vectorizer.transform
    m.vectorizer.transform = lambda texts: (calls.append(len(texts)), real(texts))[1]
    m.embed_many([RESUMES[0], RESUMES[1], RESUMES[0]])
    assert calls == [2]                                    # three requested, two distinct, ONE transform call
    m.embed_many([RESUMES[0], RESUMES[1]])
    assert calls == [2] and m.cache_hits >= 2              # all served from the cache


def test_compare_resume_to_jd_equals_the_one_text_at_a_time_path():
    class OneAtATime:                                      # a matcher with only similarity(): forces the old code path
        def __init__(self, inner):
            self.inner = inner

        def similarity(self, a, b):
            return self.inner.similarity(a, b)

    from parsers.section_extractor import extract_jd_sections, extract_resume_sections
    for jd in JDS[:3]:
        for resume in RESUMES[:6]:
            rs, js = extract_resume_sections(resume), extract_jd_sections(jd)
            fast = compare_resume_to_jd(rs, js, SemanticMatcher([resume, jd]), {"strong": 0.7, "moderate": 0.4})
            slow = compare_resume_to_jd(rs, js, OneAtATime(SemanticMatcher([resume, jd])), {"strong": 0.7, "moderate": 0.4})
            assert fast == slow


# ---------------------------------------------------------------------------------------------------- BoundedLRU
def test_cache_is_bounded_by_entries_and_evicts_least_recently_used_first():
    c = BoundedLRU("t_entries", max_items=3)
    for k in "abc":
        c.get_or_compute(k, lambda k=k: k.upper())
    c.get_or_compute("a", lambda: "never")                 # touch a: now b is the oldest
    c.get_or_compute("d", lambda: "D")                     # evicts b
    assert len(c) == 3 and c.stats()["evictions"] == 1
    assert c.get_or_compute("b", lambda: "recomputed") == "recomputed"
    assert c.get_or_compute("a", lambda: "x") == "A"


def test_cache_is_bounded_by_bytes_and_never_stores_a_value_bigger_than_the_budget():
    c = BoundedLRU("t_bytes", max_items=100, max_bytes=100, sizeof=len)
    for i in range(10):
        c.get_or_compute(i, lambda i=i: "x" * 30)
    assert c.stats()["approx_bytes"] <= 100 and len(c) <= 3
    c.get_or_compute("huge", lambda: "y" * 500)
    assert "huge" not in c._data and c.stats()["approx_bytes"] <= 100


def test_cache_counts_hits_and_misses_and_can_be_cleared_and_disabled(monkeypatch):
    c = BoundedLRU("t_stats", max_items=5)
    c.get_or_compute("k", lambda: 1)
    c.get_or_compute("k", lambda: 2)
    s = c.stats()
    assert (s["hits"], s["misses"], s["hit_rate"]) == (1, 1, 0.5)
    c.clear()
    assert len(c) == 0
    monkeypatch.setenv("ZECPATH_CACHE", "off")
    calls = []
    for _ in range(3):
        c.get_or_compute("k", lambda: calls.append(1) or 1)
    assert len(calls) == 3 and len(c) == 0
    assert BoundedLRU("t_zero", max_items=0).get_or_compute("k", lambda: 9) == 9
    with pytest.raises(ValueError):
        BoundedLRU("t_neg", max_items=-1)


def test_cache_is_thread_safe_under_contention():
    c = BoundedLRU("t_threads", max_items=50)
    errors = []

    def hammer(seed):
        rng = random.Random(seed)
        try:
            for _ in range(3000):
                k = rng.randrange(200)
                assert c.get_or_compute(k, lambda k=k: k * 2) == k * 2
        except Exception as exc:                          # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=hammer, args=(s,)) for s in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors and len(c) <= 50


def test_cache_registry_reports_every_day60_cache_and_their_total_memory_ceiling_is_small():
    stats = perf.all_cache_stats()
    assert {"skill_fuzzy", "skill_extract_text", "resume_parse"} <= set(stats)
    ceiling = sum(s["max_bytes"] for s in stats.values() if s["max_bytes"])
    assert ceiling <= 30_000_000, "the combined byte budget of the Day 60 caches must stay under 30 MB"


def test_skill_caches_stay_within_their_budgets_when_flooded():
    for i in range(12_000):
        se._closest_known_term(f"fragment{i}x")
    for i in range(1500):
        se.extract_skills(f"Skills: React, Node.js, item {i}")
    for name in ("skill_fuzzy", "skill_extract_text"):
        s = perf.all_cache_stats()[name]
        assert s["entries"] <= s["max_items"] and s["approx_bytes"] <= s["max_bytes"], s


def test_percentile_helper():
    assert perf.percentile([1, 2, 3, 4, 5], 0.5) == 3 and perf.percentile([1, 2, 3, 4, 5], 1.0) == 5 and perf.percentile([7], 0.99) == 7
    with pytest.raises(ValueError):
        perf.percentile([], 0.5)


# ---------------------------------------------------------------------------------------------------- parse cache
DOCX = str(sorted(glob.glob(str(ROOT / "data/raw_resumes/docx/*.docx")))[0])


def _parse(path=DOCX, cid="C1", ftype="docx", as_of=AS_OF):
    return ResumeParsingService(resolver=lambda ref: path).run({"candidate_id": cid, "file_ref": "x", "file_type": ftype, "as_of_date": as_of})


def test_parse_cache_returns_the_same_result_with_each_callers_own_candidate_id():
    a = _parse(cid="C1")
    b = _parse(cid="C2")
    assert _PARSE_CACHE.stats()["hits"] == 1
    assert a["candidate_id"] == "C1" and b["candidate_id"] == "C2"
    assert {**a, "candidate_id": "x"} == {**b, "candidate_id": "x"}


def test_parse_cache_results_are_not_shared_between_callers():
    a = _parse()
    a["skills"].append({"name": "tampered"})
    a["cleaned_text"] = "tampered"
    b = _parse()
    assert b["cleaned_text"] != "tampered" and all(s["name"] != "tampered" for s in b["skills"])


def test_parse_cache_is_keyed_by_file_bytes_not_by_path(tmp_path):
    from docx import Document
    path = str(tmp_path / "cv.docx")
    d1 = Document(); d1.add_paragraph("Skills: Python"); d1.save(path)
    first = _parse(path)
    d2 = Document(); d2.add_paragraph("Skills: Java, Kotlin"); d2.save(path)        # same path, different file
    second = _parse(path)
    assert first["cleaned_text"] != second["cleaned_text"]
    assert _PARSE_CACHE.stats()["hits"] == 0


def test_parse_cache_key_includes_the_as_of_date_and_the_file_type():
    a = _parse(as_of="2026-11-01")
    b = _parse(as_of="2027-11-01")
    assert b["experience"]["total_years"] > a["experience"]["total_years"] or a["experience"]["total_years"] == 0
    assert a["as_of_date"] != b["as_of_date"] and _PARSE_CACHE.stats()["hits"] == 0


def test_parse_cache_does_not_cache_errors_and_a_fixed_file_then_works(tmp_path):
    path = tmp_path / "late.pdf"
    bad = ResumeParsingService(resolver=lambda ref: str(path)).run({"candidate_id": "C1", "file_ref": "x", "file_type": "pdf"})
    assert bad["status"] == "error" and bad["error"]["code"] == "file_not_found"
    pdf = sorted(glob.glob(str(ROOT / "data/raw_resumes/pdf/*.pdf")))[0]
    path.write_bytes(Path(pdf).read_bytes())
    good = ResumeParsingService(resolver=lambda ref: str(path)).run({"candidate_id": "C1", "file_ref": "x", "file_type": "pdf"})
    assert good["status"] == "success"


def test_parse_with_caches_off_equals_parse_with_caches_on(monkeypatch):
    on = _parse()
    monkeypatch.setenv("ZECPATH_CACHE", "off")
    assert _parse() == on


# ---------------------------------------------------------------------------------------------------- warm-up
def test_warmup_runs_every_component_and_leaves_caches_empty():
    from utils.warmup import COMPONENTS, warm_up
    timings = warm_up()
    assert set(timings) == set(COMPONENTS) | {"total"} and all(v >= 0 for v in timings.values())
    assert all(s["entries"] == 0 for s in perf.all_cache_stats().values())


def test_warmup_is_repeatable_validates_names_and_restores_logging():
    from utils.warmup import warm_up
    before = logging.root.manager.disable
    warm_up(("decision",))
    warm_up(("decision",))
    assert logging.root.manager.disable == before
    with pytest.raises(ValueError):
        warm_up(("nonsense",))
    assert logging.root.manager.disable == before


def test_warmup_does_not_change_later_results():
    from utils.warmup import warm_up
    warm_up(("ats", "screening"))
    assert ATSService().run({"resume_text": RESUMES[0], "job_description": JDS[0]}) == GOLDEN["ats_pairs"][0]


def test_warmup_makes_the_first_real_request_fast_in_a_fresh_process():
    code = ("import sys,time,logging,json; logging.disable(logging.CRITICAL); sys.path.insert(0,%r)\n"
            "from utils.warmup import warm_up\nfrom ats_engine.service import ATSService\n"
            "t=time.perf_counter(); warm_up(('ats',)); warm=(time.perf_counter()-t)*1000\n"
            "t=time.perf_counter(); ATSService().run({'resume_text':'Skills: React','job_description':'Required Skills: React'}); first=(time.perf_counter()-t)*1000\n"
            "print(json.dumps([warm, first]))" % str(ROOT))
    warm, first = json.loads(subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(ROOT)).stdout.strip().splitlines()[-1])
    assert first < 100, f"first real request took {first} ms after warm-up"
    assert warm > first, "the one-time cost should have been paid in the warm-up, not in the request"


# ---------------------------------------------------------------------------------------------------- parallel batch
def _batch_body(n):
    return {"job_description": JDS[0], "candidates": [{"candidate_id": f"C{i:03d}", "resume_text": RESUMES[i % len(RESUMES)] + f"\nNote {i}."} for i in range(n)]}


def test_parallel_workers_give_exactly_the_sequential_results():
    from ats_engine import parallel
    body = _batch_body(70)
    sequential = ATSBatchService(workers=1).run(body)
    try:
        parallel_result = ATSBatchService(workers=2, min_parallel_batch=10).run(body)
    finally:
        parallel.shutdown_pool()
    if parallel_result["warnings"]:
        pytest.skip("worker processes could not be started on this machine; the fallback is tested separately")
    assert parallel_result == sequential


def test_parallel_falls_back_to_sequential_with_a_warning_when_the_pool_fails(monkeypatch):
    from ats_engine import parallel

    def boom(*a, **k):
        raise OSError("cannot start worker processes")

    monkeypatch.setattr(parallel, "score_batch_parallel", boom)
    body = _batch_body(12)
    out = ATSBatchService(workers=4, min_parallel_batch=1).run(body)
    assert out["status"] == "success" and out["warnings"] and out["results"] == ATSBatchService(workers=1).run(body)["results"]


def test_parallel_is_not_used_for_small_batches_or_when_workers_is_one(monkeypatch):
    from ats_engine import parallel

    def never(*a, **k):
        raise AssertionError("the pool must not be used here")

    monkeypatch.setattr(parallel, "score_batch_parallel", never)
    assert ATSBatchService(workers=4).run(_batch_body(10))["status"] == "success"                    # below the default threshold
    assert ATSBatchService(workers=1, min_parallel_batch=1).run(_batch_body(10))["status"] == "success"


def test_parallel_worker_count_can_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("ZECPATH_BATCH_WORKERS", "3")
    assert ATSBatchService()._workers == 3
    monkeypatch.setenv("ZECPATH_BATCH_WORKERS", "")
    assert ATSBatchService()._workers == 1


# ---------------------------------------------------------------------------------------------------- lazy imports
def _modules_loaded_after(snippet):
    code = ("import sys,logging; logging.disable(logging.CRITICAL); sys.path.insert(0,%r)\n%s\n"
            "print(sorted(m for m in ('sklearn','scipy','numpy') if m in sys.modules))" % (str(ROOT), snippet))
    return eval(subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(ROOT)).stdout.strip().splitlines()[-1])


def test_lazy_services_that_do_not_score_resumes_do_not_load_scikit_learn():
    assert _modules_loaded_after("from scoring.service import DecisionScoringService\nDecisionScoringService().run({'candidate_id':'c','ats_score':60,'hr_interview_score':70})") == []
    assert _modules_loaded_after("from interview_ai.service import InterviewIntelligenceService\nInterviewIntelligenceService().run({'interview_type':'hr','answers':['I led a team.']})") == []
    assert _modules_loaded_after("from screening_ai.service import ScreeningService\nScreeningService().run({'candidate_id':'c','turns':[{'text':'I have three years of experience.'}]})") == []


def test_lazy_the_ats_service_still_loads_it_when_it_scores():
    assert "sklearn" in _modules_loaded_after("from ats_engine.service import ATSService\nATSService().run({'resume_text':'Skills: React','job_description':'Required Skills: React'})")


# ---------------------------------------------------------------------------------------------------- scaling model
def test_scaling_workers_needed_and_utilization():
    assert sm.workers_needed(100, 0.01, 0.6) == 2          # 1.0 core of work at 0.6 target -> 2
    assert sm.workers_needed(0, 0.01) == 1
    assert sm.utilization(100, 0.01, 4) == pytest.approx(0.25)
    for bad in ((1, 1, 0.0), (1, 1, 1.0)):
        with pytest.raises(ValueError):
            sm.workers_needed(*bad)
    with pytest.raises(ValueError):
        sm.workers_needed(-1, 1)
    with pytest.raises(ValueError):
        sm.utilization(1, 1, 0)


def test_scaling_capacity_plan_grows_with_volume_and_includes_spare_workers():
    rows = [sm.capacity_plan(n, 0.022) for n in (10_000, 1_000_000, 10_000_000)]
    assert [r.workers_with_spare for r in rows] == sorted(r.workers_with_spare for r in rows)
    assert all(r.workers_with_spare == r.cores_at_target + 1 for r in rows)
    assert all(r.utilization_at_workers < 0.6 for r in rows)


def test_scaling_erlang_c_matches_known_values():
    assert sm.erlang_c(1, 0.5) == pytest.approx(0.5)                       # M/M/1: P(wait) = utilization
    assert sm.erlang_c(2, 1.0) == pytest.approx(1 / 3, abs=1e-9)            # classic M/M/2 at offered load 1
    assert sm.erlang_c(2, 3.0) == 1.0 and sm.mean_wait_mmc(10, 1, 5) == math.inf


def test_scaling_the_simulator_matches_queueing_theory_for_an_mm1_queue():
    """Why the simulator can be trusted: a plain M/M/1 queue must show the textbook mean wait rho/(mu-lambda)."""
    cls = sm.RequestClass("x", rate_per_s=0.5, mean_service_s=1.0)
    arrivals = sm.generate_arrivals([cls], horizon_s=200_000, seed=3, exponential=True)
    lat = sm.simulate(arrivals, 1, "shared_queue")["x"]
    simulated_wait = sum(lat) / len(lat) - 1.0
    assert simulated_wait == pytest.approx(sm.mean_wait_mmc(0.5, 1.0, 1), rel=0.06)       # theory: 1.0 s
    arrivals = sm.generate_arrivals([sm.RequestClass("x", 1.2, 1.0)], horizon_s=300_000, seed=4, exponential=True)      # M/M/2 at utilization 0.6
    lat = sm.simulate(arrivals, 2, "shared_queue")["x"]
    assert sum(lat) / len(lat) - 1.0 == pytest.approx(sm.mean_wait_mmc(1.2, 1.0, 2), rel=0.05)


def test_scaling_simulation_is_reproducible_and_validates_inputs():
    classes = [sm.RequestClass("a", 5, 0.01), sm.RequestClass("b", 0.2, 0.3)]
    a1, a2 = sm.generate_arrivals(classes, 100, 5), sm.generate_arrivals(classes, 100, 5)
    assert a1 == a2 and a1 != sm.generate_arrivals(classes, 100, 6)
    assert sm.simulate(a1, 3, "random", 1) == sm.simulate(a1, 3, "random", 1)
    with pytest.raises(ValueError):
        sm.simulate(a1, 2, "nonsense")
    with pytest.raises(ValueError):
        sm.simulate(a1, 0, "round_robin")


def test_scaling_a_shared_queue_never_does_worse_than_blind_round_robin_for_mixed_work():
    classes = [sm.RequestClass("quick", 100, 0.002), sm.RequestClass("slow", 7.0, 0.3, cv=0.2)]
    arrivals = sm.generate_arrivals(classes, 600, 9)
    p99 = {p: sm.summarize_latencies(sm.simulate(arrivals, 4, p, 9)["quick"])["p99_ms"] for p in sm.POLICIES}
    assert p99["shared_queue"] <= p99["least_connections"] <= p99["round_robin"]
    assert p99["shared_queue"] < p99["random"]


def test_scaling_dedicated_pools_protect_quick_requests_from_slow_jobs():
    classes = [sm.RequestClass("quick", 100, 0.002), sm.RequestClass("slow", 7.0, 0.3, cv=0.2)]       # 4 workers, utilization about 0.58
    arrivals = sm.generate_arrivals(classes, 600, 12)
    mixed = sm.summarize_latencies(sm.simulate(arrivals, 4, "shared_queue", 12)["quick"])["p99_ms"]
    fast, _ = sm.split_by_pool(arrivals, ("quick",))
    dedicated = sm.summarize_latencies(sm.simulate(fast, 2, "shared_queue", 12)["quick"])["p99_ms"]
    assert dedicated < mixed / 10, (dedicated, mixed)


# ---------------------------------------------------------------------------------------------------- recorded benchmark
def _runs(label):
    return [json.loads(Path(p).read_text(encoding="utf-8")) for p in sorted(glob.glob(str(ROOT / f"data/results/day60_runs/day60_bench_{label}_*.json")))]


def test_benchmark_recorded_runs_exist_and_every_workload_has_the_same_fingerprint_before_and_after():
    before, after, nocache = _runs("before"), _runs("after"), _runs("nocache")
    assert len(before) >= 3 and len(after) >= 3 and len(nocache) >= 3
    for run in before + after + nocache:
        for name, w in run["workloads"].items():
            assert w["fingerprint"] == before[0]["workloads"][name]["fingerprint"], f"{name}: the answers changed"


def test_benchmark_recorded_speedups_are_real_for_the_optimized_workloads():
    import statistics
    med = lambda runs, k, f="p50_ms": statistics.median(r["workloads"][k][f] for r in runs)
    before, after = _runs("before"), _runs("after")
    for name in ("ats_single_same_jd", "screening_7_turns", "interview_hr_4_answers"):
        assert med(after, name) < med(before, name) * 0.8, name
    assert med(after, "ats_batch_100", "median_ms") < med(before, "ats_batch_100", "median_ms") * 0.8
    assert med(after, "parse_pdf_same_file_again") < med(before, "parse_pdf_same_file_again") / 20


def test_benchmark_recorded_memory_and_cold_start_improvements():
    b, a = _runs("before")[0], _runs("after")[0]
    for svc in ("decision", "interview", "screening"):
        assert a["memory_by_service_mb"][svc] < b["memory_by_service_mb"][svc] * 0.25, svc
    assert a["cold_start"]["first_call_ms"] < b["cold_start"]["first_call_ms"] / 20
    assert a["cold_start"]["warmup_ms"] is not None and b["cold_start"]["warmup_ms"] is None


def test_documents_exist_and_name_every_benchmark_workload():
    report = (ROOT / "docs/day60_performance_benchmark_report.md").read_text(encoding="utf-8")
    strategy = (ROOT / "docs/day60_scalability_strategy.md").read_text(encoding="utf-8")
    for name in _runs("after")[0]["workloads"]:
        assert f"`{name}`" in report, name
    for word in ("load balancing", "Microservice", "autoscal", "warm-up", "Idempotency-Key"):
        assert word.lower() in strategy.lower(), word
