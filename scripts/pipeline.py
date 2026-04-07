"""
ds-radar pipeline — MOCK MODE
Usage: python pipeline.py

Chains scan-queue.txt → evaluate → pdf (B+ only) → tracker.tsv
No API calls, no Playwright. Import logic from evaluate.py and generate_pdf.py.
"""

import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

# Allow sibling imports without package installation
sys.path.insert(0, str(Path(__file__).resolve().parent))

from evaluate import evaluate_url
from generate_pdf import generate_pdf

# ── Paths ─────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
SCAN_QUEUE = REPO_ROOT / "scan-queue.txt"
TRACKER = REPO_ROOT / "tracker.tsv"
STATE_FILE = REPO_ROOT / "scan-queue.state.json"

TRACKER_HEADER = ["date", "company", "role", "url", "grade", "score",
                  "status", "pdf_path", "notes"]

APPLY_GRADES = {"A", "B"}

CANONICAL_STATUSES = {
    "applied", "skipped", "cv_ready", "evaluated",
    "sponsorship_fail", "seniority_fail", "pending", "interviewing",
}

_STATUS_ALIASES: dict[str, str] = {
    "sponsorship_fail": "sponsorship_fail", "sponsor_fail": "sponsorship_fail", "no_sponsor": "sponsorship_fail",
    "seniority_fail": "seniority_fail",     "senior_fail": "seniority_fail",    "too_senior": "seniority_fail",
    "cv_ready": "cv_ready",                 "cv ready": "cv_ready",             "ready": "cv_ready",
    "evaluated": "evaluated",               "eval": "evaluated",                "scored": "evaluated",
    "applied": "applied",                   "sent": "applied",                  "submitted": "applied",
    "skipped": "skipped",                   "skip": "skipped",                  "rejected": "skipped",
    "ignored": "skipped",
}


def normalize_status(status: str) -> str:
    """Map raw/legacy status strings to a canonical value. Falls back to 'skipped'."""
    clean = status.strip().lower()
    canonical = _STATUS_ALIASES.get(clean)
    if canonical is None:
        print(f"[WARN] Unknown status '{status}' — normalizing to 'skipped'")
        return "skipped"
    return canonical


# ── Tracker helpers ───────────────────────────────────────────────────────────

def load_tracked_urls() -> set[str]:
    if not TRACKER.exists():
        return set()
    with TRACKER.open(newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        return {row["url"].strip() for row in reader if row.get("url")}


def append_tracker_row(row: dict) -> None:
    write_header = not TRACKER.exists() or TRACKER.stat().st_size == 0
    with TRACKER.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TRACKER_HEADER, delimiter="\t")
        if write_header:
            writer.writeheader()
        writer.writerow({**row, "status": normalize_status(row.get("status", "skipped"))})


# ── Batch state helpers (compatible with auto_pipeline.py schema) ─────────────

def _load_state() -> dict[str, str]:
    """Return url → status mapping from STATE_FILE (auto_pipeline list-of-dicts schema)."""
    if not STATE_FILE.exists():
        return {}
    raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {item["url"]: item.get("status", "pending") for item in raw.get("items", [])}


