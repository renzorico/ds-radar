"""
ds-radar LinkedIn outreach generator — REAL MODE
Usage: python contacto.py <job_url> [--name "Hiring Manager Name"]

For B+ roles with real JD: calls Claude Haiku to generate 3 personalised variants.
Falls back to template for C/D/F grades or on API error.
Saves to applications/outreach_{company}_{date}.md
"""

import argparse
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
    extract_company_from_url,
    read_scan_history, url_already_evaluated,
    parse_eval_file, evaluate_url,
    build_lean_cv,
    _client, MODEL,
    EVALS_DIR,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
APPLICATIONS_DIR = REPO_ROOT / "applications"
OUTREACH_ERRORS_LOG = APPLICATIONS_DIR / "outreach_errors.log"

APPLY_GRADES = {"A", "B"}


# ── Rich eval parser (local — mirrors oferta.parse_eval_deep) ─────────────────

def _parse_eval_rich(eval_path: Path) -> dict:
    text = eval_path.read_text(encoding="utf-8")

    title, company = "Unknown", "Unknown"
    m = re.search(r"^#\s+(.+?)\s+@\s+(.+)$", text, re.MULTILINE)
    if m:
        title, company = m.group(1).strip(), m.group(2).strip()

    grade, overall_score = "?", 0.0
    m = re.search(r"\*\*Grade:\*\*\s*([A-F])", text)
    if m:
        grade = m.group(1)
    m = re.search(r"\*\*Score:\*\*\s*([\d.]+)/5\.0", text)
    if m:
        overall_score = float(m.group(1))

    dim_scores: dict[str, float] = {}
    for m in re.finditer(r"\|\s*([^|]+?)\s*\|\s*([\d.]+)\s*\|", text):
        try:
            dim_scores[m.group(1).strip().lower().replace(" ", "_")] = float(m.group(2))
        except ValueError:
            pass

    jd_source, jd_text = "MOCK", ""
    m = re.search(
        r"##\s+Job Description\s*\n\[JD_SOURCE: (REAL|MOCK)\]\n([\s\S]+?)(?=\n##|\Z)",
        text,
    )
    if m:
        jd_source, jd_text = m.group(1), m.group(2).strip()

    return {
        "title": title, "company": company,
        "grade": grade, "overall_score": overall_score,
        "dim_scores": dim_scores,
        "jd_source": jd_source, "jd_text": jd_text,
    }


# ── Find or create eval, return rich parsed dict ──────────────────────────────

def get_eval_rich(url: str) -> dict:
    history = read_scan_history()
    row = url_already_evaluated(url, history)
    if row:
        p = REPO_ROOT / row["eval_path"]
        if p.exists():
            print(f"[CONTACTO] Using existing eval: {p.name}")
            return _parse_eval_rich(p)

    print("[CONTACTO] No existing eval — running evaluate_url() ...")
    result = evaluate_url(url)

    if result.get("skipped"):
        for r in read_scan_history():
            if r.get("url", "").strip() == url:
                p2 = REPO_ROOT / r["eval_path"]
                if p2.exists():
                    return _parse_eval_rich(p2)

    p3 = result.get("eval_path")
    if p3:
        p3 = p3 if isinstance(p3, Path) else Path(p3)
        if p3.exists():
            return _parse_eval_rich(p3)

    # Fallback: build minimal dict from evaluate_url result
    return {
        "title": result.get("title", "Data Scientist"),
        "company": result.get("company", extract_company_from_url(url)),
        "grade": result.get("grade", "?"),
        "overall_score": result.get("overall_score", 0.0),
        "dim_scores": {},
        "jd_source": "MOCK",
        "jd_text": "",
    }


# ── Find personalisation hooks from oferta brief (if any) ────────────────────

def _find_oferta_hooks(company: str) -> str:
    """Return personalisation hooks text from the most recent deep brief for this company."""
    slug = re.sub(r"[\s_]+", "-", company.lower().strip())
    slug = re.sub(r"[^\w-]", "", slug)
    candidates = sorted(EVALS_DIR.glob(f"deep_{slug}_*.md"), reverse=True)
    if not candidates:
        return ""
    text = candidates[0].read_text(encoding="utf-8")
    m = re.search(r"##\s+5\. Personalisation Hooks\s*\n([\s\S]+?)(?=\n##|\Z)", text)
    if m:
        return m.group(1).strip()
    return ""


