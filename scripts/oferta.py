# TODO: replace mock_deep_analysis() with real Claude API call
"""
ds-radar deep offer analysis — MOCK MODE
Usage: python oferta.py <job_url>

Produces a 6-block strategic brief for a single offer.
Does NOT write to scan-history.tsv — can be re-run freely.
"""

import random
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate import extract_company_from_url, mock_extract_jd, mock_score, PROFILE_PATH, EVALS_DIR

# ── Mock deep analysis ────────────────────────────────────────────────────────

SENIORITY_OPTIONS = [
    ("Lateral move", "The role sits at the same level as your current work. Solid stability but limited stretch."),
    ("Step up", "This is a clear step up in scope — team lead expectations and broader ownership. Strong growth signal."),
    ("Step down", "The role appears more junior than your current experience level. May suit a deliberate pivot."),
]

COMP_READS = [
    "Salary band aligns with your £40k–£60k target. Market rate for a London mid-level DS is £55k–£75k; this offer sits at the lower end.",
    "Visible range is above your minimum. At £70k–£90k, this is competitive for London and above market median for the role level.",
    "No salary listed — common for early-stage startups. Likely £45k–£65k based on stage and role. Worth clarifying early.",
]

PROB_READS = [
    (
        "~40% callback likelihood.",
        "Your Python/ML background maps well but the JD emphasises domain expertise you haven't signalled. Lead with transferable work.",
    ),
    (
        "~65% callback likelihood.",
        "Strong alignment on core stack. Your Le Wagon teaching history is a differentiator for roles valuing communication. Apply promptly.",
    ),
    (
        "~55% callback likelihood.",
        "Reasonable fit with minor gaps. Strengthening the application with a short cover note referencing a specific project would improve odds.",
    ),
]


def mock_deep_analysis(jd: dict, url: str) -> dict:
    random.seed(hash(jd["company"]))
    score_result = mock_score(jd, str(PROFILE_PATH))
    grade = score_result["grade"]
    overall = score_result["overall_score"]

    sen_label, sen_detail = random.choice(SENIORITY_OPTIONS)
    comp_read = random.choice(COMP_READS)
    prob_headline, prob_detail = random.choice(PROB_READS)

    interest = "a compelling" if overall >= 3.8 else "a borderline"

    return {
        "executive_summary": (
            f"This is {interest} opportunity at {jd['company']} for a {jd['title']} role "
            f"({jd['location']}). MOCK scoring gives it a {grade} ({overall}/5.0). "
            f"{'Worth a tailored application.' if overall >= 3.8 else 'Proceed only if pipeline is thin.'}"
        ),
        "cv_match": (
            f"Strong alignment: Python, SQL, machine learning, pandas, and stakeholder comms all present in your CV. "
            f"Potential gaps: no explicit mention of {jd['company']}'s domain (MOCK). "
            f"Agentic AI and LLM experience (ds-radar, Claude API) is a differentiator if the JD touches on LLMs."
        ),
        "seniority": f"**{sen_label}.** {sen_detail}",
        "compensation": f"MOCK — {comp_read}",
        "personalisation_hooks": (
            f"1. Reference {jd['company']}'s known focus on data-driven decision-making — align with your A/B testing and dashboarding work.\n"
            f"2. Mention end-to-end ML pipeline delivery (freelance DS 2020–2022) as evidence of production-readiness.\n"
            f"3. If the JD mentions teaching or documentation: Le Wagon instructor role shows communication of complex ML concepts."
        ),
        "interview_probability": f"{prob_headline} {prob_detail}",
        "grade": grade,
        "overall": overall,
    }


# ── Report writer ─────────────────────────────────────────────────────────────

def write_deep_report(analysis: dict, jd: dict, url: str) -> Path:
    today = date.today().isoformat()
    company_slug = re.sub(r"[\s_]+", "-", jd["company"].lower().strip())
    company_slug = re.sub(r"[^\w-]", "", company_slug)
    filename = f"deep_{company_slug}_{today}.md"

    EVALS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = EVALS_DIR / filename

    report = f"""\
# DEEP ANALYSIS: {jd['title']} @ {jd['company']}
**URL:** {url} | **Date:** {today} | **Mode:** MOCK
**Grade:** {analysis['grade']} | **Score:** {analysis['overall']}/5.0

---

## 1. Executive Summary
{analysis['executive_summary']}

## 2. CV Match Analysis
{analysis['cv_match']}

## 3. Seniority & Level
{analysis['seniority']}

## 4. Compensation Assessment
{analysis['compensation']}

## 5. Personalisation Hooks
{analysis['personalisation_hooks']}

## 6. Interview Probability
{analysis['interview_probability']}
"""
    output_path.write_text(report, encoding="utf-8")
    return output_path


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python oferta.py <job_url>")
        sys.exit(1)

    url = sys.argv[1].strip()
    jd = mock_extract_jd(url)
    analysis = mock_deep_analysis(jd, url)
    output_path = write_deep_report(analysis, jd, url)

    rel = output_path.relative_to(Path(__file__).resolve().parent.parent)
    print()
    print(f"[OFERTA] MOCK MODE — no API call made")
    print(f"Company:     {jd['company']}")
    print(f"Role:        {jd['title']}")
    print(f"Grade:       {analysis['grade']} | Score: {analysis['overall']}/5.0")
    print(f"Report:      {rel}")
    print()
    print("─" * 50)
    print(output_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
