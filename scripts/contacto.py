# TODO: replace mock_outreach() with real Claude API call using real eval content
"""
ds-radar LinkedIn outreach generator — MOCK MODE
Usage: python contacto.py <job_url> [--name "Hiring Manager Name"]

Reads or generates an eval for the URL, then produces 3 LinkedIn message variants.
Saves to applications/outreach_{company}_{date}.md
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate import (
    extract_company_from_url, mock_extract_jd, mock_score,
    read_scan_history, url_already_evaluated,
    write_report, append_scan_history, PROFILE_PATH, EVALS_DIR,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
APPLICATIONS_DIR = REPO_ROOT / "applications"


# ── Find existing eval ────────────────────────────────────────────────────────

def find_existing_eval(url: str) -> Path | None:
    """Return eval path from scan-history if it exists on disk."""
    history = read_scan_history()
    row = url_already_evaluated(url, history)
    if not row:
        return None
    eval_path = REPO_ROOT / row["eval_path"]
    return eval_path if eval_path.exists() else None


def quick_eval(url: str) -> tuple[str, str, str]:
    """Run a quick mock eval without printing, return (company, title, grade)."""
    jd = mock_extract_jd(url)
    result = mock_score(jd, str(PROFILE_PATH))
    existing = find_existing_eval(url)
    if not existing:
        eval_path = write_report(result, url)
        append_scan_history(url, eval_path)
    return jd["company"], jd["title"], result["grade"]


# ── Mock outreach generator ───────────────────────────────────────────────────

def mock_outreach(company: str, title: str, grade: str, name: str | None) -> dict:
    greeting = f"Hi {name}" if name else "Hi"
    fit_phrase = "strong mutual fit" if grade in ("A", "B") else "interesting opportunity"

    variant_a = (
        f"{greeting} — saw the {title} role at {company}. "
        f"My background in Python/ML and DS instruction could be a great fit. "
        f"Happy to connect!"
    )
    # Trim to ≤300 chars
    if len(variant_a) > 300:
        variant_a = variant_a[:297] + "..."

    variant_b = f"""\
{greeting},

I came across the {title} opening at {company} and wanted to reach out directly.

I'm a Data Scientist based in London with experience in Python, ML, and teaching \
at Le Wagon — I've also been building agentic AI tools as side projects, including \
a job-search pipeline using Claude API and Playwright.

I see a {fit_phrase} between my background and what {company} is building. \
Would love to connect and learn more about the team.

Best,
Renzo"""

    variant_c = f"""\
{greeting},

One thing I'm proud of: I've mentored 200+ students through end-to-end ML projects \
at Le Wagon, and recently built an agentic pipeline ({company} is actually on my \
radar list!) that automates job discovery and CV tailoring using Claude API.

I think that combination of applied ML, teaching, and hands-on AI development maps \
well to the {title} role at {company}.

Would you be open to a quick chat?

Best,
Renzo"""

    return {
        "variant_a": variant_a,
        "variant_b": variant_b.strip(),
        "variant_c": variant_c.strip(),
    }


# ── Report writer ─────────────────────────────────────────────────────────────

def write_outreach_report(
    messages: dict, company: str, title: str, grade: str, url: str
) -> Path:
    today = date.today().isoformat()
    company_slug = re.sub(r"[\s_]+", "-", company.lower().strip())
    company_slug = re.sub(r"[^\w-]", "", company_slug)
    filename = f"outreach_{company_slug}_{today}.md"

    APPLICATIONS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = APPLICATIONS_DIR / filename

    char_a = len(messages["variant_a"])

    report = f"""\
# OUTREACH: {company} — {title}
**URL:** {url} | **Date:** {today} | **Grade:** {grade} | **Mode:** MOCK

---

## Variant A — Short ({char_a} chars, for connection request)

{messages['variant_a']}

---

## Variant B — Standard (InMail, ~150 words)

{messages['variant_b']}

---

## Variant C — Value-first (lead with achievement)

{messages['variant_c']}
"""
    output_path.write_text(report, encoding="utf-8")
    return output_path


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate LinkedIn outreach messages")
    parser.add_argument("url", help="Job listing URL")
    parser.add_argument("--name", default=None, help="Hiring manager name")
    args = parser.parse_args()

    url = args.url.strip()

    # Get eval context — use existing or run quick mock
    existing_eval = find_existing_eval(url)
    if existing_eval:
        company = extract_company_from_url(url)
        jd = mock_extract_jd(url)
        result = mock_score(jd, str(PROFILE_PATH))
        title, grade = result["title"], result["grade"]
        print(f"[CONTACTO] Using existing eval for {company}")
    else:
        company, title, grade = quick_eval(url)
        print(f"[CONTACTO] No existing eval — ran quick mock for {company}")

    messages = mock_outreach(company, title, grade, args.name)
    output_path = write_outreach_report(messages, company, title, grade, url)
    rel = output_path.relative_to(REPO_ROOT)

    print()
    print(f"[CONTACTO] MOCK MODE — no API call made")
    print(f"Company:     {company}")
    print(f"Role:        {title}")
    print(f"Grade:       {grade}")
    print(f"Saved to:    {rel}")
    print()
    print("─" * 50)
    print(output_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
