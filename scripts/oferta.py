"""
ds-radar deep offer analysis — REAL MODE
Usage: python oferta.py <job_url>

Produces a 6-block strategic brief for a single offer.
If the eval has a real JD ([JD_SOURCE: REAL]), uses Claude Haiku for all 6 blocks.
Falls back to template prose for old/mock evals.
"""

import json
import re
import sys
from datetime import date
from pathlib import Path

try:
    from identity import record_artifact_identity
except ImportError:  # pragma: no cover - module execution fallback
    from scripts.identity import record_artifact_identity

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate import (
    extract_company_from_url, mock_extract_jd,
    read_scan_history, url_already_evaluated,
    parse_eval_file, evaluate_url,
    _client, MODEL,
    PROFILE_PATH, EVALS_DIR, REPO_ROOT,
)

ERRORS_LOG = EVALS_DIR / "errors.log"


# ── Rich eval parser ──────────────────────────────────────────────────────────

def parse_eval_deep(eval_path: Path) -> dict:
    """Parse eval .md fully: title, company, grade, score, dim_scores, jd_source, jd_text."""
    text = eval_path.read_text(encoding="utf-8")

    title, company = "Unknown", "Unknown"
    m = re.search(r"^#\s+(.+?)\s+@\s+(.+)$", text, re.MULTILINE)
    if m:
        title, company = m.group(1).strip(), m.group(2).strip()

    grade = "?"
    m = re.search(r"\*\*Grade:\*\*\s*([A-F])", text)
    if m:
        grade = m.group(1)

    overall_score = 0.0
    m = re.search(r"\*\*Score:\*\*\s*([\d.]+)/5\.0", text)
    if m:
        overall_score = float(m.group(1))

    dim_scores: dict[str, float] = {}
    for m in re.finditer(r"\|\s*([^|]+?)\s*\|\s*([\d.]+)\s*\|", text):
        try:
            dim_scores[m.group(1).strip().lower().replace(" ", "_")] = float(m.group(2))
        except ValueError:
            pass  # skips the header row "| Dimension | Score |"

    keywords: list[str] = []
    m = re.search(r"##\s+Top Keywords\s*\n([^\n#]+)", text)
    if m:
        keywords = [k.strip() for k in m.group(1).split(",") if k.strip()]

    jd_source, jd_text = "MOCK", ""
    m = re.search(
        r"##\s+Job Description\s*\n\[JD_SOURCE: (REAL|MOCK)\]\n([\s\S]+?)(?=\n##|\Z)",
        text,
    )
    if m:
        jd_source = m.group(1)
        jd_text = m.group(2).strip()

    return {
        "title": title,
        "company": company,
        "grade": grade,
        "overall_score": overall_score,
        "dim_scores": dim_scores,
        "keywords": keywords,
        "jd_source": jd_source,
        "jd_text": jd_text,
    }


# ── Find or create eval, return its Path ─────────────────────────────────────

def get_eval_path(url: str) -> Path:
    history = read_scan_history()
    row = url_already_evaluated(url, history)
    if row:
        p = REPO_ROOT / row["eval_path"]
        if p.exists():
            print(f"[OFERTA] Using existing eval: {p.name}")
            return p

    print("[OFERTA] No existing eval — running evaluate_url() ...")
    result = evaluate_url(url)

    if result.get("skipped"):
        for r in read_scan_history():
            if r.get("url", "").strip() == url:
                p2 = REPO_ROOT / r["eval_path"]
                if p2.exists():
                    return p2

    p3 = result.get("eval_path")
    if p3:
        return p3 if isinstance(p3, Path) else Path(p3)

    raise RuntimeError(f"Could not find or create eval for {url}")


# ── Profile loader ────────────────────────────────────────────────────────────

def _load_profile() -> dict:
    try:
        import yaml
        data = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
        return {
            "archetypes": data["target_roles"]["archetypes"],
            "min_k": data["compensation"]["min_salary_gbp"] // 1000,
            "target_k": data["compensation"]["target_salary_gbp"] // 1000,
        }
    except Exception:
        return {
            "archetypes": ["Data Scientist", "Analytics Engineer", "ML Engineer"],
            "min_k": 40,
            "target_k": 60,
        }


# ── Claude brief generator ────────────────────────────────────────────────────

_BRIEF_KEYS = {
    "executive_summary", "cv_match", "seniority",
    "compensation", "personalisation_hooks", "interview_probability",
}

_BRIEF_PROMPT = """\
Candidate: Renzo Rico, DS/ML, London UK
Target: {archetypes}
Salary: min £{min_k}k, target £{target_k}k

Role: {title} at {company}
Grade: {grade} ({overall_score}/5.0)
Scores: {scores_line}

JD:
{jd_text}

Return JSON only:
{{
  "executive_summary": "2-4 sentences: overall fit recommendation",
  "cv_match": "2-4 sentences: specific alignment with this JD",
  "seniority": "2-4 sentences: level vs candidate background",
  "compensation": "2-4 sentences: salary fit and market context",
  "personalisation_hooks": "3 specific bullets grounded in this JD/company",
  "interview_probability": "2-4 sentences with % callback estimate"
}}"""


