"""
ds-radar pipeline — MOCK MODE
Usage: python pipeline.py

Chains scan-queue.txt → evaluate → pdf (B+ only) → tracker.tsv
No API calls, no Playwright. Import logic from evaluate.py and generate_pdf.py.
"""

import csv
import sys
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

TRACKER_HEADER = ["date", "company", "role", "url", "grade", "score",
                  "status", "pdf_path", "notes"]

APPLY_GRADES = {"A", "B"}


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
        writer.writerow(row)


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

    total = len(urls)
    print(f"\n[PIPELINE] Found {total} URLs to process\n")

    tracked_urls = load_tracked_urls()
    today = date.today().isoformat()

    # Counters
    counts = {"A": 0, "B": 0, "cdf": 0, "pdfs": 0, "already_tracked": 0, "eval_skipped": 0}
    results = []

    # Step 2 — evaluate each URL
    for i, url in enumerate(urls, 1):
        result = evaluate_url(url)
        company = result.get("company", "?")

        if result["skipped"]:
            # Already in scan-history — still check tracker
            counts["eval_skipped"] += 1
            print(f"  [{i}/{total}] {company} — already evaluated, skipping")
            results.append(result)
            continue

        grade = result.get("grade", "?")
        score = result.get("overall_score", "?")
        print(f"  [{i}/{total}] Evaluating {company}... → {grade} ({score}/5.0)")
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
    print("  Next: fill profile/cv.md with your real CV")
    print("        add ANTHROPIC_API_KEY to .env")
    print("        run python pipeline.py for real evaluations")
    print(f"{sep}\n")


if __name__ == "__main__":
    main()