# ── Claude outreach generator ─────────────────────────────────────────────────

_OUTREACH_PROMPT = """\
Write 3 LinkedIn outreach messages from Renzo Rico to a hiring manager{greeting_suffix}.

Candidate: Renzo Rico, Data Scientist & Instructor, London UK.
{lean_cv}

Role: {title} at {company}
Grade: {grade} ({overall_score}/5.0) | Key scores: {key_scores}
JD: {jd_block}
{hooks_block}
Return JSON only:
{{
  "short": "1-2 sentences, max 300 chars, cold DM opener — specific to this role/company, punchy",
  "standard": "4-5 sentences: hook → Renzo relevant experience → clear ask",
  "value_first": "leads with a genuine insight, observation, or question about the role/company, then positions Renzo naturally"
}}

Rules: personalise to {company} and this exact role, sound human, no buzzword soup, no generic filler."""


def generate_outreach_with_claude(
    eval_data: dict, oferta_hooks: str, name: str | None
) -> tuple[dict | None, int, int]:
    """One Claude call → {short, standard, value_first}. Returns (dict|None, in, out)."""
    greeting_suffix = f' (addressing "{name}" by name)' if name else ""

    key_scores = " | ".join(
        f"{k.replace('_', ' ').title()}: {v}"
        for k, v in list(eval_data["dim_scores"].items())[:5]
    ) or "N/A"

    jd_block = eval_data["jd_text"][:800] if eval_data["jd_text"] else "(not available)"
    hooks_block = f"Personalisation hooks:\n{oferta_hooks}\n" if oferta_hooks else ""

    lean_cv = build_lean_cv()

    prompt = _OUTREACH_PROMPT.format(
        greeting_suffix=greeting_suffix,
        lean_cv=lean_cv,
        title=eval_data["title"],
        company=eval_data["company"],
        grade=eval_data["grade"],
        overall_score=eval_data["overall_score"],
        key_scores=key_scores,
        jd_block=jd_block,
        hooks_block=hooks_block,
    )

    response = _client.messages.create(
        model=MODEL,
        max_tokens=600,
        system="You are a LinkedIn outreach specialist. Output valid JSON only. No explanation.",
        messages=[{"role": "user", "content": prompt}],
    )

    usage = response.usage
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw).strip()

    try:
        messages = json.loads(raw)
    except json.JSONDecodeError as exc:
        APPLICATIONS_DIR.mkdir(parents=True, exist_ok=True)
        with OUTREACH_ERRORS_LOG.open("a", encoding="utf-8") as f:
            f.write(f"\n--- {date.today().isoformat()} | {eval_data['company']} ---\n")
            f.write(f"JSONDecodeError: {exc}\n{raw}\n")
        print(f"[ERROR] Malformed JSON from Claude. Raw saved to {OUTREACH_ERRORS_LOG.name}")
        return None, usage.input_tokens, usage.output_tokens

    missing = {"short", "standard", "value_first"} - messages.keys()
    if missing:
        print(f"[WARN] Claude response missing keys: {missing}. Falling back to template.")
        return None, usage.input_tokens, usage.output_tokens

    # Enforce short variant char limit
    if len(messages["short"]) > 300:
        messages["short"] = messages["short"][:297] + "..."

    return messages, usage.input_tokens, usage.output_tokens


# ── Template fallback ─────────────────────────────────────────────────────────

