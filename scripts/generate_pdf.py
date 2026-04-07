"""
ds-radar CV generator
Usage: python generate_pdf.py <eval_path>
Example: python generate_pdf.py evals/deepmind_2026-04-01.md

If the eval contains a real JD ([JD_SOURCE: REAL]), calls Claude Haiku to
rewrite the canonical CV tailored to that job.
If JD is mock, falls back to keyword injection.
Always writes Markdown CV to applications/cv_{company}_{YYYYMMDD}.md and
attempts to render applications/cv_{company}_{YYYYMMDD}.pdf via Playwright.
"""

import html
import os
import re
import sys
from datetime import date
from pathlib import Path

import markdown as md

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


def strip_html_comments(text: str) -> str:
    return re.sub(r"<!--[\s\S]*?-->", "", text).strip()


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


# ── Step 4: Save tailored CV + render PDF ─────────────────────────────────────

def build_output_paths(company: str) -> tuple[Path, Path]:
    today = date.today().strftime("%Y%m%d")
    company_slug = slugify(company)
    stem = f"cv_{company_slug}_{today}"
    APPLICATIONS_DIR.mkdir(parents=True, exist_ok=True)
    return APPLICATIONS_DIR / f"{stem}.md", APPLICATIONS_DIR / f"{stem}.pdf"


def save_cv(
    cv: str,
    output_path: Path,
    company: str,
    grade: str,
    jd_source: str,
    interview_angle: str,
    eval_path: Path,
) -> Path:
    today = date.today().strftime("%Y%m%d")

    header = (
        f"<!-- Tailored for: {company} | Grade: {grade} | JD: {jd_source} | "
        f"Source eval: {eval_path.name} | Generated: {today} -->\n"
        f"<!-- Interview angle: {interview_angle} -->\n\n"
    )
    output_path.write_text(header + cv, encoding="utf-8")
    return output_path


def split_cv_header(cv_markdown: str) -> tuple[str, list[str], str]:
    clean = strip_html_comments(cv_markdown)
    lines = clean.splitlines()
    name = ""
    meta_lines: list[str] = []
    body_start = 0

    for idx, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("# "):
            name = line[2:].strip()
            body_start = idx + 1
            break
        body_start = idx
        break

    idx = body_start
    while idx < len(lines):
        line = lines[idx].strip()
        if not line:
            idx += 1
            continue
        if line in {"---", "***"}:
            idx += 1
            break
        if line.startswith("## "):
            break
        meta_lines.append(line)
        idx += 1

    body = "\n".join(lines[idx:]).strip()
    return name, meta_lines, body


def render_cv_html(cv_markdown: str, company: str, role: str) -> str:
    name, meta_lines, body_markdown = split_cv_header(cv_markdown)
    body_html = md.markdown(
        body_markdown,
        extensions=["extra", "sane_lists"],
        output_format="html5",
    )
    meta_html = "".join(
        f"<p>{md.markdown(line, output_format='html5').removeprefix('<p>').removesuffix('</p>')}</p>"
        for line in meta_lines
    )
    title_name = name or "Curriculum Vitae"
    role_line = html.escape(role)
    company_line = html.escape(company)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title_name)} | CV</title>
  <style>
    @page {{
      size: A4;
      margin: 14mm 12mm 14mm 12mm;
    }}
    :root {{
      color-scheme: light;
      --ink: #111827;
      --muted: #4b5563;
      --rule: #d1d5db;
      --accent: #0f172a;
      --paper: #ffffff;
    }}
    * {{
      box-sizing: border-box;
    }}
    html, body {{
      margin: 0;
      padding: 0;
      background: var(--paper);
      color: var(--ink);
      font-family: "Helvetica Neue", Arial, sans-serif;
      font-size: 10.5pt;
      line-height: 1.42;
      -webkit-font-smoothing: antialiased;
    }}
    body {{
      padding: 0;
    }}
    main {{
      width: 100%;
    }}
    header {{
      border-bottom: 1px solid var(--rule);
      padding-bottom: 10px;
      margin-bottom: 14px;
    }}
    h1 {{
      margin: 0 0 4px;
      font-size: 20pt;
      line-height: 1.1;
      color: var(--accent);
      letter-spacing: -0.02em;
    }}
    .target-role {{
      margin: 0 0 8px;
      font-size: 9.5pt;
      color: var(--muted);
    }}
    .meta p {{
      margin: 0 0 2px;
      font-size: 9.25pt;
      color: var(--muted);
    }}
    h2 {{
      margin: 14px 0 6px;
      font-size: 11pt;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--accent);
      page-break-after: avoid;
    }}
    h3 {{
      margin: 10px 0 4px;
      font-size: 10.5pt;
      color: var(--ink);
      page-break-after: avoid;
    }}
    p {{
      margin: 0 0 7px;
      orphans: 3;
      widows: 3;
    }}
    ul {{
      margin: 0 0 8px 18px;
      padding: 0;
    }}
    li {{
      margin: 0 0 4px;
      page-break-inside: avoid;
    }}
    hr {{
      display: none;
    }}
    strong {{
      color: var(--accent);
    }}
    a {{
      color: inherit;
      text-decoration: none;
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>{html.escape(title_name)}</h1>
      <p class="target-role">Tailored CV for {company_line} | {role_line}</p>
      <div class="meta">{meta_html}</div>
    </header>
    {body_html}
  </main>
</body>
</html>
"""


def render_pdf(html_content: str, output_path: Path) -> Path:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content(html_content, wait_until="load")
            page.emulate_media(media="print")
            page.pdf(
                path=str(output_path),
                format="A4",
                print_background=True,
                prefer_css_page_size=True,
                margin={
                    "top": "14mm",
                    "right": "12mm",
                    "bottom": "14mm",
                    "left": "12mm",
                },
            )
        finally:
            browser.close()

    return output_path


# ── Public API ────────────────────────────────────────────────────────────────

def generate_pdf(eval_path: "Path | str") -> str:
    """
    Generate a tailored CV from an eval report.

    Returns the relative path to the PDF when rendering succeeds, otherwise the
    relative path to the Markdown file.
    """
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

    markdown_path, pdf_path = build_output_paths(parsed["company"])
    save_cv(
        tailored_cv,
        markdown_path,
        parsed["company"],
        parsed["grade"],
        parsed["jd_source"],
        parsed["interview_angle"],
        eval_path,
    )
    print(f"[CV] Markdown saved: {markdown_path.relative_to(REPO_ROOT)}")

    try:
        html_content = render_cv_html(tailored_cv, parsed["company"], parsed["role"])
        render_pdf(html_content, pdf_path)
        print(f"[CV] PDF saved: {pdf_path.relative_to(REPO_ROOT)}")
        return str(pdf_path.relative_to(REPO_ROOT))
    except Exception as exc:
        print(f"[WARN] PDF render failed ({exc}) — Markdown kept at {markdown_path.relative_to(REPO_ROOT)}")
        return str(markdown_path.relative_to(REPO_ROOT))


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

    print(f"[CV] Main artifact: {rel_path}")


if __name__ == "__main__":
    main()
