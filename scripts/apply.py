"""
ds-radar ATS form-filler — REAL MODE
Usage: python apply.py <job_url> [--dry-run]

Opens the ATS form in a real browser (headful), detects fields by label text,
fills them from profile.yaml + a Claude-generated cover answer, pauses for
human review, then submits and records status=applied in tracker.tsv.

Supports: Greenhouse, Workable, Ashby, Lever (same targets as evaluate.py)
"""

import argparse
import csv
import re
import sys
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate import (
    _client, MODEL,
    read_scan_history, url_already_evaluated,
    evaluate_url,
    REPO_ROOT, EVALS_DIR,
)

# ── Paths ─────────────────────────────────────────────────────────────────────

APPLICATIONS_DIR = REPO_ROOT / "applications"
TRACKER          = REPO_ROOT / "tracker.tsv"
PROFILE_PATH     = REPO_ROOT / "profile" / "profile.yaml"

TRACKER_HEADER = ["date", "company", "role", "url", "grade", "score",
                  "status", "pdf_path", "notes"]

# ── Field detection map ───────────────────────────────────────────────────────

FIELD_MAP = [
    (r"first\s*name",                                            "first_name"),
    (r"last\s*name|surname|family\s*name",                       "last_name"),
    (r"^(full\s*)?name$",                                        "full_name"),
    (r"email",                                                   "email"),
    (r"phone|mobile|telephone",                                  "phone"),
    (r"linkedin",                                                "linkedin_url"),
    (r"location|city|where\s*are\s*you\s*based",                 "location"),
    (r"cover\s*letter|why\s*(this\s*)?(role|position|company)|"
     r"motivation|tell\s*us\s*about\s*yourself",                 "cover"),
    (r"\bcv\b|resum[eé]",                                        "cv_upload"),
]


# ── Profile loader ────────────────────────────────────────────────────────────

def load_profile() -> dict:
    data = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    contact  = data.get("contact", {})
    identity = data.get("identity", {})

    missing = [k for k in ("email", "phone", "linkedin_url") if not contact.get(k)]
    if missing:
        print(f"[WARN] profile.yaml missing contact fields: {missing} — those fields will be blank")

    return {
        "name":         identity.get("name", ""),
        "location":     identity.get("location", ""),
        "email":        contact.get("email", ""),
        "phone":        contact.get("phone", ""),
        "linkedin_url": contact.get("linkedin_url", ""),
    }


# ── Eval helpers ──────────────────────────────────────────────────────────────

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


def get_eval_rich(url: str) -> dict:
    history = read_scan_history()
    row = url_already_evaluated(url, history)
    if row:
        p = REPO_ROOT / row["eval_path"]
        if p.exists():
            print(f"[APPLY] Using existing eval: {p.name}")
            return _parse_eval_rich(p)

    print("[APPLY] No existing eval — running evaluate_url() ...")
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

    return {
        "title": result.get("title", "Unknown"),
        "company": result.get("company", "Unknown"),
        "grade": result.get("grade", "?"),
        "overall_score": result.get("overall_score", 0.0),
        "dim_scores": {},
        "jd_source": "MOCK",
        "jd_text": "",
    }


# ── CV + oferta helpers ───────────────────────────────────────────────────────

def find_tailored_cv(company: str) -> "Path | None":
    slug = re.sub(r"[^\w-]", "", re.sub(r"[\s_]+", "-", company.lower().strip()))
    pdf_candidates = sorted(APPLICATIONS_DIR.glob(f"cv_{slug}_*.pdf"), reverse=True)
    if pdf_candidates:
        print(f"[APPLY] CV: {pdf_candidates[0].name}")
        return pdf_candidates[0]
    md_candidates = sorted(APPLICATIONS_DIR.glob(f"cv_{slug}_*.md"), reverse=True)
    if md_candidates:
        print(f"[APPLY] CV: {md_candidates[0].name} (Markdown fallback)")
        return md_candidates[0]
    print("[WARN] No tailored CV found — upload field will be skipped")
    return None


def resolve_explicit_cv_path(path_text: str) -> "Path | None":
    if not path_text:
        return None
    candidate = Path(path_text)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    candidate = candidate.resolve()
    if not candidate.exists():
        print(f"[ERROR] Explicit CV path does not exist: {path_text}")
        sys.exit(1)
    return candidate


def find_oferta_hooks(company: str) -> str:
    slug = re.sub(r"[^\w-]", "", re.sub(r"[\s_]+", "-", company.lower().strip()))
    candidates = sorted(EVALS_DIR.glob(f"deep_{slug}_*.md"), reverse=True)
    if not candidates:
        return ""
    text = candidates[0].read_text(encoding="utf-8")
    m = re.search(r"##\s+5\. Personalisation Hooks\s*\n([\s\S]+?)(?=\n##|\Z)", text)
    return m.group(1).strip() if m else ""


