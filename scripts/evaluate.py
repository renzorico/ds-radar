# TODO: replace mock_score() with real Claude API call
"""
ds-radar evaluator — MOCK MODE
Usage: python evaluate.py <job_url>

Evaluates a job offer across 10 dimensions and writes a scored report to evals/.
In mock mode, no API keys or network calls are required.
"""

import sys
import os
import re
import csv
import random
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

# ── Paths ────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
EVALS_DIR = REPO_ROOT / "evals"
SCAN_HISTORY = REPO_ROOT / "scan-history.tsv"
PROFILE_PATH = REPO_ROOT / "profile" / "profile.yaml"

SCAN_HISTORY_HEADER = ["url", "date_seen", "eval_path"]


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

    # greenhouse.io/acme/jobs/... → "Acme"
    if "greenhouse.io" in hostname:
        parts = [p for p in path.split("/") if p]
        if parts:
            return parts[0].replace("-", " ").title()

    # jobs.lever.co/acme/... → "Acme"
    if "lever.co" in hostname:
        parts = [p for p in path.split("/") if p]
        if parts:
            return parts[0].replace("-", " ").title()

    # acme.workable.com → "Acme"
    if "workable.com" in hostname:
        sub = hostname.split(".")[0]
        if sub not in ("www", "jobs", "apply"):
            return sub.replace("-", " ").title()

    # acme.ashbyhq.com → "Acme"
    if "ashbyhq.com" in hostname:
        sub = hostname.split(".")[0]
        if sub not in ("www", "jobs"):
            return sub.replace("-", " ").title()

    # Fallback: use second-level domain (strip TLD)
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


# ── Mock JD extraction ───────────────────────────────────────────────────────

def mock_extract_jd(url: str) -> dict:
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


# ── Mock scorer ──────────────────────────────────────────────────────────────

def mock_score(jd: dict, profile_path: str) -> dict:
    random.seed(hash(jd["company"]))  # deterministic per company

    dimensions = [
        "role_match", "skills_alignment", "seniority", "compensation",
        "interview_likelihood", "geography", "company_stage",
        "product_interest", "growth_trajectory", "timeline",
    ]
    scores = {dim: round(random.uniform(2.0, 5.0), 1) for dim in dimensions}
    overall = round(sum(scores.values()) / len(scores), 1)

    if overall >= 4.5:
        grade = "A"
    elif overall >= 3.8:
        grade = "B"
    elif overall >= 3.0:
        grade = "C"
    elif overall >= 2.0:
        grade = "D"
    else:
        grade = "F"

    fit_word = "strong" if overall >= 3.8 else "weak"
    return {
        "title": jd["title"],
        "company": jd["company"],
        "location": jd["location"],
        "salary_visible": jd["salary"],
        "scores": scores,
        "overall_score": overall,
        "grade": grade,
        "recommended": overall >= 3.8,
        "summary": (
            f"MOCK EVALUATION — {jd['company']} looks like a {fit_word} fit. "
            f"Overall score: {overall}/5.0."
        ),
        "top_keywords": [
            "python", "sql", "machine learning", "pandas",
            "data pipeline", "stakeholder management",
        ],
        "interview_angle": "MOCK — Lead with your end-to-end ML project experience.",
    }


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
**Mode:** MOCK (no API call)

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

    # Step 2 — mock JD extraction
    jd = mock_extract_jd(url)

    # Step 3 — mock scoring
    result = mock_score(jd, str(PROFILE_PATH))

    # Step 4 — save report
    eval_path = write_report(result, url)

    # Step 5 — update scan-history.tsv
    append_scan_history(url, eval_path)

    return {"skipped": False, "url": url, "eval_path": eval_path, **result}


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python evaluate.py <job_url>")
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
    print("[DS-RADAR] MOCK MODE — no API call made")
    print(f"Company:     {result['company']}")
    print(f"Role:        {result['title']}")
    print(f"Grade:       {result['grade']} | Score: {result['overall_score']}/5.0")
    print(f"Recommended: {recommended_str}")
    print(f"Report:      evals/{eval_path.name}")
    print()


if __name__ == "__main__":
    main()
