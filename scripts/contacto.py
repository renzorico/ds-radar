"""
ds-radar LinkedIn outreach generator — REAL MODE
Usage: python contacto.py <job_url> [--name "Hiring Manager Name"]

Reads or generates an eval for the URL, then produces 3 LinkedIn message variants.
Uses existing eval if available, otherwise calls evaluate_url() for real scoring.
Saves to applications/outreach_{company}_{date}.md
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate import (
    extract_company_from_url,
    read_scan_history, url_already_evaluated,
    parse_eval_file, evaluate_url,
    EVALS_DIR,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
APPLICATIONS_DIR = REPO_ROOT / "applications"


# ── Find or run eval ──────────────────────────────────────────────────────────

def get_eval_context(url: str) -> tuple[str, str, str]:
    """Return (company, title, grade) from existing eval or fresh evaluate_url()."""
    history = read_scan_history()
    row = url_already_evaluated(url, history)
    if row:
        eval_path = REPO_ROOT / row["eval_path"]
        if eval_path.exists():
            parsed = parse_eval_file(eval_path)
            print(f"[CONTACTO] Using existing eval: {eval_path.name}")
            return parsed["company"], parsed["title"], parsed["grade"]

    print("[CONTACTO] No existing eval — running evaluate_url() ...")
    result = evaluate_url(url)

    # If evaluate_url returned skipped, try parsing from history again
    if result.get("skipped"):
        history2 = read_scan_history()
        row2 = url_already_evaluated(url, history2)
        if row2:
            eval_path2 = REPO_ROOT / row2["eval_path"]
            if eval_path2.exists():
                parsed2 = parse_eval_file(eval_path2)
                return parsed2["company"], parsed2["title"], parsed2["grade"]

    company = result.get("company", extract_company_from_url(url))
    title = result.get("title", "Data Scientist")
    grade = result.get("grade", "?")
    return company, title, grade


# ── Outreach generator (static — uses real grade context) ────────────────────

def build_outreach(company: str, title: str, grade: str, name: str | None) -> dict:
    greeting = f"Hi {name}" if name else "Hi"
    fit_phrase = "strong mutual fit" if grade in ("A", "B") else "interesting opportunity"

    variant_a = (
        f"{greeting} — saw the {title} role at {company}. "
        f"My background in Python/ML and DS instruction could be a great fit. "
        f"Happy to connect!"
    )
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
**URL:** {url} | **Date:** {today} | **Grade:** {grade} | **Mode:** REAL

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
    company, title, grade = get_eval_context(url)

    messages = build_outreach(company, title, grade, args.name)
    output_path = write_outreach_report(messages, company, title, grade, url)
    rel = output_path.relative_to(REPO_ROOT)

    print()
    print(f"[CONTACTO] REAL MODE — using scored eval data")
    print(f"Company:     {company}")
    print(f"Role:        {title}")
    print(f"Grade:       {grade}")
    print(f"Saved to:    {rel}")
    print()
    print("─" * 50)
    print(output_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