def generate_brief_with_claude(
    parsed: dict, profile: dict
) -> tuple[dict | None, int, int]:
    """Call Claude Haiku to produce all 6 brief sections. Returns (brief|None, in_tok, out_tok)."""
    scores_line = " | ".join(
        f"{k.replace('_', ' ').title()}: {v}"
        for k, v in parsed["dim_scores"].items()
    )
    prompt = _BRIEF_PROMPT.format(
        archetypes=", ".join(profile["archetypes"]),
        min_k=profile["min_k"],
        target_k=profile["target_k"],
        title=parsed["title"],
        company=parsed["company"],
        grade=parsed["grade"],
        overall_score=parsed["overall_score"],
        scores_line=scores_line or "N/A",
        jd_text=parsed["jd_text"][:1200],
    )

    response = _client.messages.create(
        model=MODEL,
        max_tokens=800,
        system="You are a job-fit analyst. Output valid JSON only. No explanation.",
        messages=[{"role": "user", "content": prompt}],
    )

    usage = response.usage
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw).strip()

    try:
        brief = json.loads(raw)
    except json.JSONDecodeError as exc:
        EVALS_DIR.mkdir(parents=True, exist_ok=True)
        with ERRORS_LOG.open("a", encoding="utf-8") as f:
            f.write(f"\n--- {date.today().isoformat()} | {parsed['company']} | oferta ---\n")
            f.write(f"JSONDecodeError: {exc}\n")
            f.write(raw + "\n")
        print(f"[ERROR] Malformed JSON from Claude (brief). Raw saved to {ERRORS_LOG.name}")
        return None, usage.input_tokens, usage.output_tokens

    missing = _BRIEF_KEYS - brief.keys()
    if missing:
        print(f"[WARN] Claude brief missing keys: {missing}. Falling back to template.")
        EVALS_DIR.mkdir(parents=True, exist_ok=True)
        with ERRORS_LOG.open("a", encoding="utf-8") as f:
            f.write(f"\n--- {date.today().isoformat()} | {parsed['company']} | oferta missing keys ---\n")
            f.write(str(missing) + "\n" + raw + "\n")
        return None, usage.input_tokens, usage.output_tokens

    return brief, usage.input_tokens, usage.output_tokens


# ── Deep analysis template fallback ──────────────────────────────────────────

def build_deep_analysis(jd: dict, url: str, eval_data: dict) -> dict:
    grade = eval_data.get("grade", "?")
    overall = eval_data.get("overall_score", 0.0)
    interest = "a compelling" if overall >= 3.8 else "a borderline"

    return {
        "executive_summary": (
            f"This is {interest} opportunity at {jd['company']} for a {jd['title']} role. "
            f"Scored {grade} ({overall}/5.0). "
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

def write_deep_report(
    analysis: dict, jd: dict, url: str, brief_source: str = "TEMPLATE_FALLBACK"
) -> Path:
    today = date.today().isoformat()
    company_slug = re.sub(r"[\s_]+", "-", jd["company"].lower().strip())
    company_slug = re.sub(r"[^\w-]", "", company_slug)
    filename = f"deep_{company_slug}_{today}.md"

    EVALS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = EVALS_DIR / filename

    # Normalise personalisation_hooks — Claude may return a list or a string
    hooks = analysis["personalisation_hooks"]
    if isinstance(hooks, list):
        hooks = "\n".join(f"{i+1}. {h}" for i, h in enumerate(hooks))

    report = f"""\
# DEEP ANALYSIS: {jd['title']} @ {jd['company']}
**URL:** {url} | **Date:** {today} | **Mode:** REAL | **Brief source:** {brief_source}
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
{hooks}

## 6. Interview Probability
{analysis['interview_probability']}
"""
    output_path.write_text(report, encoding="utf-8")
    record_artifact_identity(
        output_path,
        url=url,
        company=jd["company"],
        title=jd["title"],
    )
    return output_path


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python oferta.py <job_url>")
        sys.exit(1)

    url = sys.argv[1].strip()

    eval_path = get_eval_path(url)
    parsed = parse_eval_deep(eval_path)

    jd = {
        "title": parsed["title"],
        "company": parsed["company"],
        "location": "See eval",
        "salary": "See eval",
    }

    in_tok = out_tok = 0

    if parsed["jd_source"] == "REAL" and parsed["jd_text"]:
        profile = _load_profile()
        brief, in_tok, out_tok = generate_brief_with_claude(parsed, profile)
        if brief is not None:
            brief_source = "CLAUDE"
            analysis = {**brief, "grade": parsed["grade"], "overall": parsed["overall_score"]}
        else:
            print("[WARN] Claude brief failed — using template fallback")
            brief_source = "TEMPLATE_FALLBACK"
            analysis = build_deep_analysis(jd, url, parsed)
    else:
        print(f"[WARN] jd_source={parsed['jd_source']} or no JD text — using template fallback")
        brief_source = "TEMPLATE_FALLBACK"
        analysis = build_deep_analysis(jd, url, parsed)

    output_path = write_deep_report(analysis, jd, url, brief_source=brief_source)
    rel = output_path.relative_to(REPO_ROOT)

    print()
    print(
        f"OFERTA company={parsed['company']} grade={parsed['grade']} "
        f"jd_source={parsed['jd_source']} brief={brief_source}"
    )
    if in_tok or out_tok:
        cost = (in_tok * 0.25 + out_tok * 1.25) / 1_000_000
        print(f"[COST] oferta ~${cost:.5f} | {in_tok} in / {out_tok} out")
    print(f"Report: {rel}")
    print()
    print("─" * 50)
    print(output_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