def build_outreach_template(
    company: str, title: str, grade: str, name: str | None
) -> dict:
    greeting = f"Hi {name}" if name else "Hi"
    dream = f"""\
{greeting},

I’m a data scientist in London — currently teaching DS at Le Wagon and building projects on the side, including an AI pipeline in Python/Claude/Playwright and a civic tech platform that reached 10k+ users.

The {title} role at {company} stands out because it looks close to real product data work rather than generic analytics. My background is strongest in Python, SQL, ML, NLP, and shipping practical tools end to end.

Happy to send a short portfolio if useful.

Renzo"""

    bridge = f"""\
{greeting},

I’m a data scientist based in London. I teach DS at Le Wagon and build projects ranging from NLP pipelines and geospatial analysis to deployed web products in FastAPI and TypeScript.

The {title} role at {company} looks like solid technical work with a usable stack. I’m looking for solid technical data work in London right now, and this looks like a good fit on the stack and scope.

Happy to share more if it’s worth a conversation.

Renzo"""

    backup = f"""\
{greeting},

Data scientist in London — Python, SQL, ML, deployed projects. I came across the {title} role at {company} and wanted to connect directly before applying. Happy to share a portfolio if helpful.

Renzo"""

    short = backup.replace("\n\nRenzo", " Renzo")
    if len(short) > 300:
        short = short[:297] + "..."

    standard = dream if grade in APPLY_GRADES else bridge
    value_first = bridge if grade in APPLY_GRADES else backup

    return {
        "short": short,
        "standard": standard.strip(),
        "value_first": value_first.strip(),
    }


# ── Report writer ─────────────────────────────────────────────────────────────

def write_outreach_report(
    messages: dict, eval_data: dict, url: str,
    source: str, name: str | None,
) -> Path:
    today = date.today().isoformat()
    company = eval_data["company"]
    title = eval_data["title"]
    grade = eval_data["grade"]

    company_slug = re.sub(r"[\s_]+", "-", company.lower().strip())
    company_slug = re.sub(r"[^\w-]", "", company_slug)
    filename = f"outreach_{company_slug}_{today}.md"

    APPLICATIONS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = APPLICATIONS_DIR / filename

    greeting_note = f" (to: {name})" if name else ""
    char_short = len(messages["short"])

    report = f"""\
# OUTREACH: {company} — {title}
**URL:** {url} | **Date:** {today} | **Grade:** {grade} | **Source:** {source}
{greeting_note}
---

## Short
*({char_short} chars — connection request)*

{messages['short']}

---

## Standard
*(InMail / cold message)*

{messages['standard']}

---

## Value-first
*(lead with insight or question)*

{messages['value_first']}
"""
    output_path.write_text(report, encoding="utf-8")
    record_artifact_identity(
        output_path,
        url=url,
        company=company,
        title=title,
    )
    return output_path


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate LinkedIn outreach messages")
    parser.add_argument("url", help="Job listing URL")
    parser.add_argument("--name", default=None, help="Hiring manager name")
    args = parser.parse_args()

    url = args.url.strip()
    eval_data = get_eval_rich(url)
    company = eval_data["company"]
    grade = eval_data["grade"]
    jd_source = eval_data["jd_source"]

    in_tok = out_tok = 0
    review_flag = jd_source == "MOCK"

    if grade in APPLY_GRADES:
        oferta_hooks = _find_oferta_hooks(company)
        messages, in_tok, out_tok = generate_outreach_with_claude(
            eval_data, oferta_hooks, args.name
        )
        if messages is not None:
            source = "CLAUDE"
        else:
            print("[WARN] Claude generation failed — using template fallback")
            source = "TEMPLATE_FALLBACK"
            messages = build_outreach_template(company, eval_data["title"], grade, args.name)
    else:
        print(f"[CONTACTO] Grade {grade} below threshold — skipping Claude, using template")
        source = "TEMPLATE_FALLBACK"
        messages = build_outreach_template(company, eval_data["title"], grade, args.name)

    output_path = write_outreach_report(messages, eval_data, url, source, args.name)
    rel = output_path.relative_to(REPO_ROOT)

    print()
    review_note = " review_before_sending=true" if review_flag else ""
    print(
        f"CONTACTO company={company} grade={grade} "
        f"jd_source={jd_source} source={source}{review_note}"
    )
    if in_tok or out_tok:
        cost = (in_tok * 0.25 + out_tok * 1.25) / 1_000_000
        print(f"[COST] contacto ~${cost:.5f} | {in_tok} in / {out_tok} out")
    print(f"Saved to: {rel}")
    print()
    print("─" * 50)
    print(output_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