# ── Cover answer generator ────────────────────────────────────────────────────

_COVER_PROMPT = """\
Write a 3-4 sentence "Why this role?" answer for a job application.
Candidate: Renzo Rico, Data Scientist, London UK.
Role: {title} at {company} (Grade {grade}, {overall_score}/5.0)
JD excerpt: {jd_excerpt}
{hooks_block}
Output plain prose only. No bullet points, no headers."""

_COVER_TEMPLATE = (
    "I'm excited about this {title} role at {company} because it aligns with my "
    "background in Python, ML, and stakeholder-facing data science. I've recently "
    "been building agentic AI tools and would bring both technical depth and "
    "communication skills to the team."
)


def generate_cover_answer(eval_data: dict, oferta_hooks: str) -> str:
    hooks_block = f"Personalisation hooks:\n{oferta_hooks}\n" if oferta_hooks else ""
    prompt = _COVER_PROMPT.format(
        title=eval_data["title"],
        company=eval_data["company"],
        grade=eval_data["grade"],
        overall_score=eval_data["overall_score"],
        jd_excerpt=eval_data["jd_text"][:600],
        hooks_block=hooks_block,
    )
    try:
        response = _client.messages.create(
            model=MODEL,
            max_tokens=200,
            system="You are a job application assistant. Output concise plain prose only.",
            messages=[{"role": "user", "content": prompt}],
        )
        usage = response.usage
        cost = (usage.input_tokens * 0.25 + usage.output_tokens * 1.25) / 1_000_000
        print(f"[COST] cover ~${cost:.5f} | {usage.input_tokens} in / {usage.output_tokens} out")
        return response.content[0].text.strip()
    except Exception as exc:
        print(f"[WARN] Claude cover generation failed ({exc}) — using template")
        return _COVER_TEMPLATE.format(
            title=eval_data["title"], company=eval_data["company"]
        )


# ── Field detection ───────────────────────────────────────────────────────────

def detect_fields(page) -> list[dict]:
    """Return list of {field_key, locator, input_type} for matched label→input pairs."""
    from playwright.sync_api import Locator

    fields = []
    seen_keys: set[str] = set()

    labels = page.locator("label").all()
    for label in labels:
        try:
            label_text = label.inner_text().strip().lower()
        except Exception:
            continue

        matched_key = None
        for pattern, key in FIELD_MAP:
            if re.search(pattern, label_text, re.IGNORECASE):
                matched_key = key
                break

        if not matched_key or matched_key in seen_keys:
            continue

        # Resolve associated input: try for= attribute first, then child element
        input_locator = None
        try:
            for_attr = label.get_attribute("for")
            if for_attr:
                candidate = page.locator(f"#{for_attr}, [name='{for_attr}']").first
                if candidate.count() > 0:
                    input_locator = candidate
        except Exception:
            pass

        if input_locator is None:
            try:
                child = label.locator("input, textarea, select").first
                if child.count() > 0:
                    input_locator = child
            except Exception:
                pass

        if input_locator is None:
            continue

        # Determine input type
        try:
            tag = input_locator.evaluate("el => el.tagName.toLowerCase()")
            attr_type = input_locator.get_attribute("type") or ""
        except Exception:
            continue

        if attr_type == "file" or matched_key == "cv_upload":
            input_type = "file"
        elif tag == "textarea" or matched_key == "cover":
            input_type = "textarea"
        else:
            input_type = "text"

        fields.append({
            "field_key":  matched_key,
            "locator":    input_locator,
            "input_type": input_type,
        })
        seen_keys.add(matched_key)

    return fields


# ── Form filler ───────────────────────────────────────────────────────────────

def fill_fields(
    fields: list[dict], profile: dict, cover: str, cv_path: "Path | None", dry_run: bool
) -> int:
    name_parts = profile["name"].split()
    values = {
        "first_name":   name_parts[0] if name_parts else "",
        "last_name":    " ".join(name_parts[1:]) if len(name_parts) > 1 else "",
        "full_name":    profile["name"],
        "email":        profile["email"],
        "phone":        profile["phone"],
        "linkedin_url": profile["linkedin_url"],
        "location":     profile["location"],
        "cover":        cover,
    }

    filled = 0
    prefix = "[DRY]" if dry_run else "[FILL]"

    for field in fields:
        key = field["field_key"]
        locator = field["locator"]
        itype = field["input_type"]

        if itype == "file":
            if not cv_path or cv_path.suffix.lower() != ".pdf":
                print(f"[WARN] {key}: no PDF available — skipping upload field")
                continue
            print(f'{prefix} {key} → "{cv_path.name}"')
            if not dry_run:
                try:
                    locator.set_input_files(str(cv_path))
                    filled += 1
                except Exception as exc:
                    print(f"[WARN] {key}: upload failed ({exc})")
            else:
                filled += 1
            continue

        value = values.get(key, "")
        if not value:
            print(f"[WARN] {key}: no value in profile — skipping")
            continue

        display = value[:80].replace("\n", " ")
        print(f'{prefix} {key} → "{display}{"..." if len(value) > 80 else ""}"')

        if not dry_run:
            try:
                locator.scroll_into_view_if_needed()
                locator.fill(value)
                filled += 1
            except Exception as exc:
                print(f"[WARN] {key}: fill failed ({exc})")
        else:
            filled += 1

    return filled


