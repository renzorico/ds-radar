"""
ds-radar CV generator
Usage: python generate_pdf.py <eval_path>
Example: python generate_pdf.py evals/deepmind_2026-04-01.md

If the eval contains a real JD ([JD_SOURCE: REAL]), calls the configured LLM to
rewrite a canonical CV built from profile/profile.yaml tailored to that job.
If JD is mock, falls back to keyword injection.
Always writes Markdown CV to applications/cv_{company}_{YYYYMMDD}.md and
attempts to render applications/cv_{company}_{YYYYMMDD}.pdf via Playwright.
"""

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
    "ds-radar": {
        "name": "ds-radar",
        "tech": "Python, OpenAI API, Playwright",
        "repo_url": "https://github.com/renzorico/ds-radar",
        "summary": (
            "AI-powered job search pipeline that scans roles, evaluates fit, generates tailored CVs, and tracks "
            "applications."
        ),
    },
    "no botes tu voto": {
        "name": "No botes tu voto",
        "tech": "FastAPI, Next.js, TypeScript, Railway",
        "repo_url": "https://github.com/renzorico/colombia-matcher",
        "summary": (
            "Civic-tech platform for election guidance, described in the profile as supporting 10,000+ users."
        ),
    },
    "the london bible": {
        "name": "The London Bible",
        "tech": "Python, GeoPandas, Leaflet",
        "repo_url": "https://github.com/renzorico/the-london-bible",
        "summary": "Interactive London data atlas built from public datasets and geospatial analysis.",
    },
    "adcc universe": {
        "name": "ADCC Universe",
        "tech": "React, TypeScript, Sigma.js",
        "repo_url": "https://github.com/renzorico/bjj-universe",
        "summary": "Grappling competition network graph and interactive relationship explorer.",
    },
    "un speeches nlp": {
        "name": "UN Speeches NLP",
        "tech": "Python, scikit-learn, Streamlit, BigQuery",
        "repo_url": "https://github.com/renzorico/speeches-at-UN",
        "summary": "NLP pipeline analysing 8,000+ UN General Debate speeches across time.",
    },
}

