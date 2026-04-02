"""
ds-radar CV generator
Usage: python generate_pdf.py <eval_path>
Example: python generate_pdf.py evals/deepmind_2026-04-01.md

If the eval contains a real JD ([JD_SOURCE: REAL]), calls Claude Haiku to
rewrite the canonical CV tailored to that job.
If JD is mock, falls back to keyword injection.
Writes Markdown CV to applications/cv_{company}_{YYYYMMDD}.md
"""

import os
import re
import sys
from datetime import date
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
CV_PATH = REPO_ROOT / "profile" / "cv.md"
APPLICATIONS_DIR = REPO_ROOT / "applications"

# ── API client setup (same pattern as evaluate.py) ────────────────────────────

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")

_api_key = os.getenv("ANTHROPIC_API_KEY")
if not _api_key:
    print("[ERROR] ANTHROPIC_API_KEY not found. Add it to ds-radar/.env")
    sys.exit(1)

import anthropic
_client = anthropic.Anthropic(api_key=_api_key)

MODEL = "claude-haiku-4-5-20251001"
CV_REWRITE_MAX_TOKENS = 1500

# ── Helpers ───────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text


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

    return {
        "role": role,
        "company": company,
        "grade": grade,
        "score": score,
        "dim_scores": dim_scores,
        "keywords": keywords,
        "interview_angle": interview_angle,
        "jd_source": jd_source,
        "jd_text": jd_text,
    }


# ── Step 2: Load base CV ──────────────────────────────────────────────────────

def load_base_cv() -> str:
    return CV_PATH.read_text(encoding="utf-8")


# ── Step 3a: Claude CV rewrite (REAL JD path) ────────────────────────────────

_CV_REWRITE_PROMPT = """\
Rewrite the CV below tailored to the job description provided.

Rules:
- Keep all facts true — do not invent experience.
- Reorder bullets so the most relevant experience for this JD comes first.
- Rewrite the Summary section (max 3 sentences) to emphasise fit for THIS specific role.
- Keep the same sections as the original CV unless there is a strong reason to drop one.
- Inject important JD keywords naturally — no keyword stuffing.
- Output a complete CV in GitHub-flavoured Markdown only. No preamble, no explanation.

Candidate fit grade: {grade}
Dimension scores: {scores_str}

---
JOB DESCRIPTION:
{jd_text}

---
CANONICAL CV:
{cv_text}"""


def rewrite_cv_with_claude(parsed: dict, base_cv: str) -> str:
    scores_str = " | ".join(
        f"{k.replace('_', ' ').title()}: {v}"
        for k, v in parsed["dim_scores"].items()
    )
    prompt = _CV_REWRITE_PROMPT.format(
        grade=parsed["grade"],
        scores_str=scores_str or "N/A",
        jd_text=parsed["jd_text"],
        cv_text=base_cv,
    )

    response = _client.messages.create(
        model=MODEL,
        max_tokens=CV_REWRITE_MAX_TOKENS,
        system="You are a professional CV writer. Output clean Markdown only.",
        messages=[{"role": "user", "content": prompt}],
    )

    usage = response.usage
    cost = (usage.input_tokens * 0.25 + usage.output_tokens * 1.25) / 1_000_000
    print(f"[COST] cv_rewrite ~${cost:.5f} | {usage.input_tokens} in / {usage.output_tokens} out")

    return response.content[0].text.strip()


# ── Step 3b: Keyword injection fallback (MOCK JD path) ───────────────────────

def inject_keywords(cv: str, keywords: list[str]) -> str:
    kw_line = "**Key skills for this role:** " + ", ".join(keywords[:8])
    return cv.replace("## Skills", f"## Skills\n{kw_line}\n")


# ── Step 4: Save tailored CV ──────────────────────────────────────────────────

def save_cv(cv: str, company: str, grade: str, jd_source: str, interview_angle: str, eval_path: Path) -> Path:
    today = date.today().strftime("%Y%m%d")
    company_slug = slugify(company)
    filename = f"cv_{company_slug}_{today}.md"

    APPLICATIONS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = APPLICATIONS_DIR / filename

    header = (
        f"<!-- Tailored for: {company} | Grade: {grade} | JD: {jd_source} | "
        f"Source eval: {eval_path.name} | Generated: {today} -->\n"
        f"<!-- Interview angle: {interview_angle} -->\n\n"
    )
    output_path.write_text(header + cv, encoding="utf-8")
    return output_path


# ── Public API ────────────────────────────────────────────────────────────────

def generate_pdf(eval_path: "Path | str") -> str:
    """Generate a tailored CV from an eval report. Returns relative path to the output file."""
    eval_path = Path(eval_path)
    if not eval_path.is_absolute():
        eval_path = REPO_ROOT / eval_path

    if not eval_path.exists():
        raise FileNotFoundError(f"Eval file not found: {eval_path}")

    parsed = parse_eval(eval_path)
    base_cv = load_base_cv()

    print(f"CV_REWRITE company={parsed['company']} grade={parsed['grade']} jd_source={parsed['jd_source']}")

    if parsed["jd_source"] == "REAL" and parsed["jd_text"]:
        tailored_cv = rewrite_cv_with_claude(parsed, base_cv)
    else:
        if parsed["jd_source"] != "REAL":
            print("[WARN] JD_SOURCE is MOCK — Claude rewrite skipped, using keyword injection")
        elif not parsed["jd_text"]:
            print("[WARN] JD text missing from eval — Claude rewrite skipped, using keyword injection")
        tailored_cv = inject_keywords(base_cv, parsed["keywords"])

    output_path = save_cv(
        tailored_cv,
        parsed["company"],
        parsed["grade"],
        parsed["jd_source"],
        parsed["interview_angle"],
        eval_path,
    )
    return str(output_path.relative_to(REPO_ROOT))


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python generate_pdf.py <eval_path>")
        sys.exit(1)

    try:
        rel_path = generate_pdf(sys.argv[1])
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    print(f"[CV] Saved to: {rel_path}")


if __name__ == "__main__":
    main()
