"""
ds-radar evaluator — REAL MODE (Claude Haiku)
Usage: python evaluate.py <job_url>

Evaluates a job offer across 10 dimensions and writes a scored report to evals/.
Requires ANTHROPIC_API_KEY in ds-radar/.env
"""

import sys
import os
import re
import csv
import json
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import yaml

# ── Env / API setup ──────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")

_api_key = os.getenv("ANTHROPIC_API_KEY")
if not _api_key:
    print("[ERROR] ANTHROPIC_API_KEY not found. Add it to ds-radar/.env")
    sys.exit(1)

import anthropic
_client = anthropic.Anthropic(api_key=_api_key)

# ── Paths ────────────────────────────────────────────────────────────────────

EVALS_DIR = REPO_ROOT / "evals"
SCAN_HISTORY = REPO_ROOT / "scan-history.tsv"
PROFILE_PATH = REPO_ROOT / "profile" / "profile.yaml"
CV_PATH = REPO_ROOT / "profile" / "cv.md"
ERRORS_LOG = EVALS_DIR / "errors.log"
CALIBRATION_PATH = EVALS_DIR / "calibration_notes.tsv"

SCAN_HISTORY_HEADER = ["url", "date_seen", "eval_path"]
SOURCE_HISTORY = REPO_ROOT / "source-history.tsv"

MODEL = "claude-haiku-4-5-20251001"
_PROFILE_CACHE: dict | None = None
_CALIBRATION_CACHE: list[dict] | None = None

# ── Sponsorship detection patterns ───────────────────────────────────────────

_NEG_PATTERNS = [
    r"no\s+(?:visa\s+)?sponsorship",
    r"cannot\s+sponsor",
    r"unable\s+to\s+sponsor",
    r"must\s+have\s+(?:the\s+)?right\s+to\s+work",
    r"must\s+possess\s+(?:the\s+)?right\s+to\s+work",
    r"requires?\s+(?:the\s+)?right\s+to\s+work",
    r"we\s+do\s+not\s+offer\s+visa\s+sponsorship",
    r"without\s+sponsorship",
    r"not\s+(?:provide|providing|offer|offering)\s+(?:visa\s+)?sponsorship",
    r"not\s+able\s+to\s+offer\s+(?:visa\s+)?sponsorship",
    r"do\s+not\s+sponsor",
    r"will\s+not\s+sponsor",
]

