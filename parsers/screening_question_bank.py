"""
HR Screening Dataset Creation (Day 22)

Generates the question bank that would power PRD Phase 5 ("AI Screening
Conversation Flow") -- structured, tagged, AI-conversation-ready
questions covering the 7 categories the brief specifies: Introduction,
Education, Experience, Skills, Location, Salary, Notice Period.

This does NOT just author a static list of generic questions. It builds
on the ATS pipeline that already exists:
  - `jd_parser.parse_jd()` (an existing, previously-unused-by-the-
    current-pipeline module) supplies structured JD facts -- required
    skills, education requirement, experience band, salary range -- used
    to render role-SPECIFIC questions instead of generic ones.
  - When a candidate's resume + ATS result are also supplied, questions
    become candidate-specific: a genuinely useful, real integration is
    turning Day 13's `missing_data_notes` and skill_match's
    matched/missing skill lists directly into targeted follow-up
    questions an AI screening call should actually ask -- "we didn't
    find X on your resume, can you confirm" is a far better use of that
    data than just logging it.
  - Day 21's documented gap (`require_availability` isn't a real gate
    because notice period isn't captured pre-call) is exactly what the
    "notice_period" category exists to close -- this is where that
    information actually gets collected.

Multilingual readiness: the schema is structured for it
(SUPPORTED_LANGUAGES, per-template localization dict), but only English
("en") content is actually populated. Fabricating Hindi/Malayalam/Tamil
translations without a verified translator would risk shipping wrong
or offensive phrasing in a live screening call -- worse than not having
it. See `get_template_text()` and the module-level note below.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from parsers.jd_parser import parse_jd
from parsers.experience_parser import parse_experience, compute_total_experience
from parsers.section_extractor import extract_resume_sections, extract_jd_sections
from parsers.skill_extractor import extract_skills
from parsers.ats_scoring_engine import ATSScoreResult

# ---------------------------------------------------------------------------
# Category taxonomy -- the "question category mapping" deliverable
# ---------------------------------------------------------------------------

CATEGORY_METADATA: Dict[str, Dict] = {
    "introduction": {"default_mandatory": True, "default_scoring_importance": "high", "applicable_roles": "universal"},
    "education": {"default_mandatory": True, "default_scoring_importance": "medium", "applicable_roles": "universal"},
    "experience": {"default_mandatory": True, "default_scoring_importance": "high", "applicable_roles": "universal"},
    "skills": {"default_mandatory": True, "default_scoring_importance": "high", "applicable_roles": "job_specific"},
    "location": {"default_mandatory": True, "default_scoring_importance": "medium", "applicable_roles": "universal"},
    "salary": {"default_mandatory": True, "default_scoring_importance": "medium", "applicable_roles": "universal"},
    "notice_period": {"default_mandatory": True, "default_scoring_importance": "high", "applicable_roles": "universal"},
}
CATEGORIES = list(CATEGORY_METADATA.keys())

# ---------------------------------------------------------------------------
# Multilingual scaffolding -- honestly incomplete, not fabricated
# ---------------------------------------------------------------------------

SUPPORTED_LANGUAGES = ["en", "hi", "ml", "ta"]  # matches the PRD's stated language set
# Only "en" is populated. The other three are placeholders so a real
# translator's work has somewhere structurally correct to go -- an empty
# dict entry here is an honest "not done," not a promise this dataset is
# actually usable in those languages yet.


def get_template_text(template_id: str, templates: Dict[str, "QuestionTemplate"], lang: str = "en") -> str:
    """Looks up localized template text. Falls back to English with an
    explicit marker if the requested language isn't populated -- never
    silently returns English while claiming it's the requested language,
    and never fabricates a translation on the fly.
    """
    tmpl = templates[template_id]
    if lang in tmpl.localized_text and tmpl.localized_text[lang]:
        return tmpl.localized_text[lang]
    if lang != "en":
        return f"[NO {lang.upper()} TRANSLATION YET -- showing English] {tmpl.localized_text['en']}"
    return tmpl.localized_text["en"]


# ---------------------------------------------------------------------------
# Reusable question templates -- the "design reusable question templates" deliverable
# ---------------------------------------------------------------------------

@dataclass
class QuestionTemplate:
    template_id: str
    category: str
    localized_text: Dict[str, str]  # {"en": "...", "hi": "", "ml": "", "ta": ""}
    expected_answer_type: str  # "free_text" | "number" | "duration" | "yes_no" | "list"
    mandatory: bool
    scoring_importance: str  # "high" | "medium" | "low"


def _tmpl(template_id, category, en_text, answer_type, mandatory=None, importance=None):
    meta = CATEGORY_METADATA[category]
    return QuestionTemplate(
        template_id=template_id, category=category,
        localized_text={"en": en_text, "hi": "", "ml": "", "ta": ""},
        expected_answer_type=answer_type,
        mandatory=meta["default_mandatory"] if mandatory is None else mandatory,
        scoring_importance=meta["default_scoring_importance"] if importance is None else importance,
    )


QUESTION_TEMPLATES: Dict[str, QuestionTemplate] = {
    "intro_general": _tmpl(
        "intro_general", "introduction",
        "Could you briefly introduce yourself and walk me through your professional background?",
        "free_text",
    ),
    "education_general": _tmpl(
        "education_general", "education",
        "Could you tell me about your educational background and any certifications relevant to this role?",
        "free_text",
    ),
    "education_specific": _tmpl(
        "education_specific", "education",
        "This role prefers candidates with {degree}. Could you tell me about your educational background in that context?",
        "free_text",
    ),
    "education_missing_followup": _tmpl(
        "education_missing_followup", "education",
        "We weren't able to find a formal education section on your application -- could you walk me through your educational background?",
        "free_text", importance="high",
    ),
    "experience_general": _tmpl(
        "experience_general", "experience",
        "Could you walk me through your professional experience, starting with your most recent role?",
        "free_text",
    ),
    "experience_specific": _tmpl(
        "experience_specific", "experience",
        "This role is looking for {min_years}-{max_years} years of experience. You have approximately {candidate_years} years -- could you walk me through how your background lines up with this role?",
        "free_text",
    ),
    "experience_missing_followup": _tmpl(
        "experience_missing_followup", "experience",
        "We weren't able to find work experience entries on your application -- could you tell me about any relevant experience, including internships or projects?",
        "free_text", importance="high",
    ),
    "skill_ask": _tmpl(
        "skill_ask", "skills",
        "Could you describe your experience with {skill}?",
        "free_text",
    ),
    "skill_verify_missing": _tmpl(
        "skill_verify_missing", "skills",
        "This role requires {skill}, which we didn't find highlighted on your resume -- do you have hands-on experience with it?",
        "free_text", mandatory=True, importance="high",
    ),
    "skill_depth_matched": _tmpl(
        "skill_depth_matched", "skills",
        "You've listed {skill} on your resume -- could you walk me through a specific project where you used it?",
        "free_text", mandatory=False, importance="medium",
    ),
    "location_general": _tmpl(
        "location_general", "location",
        "What is your current location, and are you open to relocating or working {work_mode} for this role?",
        "free_text",
    ),
    "salary_general": _tmpl(
        "salary_general", "salary",
        "What are your salary expectations for this role?",
        "number",
    ),
    "salary_range_aware": _tmpl(
        "salary_range_aware", "salary",
        "This role's budgeted range is {min_salary}-{max_salary} {currency}. Could you share your current compensation and expectations?",
        "number",
    ),
    "notice_period_general": _tmpl(
        "notice_period_general", "notice_period",
        "What is your current notice period, or how soon would you be able to join if selected?",
        "duration",
    ),
}


# ---------------------------------------------------------------------------
# AI conversation-ready question objects -- the rendered, per-candidate output
# ---------------------------------------------------------------------------

@dataclass
class ScreeningQuestion:
    id: str
    category: str
    text: str  # fully rendered, ready to speak/display -- no placeholders left
    expected_answer_type: str
    mandatory: bool
    scoring_importance: str
    source: str  # "template" | "jd_derived" | "ats_followup"
    language: str = "en"


def generate_screening_questions(
    jd_text: str,
    jd_id: str,
    resume_text: Optional[str] = None,
    ats_result: Optional[ATSScoreResult] = None,
    lang: str = "en",
    max_skill_questions: int = 3,
) -> List[ScreeningQuestion]:
    """Builds the full question set for one candidate/JD pair.

    Works with JD-only input (generic-but-role-aware questions) or with
    resume_text + ats_result also supplied (adds personalized follow-ups
    from real ATS findings -- missing sections, missing/matched skills).
    Degrades gracefully: every JD-derived question has a generic fallback
    if `jd_parser.parse_jd()` can't extract a given field.
    """
    jd = parse_jd(jd_text, jd_id)
    questions: List[ScreeningQuestion] = []
    n = 0

    def add(template_id: str, source: str, **fmt):
        nonlocal n
        n += 1
        tmpl = QUESTION_TEMPLATES[template_id]
        text = get_template_text(template_id, QUESTION_TEMPLATES, lang)
        if fmt:
            text = text.format(**fmt)
        questions.append(ScreeningQuestion(
            id=f"{jd_id}-q{n:02d}", category=tmpl.category, text=text,
            expected_answer_type=tmpl.expected_answer_type, mandatory=tmpl.mandatory,
            scoring_importance=tmpl.scoring_importance, source=source, language=lang,
        ))

    # --- Universal questions ------------------------------------------
    add("intro_general", "template")

    # --- Education (JD-derived if available) ---------------------------
    edu_req = jd.get("educationRequired") or {}
    if edu_req.get("degree"):
        add("education_specific", "jd_derived", degree=edu_req["degree"])
    else:
        add("education_general", "template")

    # --- Experience (JD-derived, personalized further if resume given) ---
    exp_req = jd.get("experienceRequired") or {}
    candidate_years = None
    if resume_text:
        sections = extract_resume_sections(resume_text)
        entries = parse_experience(sections["experience"])
        summary = compute_total_experience(entries)
        candidate_years = summary.total_years

    if exp_req.get("minYears") is not None and candidate_years is not None:
        add(
            "experience_specific", "jd_derived",
            min_years=exp_req["minYears"], max_years=exp_req.get("maxYears", "+"),
            candidate_years=round(candidate_years, 1),
        )
    else:
        add("experience_general", "template")

    # --- Skills: top N required skills, using skill_extractor's clean
    # canonical names (not jd_parser.requiredSkills, which returns whole
    # requirement sentences like "Strong proficiency in React.js and
    # Node.js" rather than individual skill names -- verified this
    # produces broken, ungrammatical questions; skill_extractor is the
    # module this whole project already trusts for clean skill names) ---
    jd_sections = extract_jd_sections(jd_text)
    jd_skills = extract_skills(jd_sections["skills"])
    for skill_entry in jd_skills[:max_skill_questions]:
        add("skill_ask", "jd_derived", skill=skill_entry.name)

    # --- Location (JD-aware work mode if available) --------------------
    work_mode = "remotely" if "remote" in (jd.get("location") or "").lower() else "on-site/hybrid"
    add("location_general", "jd_derived", work_mode=work_mode)

    # --- Salary (JD range-aware if available) ---------------------------
    salary = jd.get("salaryRange") or {}
    if salary.get("min") and salary.get("max"):
        add("salary_range_aware", "jd_derived", min_salary=salary["min"], max_salary=salary["max"], currency=salary.get("currency", ""))
    else:
        add("salary_general", "template")

    # --- Notice period (always universal, always asked live -- see Day 21) ---
    add("notice_period_general", "template")

    # --- ATS-driven personalized follow-ups (only when ATS data available) ---
    if ats_result is not None:
        for note in ats_result.missing_data_notes:
            if note.startswith("education:"):
                add("education_missing_followup", "ats_followup")
            elif note.startswith("experience:"):
                add("experience_missing_followup", "ats_followup")

        skill_component = next((c for c in ats_result.components if c.name == "skill_match"), None)
        if skill_component:
            for skill in skill_component.details.get("missing_skills", [])[:2]:
                add("skill_verify_missing", "ats_followup", skill=skill)
            for skill in skill_component.details.get("matched_skills", [])[:1]:
                add("skill_depth_matched", "ats_followup", skill=skill)

    return questions
