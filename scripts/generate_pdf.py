"""
ds-radar CV generator
Usage: python generate_pdf.py <eval_path> [--model MODEL]
Example: python generate_pdf.py evals/deepmind_2026-04-01.md --model claude-haiku-4-5-20251001

If the eval contains a real JD ([JD_SOURCE: REAL]), calls the configured LLM to
rewrite a canonical CV built from profile/profile.yaml tailored to that job.
If JD is mock, falls back to keyword injection.
Always writes Markdown CV to applications/cv_{company}_{YYYYMMDD}.md and
attempts to render applications/cv_{company}_{YYYYMMDD}.pdf via Playwright.
"""

import argparse
import html
import os
import re
import sys
from datetime import date
from pathlib import Path

import markdown as md
import yaml
try:
    from identity import build_job_key, record_artifact_identity
except ImportError:  # pragma: no cover - module execution fallback
    from scripts.identity import build_job_key, record_artifact_identity

# ── Paths ─────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
PROFILE_PATH = REPO_ROOT / "profile" / "profile.yaml"
APPLICATIONS_DIR = REPO_ROOT / "applications"

CV_REWRITE_MAX_TOKENS = 2500
GITHUB_PROFILE_URL = "https://github.com/renzorico"
DEFAULT_CANDIDATE_TITLE = "Data Scientist | AI & Analytics Engineer"

COMPANY_DESCRIPTIONS: dict[str, str] = {
    "le wagon": (
        "Le Wagon is an intensive coding bootcamp and tech education company that trains career-switchers "
        "and professionals in software, data, and AI skills. It solves practical upskilling and employability "
        "problems for learners and teams moving into technical roles."
    ),
    "bac engineering / socotec": (
        "BAC Engineering / SOCOTEC operates in engineering, construction, and infrastructure delivery, supporting "
        "the design and coordination work needed for complex built-environment projects. It helps project teams "
        "and asset owners reduce risk, improve delivery quality, and keep technical information aligned."
    ),
    "bac engineering": (
        "BAC Engineering works in engineering and construction project delivery, helping technical teams produce "
        "coordinated models and documentation for infrastructure and built-environment projects. It solves "
        "information-quality and coordination problems for project stakeholders and end clients."
    ),
    "socotec": (
        "SOCOTEC provides testing, inspection, certification, and engineering services across the built "
        "environment. It helps infrastructure, construction, and property clients manage compliance, quality, "
        "and technical risk."
    ),
}

PROJECT_DETAILS: dict[str, dict[str, str]] = {
    "legalize-co": {
        "name": "legalize-co",
        "tech": "Python, web scraping, Markdown pipelines, git",
        "repo_url": "https://github.com/renzorico/legalize-co",
        "summary": (
            "Built a legislation-as-code pipeline for Colombian law that turns official legal texts into "
            "version-controlled Markdown, making public legislation easier to scrape, diff, inspect, and reuse in "
            "developer-friendly workflows."
        ),
    },
    "ds-radar": {
        "name": "ds-radar",
        "tech": "Python, OpenAI API, Playwright",
        "repo_url": "https://github.com/renzorico/ds-radar",
        "summary": (
            "Built a four-stage agentic pipeline that scans ATS boards, filters for sponsorship fit, scores roles "
            "across ten dimensions, and generates tailored CVs and application artifacts from a single workflow."
        ),
    },
    "no botes tu voto": {
        "name": "No botes tu voto",
        "tech": "Python, FastAPI, product delivery",
        "repo_url": "https://github.com/renzorico/colombia-matcher",
        "website_url": "https://nobotestuvoto.vercel.app/",
        "summary": (
            "Shipped a civic-tech platform that matched users to parties based on policy alignment, combining NLP, "
            "scoring logic, and product delivery for an audience of 10,000+ users."
        ),
    },
    "the london bible": {
        "name": "The London Bible",
        "tech": "Python, GeoPandas, Streamlit",
        "repo_url": "https://github.com/renzorico/the-london-bible",
        "website_url": "https://the-london-bible.netlify.app/",
        "summary": (
            "Built an interactive London data atlas by aggregating public datasets across transport, affordability, "
            "green space, and neighbourhood indicators into a decision-support tool."
        ),
    },
    "adcc universe": {
        "name": "ADCC Universe",
        "tech": "Python, network analysis, interactive visualisation",
        "repo_url": "https://github.com/renzorico/bjj-universe",
        "website_url": "https://renzorico.github.io/bjj-universe/",
        "summary": (
            "Developed an interactive network graph explorer that maps athlete relationships and match histories, "
            "turning dense competition data into a navigable frontend experience."
        ),
    },
    "un speeches nlp": {
        "name": "UN Speeches NLP",
        "tech": "Python, scikit-learn, Streamlit, BigQuery",
        "repo_url": "https://github.com/renzorico/speeches-at-UN",
        "website_url": "https://speeches-at-un.streamlit.app/",
        "summary": (
            "Analysed 8,000+ UN General Debate speeches with topic modelling and temporal analysis to surface how "
            "global priorities shifted over time, then packaged the findings in an interactive app."
        ),
    },
}

