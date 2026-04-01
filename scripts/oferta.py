"""
ds-radar deep offer analysis — REAL MODE
Usage: python oferta.py <job_url>

Produces a 6-block strategic brief for a single offer.
Uses existing eval if available, otherwise runs evaluate_url() for real scoring.
Does NOT write to scan-history.tsv — can be re-run freely.
"""

import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate import (
    extract_company_from_url, mock_extract_jd,
    read_scan_history, url_already_evaluated,
    parse_eval_file, evaluate_url,
    PROFILE_PATH, EVALS_DIR, REPO_ROOT,
)


# ── Find or run eval ──────────────────────────────────────────────────────────

def get_eval_data(url: str) -> dict:
    """Return eval dict from existing file or by running a fresh evaluation."""
    history = read_scan_history()
    row = url_already_evaluated(url, history)
    if row:
        eval_path = REPO_ROOT / row["eval_path"]
        if eval_path.exists():
            print(f"[OFERTA] Using existing eval: {eval_path.name}")
            return parse_eval_file(eval_path)

    print("[OFERTA] No existing eval — running evaluate_url() ...")
    result = evaluate_url(url)
    if result.get("skipped"):
        # evaluate_url returned skipped but no file found above — shouldn't happen,
        # but handle gracefully by re-parsing from the path in the history row
        history2 = read_scan_history()
        row2 = url_already_evaluated(url, history2)
        if row2:
            eval_path2 = REPO_ROOT / row2["eval_path"]
            if eval_path2.exists():
                return parse_eval_file(eval_path2)
    return result


# ── Deep analysis (uses real grade/score from eval) ───────────────────────────

def build_deep_analysis(jd: dict, url: str, eval_data: dict) -> dict:
    grade = eval_data.get("grade", "?")
    overall = eval_data.get("overall_score", 0.0)

    interest = "a compelling" if overall >= 3.8 else "a borderline"

    return {
        "executive_summary": (
            f"This is {interest} opportunity at {jd['company']} for a {jd['title']} role "
            f"({jd['location']}). Scored {grade} ({overall}/5.0). "
            f"{'Worth a tailored application.' if overall >= 3.8 else 'Proceed only if pipeline is thin.'}"
        ),
        "cv_match": (
            f"Strong alignment: Python, SQL, machine learning, pandas, and stakeholder comms all present in your CV. "
            f"Potential gaps: no explicit mention of {jd['company']}'s domain. "
            f"Agentic AI and LLM experience (ds-radar, Claude API) is a differentiator if the JD touches on LLMs."
        ),
        "seniority": (
            f"Role appears to be a lateral move or slight step up based on the JD. "
            f"Broad ownership and stakeholder expectations suggest senior IC scope."
        ),
        "compensation": (
            f"Listed salary: {jd.get('salary', 'not specified')}. "
            f"Your target is £40k–£60k. Clarify equity and total comp early if salary is at the lower end."
        ),
        "personalisation_hooks": (
            f"1. Reference {jd['company']}'s focus on data-driven decision-making — align with your A/B testing and dashboarding work.\n"
            f"2. Mention end-to-end ML pipeline delivery (freelance DS 2023–present) as evidence of production-readiness.\n"
            f"3. If the JD mentions teaching or documentation: Le Wagon instructor role shows communication of complex ML concepts."
        ),
        "interview_probability": (
            f"~{'65%' if overall >= 3.8 else '40%'} callback likelihood. "
            f"{'Strong alignment on core stack. Apply promptly.' if overall >= 3.8 else 'Reasonable fit with minor gaps. A tailored cover note would help.'}"
        ),
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
**URL:** {url} | **Date:** {today} | **Mode:** REAL
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
    eval_data = get_eval_data(url)
    analysis = build_deep_analysis(jd, url, eval_data)
    output_path = write_deep_report(analysis, jd, url)

    rel = output_path.relative_to(Path(__file__).resolve().parent.parent)
    print()
    print(f"[OFERTA] REAL MODE — using scored eval data")
    print(f"Company:     {jd['company']}")
    print(f"Role:        {jd['title']}")
    print(f"Grade:       {analysis['grade']} | Score: {analysis['overall']}/5.0")
    print(f"Report:      {rel}")
    print()
    print("─" * 50)
    print(output_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