# ── Tracker update ────────────────────────────────────────────────────────────

def update_tracker(
    url: str, eval_data: dict, cv_path: "Path | None", dry_run: bool
) -> None:
    if dry_run:
        return

    today = date.today().isoformat()
    cv_rel = str(cv_path.relative_to(REPO_ROOT)) if cv_path else ""

    rows: list[dict] = []
    found = False

    if TRACKER.exists():
        with TRACKER.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                if row.get("url", "").strip() == url:
                    row["status"]   = "applied"
                    row["pdf_path"] = cv_rel
                    row["date"]     = today
                    found = True
                rows.append(row)

    if not found:
        rows.append({
            "date":     today,
            "company":  eval_data["company"],
            "role":     eval_data["title"],
            "url":      url,
            "grade":    eval_data["grade"],
            "score":    eval_data["overall_score"],
            "status":   "applied",
            "pdf_path": cv_rel,
            "notes":    "",
        })

    write_header = not TRACKER.exists() or TRACKER.stat().st_size == 0
    with TRACKER.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TRACKER_HEADER, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    action = "updated" if found else "added"
    print(f"[APPLY] tracker.tsv {action}: {eval_data['company']} → applied")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="ATS form-filler for ds-radar")
    parser.add_argument("url", help="ATS job application URL")
    parser.add_argument("--dry-run", action="store_true",
                        help="Detect and show field mapping without filling or submitting")
    parser.add_argument("--cv-path", default="", help="Explicit CV artifact path from dashboard preflight")
    parser.add_argument("--job-key", default="", help="Optional job identity key for debug logging")
    args = parser.parse_args()

    url = args.url.strip()

    if args.dry_run:
        print("[DRY RUN] No fields will be filled or submitted.\n")

    # ── Prep ──────────────────────────────────────────────────────────────────
    profile    = load_profile()
    eval_data  = get_eval_rich(url)
    company    = eval_data["company"]
    cv_path    = resolve_explicit_cv_path(args.cv_path) or find_tailored_cv(company)
    hooks      = find_oferta_hooks(company)

    if args.job_key:
        print(f"[APPLY] job_key={args.job_key}")

    if eval_data["jd_source"] == "REAL" and eval_data["jd_text"]:
        cover = generate_cover_answer(eval_data, hooks)
    else:
        cover = _COVER_TEMPLATE.format(
            title=eval_data["title"], company=company
        )
        if eval_data["jd_source"] != "REAL":
            print("[WARN] jd_source=MOCK — cover answer is template (not Claude)")

    # ── Browser ───────────────────────────────────────────────────────────────
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        page = browser.new_page()

        print(f"\n[APPLY] Opening: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(2000)  # let dynamic JS render

        fields = detect_fields(page)
        print(f"[APPLY] Detected {len(fields)} fields: "
              f"{[f['field_key'] for f in fields]}\n")

        filled = fill_fields(fields, profile, cover, cv_path, args.dry_run)

        if not args.dry_run:
            try:
                input(
                    "\n[APPLY] Review the form in the browser. "
                    "Press Enter to submit (Ctrl+C to abort): "
                )
                submit = page.locator(
                    "button[type=submit], input[type=submit]"
                ).first
                submit.click()
                print("[APPLY] Form submitted.")
                page.wait_for_timeout(3000)
            except KeyboardInterrupt:
                print("\n[APPLY] Aborted by user — form not submitted.")
                browser.close()
                return
        else:
            print("\n[DRY RUN] Would submit — skipping.")

        browser.close()

    # ── Record ────────────────────────────────────────────────────────────────
    update_tracker(url, eval_data, cv_path, args.dry_run)

    print()
    print(
        f"APPLY company={company} grade={eval_data['grade']} "
        f"fields_detected={len(fields)} fields_filled={filled} "
        f"dry_run={args.dry_run}"
    )


if __name__ == "__main__":
    main()