EXPERIENCE_DETAILS: dict[str, dict[str, object]] = {
    "data scientist|le wagon": {
        "positioning": (
            "Treat this as applied data-science delivery in an education environment, centered on analytical coaching, code review, project scoping, and experimentation support rather than classroom teaching."
        ),
        "highlights": [
            "Reviewed notebooks, code, and end-to-end analytics projects across Python, SQL, machine learning, and experimentation workflows.",
            "Helped learners scope ambiguous problems, test assumptions, debug models, and communicate findings clearly.",
            "Supported 1000+ learners across applied analytics and machine learning work.",
        ],
        "avoid": [
            "Do not over-index on learner volume alone.",
            "Prioritise transferable strengths such as communication, project scoping, analytical rigor, debugging, experimentation, and code review.",
            "Do not lead bullets with 'taught' or 'mentored' unless unavoidable.",
            "Mention learner count at most once across the entire role.",
            "Do not frame the role primarily as classroom teaching.",
        ],
    },
    "freelance data scientist|": {
        "positioning": (
            "Emphasise consulting, dashboards, reporting workflows, and the private finance app without repeating the Projects section verbatim."
        ),
        "highlights": [
            "Built a private business management and personal finance application.",
            "Delivered consulting for data analytics teams focused on dashboarding, reporting workflows, and structuring messy operational data.",
        ],
        "avoid": [
            "Do not reuse project bullets verbatim from No botes tu voto, UN Speeches NLP, or The London Bible.",
            "Use Experience to describe consulting scope and delivery style; use Projects to describe named builds.",
            "Do not describe the private application as client-facing.",
            "Do not include the private application's URL or product name.",
            "Do not claim product/commercial strategy work that is not explicitly verified.",
        ],
        "must_include_terms": ["private business management and personal finance application"],
    },
    "bim modeler|bac engineering / socotec": {
        "positioning": (
            "Translate BIM work into structured modelling, QA, precision, and cross-functional coordination rather than domain-specific construction jargon."
        ),
        "highlights": [
            "Worked in the installation department using Revit, Navisworks, and AutoCAD.",
            "Coordinated technical models and drawings across disciplines, reducing ambiguity and surfacing inconsistencies before downstream delivery.",
            "Brings detail orientation, structured documentation, and workflow discipline that transfer well to data quality and analytics operations.",
        ],
        "avoid": [
            "Do not make this sound like a data role.",
            "Do extract transferable strengths: structured information management, QA, and coordination under constraints.",
        ],
    },
}

SKILL_GROUPS = {
    "Languages": ["Python (data + ML).", "SQL.", "JavaScript."],
    "Data & ML": [
        "Pandas / NumPy / scikit-learn.",
        "TensorFlow/Keras.",
        "Feature engineering.",
        "Statistical analysis.",
        "Experimentation and A/B testing.",
        "NLP and UMAP.",
        "LLMs and agentic AI systems.",
    ],
    "Data Engineering": [
        "BigQuery and GCP.",
        "Docker.",
        "Playwright.",
        "API integration.",
        "Web scraping.",
    ],
    "Product Engineering": [
        "FastAPI.",
        "Vercel and Railway.",
        "Streamlit.",
        "GeoPandas and geospatial analysis.",
    ],
    "Tools & Workflow": [
        "Git.",
        "Teaching and data/ML instruction.",
        "Linux / CLI-focused workflows.",
    ],
}

ARCHETYPE_CV_CONFIG: dict[str, dict[str, object]] = {
    "ds-product": {
        "title_line": "Data Scientist, Product Analytics & ML",
        "summary_seed": [
            "Data scientist working across Python, SQL, experimentation, and applied machine learning through teaching and freelance product delivery.",
            "Best positioned for product-facing roles that combine analytics, feature engineering, stakeholder communication, and decision-support systems."
        ],
        "skill_group_order": ["Languages", "Data & ML", "Data Engineering", "Product Engineering", "Tools & Workflow"],
        "skill_priority": [
            "Python (data + ML).", "SQL.", "Statistical analysis.", "Experimentation and A/B testing.",
            "Feature engineering.", "Pandas / NumPy / scikit-learn.", "BigQuery and GCP.",
            "API integration.", "FastAPI.", "Streamlit."
        ],
        "bullet_emphasis": "Emphasise experimentation, product metrics, feature engineering, stakeholder communication, dashboard thinking, and translating ambiguous business questions into decision-support outputs.",
    },
    "data-analyst": {
        "title_line": "Data Analyst, Analytics Specialist",
        "summary_seed": [
            "Data-focused analyst with hands-on experience in Python, SQL, dashboards, reporting, and decision-support workflows across teaching and freelance delivery.",
            "Best positioned for roles centered on business analysis, KPI tracking, dashboarding, stakeholder support, and turning messy data into clear operational insight."
        ],
        "skill_group_order": ["Languages", "Data & ML", "Data Engineering", "Product Engineering", "Tools & Workflow"],
        "skill_priority": [
            "SQL.", "Python (data + ML).", "Statistical analysis.", "Pandas / NumPy / scikit-learn.",
            "Experimentation and A/B testing.", "BigQuery and GCP.", "Streamlit.", "API integration."
        ],
        "bullet_emphasis": "Emphasise dashboards, reporting, KPI tracking, stakeholder support, analytical clarity, and turning data into clear recommendations and operational insight.",
    },
    "analytics-engineer": {
        "title_line": "Analytics Engineer, Data Scientist",
        "summary_seed": [
            "Analytics-oriented data scientist with hands-on experience in Python, SQL, dashboards, data modeling, and business-facing decision support.",
            "Best positioned for roles that sit between analytics, data infrastructure, reporting, and stakeholder enablement."
        ],
        "skill_group_order": ["Languages", "Data Engineering", "Data & ML", "Product Engineering", "Tools & Workflow"],
        "skill_priority": [
            "SQL.", "Python (data + ML).", "BigQuery and GCP.", "API integration.", "Web scraping.",
            "Statistical analysis.", "Pandas / NumPy / scikit-learn.", "Streamlit.", "FastAPI."
        ],
        "bullet_emphasis": "Emphasise SQL, metrics layers, dashboards, reporting workflows, analytical reliability, and enabling teams with clearer data products.",
    },
    "data-engineer": {
        "title_line": "Data Engineer, Analytics Engineer",
        "summary_seed": [
            "Python-first data builder with experience in pipelines, APIs, scraping, structured datasets, and production-oriented analytics workflows.",
            "Best positioned for roles focused on data movement, transformation, reliability, and the systems that support analytics and ML use cases."
        ],
        "skill_group_order": ["Languages", "Data Engineering", "Data & ML", "Product Engineering", "Tools & Workflow"],
        "skill_priority": [
            "Python (data + ML).", "SQL.", "BigQuery and GCP.", "Docker.", "Playwright.",
            "API integration.", "Web scraping.", "FastAPI.", "Git."
        ],
        "bullet_emphasis": "Emphasise data pipelines, ingestion, automation, scraping, APIs, reproducible workflows, and turning messy inputs into usable structured datasets.",
    },
    "ml-engineer": {
        "title_line": "Machine Learning Engineer, Data Scientist",
        "summary_seed": [
            "Machine-learning-oriented data scientist with hands-on experience in Python, feature engineering, model development, and applied NLP workflows.",
            "Best positioned for roles that combine analytical rigor with production-minded ML delivery and close collaboration with product or engineering teams."
        ],
        "skill_group_order": ["Languages", "Data & ML", "Data Engineering", "Product Engineering", "Tools & Workflow"],
        "skill_priority": [
            "Python (data + ML).", "SQL.", "Pandas / NumPy / scikit-learn.", "TensorFlow/Keras.",
            "Feature engineering.", "Statistical analysis.", "NLP and UMAP.", "BigQuery and GCP.",
            "Docker.", "FastAPI."
        ],
        "bullet_emphasis": "Emphasise model-building workflows, feature engineering, NLP, experimentation, deployment-minded thinking, and collaboration needed to productionise high-value models.",
    },
    "ai-engineer": {
        "title_line": "AI Engineer, Applied ML Engineer",
        "summary_seed": [
            "AI-focused data scientist building Python-based systems around LLMs, automation, decision support, and applied machine learning.",
            "Best positioned for roles that combine agentic workflows, model-enabled products, and pragmatic engineering for real user or business outcomes."
        ],
        "skill_group_order": ["Languages", "Data & ML", "Data Engineering", "Product Engineering", "Tools & Workflow"],
        "skill_priority": [
            "Python (data + ML).", "SQL.", "LLMs and agentic AI systems.", "Pandas / NumPy / scikit-learn.",
            "Feature engineering.", "API integration.", "Playwright.", "FastAPI.", "Docker."
        ],
        "bullet_emphasis": "Emphasise LLM workflows, automation, agentic systems, APIs, rapid prototyping, and applied ML work that drives concrete operational value.",
    },
}

