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

SCAN_HISTORY_HEADER = ["url", "date_seen", "eval_path"]

MODEL = "claude-haiku-4-5-20251001"


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
    """Extract a compact CV summary from profile/cv.md for API prompts (~120 tokens)."""
    cv_text = CV_PATH.read_text(encoding="utf-8")
    lines = cv_text.splitlines()

    # Title from first heading
    title = "Data Scientist & Instructor"
    for line in lines:
        if line.startswith("# "):
            parts = line[2:].split("—")
            if len(parts) > 1:
                title = parts[1].strip()
            break

    # Location
    location = "London, UK"
    for line in lines:
        if "**Location:**" in line:
            location = line.replace("**Location:**", "").strip()
            break

    # Skills (first two lines of skills section)
    skills_lines = []
    in_skills = False
    for line in lines:
        if line.strip() == "## Skills":
            in_skills = True
            continue
        if in_skills:
            if line.startswith("## "):
                break
            stripped = line.strip()
            if stripped and not stripped.startswith("---"):
                skills_lines.append(stripped)
                if len(skills_lines) >= 2:
                    break

    # Top 2 projects
    projects = []
    in_projects = False
    for line in lines:
        if line.strip() == "## Projects":
            in_projects = True
            continue
        if in_projects:
            if line.startswith("## "):
                break
            if line.startswith("**") and "—" in line:
                name_part = line.split("—")[0].replace("**", "").strip()
                desc_part = line.split("—")[1].split(".")[0].strip() if "—" in line else ""
                projects.append(f"{name_part}: {desc_part}")
                if len(projects) >= 2:
                    break

    skills_text = "\n".join(skills_lines)
    projects_text = "\n".join(f"- {p}" for p in projects)

    return (
        f"Title: {title}\n"
        f"Location: {location}\n"
        f"Experience: DS Instructor 2022–present; Freelance DS 2023–present\n"
        f"{skills_text}\n"
        f"Top projects:\n{projects_text}"
    )


# ── Real scorer ───────────────────────────────────────────────────────────────

def real_score(jd: dict) -> dict:
    """Call Claude Haiku to score a JD against the candidate profile."""
    lean_cv = build_lean_cv()
    jd_text = (
        f"Title: {jd['title']}\n"
        f"Company: {jd['company']}\n"
        f"Location: {jd['location']}\n"
        f"Salary: {jd.get('salary', 'not specified')}\n"
        f"Description:\n{jd['description']}"
    )

    user_prompt = f"""\
Candidate profile:
{lean_cv}

Job description:
{truncate_jd(jd_text)}

Score the candidate's fit for this job. Return ONLY valid JSON with this exact schema:
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
  "summary": "<2-3 sentence evaluation of the fit>",
  "top_keywords": ["<5-8 JD keywords relevant to this candidate>"],
  "interview_angle": "<one sentence: best angle for this candidate to lead with>"
}}"""

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
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        EVALS_DIR.mkdir(parents=True, exist_ok=True)
        with ERRORS_LOG.open("a", encoding="utf-8") as f:
            f.write(f"\n--- {date.today().isoformat()} | {jd['company']} ---\n")
            f.write(f"JSONDecodeError: {exc}\n")
            f.write(raw + "\n")
        print(f"[ERROR] Malformed JSON from API. Raw response saved to {ERRORS_LOG}")
        raise

    return result


# ── Report writer ────────────────────────────────────────────────────────────

def write_report(result: dict, url: str) -> Path:
    today = date.today().isoformat()
    company_slug = slugify(result["company"])
    filename = f"{company_slug}_{today}.md"

    EVALS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = EVALS_DIR / filename

    recommended_str = "YES ✓" if result["recommended"] else "NO ✗"

    dimension_rows = "\n".join(
        f"| {dim.replace('_', ' ').title()} | {score} |"
        for dim, score in result["scores"].items()
    )
    keywords_str = ", ".join(result["top_keywords"])

    report = f"""\
# {result['title']} @ {result['company']}
**Grade:** {result['grade']} | **Score:** {result['overall_score']}/5.0 | **Recommended:** {recommended_str}
**URL:** {url}
**Date:** {today}
**Mode:** REAL (Claude Haiku)

## Verdict
{result['summary']}

## Dimension Scores
| Dimension | Score |
|-----------|-------|
{dimension_rows}

## Top Keywords
{keywords_str}

## Interview Angle
{result['interview_angle']}
"""
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

    # Step 3 — real API scoring
    result = real_score(jd)

    # Step 4 — save report
    eval_path = write_report(result, url)

    # Step 5 — update scan-history.tsv
    append_scan_history(url, eval_path)

    return {"skipped": False, "url": url, "eval_path": eval_path, **result}


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
