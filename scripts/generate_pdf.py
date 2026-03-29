# TODO: replace Markdown output with real PDF rendering (Puppeteer or WeasyPrint)
# TODO: replace inject_keywords() with real Claude API call for full CV rewrite
"""
ds-radar pdf generator — MOCK MODE
Usage: python generate_pdf.py <eval_path>
Example: python generate_pdf.py evals/deepmind_2026-03-30.md

Reads an eval report, tailors the base CV with extracted keywords,
and writes a Markdown CV to applications/. No PDF library required in mock mode.
"""

import re
import sys
from datetime import date
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
CV_PATH = REPO_ROOT / "profile" / "cv.md"
APPLICATIONS_DIR = REPO_ROOT / "applications"

PLACEHOLDER_MARKER = "[PLACEHOLDER"

MOCK_CV = """\
# Renzo Rico — Data Scientist

## Summary
Data Scientist and educator with 5+ years experience in ML, Python, and analytics.
Based in London. Open to hybrid and remote roles.

## Skills
Python, SQL, pandas, scikit-learn, TensorFlow, Tableau, dbt, Spark, Git

## Experience
### Senior Data Science Instructor — Le Wagon (2022–present)
- Taught ML, statistics, and Python to 200+ students
- Built curriculum for deep learning and NLP modules

### Data Scientist — Freelance (2020–2022)
- Built end-to-end ML pipelines for e-commerce clients
- Delivered A/B testing frameworks and dashboards

## Education
BSc Computer Science | Universidad Autónoma de Madrid
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text


# ── Step 1: Parse eval report ─────────────────────────────────────────────────

def parse_eval(eval_path: Path) -> dict:
    text = eval_path.read_text(encoding="utf-8")

    # # Senior Data Scientist @ DeepMind
    title_match = re.search(r"^#\s+(.+?)\s+@\s+(.+)$", text, re.MULTILINE)
    if not title_match:
        print(f"Error: cannot parse title line from {eval_path.name}")
        sys.exit(1)
    role = title_match.group(1).strip()
    company = title_match.group(2).strip()

    # **Grade:** B | **Score:** 3.8/5.0
    grade_match = re.search(r"\*\*Grade:\*\*\s*([A-F])", text)
    score_match = re.search(r"\*\*Score:\*\*\s*([\d.]+)/5\.0", text)
    grade = grade_match.group(1) if grade_match else "?"
    score = score_match.group(1) if score_match else "?"

    # ## Top Keywords\npython, sql, ...
    kw_match = re.search(r"##\s+Top Keywords\s*\n([^\n#]+)", text)
    keywords: list[str] = []
    if kw_match:
        raw = kw_match.group(1).strip()
        keywords = [k.strip() for k in raw.split(",") if k.strip()]

    # ## Interview Angle\n...
    angle_match = re.search(r"##\s+Interview Angle\s*\n([^\n#]+)", text)
    interview_angle = angle_match.group(1).strip() if angle_match else ""

    return {
        "role": role,
        "company": company,
        "grade": grade,
        "score": score,
        "keywords": keywords,
        "interview_angle": interview_angle,
    }


# ── Step 2: Load base CV ──────────────────────────────────────────────────────

def load_base_cv() -> str:
    if CV_PATH.exists():
        content = CV_PATH.read_text(encoding="utf-8")
        if PLACEHOLDER_MARKER not in content:
            return content
    # cv.md is still a placeholder — use mock
    return MOCK_CV


# ── Step 3: Keyword injection ─────────────────────────────────────────────────

def inject_keywords(cv: str, keywords: list[str]) -> str:
    kw_line = "**Key skills for this role:** " + ", ".join(keywords[:8])
    return cv.replace("## Skills", f"## Skills\n{kw_line}\n")


# ── Step 4: Save tailored CV ──────────────────────────────────────────────────

def save_cv(cv: str, company: str, grade: str, interview_angle: str, eval_path: Path) -> Path:
    today = date.today().isoformat()
    company_slug = slugify(company)
    filename = f"{company_slug}_{grade}_{today}.md"

    APPLICATIONS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = APPLICATIONS_DIR / filename

    header = (
        f"<!-- Tailored for: {company} | Grade: {grade} | "
        f"Source eval: {eval_path.name} | Generated: {today} -->\n"
        f"<!-- Interview angle: {interview_angle} -->\n\n"
    )
    output_path.write_text(header + cv, encoding="utf-8")
    return output_path


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python generate_pdf.py <eval_path>")
        sys.exit(1)

    eval_path = Path(sys.argv[1])
    if not eval_path.is_absolute():
        eval_path = REPO_ROOT / eval_path

    if not eval_path.exists():
        print(f"Error: eval file not found: {eval_path}")
        sys.exit(1)

    # Step 1
    parsed = parse_eval(eval_path)

    # Step 2
    base_cv = load_base_cv()

    # Step 3
    tailored_cv = inject_keywords(base_cv, parsed["keywords"])

    # Step 4
    output_path = save_cv(
        tailored_cv,
        parsed["company"],
        parsed["grade"],
        parsed["interview_angle"],
        eval_path,
    )

    # Step 5 — summary
    rel_path = output_path.relative_to(REPO_ROOT)
    kw_count = min(len(parsed["keywords"]), 8)
    print()
    print(f"[PDF] Tailored CV generated for: {parsed['company']}")
    print(f"[PDF] Grade: {parsed['grade']} | Keywords injected: {kw_count}")
    print(f"[PDF] Saved to: {rel_path}")
    print("[PDF] NOTE: Mock mode — no real PDF rendered. Real PDF via Puppeteer/WeasyPrint later.")
    print()


if __name__ == "__main__":
    main()
