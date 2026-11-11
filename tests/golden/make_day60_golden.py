"""
Generates tests/golden/day60_golden_outputs.json: what the services and engines returned BEFORE the Day 60 optimizations.

Run it ONLY against the pre-optimization code (the Day 59 repository state):
    python tests/golden/make_day60_golden.py --out tests/golden/day60_golden_outputs.json
    python tests/golden/make_day60_golden.py --legacy-sum --out tests/golden/day60_golden_outputs_py311sum.json

WHY TWO FILES. Python 3.12 changed sum() on floats to a more exact (compensated) algorithm. The HR scorer averages values with sum(), and
for some inputs the average lands exactly on a rounding boundary: for example (88.2 + 25.9 + 66.8 + 92.9) / 4 is 68.45 with the new sum()
and 68.44999999999999 with the old one, so the score rounds to 68.5 on Python 3.12 and to 68.4 on Python 3.11 and earlier. The untouched
Day 59 code does this too; it is not caused by the Day 60 changes. `--legacy-sum` replaces sum() with the pre-3.12 left-to-right sum while
generating, which gives the answers older Pythons produce. The test reads the file that matches the Python it runs on.
tests/test_day60_performance.py then requires the optimized code to reproduce every value exactly. Do not regenerate this file from
optimized code: that would make the test compare the code with itself.
"""

import argparse
import glob
import hashlib
import json
import logging
import random
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
logging.disable(logging.CRITICAL)

AS_OF = "2026-11-01"


def h(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:20]


def plain(x):
    return asdict(x) if is_dataclass(x) else x


def answer_corpus(n=240, seed=60):
    """Deterministic varied answers built from phrases the engines look for, so every pattern is hit and missed."""
    rng = random.Random(seed)
    parts = ["um", "uh", "you know", "i mean", "sort of", "kind of", "or something", "maybe", "i guess", "i think", "not sure", "probably",
             "yes", "no", "nope", "not really", "of course", "definitely", "i dont know", "whatever", "basically", "then", "however", "because",
             "for example", "first", "finally", "i has", "me and him", "could of", "the the", "React and Node.js", "three years", "i led a team",
             "so um yeah", "i am confused", "can you repeat that", "what do you mean", "etc", "stuff like that", "a lot of things", "anything really",
             "I built a payments API", "We reduced latency by 40 percent", "I worked in Bengaluru", "My notice period is one month"]
    out = []
    for _ in range(n):
        k = rng.randint(1, 9)
        out.append((" ".join(rng.choice(parts) for _ in range(k)) + rng.choice(["", ".", "!", "?"])).capitalize())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--legacy-sum", action="store_true", help="generate with the pre-Python-3.12 float sum()")
    args = ap.parse_args()
    if args.legacy_sum:
        import builtins

        def naive_sum(iterable, start=0):
            total = start
            for x in iterable:
                total = total + x
            return total

        builtins.sum = naive_sum
    g = {"note": "Generated from the pre-Day-60 code. See make_day60_golden.py.", "as_of": AS_OF, "legacy_sum": bool(args.legacy_sum),
         "generated_with_python": sys.version.split()[0]}

    from ats_engine.batch_service import ATSBatchService
    from ats_engine.resume_parsing_service import ResumeParsingService
    from ats_engine.service import ATSService
    from interview_ai.service import InterviewIntelligenceService
    from parsers import communication_skill_engine as cse, confidence_sentiment_engine as csent, conversation_flow_engine as cfe
    from parsers import hr_followup_engine as hfe, transcript_schema as ts
    from parsers.answer_intent_engine import _is_vague
    from parsers.skill_extractor import extract_skills
    from scoring.service import DecisionScoringService
    from screening_ai.service import ScreeningService

    jds = [Path(p).read_text(encoding="utf-8") for p in sorted(glob.glob(str(ROOT / "data/samples/jds/*.txt")))]
    resumes = [Path(p).read_text(encoding="utf-8") for p in sorted(glob.glob(str(ROOT / "data/samples/resumes/*.txt")))]
    g["ats_pairs"] = [ATSService().run({"resume_text": r, "job_description": j}) for j in jds for r in resumes]
    g["ats_n"] = {"jds": len(jds), "resumes": len(resumes)}
    g["ats_batch"] = ATSBatchService().run({"job_description": jds[0], "candidates": [{"candidate_id": f"C{i:02d}", "resume_text": r} for i, r in enumerate(resumes)]})

    parsed = {}
    for p in sorted(glob.glob(str(ROOT / "data/raw_resumes/docx/*.docx")) + glob.glob(str(ROOT / "data/raw_resumes/pdf/*.pdf"))):
        ft = Path(p).suffix.lstrip(".")
        out = ResumeParsingService(resolver=lambda ref, p=p: p).run({"candidate_id": "C1", "file_ref": Path(p).name, "file_type": ft, "as_of_date": AS_OF})
        parsed[Path(p).name] = h(out)
    g["parse_hashes"] = parsed

    skill_texts = resumes + jds + ["Skills: Reactjs, Node js, mongo db, comunication, Pythn, Javscript, Dockr, Kubernetes, AWSS, postgress", "x, yy, zzz, " * 120,
                                   "Skills: MERN stack, full stack, data science, power bi, tableau", "", "no skills listed here at all"]
    g["skills"] = [h([plain(s) for s in extract_skills(t)]) for t in skill_texts]
    g["skills_repeat"] = [h([plain(s) for s in extract_skills(t)]) for t in skill_texts]     # a second call must equal the first

    answers = answer_corpus()
    g["answer_corpus_size"] = len(answers)
    g["phrase_engines"] = {
        "assess_grammar": [h(plain(cse.assess_grammar(a))) for a in answers],
        "assess_fluency": [h(plain(cse.assess_fluency(a))) for a in answers],
        "assess_structure": [h(plain(cse.assess_structure(a))) for a in answers],
        "detect_hesitation": [h(plain(csent.detect_hesitation(a))) for a in answers],
        "detect_uncertainty": [h(plain(csent.detect_uncertainty(a))) for a in answers],
        "detect_confusion": [cfe.detect_confusion(a) for a in answers],
        "is_vague_behavioral_answer": [hfe.is_vague_behavioral_answer(a) for a in answers],
        "extract_yes_no": [ts._extract_yes_no(a) for a in answers],
        "is_vague": [_is_vague(a) for a in answers],
    }
    g["screening"] = [ScreeningService().run({"candidate_id": "C1", "turns": [{"text": a, "confidence": 0.9} for a in answers[i:i + 7]]}) for i in range(0, 70, 7)]
    g["interview_hr"] = [InterviewIntelligenceService().run({"interview_type": "hr", "answers": answers[i:i + 4]}) for i in range(0, 80, 4)]
    g["interview_technical"] = [InterviewIntelligenceService().run({"interview_type": "technical", "domain": d, "experience_years": y, "answers": answers[i:i + 3]})
                                for i, (d, y) in enumerate([("mern", 1), ("mern", 4), ("java", 2), ("devops", 6), ("mern", 0), ("java", 9)] * 3)]
    g["decision"] = [DecisionScoringService().run({"candidate_id": "C1", "ats_score": a, "screening_score": s, "hr_interview_score": hr, "technical_score": t})
                     for a, s, hr, t in [(70, 75, 80, 60), (30, 40, 50, 20), (90, 90, 90, 90), (55, 60, None, None), (45, 80, 80, 80)]
                     if True]
    Path(args.out).write_text(json.dumps(g, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print("wrote", args.out, "-", Path(args.out).stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