_POS_PATTERNS = [
    r"visa\s+sponsorship\s+(?:is\s+)?available",
    r"offers?\s+visa\s+sponsorship",
    r"can\s+(?:and\s+will\s+)?sponsor",
    r"(?:provide|providing)\s+(?:visa\s+)?sponsorship",
    r"skilled\s+worker\s+visa",
    r"eligible\s+for\s+sponsorship",
    r"sponsorship\s+(?:is\s+)?provided",
    r"we\s+(?:are\s+)?(?:able\s+to\s+)?sponsor",
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text


def extract_company_from_url(url: str) -> str:
    """Best-effort company name extraction from common ATS URL patterns."""
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    path = parsed.path

    if "greenhouse.io" in hostname:
        parts = [p for p in path.split("/") if p]
        if parts:
            return parts[0].replace("-", " ").title()

    if "lever.co" in hostname:
        parts = [p for p in path.split("/") if p]
        if parts:
            return parts[0].replace("-", " ").title()

    if "workable.com" in hostname:
        sub = hostname.split(".")[0]
        if sub not in ("www", "jobs", "apply"):
            return sub.replace("-", " ").title()

    if "ashbyhq.com" in hostname:
        sub = hostname.split(".")[0]
        if sub not in ("www", "jobs"):
            return sub.replace("-", " ").title()

    parts = hostname.replace("www.", "").split(".")
    return parts[0].replace("-", " ").title() if parts else "Unknown"


def read_scan_history() -> list[dict]:
    if not SCAN_HISTORY.exists():
        return []
    with SCAN_HISTORY.open(newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        return list(reader)


def url_already_evaluated(url: str, history: list[dict]) -> dict | None:
    for row in history:
        if row.get("url", "").strip() == url.strip():
            return row
    return None


def append_scan_history(url: str, eval_path: Path) -> None:
    today = date.today().isoformat()
    rel_path = eval_path.relative_to(REPO_ROOT)
    write_header = not SCAN_HISTORY.exists()
    with SCAN_HISTORY.open("a", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        if write_header:
            writer.writerow(SCAN_HISTORY_HEADER)
        writer.writerow([url, today, str(rel_path)])


def load_profile() -> dict:
    """Load the profile YAML once and return the sections used for scoring."""
    global _PROFILE_CACHE
    if _PROFILE_CACHE is None:
        data = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8")) or {}
        _PROFILE_CACHE = {
            "identity": data.get("identity", {}),
            "work_authorization": data.get("work_authorization", {}),
            "search_priorities": data.get("search_priorities", {}),
            "roles": data.get("roles", {}),
            "long_term_targets": data.get("long_term_targets", {}),
            "companies": data.get("companies", {}),
            "work_content_preferences": data.get("work_content_preferences", {}),
            "tech_stack": data.get("tech_stack", {}),
            "scoring": data.get("scoring", {}),
            "sponsorship_rules": data.get("sponsorship_rules", {}),
        }
    return _PROFILE_CACHE


def load_calibration_notes() -> list[dict]:
    """Load human calibration examples once for prompt-shaping only."""
    global _CALIBRATION_CACHE
    if _CALIBRATION_CACHE is None:
        if not CALIBRATION_PATH.exists():
            _CALIBRATION_CACHE = []
        else:
            with CALIBRATION_PATH.open(newline="", encoding="utf-8") as handle:
                _CALIBRATION_CACHE = list(csv.DictReader(handle, delimiter="\t"))
    return _CALIBRATION_CACHE


# ── Sponsorship helpers ───────────────────────────────────────────────────────

def _load_linkedin_sponsorship(url: str) -> str | None:
    """Return sponsorship_signal ('yes'/'no'/'unknown') from source-history.tsv, or None."""
    if not SOURCE_HISTORY.exists():
        return None
    with SOURCE_HISTORY.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if row.get("target_url", "").strip() == url.strip():
                sig = row.get("sponsorship_signal", "").strip().lower()
                return sig if sig else None
    return None


def detect_sponsorship_status(url: str, jd_text: str) -> dict:
    """Deterministic sponsorship gate.

    Returns {"status": "positive"|"negative"|"neutral", "reason": str, "evidence": str}.
    Priority: JD negative > JD positive > LinkedIn signal > neutral.
    """
    clean = re.sub(r"^\[JD_SOURCE: (?:REAL|MOCK)\]\n", "", jd_text)

    neg_hits = [
        m.group() for p in _NEG_PATTERNS
        for m in [re.search(p, clean, re.IGNORECASE)] if m
    ]
    pos_hits = [
        m.group() for p in _POS_PATTERNS
        for m in [re.search(p, clean, re.IGNORECASE)] if m
    ]

    if neg_hits:
        return {
            "status":   "negative",
            "reason":   "explicit no-sponsorship signal in JD",
            "evidence": "; ".join(neg_hits[:3]),
        }
    if pos_hits:
        return {
            "status":   "positive",
            "reason":   "explicit sponsorship available in JD",
            "evidence": "; ".join(pos_hits[:3]),
        }

    li_sig = _load_linkedin_sponsorship(url)
    if li_sig == "no":
        return {
            "status":   "negative",
            "reason":   "LinkedIn metadata: sponsorship_signal=no",
            "evidence": "source-history.tsv",
        }
    if li_sig == "yes":
        return {
            "status":   "positive",
            "reason":   "LinkedIn metadata: sponsorship_signal=yes",
            "evidence": "source-history.tsv",
        }

    return {"status": "neutral", "reason": "no sponsorship signal found", "evidence": ""}


# ── JD extraction ────────────────────────────────────────────────────────────

JD_TIMEOUT_MS = 12_000
JD_MAX_CHARS = 3000

# Ordered from most-specific to generic
SELECTOR_CASCADE = [
    ".job__description", "#content",            # Greenhouse
    ".posting-content", ".content",             # Lever
    '[data-ui="job-description"]', ".styles__JobDescription",  # Workable
    ".ashby-job-posting-description",           # Ashby
    "article", "main",                          # Generic
]


def _scrape_jd_text(page) -> str | None:
    """Try selector cascade; return first block with >200 chars."""
    for sel in SELECTOR_CASCADE:
        try:
            el = page.query_selector(sel)
            if el:
                text = el.inner_text().strip()
                if len(text) > 200:
                    return text
        except Exception:
            continue
    # Last resort: join <p> paragraphs
    try:
        paras = [el.inner_text().strip() for el in page.query_selector_all("p")]
        combined = "\n".join(p for p in paras if len(p) > 30)
        return combined if len(combined) > 200 else None
    except Exception:
        return None


def extract_jd(url: str) -> dict:
    """Extract real JD via Playwright; falls back to mock template on any error."""
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    company = extract_company_from_url(url)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=JD_TIMEOUT_MS)
            try:
                page.wait_for_load_state("networkidle", timeout=8_000)
            except PWTimeout:
                pass  # proceed with whatever loaded

            title = "Data Scientist"
            h1 = page.query_selector("h1")
            if h1:
                t = h1.inner_text().strip()
                if t:
                    title = t

            jd_text = _scrape_jd_text(page)
            browser.close()

        if jd_text:
            jd_text = jd_text[:JD_MAX_CHARS]
            print(f"[JD] REAL — {len(jd_text)} chars | {url[:70]}")
            return {
                "title": title,
                "company": company,
                "location": "See JD",
                "salary": "See JD",
                "description": "[JD_SOURCE: REAL]\n" + jd_text,
            }

    except PWTimeout:
        print(f"[JD] WARN — timeout scraping {url[:70]}, using mock")
    except Exception as exc:
        print(f"[JD] WARN — {exc} | {url[:70]}, using mock")

    # Mock fallback
    print(f"[JD] MOCK — template used for {url[:70]}")
    mock = mock_extract_jd(url)
    mock["description"] = "[JD_SOURCE: MOCK]\n" + mock["description"]
    return mock


def mock_extract_jd(url: str) -> dict:
    """Template JD — used as fallback when Playwright extraction fails."""
    company = extract_company_from_url(url)
    return {
        "title": "Senior Data Scientist",
        "company": company,
        "location": "London, UK (Hybrid)",
        "salary": "£70,000 - £90,000",
        "description": (
            f"We are looking for a Senior Data Scientist at {company} with Python, SQL, "
            "machine learning experience to join our growing analytics team. You will "
            "build and deploy ML models, work closely with stakeholders, and own "
            "end-to-end data pipelines in a fast-paced environment."
        ),
    }


# ── Token efficiency helpers ─────────────────────────────────────────────────

def truncate_jd(text: str, max_tokens: int = 600) -> str:
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
    cut = int(max_chars * 0.8)
    return text[:cut] + "\n...[truncated]...\n" + text[-(max_chars - cut):]


def build_lean_cv() -> str:
    """Extract a compact profile summary from profile/profile.yaml for API prompts."""
    profile = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8")) or {}
    identity = profile.get("identity", {})
    location = identity.get("location", "London, UK")

    title = "Data Scientist"
    experience_items = profile.get("experience", [])
    projects = profile.get("projects", [])
    tech = profile.get("tech_stack", {})

    experience_text = "; ".join(str(item) for item in experience_items[:2]) or "Data Scientist"
    skills_text = (
        f"Skills: {_compact_list(tech.get('strong_skills', []), 5)}\n"
        f"Core stack: {_compact_list(tech.get('must_match_skills', []), 4)}"
    )
    projects_text = "\n".join(f"- {project}" for project in projects[:5])

    return (
        f"Title: {title}\n"
        f"Location: {location}\n"
        f"Experience: {experience_text}\n"
        f"{skills_text}\n"
        f"Top projects:\n{projects_text}"
    )


def _compact_list(items, limit: int = 4) -> str:
    if not items:
        return "n/a"
    if not isinstance(items, list):
        return str(items)
    picked = [str(item) for item in items[:limit]]
    return ", ".join(picked)


def build_profile_context(profile: dict) -> str:
    identity = profile.get("identity", {})
    work_auth = profile.get("work_authorization", {})
    search = profile.get("search_priorities", {})
    roles = profile.get("roles", {})
    long_term = profile.get("long_term_targets", {})
    companies = profile.get("companies", {})
    content = profile.get("work_content_preferences", {})
    tech = profile.get("tech_stack", {})
    scoring = profile.get("scoring", {})
    sponsorship_rules = profile.get("sponsorship_rules", {})

    priority_map = content.get("priorities", {})
    top_content = sorted(priority_map.items(), key=lambda item: item[1])[:4]
    top_content_text = ", ".join(f"{name}:{score}" for name, score in top_content) if top_content else "n/a"

    min_seniority = roles.get("acceptable_seniority", {}).get("min", "?")
    max_seniority = roles.get("acceptable_seniority", {}).get("max", "?")

    lines = [
        "Renzo profile:",
        f"- identity: {identity.get('name', 'Renzo Rico')} | {identity.get('location', 'London, UK')}",
        f"- short_term_goal: {search.get('primary_goal', 'Secure a solid data role with sponsorship')}",
        f"- short_term_notes: {_compact_list(search.get('short_term_notes', []), 2)}",
        f"- work_auth: needs_visa={work_auth.get('needs_visa')} | sponsorship_required={work_auth.get('sponsorship_required')}",
        f"- target_roles: {_compact_list(roles.get('target_titles_ordered', []), 6)}",
        f"- acceptable_seniority: {min_seniority} to {max_seniority}",
        f"- anti_targets: {_compact_list(roles.get('anti_targets', []), 3)}",
        f"- long_term_archetypes: {_compact_list(long_term.get('archetypes', []), 4)}",
        f"- preferred_companies: {_compact_list(companies.get('preferred_types_ordered', []), 3)}",
        f"- deprioritise: {_compact_list(companies.get('deprioritise', []), 2)}",
        f"- work_content_priorities: {top_content_text}",
        f"- work_content_notes: {_compact_list(content.get('notes', []), 2)}",
        f"- tech_must_match: {_compact_list(tech.get('must_match_skills', []), 4)}",
        f"- tech_nice_to_have: {_compact_list(tech.get('nice_to_have_skills', []), 5)}",
        f"- scoring_context: min_grade_to_apply={scoring.get('min_grade_to_apply', 'B')} | gate_dimensions={_compact_list(scoring.get('gate_dimensions', []), 4)}",
        f"- sponsorship_context_only: {_compact_list(sponsorship_rules.get('evaluation', []), 2)}",
    ]
    return "\n".join(lines)


def build_calibration_hints(calibration_rows: list[dict]) -> str:
    if not calibration_rows:
        return "Renzo calibration hints:\n- none loaded"

    lines = [
        "Renzo calibration hints:",
        "- Treat clearly senior roles as weaker matches even when the title sounds attractive; seniority fit matters a lot.",
        "- Consulting roles can be acceptable short-term bridge roles when stable and technical, but usually rank below strong product data/ML roles.",
        "- Product ML roles at credible brands or interesting product companies should lean higher when skill and seniority fit are reasonable.",
        "- Agency or recruiter-led postings are acceptable if the underlying role looks genuinely technical and worth pursuing.",
        "- Explicit no-sponsorship or must-already-be-authorized language is a hard fail in practice; code enforces this deterministically, so do not rescue such roles with strong scores.",
        "- Short-term flexibility is real: stable, technical data roles with sponsorship can still be good fits even if they are not perfect long-term archetype matches.",
        "- Consulting or reporting-heavy data roles can still be acceptable short-term bridge roles when: they use a modern data stack, are clearly data-facing (not generic operations), and offer stability and sponsorship.",
        "- For such bridge roles, keep grades in the C / low-B range when they are stable, technical, and plausibly helpful for Renzo's long-term goals, rather than pushing them down to D by default.",
        "- Penalise roles more heavily only when they are clearly low-leverage reporting jobs with weak tooling, little ownership, and limited learning surface, even if they are labelled as analytics or consulting.",
        "- When sponsorship is explicitly available and the role is at least moderately technical with a medium learning surface, lean toward treating it as a viable 12–24 month bridge even if it is not an ideal long-term archetype match.",
    ]
    return "\n".join(lines)


def build_score_prompt(jd: dict, lean_cv: str, profile_context: str, calibration_hints: str) -> str:
    jd_text = (
        f"Title: {jd['title']}\n"
        f"Company: {jd['company']}\n"
        f"Location: {jd['location']}\n"
        f"Salary: {jd.get('salary', 'not specified')}\n"
        f"Description:\n{jd['description']}"
    )

    return f"""\
Candidate profile:
{lean_cv}

{profile_context}

{calibration_hints}

Job description:
{truncate_jd(jd_text)}

Score this job for Renzo Rico given the profile above. Short-term, any solid data role with visa sponsorship and real technical data work is acceptable, but roles closer to the long-term archetypes should score better. Penalise anti-targets such as pure reporting, non-technical 'data', or clearly non-technical AI titles. Seniority must fit Renzo's junior-to-mid level. Strong product ML roles at good brands should generally lean higher than consulting-heavy roles, while consulting roles may still be acceptable as bridge options if stable and technical. Sponsorship negatives are already enforced by code and should not be rescued by high scores here. Keep the scoring dimensions exactly as defined below, but interpret role_match, skills_alignment, and seniority in light of this profile and calibration.

Learning surface and growth

When you judge overall fit, explicitly consider the "learning surface" of the role:

- Strong learning surface:
  - Hands-on work with data or ML models (not just consuming dashboards).
  - Ownership of analyses, models, or data products that influence real decisions.
  - Exposure to experimentation, A/B tests, model iteration, or building/maintaining data pipelines or ML systems.
  - Modern stack: SQL + Python/R + modern BI / analytics tools; for ML, common frameworks and cloud platforms.

- Medium learning surface:
  - Solid analytics and reporting that support decision-making, with some room for proactive analysis.
  - Regular stakeholder interaction, explaining insights and helping shape decisions.
  - Reasonable tools (SQL + at least one of Python/R/modern BI), but limited direct ownership of models or core data products.

- Weak learning surface:
  - Mostly ad-hoc or routine reporting, KPI refreshes, or dashboard maintenance.
  - Little scope to propose or own analyses; work is largely reactive and task-based.
  - Strong reliance on Excel or legacy tools, with limited access to raw data or modern tooling.
  - Minimal exposure to experimentation, modelling, or end-to-end ownership.

Use this learning-surface judgment as a soft factor when assigning the final grade:
- Strong learning surface should push roles up slightly (for example from a marginal C toward a stronger C/B) when seniority and sponsorship are acceptable.
- Medium learning surface is fine for "bridge" roles, especially if sponsorship and stability are present.
- Weak learning surface should pull roles down unless there is some compensating factor (for example, excellent sponsorship plus brand plus a clear path to transition into a stronger data/ML track).

Renzo long-term archetype (for context)

Keep the following in mind when judging overall fit:

- Long-term target: product-style data or ML roles in tech or tech-adjacent organisations (product companies, platforms, or strong internal data teams), where he can own or co-own data products, models, or critical analyses.
- Roles that combine technical depth with teaching, communication, and stakeholder work are a plus; Renzo is comfortable explaining complex topics and working with non-technical partners.
- Work on experimentation, agentic/AI systems, or data-driven product features is particularly attractive when seniority and sponsorship fit are reasonable.
- Consulting or bridge roles are acceptable when they move him closer to this archetype (for example, strong technical consulting for data/ML, or analytics roles with good learning surface and sponsorship).

If the job description explicitly mentions that visa sponsorship is available or supports relocation/sponsorship to the UK, treat this as a positive factor in your overall judgment:

- Do not let sponsorship alone override very poor fit (for example, non-technical roles), but
- When the role is at least moderately technical with medium learning surface and acceptable seniority, lean slightly more positive in your grading, since sponsorship increases its practical value for Renzo.

Respond ONLY with a single valid JSON object.

Important:
- The JSON must be syntactically valid and parseable by a strict JSON parser.
- Do not include any markdown, backticks, or commentary outside the JSON.
- Do not wrap the JSON in ```json``` or any other fences.
- Escape any double quotes inside string values.
- Do not include newline characters in JSON keys.
- All array values (for example in top_keywords or similar fields) must be simple JSON strings without embedded newlines or unescaped quotes.
- Do not leave trailing commas in arrays or objects.
- Avoid fancy formatting; plain JSON is preferred.

Use this exact schema:
{{
  "title": "<job title>",
  "company": "<company name>",
  "location": "<location>",
  "salary_visible": "<salary or null>",
  "scores": {{
    "role_match": <0.0-5.0>,
    "skills_alignment": <0.0-5.0>,
    "seniority": <0.0-5.0>,
    "compensation": <0.0-5.0>,
    "interview_likelihood": <0.0-5.0>,
    "geography": <0.0-5.0>,
    "company_stage": <0.0-5.0>,
    "product_interest": <0.0-5.0>,
    "growth_trajectory": <0.0-5.0>,
    "timeline": <0.0-5.0>
  }},
  "overall_score": <average of all 10 scores rounded to 1 decimal>,
  "grade": "<A if >=4.5, B if >=3.8, C if >=3.0, D if >=2.0, F otherwise>",
  "recommended": <true if overall_score>=3.8, else false>,
  "summary": "<A concise plain-text explanation of your reasoning, 3–6 sentences total. Use short sentences and paragraphs only. Do NOT use markdown syntax, including lists with '-', headings, or backticks. It is fine for this string to contain newlines, but it must still be valid JSON with proper quoting and escaping. Include a clearly marked plain-text sub-section starting with 'Bridge-role assessment: ...' that answers whether this would be a reasonable 12–24 month bridge role for Renzo and explain why or why not in 1–2 sentences within the overall 3–6 sentence limit.>",
  "top_keywords": ["<5-8 JD keywords relevant to this candidate>"],
  "interview_angle": "<Optional short note on how Renzo might pitch himself in an interview for this role, or null if not sure.>"
}}"""


def log_prompt_preview(prompt: str, limit: int = 20) -> None:
    lines = prompt.splitlines()[:limit]
    print("[PROMPT] First 20 lines:")
    for idx, line in enumerate(lines, 1):
        print(f"[PROMPT:{idx:02d}] {line}")


def log_instruction_block(profile_context: str, calibration_hints: str) -> None:
    print("[INSTRUCTIONS] Profile + calibration block:")
    for line in (profile_context + "\n" + calibration_hints).splitlines():
        print(f"[INSTR] {line}")


def _safe_json_loads(raw: str):
    raw_str = raw.strip()
    try:
        return json.loads(raw_str)
    except json.JSONDecodeError as original_error:
        last_brace = raw_str.rfind("}")
        last_bracket = raw_str.rfind("]")
        cutoff = max(last_brace, last_bracket)
        if cutoff == -1:
            raise original_error
        trimmed = raw_str[:cutoff + 1]
        try:
            return json.loads(trimmed)
        except json.JSONDecodeError:
            raise original_error


def _repair_json_with_model(raw: str, error_message: str) -> str:
    repair_prompt = f"""\
You previously tried to output a JSON object but it was invalid.

JSON parse error:
{error_message}

Your task now:
- Read the original raw output between <raw> and </raw>.
- Fix ONLY the formatting so it becomes valid JSON that a strict parser can load.
- Do not change field names or add/remove fields.
- If a string was cut off, you may truncate it to the last complete sentence, but do NOT invent new content.
- Respond with a single valid JSON object only. No markdown, no code fences, no explanation.

<raw>
{raw}
</raw>"""

    response = _client.messages.create(
        model=MODEL,
        max_tokens=512,
        temperature=0,
        system="You repair malformed JSON. Output a single valid JSON object only.",
        messages=[{"role": "user", "content": repair_prompt}],
    )
    repaired = response.content[0].text.strip()
    if repaired.startswith("```"):
        repaired = re.sub(r"^```(?:json)?\s*", "", repaired)
        repaired = re.sub(r"\s*```$", "", repaired).strip()
    return repaired


# ── Real scorer ───────────────────────────────────────────────────────────────

def real_score(jd: dict) -> dict:
    """Call Claude Haiku to score a JD against the candidate profile."""
    lean_cv = build_lean_cv()
    profile = load_profile()
    profile_context = build_profile_context(profile)
    calibration_hints = build_calibration_hints(load_calibration_notes())
    user_prompt = build_score_prompt(jd, lean_cv, profile_context, calibration_hints)
    log_instruction_block(profile_context, calibration_hints)
    log_prompt_preview(user_prompt)

    response = _client.messages.create(
        model=MODEL,
        max_tokens=500,
        system="You are a job-fit evaluator. Output valid JSON only. No explanation. No preamble.",
        messages=[{"role": "user", "content": user_prompt}],
    )

    # Cost reporting
    usage = response.usage
    cost = (usage.input_tokens * 0.25 + usage.output_tokens * 1.25) / 1_000_000
    print(f"[COST] ~${cost:.5f} | {usage.input_tokens} in / {usage.output_tokens} out")

    raw = response.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw).strip()

    try:
        result = _safe_json_loads(raw)
    except json.JSONDecodeError as exc:
        try:
            repaired_raw = _repair_json_with_model(raw, str(exc))
            result = _safe_json_loads(repaired_raw)
        except Exception:
            EVALS_DIR.mkdir(parents=True, exist_ok=True)
            with ERRORS_LOG.open("a", encoding="utf-8") as f:
                f.write(f"\n--- {date.today().isoformat()} | {jd['company']} ---\n")
                f.write(f"JSONDecodeError: {exc}\n")
                f.write(raw + "\n")
            print(f"[ERROR] Malformed JSON from API. Raw response saved to {ERRORS_LOG}")
            raise exc

    result["interview_angle"] = result.get("interview_angle")

    return result


# ── Report writer ────────────────────────────────────────────────────────────

def write_report(
    result: dict, url: str,
    jd: dict | None = None,
    sponsorship: dict | None = None,
) -> Path:
    today = date.today().isoformat()
    company_slug = slugify(result["company"])
    filename = f"{company_slug}_{today}.md"

    EVALS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = EVALS_DIR / filename

    recommended_str = "YES ✓" if result["recommended"] else "NO ✗"

    # Sponsorship flag for header + dedicated section
    sponsor_flag = ""
    sponsor_section = ""
    if sponsorship:
        icon = {"positive": "✓", "negative": "⛔", "neutral": "—"}.get(
            sponsorship["status"], "—"
        )
        ev_part = (
            f' | **Evidence:** `{sponsorship["evidence"]}`'
            if sponsorship["evidence"] else ""
        )
        sponsor_section = (
            f"\n## Sponsorship\n"
            f"**Status:** {sponsorship['status'].upper()} {icon}"
            f" | **Reason:** {sponsorship['reason']}{ev_part}\n"
        )
        if sponsorship["status"] == "negative":
            sponsor_flag = " | ⛔ SPONSORSHIP GATE FAIL"

    dimension_rows = "\n".join(
        f"| {dim.replace('_', ' ').title()} | {score} |"
        for dim, score in result["scores"].items()
    )
    keywords_str = ", ".join(result.get("top_keywords") or [])

    # Embed JD source + truncated text so generate_pdf.py can use real JD later
    jd_section = ""
    if jd:
        desc = jd.get("description", "")
        jd_source = "REAL" if "[JD_SOURCE: REAL]" in desc else "MOCK"
        jd_text = desc.replace("[JD_SOURCE: REAL]\n", "").replace("[JD_SOURCE: MOCK]\n", "")[:1500]
        jd_section = f"\n## Job Description\n[JD_SOURCE: {jd_source}]\n{jd_text}\n"

    report = f"""\
# {result['title']} @ {result['company']}
**Grade:** {result['grade']} | **Score:** {result['overall_score']}/5.0 | **Recommended:** {recommended_str}{sponsor_flag}
**URL:** {url}
**Date:** {today}
**Mode:** REAL (Claude Haiku)
{sponsor_section}
## Verdict
{result['summary']}

## Dimension Scores
| Dimension | Score |
|-----------|-------|
{dimension_rows}

## Top Keywords
{keywords_str}

## Interview Angle
{result.get('interview_angle')}
{jd_section}"""
    output_path.write_text(report, encoding="utf-8")
    return output_path


# ── Eval file parser (shared by oferta.py and contacto.py) ───────────────────

def parse_eval_file(eval_path: Path) -> dict:
    """Parse grade/score/title/company from a written eval .md file."""
    text = eval_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    title, company, grade, overall_score = "Unknown", "Unknown", "?", 0.0

    # First heading: "# {title} @ {company}"
    for line in lines:
        if line.startswith("# "):
            match = re.match(r"^# (.+?) @ (.+)$", line)
            if match:
                title = match.group(1).strip()
                company = match.group(2).strip()
            break

    # Second line: "**Grade:** B | **Score:** 3.9/5.0 | ..."
    for line in lines:
        grade_match = re.search(r"\*\*Grade:\*\*\s*([A-F])", line)
        score_match = re.search(r"\*\*Score:\*\*\s*([\d.]+)/5", line)
        if grade_match:
            grade = grade_match.group(1)
        if score_match:
            overall_score = float(score_match.group(1))
        if grade_match or score_match:
            break

    return {
        "title": title,
        "company": company,
        "grade": grade,
        "overall_score": overall_score,
        "recommended": overall_score >= 3.8,
    }


# ── Public API ───────────────────────────────────────────────────────────────

def evaluate_url(url: str) -> dict:
    """Evaluate a single job URL. Returns result dict with eval_path and skipped flag.

    Returns:
        {"skipped": True, "url": url, ...existing_row}   — if already in scan-history
        {"skipped": False, "url": url, "eval_path": Path, ...score_fields}  — if new
    """
    url = url.strip()

    # Step 1 — dedup check
    history = read_scan_history()
    existing = url_already_evaluated(url, history)
    if existing:
        return {"skipped": True, "url": url, **existing}

    # Step 2 — JD extraction (real Playwright; mock fallback on failure)
    jd = extract_jd(url)

    # Step 2.5 — sponsorship gate (deterministic, pre-LLM)
    sponsorship = detect_sponsorship_status(url, jd.get("description", ""))
    if sponsorship["status"] == "negative":
        print(f"[SPONSOR] GATE FAIL — {sponsorship['reason']} | {sponsorship['evidence']}")

    # Step 3 — real API scoring
    result = real_score(jd)

    # Override grade/recommendation if sponsorship gate failed
    if sponsorship["status"] == "negative":
        result["grade"] = "F"
        result["recommended"] = False
        result["summary"] = (
            f"[SPONSORSHIP GATE: FAIL] {sponsorship['reason']}. "
            + result.get("summary", "")
        )

    # Step 4 — save report (pass jd + sponsorship so sections are embedded)
    eval_path = write_report(result, url, jd=jd, sponsorship=sponsorship)

    # Step 5 — update scan-history.tsv
    append_scan_history(url, eval_path)

    return {"skipped": False, "url": url, "eval_path": eval_path,
            "sponsorship": sponsorship, **result}


# ── JD test helper ───────────────────────────────────────────────────────────

def test_jd_extraction() -> None:
    """Read first 3 URLs from scan-queue.txt and print extracted JD previews."""
    queue_path = REPO_ROOT / "scan-queue.txt"
    if not queue_path.exists() or not queue_path.read_text().strip():
        print("scan-queue.txt is empty. Run scan.py first.")
        return
    urls = [u.strip() for u in queue_path.read_text().splitlines() if u.strip()][:3]
    for url in urls:
        print(f"\n{'─' * 60}")
        print(f"URL: {url}")
        jd = extract_jd(url)
        desc = jd["description"]
        tag = "[JD_SOURCE: REAL]" if desc.startswith("[JD_SOURCE: REAL]") else "[JD_SOURCE: MOCK]"
        preview = desc.split("\n", 1)[1][:400] if "\n" in desc else desc[:400]
        print(f"Tag:     {tag}")
        print(f"Title:   {jd['title']}")
        print(f"Preview:\n{preview}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] == "--test-jd":
        test_jd_extraction()
        sys.exit(0)

    if len(sys.argv) != 2:
        print("Usage: python evaluate.py <job_url>")
        print("       python evaluate.py --test-jd   (test JD extraction on scan-queue)")
        sys.exit(1)

    result = evaluate_url(sys.argv[1])

    if result["skipped"]:
        print("Already evaluated. Skipping.")
        print(f"  Seen:   {result.get('date_seen', '?')}")
        print(f"  Report: {result.get('eval_path', '?')}")
        sys.exit(0)

    recommended_str = "YES ✓" if result["recommended"] else "NO ✗"
    eval_path = result["eval_path"]
    print()
    print("[DS-RADAR] REAL MODE — Claude Haiku API call")
    print(f"Company:     {result['company']}")
    print(f"Role:        {result['title']}")
    print(f"Grade:       {result['grade']} | Score: {result['overall_score']}/5.0")
    print(f"Recommended: {recommended_str}")
    print(f"Report:      evals/{eval_path.name}")
    print()


if __name__ == "__main__":
    main()