def _save_state(url_status: dict[str, str]) -> None:
    """Merge url_status into STATE_FILE preserving all existing fields."""
    raw: dict = {}
    if STATE_FILE.exists():
        raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    items_by_url = {item["url"]: item for item in raw.get("items", [])}
    for url, status in url_status.items():
        if url in items_by_url:
            items_by_url[url]["status"] = status
        else:
            items_by_url[url] = {"url": url, "status": status}
    raw["items"] = list(items_by_url.values())
    raw["updated_at"] = date.today().isoformat()
    STATE_FILE.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    # Step 1 — read queue
    if not SCAN_QUEUE.exists() or SCAN_QUEUE.stat().st_size == 0:
        print("[PIPELINE] scan-queue.txt is empty. Run scan.py first.")
        sys.exit(0)

    urls = [u.strip() for u in SCAN_QUEUE.read_text(encoding="utf-8").splitlines() if u.strip()]
    if not urls:
        print("[PIPELINE] scan-queue.txt is empty. Run scan.py first.")
        sys.exit(0)

    # Parse --parallel N (default 1)
    parallel = 1
    if "--parallel" in sys.argv:
        idx = sys.argv.index("--parallel")
        try:
            parallel = max(1, int(sys.argv[idx + 1]))
        except (IndexError, ValueError):
            print("[PIPELINE] --parallel requires an integer argument")
            sys.exit(1)

    resume = "--resume" in sys.argv
    retry_failed = "--retry-failed" in sys.argv

    # Apply resume filter
    if resume:
        state = _load_state()
        skip_statuses = {"succeeded"}
        if not retry_failed:
            skip_statuses.add("failed")
        skipped = [u for u in urls if state.get(u) in skip_statuses]
        urls = [u for u in urls if state.get(u) not in skip_statuses]
        if skipped:
            print(f"[RESUME] Skipping {len(skipped)} already-succeeded URLs")
        if not urls:
            print("[RESUME] All URLs already processed. Nothing to do.")
            sys.exit(0)

    total = len(urls)
    print(f"\n[PIPELINE] Found {total} URLs to process\n")
    if parallel > 1:
        print(f"[PARALLEL] Running {parallel} workers\n")

    tracked_urls = load_tracked_urls()
    today = date.today().isoformat()

    # Counters
    counts = {"A": 0, "B": 0, "cdf": 0, "pdfs": 0, "already_tracked": 0, "eval_skipped": 0}

    # Step 2 — evaluate URLs (sequential or parallel)
    pending_state: dict[str, str] = {}
    if parallel > 1:
        with ThreadPoolExecutor(max_workers=parallel) as executor:
            results = list(executor.map(evaluate_url, urls))
        for result in results:
            pending_state[result["url"]] = "succeeded" if not result.get("skipped") else "skipped"
        _save_state(pending_state)
    else:
        results = []
        for i, url in enumerate(urls, 1):
            result = evaluate_url(url)
            company = result.get("company", "?")
            if result["skipped"]:
                counts["eval_skipped"] += 1
                print(f"  [{i}/{total}] {company} — already evaluated, skipping")
            else:
                grade = result.get("grade", "?")
                score = result.get("overall_score", "?")
                print(f"  [{i}/{total}] Evaluating {company}... → {grade} ({score}/5.0)")
            pending_state[url] = "succeeded" if not result.get("skipped") else "skipped"
            _save_state(pending_state)
            results.append(result)

    # Step 3 — generate PDFs for B+ grades, Step 4 — update tracker
    print()
    for result in results:
        if result["skipped"]:
            continue

        url = result["url"]
        company = result.get("company", "?")
        grade = result.get("grade", "?")
        score = str(result.get("overall_score", ""))
        title = result.get("title", "")
        eval_path = result.get("eval_path")

        # Tracker dedup
        if url in tracked_urls:
            counts["already_tracked"] += 1
            continue

        pdf_path = ""
        if grade in APPLY_GRADES and eval_path:
            try:
                pdf_path = generate_pdf(eval_path)
                print(f"  → PDF generated: {pdf_path}")
            except Exception as e:
                print(f"  → PDF error for {company}: {e}")

        # Tally grades
        if grade == "A":
            counts["A"] += 1
        elif grade == "B":
            counts["B"] += 1
        else:
            counts["cdf"] += 1

        if pdf_path:
            counts["pdfs"] += 1

        status = "applied" if grade in APPLY_GRADES else "skipped"
        append_tracker_row({
            "date": today,
            "company": company,
            "role": title,
            "url": url,
            "grade": grade,
            "score": score,
            "status": status,
            "pdf_path": pdf_path,
            "notes": "MOCK",
        })
        tracked_urls.add(url)

    # Step 5 — summary
    sep = "─" * 45
    print(f"\n{sep}")
    print("  DS-RADAR PIPELINE COMPLETE — MOCK MODE")
    print(sep)
    print(f"  URLs processed:     {total}")
    print(f"  A grades:           {counts['A']} → applied")
    print(f"  B grades:           {counts['B']} → applied")
    print(f"  C/D/F grades:       {counts['cdf']} → skipped")
    print(f"  CVs generated:      {counts['pdfs']}")
    print(f"  Already in tracker: {counts['already_tracked']} (skipped)")
    print(sep)
    print("  Next: keep profile/profile.yaml up to date with your real CV facts")
    print("        add ANTHROPIC_API_KEY to .env")
    print("        run python pipeline.py for real evaluations")
    print(f"{sep}\n")


if __name__ == "__main__":
    main()