SKILL_GROUPS = {
    "Languages": ["Python (data + ML).", "SQL.", "JavaScript and TypeScript."],
    "Data/ML": [
        "Pandas / NumPy / scikit-learn.",
        "TensorFlow/Keras.",
        "NLP and UMAP.",
        "LLMs and agentic AI systems.",
    ],
    "Web/Cloud/Tools": [
        "FastAPI.",
        "BigQuery and GCP.",
        "Docker.",
        "React.",
        "Vercel and Railway.",
        "Streamlit.",
        "Git.",
        "Linux / CLI-focused workflows.",
    ],
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
    if match:
        data = match.groupdict()
        data.setdefault("location", "")
        data["company_description"] = COMPANY_DESCRIPTIONS.get(data["company"].strip().lower(), "")
        return data
    return {
        "title": item.strip(),
        "company": "",
        "location": "",
        "dates": "",
        "company_description": "",
    }


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
    "ds-product":         ["London Bible", "UN Speeches", "No botes", "ADCC", "ds-radar"],
    "ml-engineer":        ["ds-radar", "UN Speeches", "London Bible", "ADCC", "No botes"],
    "analytics-engineer": ["London Bible", "ADCC", "UN Speeches", "No botes", "ds-radar"],
    "data-engineer":      ["ds-radar", "No botes", "UN Speeches", "London Bible", "ADCC"],
    "ai-engineer":        ["ds-radar", "UN Speeches", "ADCC", "No botes", "London Bible"],
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


def build_canonical_cv(profile: dict) -> str:
    identity = profile.get("identity", {}) or {}
    contact = profile.get("contact", {}) or {}
    tech = profile.get("tech_stack", {}) or {}

    name = identity.get("name", "Renzo Rico").strip()
    location = identity.get("location", "").strip()
    role_title = DEFAULT_CANDIDATE_TITLE
    contact_parts = [
        location,
        contact.get("email", "").strip(),
        contact.get("phone", "").strip(),
        contact.get("linkedin_url", "").strip(),
        GITHUB_PROFILE_URL,
    ]
    meta_line = " | ".join(part for part in contact_parts if part)

    experience_items = [_parse_experience_item(str(item).strip()) for item in profile.get("experience", []) if str(item).strip()]
    education_items = [_parse_education_item(str(item).strip()) for item in profile.get("education", []) if str(item).strip()]
    project_items = [_project_record(str(item).strip()) for item in profile.get("projects", []) if str(item).strip()]
    strong_skills = [str(item).strip() for item in tech.get("strong_skills", []) if str(item).strip()]
    must_match = [str(item).strip() for item in tech.get("must_match_skills", []) if str(item).strip()]

    summary_parts: list[str] = []
    if location:
        summary_parts.append(f"{role_title} based in {location}.")
    if experience_items:
        lead_role = experience_items[0]
        lead_company = _first_non_empty([lead_role.get("company", ""), "recent employers"])
        summary_parts.append(
            f"Experience spans technical delivery across {lead_company} and freelance product work."
        )
    skill_summary = _compact_list(_unique(strong_skills[:4] + must_match), 6)
    if skill_summary:
        summary_parts.append(f"Core skills: {skill_summary}.")

    lines = [f"# {name}"]
    lines.extend(["", role_title])
    if meta_line:
        lines.extend(["", meta_line])

    lines.extend(["", "## Summary", " ".join(summary_parts).strip()])

    skill_lines: list[str] = []
    for label, items in SKILL_GROUPS.items():
        available = [item for item in items if item in strong_skills or item.rstrip(".").lower() in {s.rstrip('.').lower() for s in strong_skills + must_match}]
        if available:
            skill_lines.append(f"- **{label}:** {', '.join(available)}")
    if not skill_lines:
        skill_lines = [f"- **Core:** {', '.join(_unique(strong_skills or must_match))}"]
    lines.extend(["", "## Skills"])
    lines.extend(skill_lines)

    if project_items:
        lines.extend(["", "## Projects"])
        for project in project_items[:5]:
            project_heading = f"### {project['name']}"
            if project.get("tech"):
                project_heading += f" ({project['tech']})"
            lines.extend(["", project_heading])
            if project.get("repo_url"):
                lines.append(f"Repository: {project['repo_url']}")
            if project.get("summary"):
                lines.append(f"- {project['summary']}")

    if experience_items:
        lines.extend(["", "## Experience"])
        for experience in experience_items:
            heading_bits = [experience.get("title", "").strip(), experience.get("company", "").strip()]
            heading = " - ".join(part for part in heading_bits if part)
            meta_bits = [experience.get("location", "").strip(), experience.get("dates", "").strip()]
            lines.extend(["", f"### {heading}"])
            if any(meta_bits):
                lines.append(" | ".join(part for part in meta_bits if part))
            if experience.get("company_description"):
                lines.append(experience["company_description"])
            lines.append("- Add role-relevant bullets grounded in the verified profile and job description.")

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


def build_profile_fact_block(profile: dict) -> str:
    identity = profile.get("identity", {}) or {}
    contact = profile.get("contact", {}) or {}
    tech = profile.get("tech_stack", {}) or {}
    experience_items = [_parse_experience_item(str(item).strip()) for item in profile.get("experience", []) if str(item).strip()]
    education_items = [_parse_education_item(str(item).strip()) for item in profile.get("education", []) if str(item).strip()]
    project_items = [_project_record(str(item).strip()) for item in profile.get("projects", []) if str(item).strip()]
    skill_lines = [
        f"- {label}: {', '.join(items)}"
        for label, items in SKILL_GROUPS.items()
    ]
    lines = [
        f"- name: {identity.get('name', '').strip()}",
        f"- target_title: {DEFAULT_CANDIDATE_TITLE}",
        f"- location: {identity.get('location', '').strip()}",
        f"- email: {contact.get('email', '').strip()}",
        f"- phone: {contact.get('phone', '').strip()}",
        f"- linkedin: {contact.get('linkedin_url', '').strip()}",
        f"- github: {GITHUB_PROFILE_URL}",
        "- recruiter_priorities: qualifications, similar experience, visible GitHub profile, visible repo links, skimmable XYZ bullets, education last",
        "- experience:",
    ]
    for item in experience_items:
        lines.append(
            "  - "
            f"title={item.get('title', '')}; company={item.get('company', '')}; "
            f"location={item.get('location', '')}; dates={item.get('dates', '')}; "
            f"company_description={item.get('company_description', '') or 'n/a'}"
        )
    lines.append("- projects:")
    for item in project_items[:5]:
        lines.append(
            "  - "
            f"name={item.get('name', '')}; repo_url={item.get('repo_url', '') or 'n/a'}; "
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

=== SECTION ORDER (follow exactly) ===
1. Contact / meta line (name already in H1 header — do not repeat it)
2. Summary (2 sentences)
3. Experience
4. Projects
5. Skills
6. Education

=== FORMATTING RULES ===
- Output a complete CV in GitHub-flavoured Markdown only. No preamble, no explanation, no code fences.
- Every bullet under Experience and Projects must follow the XYZ pattern: "Accomplished [X] by doing [Y], resulting in [Z]." Use real numbers from the profile where available.
- Include the GitHub URL for each project where the profile provides one. Format: (github.com/...) inline after the project name.
- For each Experience entry, add a 1-sentence company blurb in italics below the job title line if the company is well-known enough to describe (skip if freelance or self-employed).
- Do not add a page-count note or any meta-commentary.

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
    meta_html = "".join(
        f"<p>{md.markdown(line, output_format='html5').removeprefix('<p>').removesuffix('</p>')}</p>"
        for line in meta_lines
    )
    title_name = name or "Curriculum Vitae"
    role_line = html.escape(role)
    company_line = html.escape(company)

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
    .target-role {{
      margin: 0 0 8px;
      font-size: 9.5pt;
      color: var(--muted);
    }}
    .meta p {{
      margin: 0 0 2px;
      font-size: 9.25pt;
      color: var(--muted);
    }}
    h2 {{
      margin: 14px 0 6px;
      font-size: 11pt;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--accent);
      page-break-after: avoid;
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
    }}
    ul {{
      margin: 0 0 8px 18px;
      padding: 0;
    }}
    li {{
      margin: 0 0 4px;
      page-break-inside: avoid;
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
      <p class="target-role">Tailored CV for {company_line} | {role_line}</p>
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
    profile["projects"] = reorder_projects_for_archetype(
        profile.get("projects", []), parsed.get("archetype", "ds-product")
    )
    print(f"[ARCHETYPE] {parsed.get('archetype', 'ds-product')} — projects reordered")
    base_cv = build_canonical_cv(profile)
    profile_facts = build_profile_fact_block(profile)

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
    print(f"[CV] Target markdown: {markdown_path.relative_to(REPO_ROOT)}")
    print(f"[CV] Target PDF: {pdf_path.relative_to(REPO_ROOT)}")
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
        print(f"[CV] PDF saved: {pdf_path.relative_to(REPO_ROOT)}")
        return str(pdf_path.relative_to(REPO_ROOT))
    except Exception as exc:
        print(
            f"[WARN] PDF render failed for {pdf_path.relative_to(REPO_ROOT)} "
            f"({exc}) — Markdown kept at {markdown_path.relative_to(REPO_ROOT)}"
        )
        return str(markdown_path.relative_to(REPO_ROOT))


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python generate_pdf.py <eval_path>")
        sys.exit(1)

    try:
        rel_path = generate_pdf(sys.argv[1])
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}")
        sys.exit(1)

    print(f"[CV] Main artifact: {rel_path}")


if __name__ == "__main__":
    main()