try:
    from llm_provider import describe_task_model, format_usage, run_cv_tailoring
except ImportError:  # pragma: no cover - module execution fallback
    from scripts.llm_provider import describe_task_model, format_usage, run_cv_tailoring

# ── ATS Unicode normalisation ─────────────────────────────────────────────────

def normalize_for_ats(text: str) -> str:
    """Replace typographic characters with ASCII equivalents for ATS compatibility."""
    return (
        text
        .replace("\u201c", '"').replace("\u201d", '"')   # " "  → "
        .replace("\u2018", "'").replace("\u2019", "'")   # ' '  → '
        .replace("\u2013", "-").replace("\u2014", "-")   # – —  → -
        .replace("\u2026", "...")                         # …    → ...
        .replace("\u2022", "-")                           # •    → -
        .replace("\u00a0", " ")                           # NBSP → space
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text


def strip_html_comments(text: str) -> str:
    return re.sub(r"<!--[\s\S]*?-->", "", text).strip()


def _first_non_empty(values: list[str]) -> str:
    for value in values:
        clean = str(value).strip()
        if clean:
            return clean
    return ""


def _project_key(project_text: str) -> str:
    head = str(project_text).split(":", 1)[0].strip()
    return re.sub(r"\s+", " ", head).lower()


def _parse_experience_item(item: str) -> dict[str, str]:
    match = re.match(r"^(?P<title>.+?)\s+[—–-]\s+(?P<company>.+?),\s+(?P<location>.+?)\s+\((?P<dates>.+)\)$", item)
    if not match:
        match = re.match(r"^(?P<title>.+?)\s+[—–-]\s+(?P<company>.+?)\s+\((?P<dates>.+)\)$", item)
    if not match:
        match = re.match(r"^(?P<title>.+?)\s+\((?P<dates>.+)\)$", item)
    if match:
        data = match.groupdict()
        data.setdefault("location", "")
        data.setdefault("company", "")
        data["company_description"] = COMPANY_DESCRIPTIONS.get(data["company"].strip().lower(), "")
        return data
    return {
        "title": item.strip(),
        "company": "",
        "location": "",
        "dates": "",
        "company_description": "",
    }


def _experience_key(title: str, company: str) -> str:
    return f"{title.strip().lower()}|{company.strip().lower()}"


def _experience_record(item: str) -> dict[str, object]:
    record = _parse_experience_item(item)
    details = EXPERIENCE_DETAILS.get(
        _experience_key(record.get("title", ""), record.get("company", "")),
        {},
    )
    merged: dict[str, object] = dict(record)
    merged["positioning"] = details.get("positioning", "")
    merged["highlights"] = details.get("highlights", [])
    merged["avoid"] = details.get("avoid", [])
    merged["must_include_terms"] = details.get("must_include_terms", [])
    return merged


def _parse_education_item(item: str) -> dict[str, str]:
    match = re.match(r"^(?P<degree>.+?)\s+[—–-]\s+(?P<institution>.+?)\s+\((?P<dates>.+)\)$", item)
    if match:
        return match.groupdict()
    return {"degree": item.strip(), "institution": "", "dates": ""}


def _project_record(item: str) -> dict[str, str]:
    key = _project_key(item)
    details = PROJECT_DETAILS.get(key, {})
    name = details.get("name") or item.split(":", 1)[0].strip()
    return {
        "name": name,
        "summary": details.get("summary", item.strip()),
        "tech": details.get("tech", ""),
        "website_url": details.get("website_url", ""),
        "repo_url": details.get("repo_url", ""),
    }


# ── Step 1: Parse eval report ─────────────────────────────────────────────────

def parse_eval(eval_path: Path) -> dict:
    text = eval_path.read_text(encoding="utf-8")

    title_match = re.search(r"^#\s+(.+?)\s+@\s+(.+)$", text, re.MULTILINE)
    if not title_match:
        print(f"Error: cannot parse title line from {eval_path.name}")
        sys.exit(1)
    role = title_match.group(1).strip()
    company = title_match.group(2).strip()

    grade_match = re.search(r"\*\*Grade:\*\*\s*([A-F])", text)
    score_match = re.search(r"\*\*Score:\*\*\s*([\d.]+)/5\.0", text)
    grade = grade_match.group(1) if grade_match else "?"
    score = score_match.group(1) if score_match else "?"

    # Dimension scores table: "| Role Match | 4.2 |"
    dim_scores: dict[str, float] = {}
    for m in re.finditer(r"\|\s*([^|]+?)\s*\|\s*([\d.]+)\s*\|", text):
        key = m.group(1).strip().lower().replace(" ", "_")
        try:
            dim_scores[key] = float(m.group(2))
        except ValueError:
            pass

    kw_match = re.search(r"##\s+Top Keywords\s*\n([^\n#]+)", text)
    keywords: list[str] = []
    if kw_match:
        keywords = [k.strip() for k in kw_match.group(1).split(",") if k.strip()]

    angle_match = re.search(r"##\s+Interview Angle\s*\n([^\n#]+)", text)
    interview_angle = angle_match.group(1).strip() if angle_match else ""

    # JD block: "## Job Description\n[JD_SOURCE: REAL]\n<text>"
    jd_source = "MOCK"
    jd_text = ""
    jd_match = re.search(r"##\s+Job Description\s*\n(\[JD_SOURCE: (REAL|MOCK)\])\n([\s\S]+?)(?=\n##|\Z)", text)
    if jd_match:
        jd_source = jd_match.group(2)
        jd_text = jd_match.group(3).strip()

    url_match = re.search(r"\*\*URL:\*\*\s*([^\n|]+)", text)
    url = url_match.group(1).strip() if url_match else ""

    archetype_match = re.search(r"\*\*Archetype:\*\*\s*([^\n|]+)", text)
    archetype = archetype_match.group(1).strip() if archetype_match else "ds-product"

    return {
        "role": role,
        "company": company,
        "url": url,
        "grade": grade,
        "score": score,
        "dim_scores": dim_scores,
        "keywords": keywords,
        "interview_angle": interview_angle,
        "jd_source": jd_source,
        "jd_text": jd_text,
        "archetype": archetype,
    }


# ── Step 2: Load base CV ──────────────────────────────────────────────────────

ARCHETYPE_PROJECT_ORDER: dict[str, list[str]] = {
    "ds-product":         ["legalize-co", "London Bible", "UN Speeches", "No botes", "ADCC", "ds-radar"],
    "data-analyst":       ["London Bible", "No botes", "UN Speeches", "legalize-co", "ds-radar", "ADCC"],
    "ml-engineer":        ["ds-radar", "legalize-co", "UN Speeches", "London Bible", "ADCC", "No botes"],
    "analytics-engineer": ["London Bible", "legalize-co", "UN Speeches", "ADCC", "No botes", "ds-radar"],
    "data-engineer":      ["legalize-co", "ds-radar", "No botes", "UN Speeches", "London Bible", "ADCC"],
    "ai-engineer":        ["ds-radar", "legalize-co", "UN Speeches", "ADCC", "No botes", "London Bible"],
}


def reorder_projects_for_archetype(projects: list, archetype: str) -> list:
    """Reorder project list so archetype-preferred projects appear first.

    Projects not matching any slug keep their original relative order at the end.
    """
    order = ARCHETYPE_PROJECT_ORDER.get(archetype, ARCHETYPE_PROJECT_ORDER["ds-product"])
    slugs = [s.lower() for s in order]

    def rank(p: str) -> int:
        p_lower = p.lower()
        for i, slug in enumerate(slugs):
            if slug.lower() in p_lower:
                return i
        return len(slugs)

    return sorted(projects, key=rank)

def _compact_list(items: list[str], limit: int = 8) -> str:
    picked = [str(item).strip() for item in items if str(item).strip()][:limit]
    return ", ".join(picked)


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        text = str(item).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(text)
    return ordered


def _archetype_config(archetype: str) -> dict[str, object]:
    return ARCHETYPE_CV_CONFIG.get(archetype, ARCHETYPE_CV_CONFIG["ds-product"])


def _ordered_skills(items: list[str], priority: list[str]) -> list[str]:
    priority_map = {item.rstrip(".").lower(): idx for idx, item in enumerate(priority)}
    return sorted(
        items,
        key=lambda item: (priority_map.get(item.rstrip(".").lower(), len(priority_map)), items.index(item)),
    )


def _build_archetype_summary(archetype: str) -> str:
    config = _archetype_config(archetype)
    summary_seed = config.get("summary_seed", [])
    if not isinstance(summary_seed, list):
        return ""
    return " ".join(str(sentence).strip() for sentence in summary_seed if str(sentence).strip())


def load_profile_data() -> dict:
    if not PROFILE_PATH.exists():
        raise FileNotFoundError(f"Profile file not found: {PROFILE_PATH}")

    profile = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(profile, dict):
        raise ValueError(f"Invalid profile YAML: {PROFILE_PATH}")

    identity = profile.get("identity", {}) or {}
    if not identity.get("name"):
        raise ValueError("profile/profile.yaml is missing identity.name")

    verified_sections = (
        profile.get("experience", []),
        profile.get("education", []),
        profile.get("projects", []),
        (profile.get("tech_stack", {}) or {}).get("strong_skills", []),
    )
    if not any(section for section in verified_sections):
        raise ValueError("profile/profile.yaml has no verified experience, education, projects, or skills")

    return profile


def build_canonical_cv(profile: dict, archetype: str = "ds-product") -> str:
    identity = profile.get("identity", {}) or {}
    contact = profile.get("contact", {}) or {}
    tech = profile.get("tech_stack", {}) or {}
    archetype_config = _archetype_config(archetype)

    name = identity.get("name", "Renzo Rico").strip()
    location = identity.get("location", "").strip()
    role_title = str(archetype_config.get("title_line", DEFAULT_CANDIDATE_TITLE)).strip()
    contact_parts = [
        location,
        contact.get("phone", "").strip(),
        contact.get("email", "").strip(),
        GITHUB_PROFILE_URL,
        contact.get("linkedin_url", "").strip(),
    ]
    meta_line = " | ".join(part for part in contact_parts if part)

    experience_items = [_experience_record(str(item).strip()) for item in profile.get("experience", []) if str(item).strip()]
    education_items = [_parse_education_item(str(item).strip()) for item in profile.get("education", []) if str(item).strip()]
    project_items = [_project_record(str(item).strip()) for item in profile.get("projects", []) if str(item).strip()]
    strong_skills = [str(item).strip() for item in tech.get("strong_skills", []) if str(item).strip()]
    must_match = [str(item).strip() for item in tech.get("must_match_skills", []) if str(item).strip()]
    summary_text = _build_archetype_summary(archetype)

    lines = [f"# {name}"]
    lines.extend(["", role_title])
    if meta_line:
        lines.extend(["", meta_line])

    lines.extend(["", "## Summary", summary_text])

    normalized_skills = {s.rstrip(".").lower() for s in strong_skills + must_match}
    skill_group_order = archetype_config.get("skill_group_order", list(SKILL_GROUPS.keys()))
    if not isinstance(skill_group_order, list):
        skill_group_order = list(SKILL_GROUPS.keys())
    skill_priority = archetype_config.get("skill_priority", [])
    if not isinstance(skill_priority, list):
        skill_priority = []
    skill_lines: list[str] = []
    for label in [str(group) for group in skill_group_order if str(group) in SKILL_GROUPS]:
        items = SKILL_GROUPS[label]
        available = [item for item in items if item.rstrip(".").lower() in normalized_skills]
        available = _ordered_skills(available, [str(item) for item in skill_priority])
        if available:
            skill_lines.append(f"- **{label}:** {', '.join(available)}")
    if not skill_lines:
        skill_lines = [f"- **Core:** {', '.join(_unique(strong_skills or must_match))}"]

    lines.extend(["", "## Skills"])
    lines.extend(skill_lines)

    if experience_items:
        lines.extend(["", "## Experience"])
        for experience in experience_items:
            heading_bits = [experience.get("title", "").strip(), experience.get("company", "").strip()]
            heading = " - ".join(part for part in heading_bits if part)
            dates = experience.get("dates", "").strip()
            location_text = experience.get("location", "").strip()
            if dates:
                heading = f"{heading} | {dates}" if heading else dates
            lines.extend(["", f"### {heading}"])
            if location_text:
                lines.append(location_text)
            if experience.get("company_description"):
                lines.append(experience["company_description"])
            if experience.get("positioning"):
                lines.append(f"Focus: {str(experience.get('positioning', '')).strip()}")
            highlights = [str(item).strip() for item in experience.get("highlights", []) if str(item).strip()]
            if highlights:
                lines.append(f"Verified highlights: {' | '.join(highlights)}")
            avoid_notes = [str(item).strip() for item in experience.get("avoid", []) if str(item).strip()]
            if avoid_notes:
                lines.append(f"Avoid: {' | '.join(avoid_notes)}")
            must_include_terms = [str(item).strip() for item in experience.get("must_include_terms", []) if str(item).strip()]
            if must_include_terms:
                lines.append(f"Must include if relevant: {' | '.join(must_include_terms)}")
            lines.append(
                "- Add role-relevant bullets grounded in the verified profile and job description, "
                f"with emphasis on {str(archetype_config.get('bullet_emphasis', '')).strip()}"
            )

    if project_items:
        lines.extend(["", "## Projects"])
        for project in project_items[:5]:
            project_heading = f"### {project['name']}"
            if project.get("tech"):
                project_heading += f" ({project['tech']})"
            lines.extend(["", project_heading])
            project_url = project.get("website_url") or project.get("repo_url")
            if project_url:
                lines.append(f"Project: {project_url}")
            if project.get("summary"):
                lines.append(f"- {project['summary']}")

    if education_items:
        lines.extend(["", "## Education"])
        for education in education_items:
            degree = education.get("degree", "").strip()
            institution = education.get("institution", "").strip()
            dates = education.get("dates", "").strip()
            if institution:
                line = f"- **{degree}** - {institution}"
            else:
                line = f"- **{degree}**"
            if dates:
                line += f" ({dates})"
            lines.append(line)

    return "\n".join(lines).strip() + "\n"


def build_profile_fact_block(profile: dict, archetype: str = "ds-product") -> str:
    identity = profile.get("identity", {}) or {}
    contact = profile.get("contact", {}) or {}
    tech = profile.get("tech_stack", {}) or {}
    archetype_config = _archetype_config(archetype)
    experience_items = [_experience_record(str(item).strip()) for item in profile.get("experience", []) if str(item).strip()]
    education_items = [_parse_education_item(str(item).strip()) for item in profile.get("education", []) if str(item).strip()]
    project_items = [_project_record(str(item).strip()) for item in profile.get("projects", []) if str(item).strip()]
    group_order = archetype_config.get("skill_group_order", list(SKILL_GROUPS.keys()))
    if not isinstance(group_order, list):
        group_order = list(SKILL_GROUPS.keys())
    skill_lines = [
        f"- {label}: {', '.join(SKILL_GROUPS[label])}"
        for label in [str(group) for group in group_order if str(group) in SKILL_GROUPS]
    ]
    lines = [
        f"- name: {identity.get('name', '').strip()}",
        f"- target_title: {str(archetype_config.get('title_line', DEFAULT_CANDIDATE_TITLE)).strip()}",
        f"- selected_archetype: {archetype}",
        f"- archetype_summary_seed: {_build_archetype_summary(archetype)}",
        f"- archetype_bullet_emphasis: {str(archetype_config.get('bullet_emphasis', '')).strip()}",
        f"- location: {identity.get('location', '').strip()}",
        f"- email: {contact.get('email', '').strip()}",
        f"- phone: {contact.get('phone', '').strip()}",
        f"- linkedin: {contact.get('linkedin_url', '').strip()}",
        f"- github: {GITHUB_PROFILE_URL}",
        "- recruiter_priorities: qualifications, similar experience, visible project links, skimmable XYZ bullets, education last",
        "- experience:",
    ]
    for item in experience_items:
        lines.append(
            "  - "
            f"title={item.get('title', '')}; company={item.get('company', '')}; "
            f"location={item.get('location', '')}; dates={item.get('dates', '')}; "
            f"company_description={item.get('company_description', '') or 'n/a'}; "
            f"positioning={item.get('positioning', '') or 'n/a'}; "
            f"highlights={' | '.join(str(v) for v in item.get('highlights', []) if str(v).strip()) or 'n/a'}; "
            f"avoid={' | '.join(str(v) for v in item.get('avoid', []) if str(v).strip()) or 'n/a'}; "
            f"must_include_terms={' | '.join(str(v) for v in item.get('must_include_terms', []) if str(v).strip()) or 'n/a'}"
        )
    lines.append("- projects:")
    for item in project_items[:5]:
        lines.append(
            "  - "
            f"name={item.get('name', '')}; website_url={item.get('website_url', '') or 'n/a'}; "
            f"repo_url={item.get('repo_url', '') or 'n/a'}; "
            f"tech={item.get('tech', '') or 'n/a'}; summary={item.get('summary', '')}"
        )
    lines.append("- education:")
    for item in education_items:
        lines.append(
            "  - "
            f"degree={item.get('degree', '')}; institution={item.get('institution', '')}; dates={item.get('dates', '')}"
        )
    lines.append("- grouped_skills:")
    lines.extend(f"  {line}" for line in skill_lines)
    lines.append(f"- verified_skills: {_compact_list(tech.get('strong_skills', []), 12) or 'n/a'}")
    return "\n".join(lines)


# ── Step 3a: Provider-backed CV rewrite (REAL JD path) ───────────────────────

_CV_REWRITE_PROMPT = """\
Rewrite the CV below tailored to the job description provided.

=== CONTENT RULES (mandatory) ===
- All factual content must come from the provided structured profile data and canonical CV.
- You may reorder, rephrase, condense, and selectively omit items, but you may not invent any facts.
- Never fabricate employers, clients, institutions, degrees, certifications, dates, locations, projects, or skills.
- If a field is absent from the provided profile data, omit it; never guess.
- Reorder bullets so the most relevant experience for this JD comes first.
- Inject important JD keywords naturally — no keyword stuffing.
- Rewrite the professional summary as 2 sentences: sentence 1 grounds the candidate in their current work; sentence 2 connects it forward to this role ({role} at {company}). Avoid generic phrases like "passionate about" or "seeking opportunities".
- Keep the same sections as the canonical CV unless there is a strong reason to drop one.
- Treat the canonical CV as the selected archetype template. Preserve its title line, skill emphasis, project ordering logic, and overall positioning unless the JD creates a strong reason to adjust within that archetype.
- Avoid repeating the same accomplishment in both Experience and Projects. Use Experience for role scope, delivery style, and transferable value; use Projects for named builds.
- For teaching roles, emphasise transferable technical and analytical value over learner-count vanity metrics.
- Preserve proper nouns and named artifacts from verified profile facts when they materially strengthen credibility. Do not replace them with generic descriptions.
- For Le Wagon specifically, frame the role through analytical coaching, code review, project scoping, experimentation, and stakeholder communication. Do not lead bullets with `taught` or `mentored`, and mention learner volume at most once.
- For Le Wagon, use exactly 2 bullets.
- For Freelance Data Scientist, use exactly 2 bullets.
- Write in a plain, professional style. Prefer direct facts over polished CV language.
- Avoid inflated phrasing such as `positioned to`, `drive`, `rigorous`, `high-velocity`, `stakeholder-ready`, `decision-support`, `production-quality`, `fast-moving`, or similar filler unless the exact wording is needed from the JD.
- Keep sentences compact and concrete.

=== SECTION ORDER (follow exactly) ===
1. Contact / meta line (name already in H1 header — do not repeat it)
2. Summary (2 sentences)
3. Skills
4. Experience
5. Projects
6. Education

=== FORMATTING RULES ===
- Output a complete CV in GitHub-flavoured Markdown only. No preamble, no explanation, no code fences.
- Every bullet under Experience and Projects should follow the Google XYZ idea: what was done, how it was done, and the outcome. Use real numbers from the profile where available.
- Vary sentence structure naturally. Do not repeat `resulting in` mechanically across bullets.
- Keep the title line aligned with the selected archetype while still matching the job naturally.
- Use exactly one coherent title line, not multiple stacked titles or two separate role labels.
- Put dates on the same line as each Experience heading using the format: `### Title - Company | Dates`.
- Put location on the next line only if useful.
- Use the project website URL when one is provided in the profile facts; otherwise use the GitHub URL. Format the chosen link inline after the project name.
- For each Experience entry, add a 1-sentence company blurb in italics below the job title line if the company is well-known enough to describe (skip if freelance or self-employed).
- Do not add a page-count note or any meta-commentary.
- Do not include an Interests section unless it is explicitly present in the required section order.
- Project bullets should be concise and factual: what the project is, what you built, and one clear outcome.

=== CANDIDATE FIT ===
Grade: {grade}
Dimension scores: {scores_str}

=== VERIFIED PROFILE FACTS ===
{profile_facts}

---
JOB DESCRIPTION:
{jd_text}

---
CANONICAL CV:
{cv_text}"""


def rewrite_cv_with_model(parsed: dict, base_cv: str, profile_facts: str) -> str:
    scores_str = " | ".join(
        f"{k.replace('_', ' ').title()}: {v}"
        for k, v in parsed["dim_scores"].items()
    )
    prompt = _CV_REWRITE_PROMPT.format(
        grade=parsed["grade"],
        scores_str=scores_str or "N/A",
        profile_facts=profile_facts,
        jd_text=parsed["jd_text"],
        cv_text=base_cv,
        role=parsed["role"],
        company=parsed["company"],
    )

    text, usage = run_cv_tailoring(
        system=(
            "You are a professional CV writer. Output clean Markdown only. "
            "Be concise, credible, and specific. No fluff."
        ),
        prompt=prompt,
        max_output_tokens=CV_REWRITE_MAX_TOKENS,
    )
    print(format_usage(usage, label="cv_rewrite"))
    return text.strip()


# ── Step 3b: Keyword injection fallback (MOCK JD path) ───────────────────────

def inject_keywords(cv: str, keywords: list[str]) -> str:
    kw_line = "**Key skills for this role:** " + ", ".join(keywords[:8])
    if "## Skills" in cv:
        return cv.replace("## Skills", f"## Skills\n{kw_line}\n", 1)
    return cv.rstrip() + f"\n\n## Skills\n{kw_line}\n"


# ── Step 4: Save tailored CV + render PDF ─────────────────────────────────────

def build_output_paths(company: str) -> tuple[Path, Path]:
    today = date.today().strftime("%Y%m%d")
    company_slug = slugify(company)
    stem = f"cv_{company_slug}_{today}"
    APPLICATIONS_DIR.mkdir(parents=True, exist_ok=True)
    return APPLICATIONS_DIR / f"{stem}.md", APPLICATIONS_DIR / f"{stem}.pdf"


def save_cv(
    cv: str,
    output_path: Path,
    company: str,
    role: str,
    url: str,
    grade: str,
    jd_source: str,
    interview_angle: str,
    eval_path: Path,
    keyword_coverage_matched: int = 0,
    keyword_coverage_total: int = 0,
    keyword_coverage_pct: int = 0,
) -> Path:
    today = date.today().strftime("%Y%m%d")
    job_key = build_job_key(url=url, company=company, title=role)

    header = (
        f"<!-- Tailored for: {company} | Grade: {grade} | JD: {jd_source} | "
        f"Source eval: {eval_path.name} | Generated: {today} | "
        f"Keywords: {keyword_coverage_matched}/{keyword_coverage_total} ({keyword_coverage_pct}%) -->\n"
        f"<!-- Job key: {job_key} -->\n"
        f"<!-- Interview angle: {interview_angle} -->\n\n"
    )
    try:
        output_path.write_text(header + cv, encoding="utf-8")
    except OSError as exc:
        raise OSError(f"Failed to write CV markdown to {output_path}") from exc
    if not output_path.exists():
        raise FileNotFoundError(f"CV markdown was not created at {output_path}")
    record_artifact_identity(
        output_path,
        url=url,
        company=company,
        title=role,
        source_eval=eval_path.name,
    )
    return output_path


def split_cv_header(cv_markdown: str) -> tuple[str, list[str], str]:
    clean = strip_html_comments(cv_markdown)
    lines = clean.splitlines()
    name = ""
    meta_lines: list[str] = []
    body_start = 0

    for idx, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("# "):
            name = line[2:].strip()
            body_start = idx + 1
            break
        body_start = idx
        break

    idx = body_start
    while idx < len(lines):
        line = lines[idx].strip()
        if not line:
            idx += 1
            continue
        if line in {"---", "***"}:
            idx += 1
            break
        if line.startswith("## "):
            break
        meta_lines.append(line)
        idx += 1

    body = "\n".join(lines[idx:]).strip()
    return name, meta_lines, body


def render_cv_html(cv_markdown: str, company: str, role: str) -> str:
    name, meta_lines, body_markdown = split_cv_header(cv_markdown)
    body_html = md.markdown(
        body_markdown,
        extensions=["extra", "sane_lists"],
        output_format="html5",
    )
    body_html = body_html.replace(
        "<h2>Projects</h2>",
        '<h2 class="page-break-before">Projects</h2>',
        1,
    )
    meta_html = "".join(
        f"<p>{md.markdown(line, output_format='html5').removeprefix('<p>').removesuffix('</p>')}</p>"
        for line in meta_lines
    )
    title_name = name or "Curriculum Vitae"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title_name)} | CV</title>
  <style>
    @page {{
      size: A4;
      margin: 14mm 12mm 14mm 12mm;
    }}
    :root {{
      color-scheme: light;
      --ink: #111827;
      --muted: #4b5563;
      --rule: #d1d5db;
      --accent: #0f172a;
      --paper: #ffffff;
    }}
    * {{
      box-sizing: border-box;
    }}
    html, body {{
      margin: 0;
      padding: 0;
      background: var(--paper);
      color: var(--ink);
      font-family: "Helvetica Neue", Arial, sans-serif;
      font-size: 10.5pt;
      line-height: 1.42;
      -webkit-font-smoothing: antialiased;
    }}
    body {{
      padding: 0;
    }}
    main {{
      width: 100%;
    }}
    header {{
      border-bottom: 1px solid var(--rule);
      padding-bottom: 10px;
      margin-bottom: 14px;
    }}
    h1 {{
      margin: 0 0 4px;
      font-size: 20pt;
      line-height: 1.1;
      color: var(--accent);
      letter-spacing: -0.02em;
    }}
    .meta p {{
      margin: 0 0 2px;
      font-size: 9.25pt;
      color: var(--muted);
    }}
    .meta p:first-child {{
      font-size: 10pt;
      font-weight: 600;
      color: var(--accent);
      margin-bottom: 4px;
    }}
    h2 {{
      margin: 14px 0 6px;
      font-size: 11pt;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--accent);
      page-break-after: avoid;
    }}
    h2.page-break-before {{
      break-before: page;
      page-break-before: always;
    }}
    h3 {{
      margin: 10px 0 4px;
      font-size: 10.5pt;
      color: var(--ink);
      page-break-after: avoid;
    }}
    p {{
      margin: 0 0 7px;
      orphans: 3;
      widows: 3;
      text-align: justify;
    }}
    ul {{
      margin: 0 0 8px 18px;
      padding: 0;
    }}
    li {{
      margin: 0 0 4px;
      page-break-inside: avoid;
      text-align: justify;
    }}
    hr {{
      display: none;
    }}
    strong {{
      color: var(--accent);
    }}
    a {{
      color: inherit;
      text-decoration: none;
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>{html.escape(title_name)}</h1>
      <div class="meta">{meta_html}</div>
    </header>
    {body_html}
  </main>
</body>
</html>
"""


def render_pdf(html_content: str, output_path: Path) -> Path:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content(html_content, wait_until="load")
            page.emulate_media(media="print")
            page.pdf(
                path=str(output_path),
                format="A4",
                print_background=True,
                prefer_css_page_size=True,
                margin={
                    "top": "14mm",
                    "right": "12mm",
                    "bottom": "14mm",
                    "left": "12mm",
                },
            )
        finally:
            browser.close()

    if not output_path.exists():
        raise FileNotFoundError(f"PDF render completed without creating {output_path}")
    return output_path


# ── Public API ────────────────────────────────────────────────────────────────

def generate_pdf(eval_path: "Path | str") -> str:
    """
    Generate a tailored CV from an eval report.

    Returns the relative path to the PDF when rendering succeeds, otherwise the
    relative path to the Markdown file.
    """
    eval_path = Path(eval_path)
    if not eval_path.is_absolute():
        eval_path = REPO_ROOT / eval_path

    if not eval_path.exists():
        raise FileNotFoundError(f"Eval file not found: {eval_path}")

    parsed = parse_eval(eval_path)
    profile = load_profile_data()
    archetype = parsed.get("archetype", "ds-product")
    profile["projects"] = reorder_projects_for_archetype(
        profile.get("projects", []), archetype
    )
    print(f"[ARCHETYPE] {archetype} — archetype overlay applied")
    base_cv = build_canonical_cv(profile, archetype=archetype)
    profile_facts = build_profile_fact_block(profile, archetype=archetype)

    print(
        f"CV_REWRITE company={parsed['company']} grade={parsed['grade']} "
        f"jd_source={parsed['jd_source']} model={describe_task_model('cv')}"
    )

    if parsed["jd_source"] == "REAL" and parsed["jd_text"]:
        tailored_cv = rewrite_cv_with_model(
            parsed,
            base_cv,
            profile_facts,
        )
    else:
        if parsed["jd_source"] != "REAL":
            print("[WARN] JD_SOURCE is MOCK — provider rewrite skipped, using keyword injection")
        elif not parsed["jd_text"]:
            print("[WARN] JD text missing from eval — provider rewrite skipped, using keyword injection")
        tailored_cv = inject_keywords(base_cv, parsed["keywords"])

    keywords = parsed.get("keywords", [])
    keyword_coverage_total = len(keywords)
    keyword_coverage_matched = 0
    keyword_coverage_pct = 0
    if keywords:
        cv_lower = tailored_cv.lower()
        keyword_coverage_matched = sum(1 for kw in keywords if kw.lower() in cv_lower)
        keyword_coverage_pct = round(keyword_coverage_matched / keyword_coverage_total * 100)
        print(f"[KEYWORDS] {keyword_coverage_matched}/{keyword_coverage_total} coverage ({keyword_coverage_pct}%)")
    # TODO: pass keyword_coverage_* into save_cv() header comment or tracker notes field

    markdown_path, pdf_path = build_output_paths(parsed["company"])
    print(
        "[CV] Outputs planned: "
        f"markdown={markdown_path.relative_to(REPO_ROOT)} "
        f"pdf={pdf_path.relative_to(REPO_ROOT)}"
    )
    save_cv(
        tailored_cv,
        markdown_path,
        parsed["company"],
        parsed["role"],
        parsed["url"],
        parsed["grade"],
        parsed["jd_source"],
        parsed["interview_angle"],
        eval_path,
        keyword_coverage_matched=keyword_coverage_matched,
        keyword_coverage_total=keyword_coverage_total,
        keyword_coverage_pct=keyword_coverage_pct,
    )
    if not markdown_path.exists():
        raise FileNotFoundError(f"Expected markdown output missing after save: {markdown_path}")
    print(f"[CV] Markdown saved: {markdown_path.relative_to(REPO_ROOT)}")

    try:
        html_content = normalize_for_ats(render_cv_html(tailored_cv, parsed["company"], parsed["role"]))
        render_pdf(html_content, pdf_path)
        record_artifact_identity(
            pdf_path,
            url=parsed["url"],
            company=parsed["company"],
            title=parsed["role"],
            source_eval=eval_path.name,
        )
        print(
            "[CV] Outputs saved: "
            f"markdown={markdown_path.relative_to(REPO_ROOT)} "
            f"pdf={pdf_path.relative_to(REPO_ROOT)}"
        )
        return str(pdf_path.relative_to(REPO_ROOT))
    except Exception as exc:
        print(
            f"[WARN] PDF render failed for {pdf_path.relative_to(REPO_ROOT)} "
            f"({exc}) — Markdown kept at {markdown_path.relative_to(REPO_ROOT)}"
        )
        return str(markdown_path.relative_to(REPO_ROOT))


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a tailored CV and PDF from an eval report.")
    parser.add_argument("eval_path", help="Path to the eval markdown file.")
    parser.add_argument(
        "--model",
        help="LLM model override for this run. Overrides MODEL_OVERRIDE when provided.",
    )
    args = parser.parse_args()

    if args.model:
        os.environ["MODEL_OVERRIDE"] = args.model

    try:
        rel_path = generate_pdf(args.eval_path)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}")
        sys.exit(1)

    print(f"[CV] Main artifact: {rel_path}")


if __name__ == "__main__":
    main()
