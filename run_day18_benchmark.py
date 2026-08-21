"""
Day 18 performance benchmark. Run once BEFORE the optimizations are applied
(git stash) and once AFTER (git stash pop) to get genuine before/after
numbers -- not estimates.

Five benchmarks, one per fix:
  1. normalize_for_embedding() -- sequential re.sub chain vs combined pattern
  2. extract_skills() exact-match path -- N re.finditer passes vs 1
  3. score_candidate() -- redundant extract_skills() calls on JD text
  4. parse_certifications() -- catastrophic backtracking on a pathological line
  5. extract_skills() fuzzy path -- unbounded fragment count on noisy input
"""

import sys
import time

sys.path.insert(0, ".")

from pathlib import Path

RESUME_DIR = Path("data/samples/resumes")
JD_DIR = Path("data/samples/jds")


def bench(label, fn, repeat=1):
    start = time.perf_counter()
    for _ in range(repeat):
        fn()
    elapsed = time.perf_counter() - start
    print(f"  {label:55s} {elapsed:8.4f}s  ({elapsed/repeat*1000:.2f}ms/call)")
    return elapsed


def main():
    resume_files = sorted(RESUME_DIR.glob("*.txt"))
    jd_files = sorted(JD_DIR.glob("*.txt"))
    resume_texts = [f.read_text() for f in resume_files]
    jd_texts = [f.read_text() for f in jd_files]
    corpus = resume_texts + jd_texts

    print("=" * 78)
    print(f"DAY 18 BENCHMARK  ({len(resume_texts)} resumes x {len(jd_texts)} JDs = "
          f"{len(resume_texts)*len(jd_texts)} pairs)")
    print("=" * 78)

    # --- 1. normalize_for_embedding over the full batch --------------------
    from parsers.semantic_matcher import normalize_for_embedding
    print("\n[1] normalize_for_embedding() across every resume+JD, x10 passes")
    bench("normalize_for_embedding batch", lambda: [normalize_for_embedding(t) for t in corpus], repeat=10)

    # --- 2. extract_skills exact-match path over the full batch ------------
    from parsers.skill_extractor import extract_skills
    print("\n[2] extract_skills() across every resume+JD, x10 passes")
    bench("extract_skills batch", lambda: [extract_skills(t) for t in corpus], repeat=10)

    # --- 3. score_candidate over every resume x JD pair ---------------------
    from parsers.semantic_matcher import SemanticMatcher
    from parsers.ats_scoring_engine import score_candidate
    matcher = SemanticMatcher(corpus)
    print(f"\n[3] score_candidate() across all {len(resume_texts)*len(jd_texts)} resume x JD pairs")

    def run_all_pairs():
        for r in resume_texts:
            for j in jd_texts:
                score_candidate(r, j, matcher)
    bench("score_candidate full batch", run_all_pairs)

    # --- 4. parse_certifications on a pathological no-open-paren line ------
    from parsers.education_parser import parse_certifications
    print("\n[4] parse_certifications() on a pathological comma-heavy, no-'(' line")
    # Growth is quadratic in line length for this pattern (confirmed by direct
    # measurement: 1000 reps -> 1.6s, 2000 reps -> 6.4s), not linear -- needs
    # real length to show up. 1500 reps lands consistently in the few-seconds
    # range pre-fix. Real-world trigger: a resume with a long, malformed
    # "certifications" paragraph copy-pasted without any parenthesized years.
    pathological_line = "Certifications:\n" + ("Advanced Professional Certificate in Something, " * 1500)
    t0 = time.perf_counter()
    parse_certifications(pathological_line)
    elapsed = time.perf_counter() - t0
    print(f"  {'single pathological line (1500 reps, ~72KB)':55s} {elapsed:8.4f}s")

    # --- 5. extract_skills fuzzy path on noisy/garbled input ---------------
    print("\n[5] extract_skills() on a noisy resume (3000 short garbage fragments)")
    import random
    random.seed(42)
    junk_words = ["xzq", "flrm", "qwzt", "brnk", "vxpl", "trqm", "zxfn"]
    noisy_text = "Skills: " + ", ".join(
        "".join(random.choice(junk_words) for _ in range(2)) for _ in range(3000)
    )
    t0 = time.perf_counter()
    extract_skills(noisy_text)
    elapsed = time.perf_counter() - t0
    print(f"  {'noisy resume (3000 fragments)':55s} {elapsed:8.4f}s")

    print("\n" + "=" * 78)


if __name__ == "__main__":
    main()
