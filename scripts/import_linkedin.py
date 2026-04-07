"""
ds-radar LinkedIn importer
Usage: python scripts/import_linkedin.py [options]

Reads a LinkedIn jobs CSV, filters by relevance and recency,
deduplicates against scan-history.tsv, and feeds new URLs into scan-queue.txt.
Also appends to source-history.tsv for provenance tracking.

Options:
  --csv PATH            Path to LinkedIn CSV (default: ../linkedin/visa_jobs_results.csv)
  --min-score FLOAT     Minimum relevance_score to import (default: 0.6)
  --max-age-days INT    Maximum job age in days (default: 45)
  --dry-run             Print what would happen without writing any files
"""

import argparse
import csv
import sys
from datetime import date, timedelta
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
SCAN_HISTORY = REPO_ROOT / "scan-history.tsv"
SCAN_QUEUE   = REPO_ROOT / "scan-queue.txt"
SOURCE_HIST  = REPO_ROOT / "source-history.tsv"

DEFAULT_CSV = REPO_ROOT.parent / "linkedin" / "visa_jobs_results.csv"

SOURCE_HISTORY_HEADER = [
    "source", "discovered_at", "search_title", "job_title",
    "company", "location", "posted", "relevance_score",
    "licensed_sponsor", "sponsorship_signal", "sponsorship_evidence",
    "source_url", "target_url",
]


# ── TSV helpers ───────────────────────────────────────────────────────────────

def load_seen_urls() -> set[str]:
    """Return all URLs already in scan-history.tsv."""
    if not SCAN_HISTORY.exists():
        return set()
    with SCAN_HISTORY.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        return {row["url"].strip() for row in reader if row.get("url")}


def load_queued_urls() -> set[str]:
    """Return URLs already in scan-queue.txt (avoid double-add within same run)."""
    if not SCAN_QUEUE.exists():
        return set()
    return {u.strip() for u in SCAN_QUEUE.read_text(encoding="utf-8").splitlines() if u.strip()}


def append_to_queue(urls: list[str], dry_run: bool) -> None:
    if dry_run or not urls:
        return
    with SCAN_QUEUE.open("a", encoding="utf-8") as f:
        for url in urls:
            f.write(url + "\n")


def append_to_source_history(rows: list[dict], dry_run: bool) -> None:
    if dry_run or not rows:
        return
    write_header = not SOURCE_HIST.exists() or SOURCE_HIST.stat().st_size == 0
    with SOURCE_HIST.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SOURCE_HISTORY_HEADER, delimiter="\t")
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


# ── CSV parser ────────────────────────────────────────────────────────────────

def parse_bool(value: str) -> bool:
    return str(value).strip().lower() in ("true", "yes", "1")


def parse_csv(csv_path: Path) -> list[dict]:
    if not csv_path.exists():
        print(f"[ERROR] CSV not found: {csv_path}")
        sys.exit(1)
    records = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                score = float(row.get("relevance_score") or 0)
            except ValueError:
                score = 0.0
            try:
                posted = date.fromisoformat(row.get("posted", "").strip())
            except ValueError:
                posted = None
            records.append({
                "source": "linkedin",
                "search_title":         row.get("search_title", "").strip(),
                "job_title":            row.get("job_title", "").strip(),
                "relevance_score":      score,
                "company":              row.get("company", "").strip(),
                "location":             row.get("location", "").strip(),
                "posted":               posted,
                "source_url":           row.get("url", "").strip(),
                "target_url":           row.get("url", "").strip(),
                "licensed_sponsor":     parse_bool(row.get("licensed_sponsor", "")),
                "sponsorship_signal":   row.get("sponsorship_signal", "").strip(),
                "sponsorship_evidence": row.get("sponsorship_evidence", "").strip(),
            })
    return records


# ── Importable entry point ────────────────────────────────────────────────────

def run_import(
    csv_path: "Path | None" = None,
    min_score: float = 0.6,
    max_age_days: int = 45,
    dry_run: bool = False,
) -> tuple[dict, list[str]]:
    """Run the LinkedIn import. Returns (stats_dict, queued_urls_list).

    Suitable for calling from auto_pipeline without subprocess.
    """
    csv_path = csv_path or DEFAULT_CSV
    records = parse_csv(csv_path)
    seen_urls = load_seen_urls()
    queued_urls = load_queued_urls()
    cutoff = date.today() - timedelta(days=max_age_days)
    today_str = date.today().isoformat()

    skipped_score = skipped_age = skipped_history = 0
    to_queue: list[str] = []
    to_history: list[dict] = []

    for rec in records:
        if rec["relevance_score"] < min_score:
            skipped_score += 1
            continue
        if False and (rec["posted"] is None or rec["posted"] < cutoff):
            skipped_age += 1
            continue
        url = rec["target_url"]
        if not url or url in seen_urls or url in queued_urls:
            skipped_history += 1
            continue
        queued_urls.add(url)
        to_queue.append(url)
        to_history.append({
            "source":               rec["source"],
            "discovered_at":        today_str,
            "search_title":         rec["search_title"],
            "job_title":            rec["job_title"],
            "company":              rec["company"],
            "location":             rec["location"],
            "posted":               rec["posted"].isoformat() if rec["posted"] else "",
            "relevance_score":      rec["relevance_score"],
            "licensed_sponsor":     rec["licensed_sponsor"],
            "sponsorship_signal":   rec["sponsorship_signal"],
            "sponsorship_evidence": rec["sponsorship_evidence"],
            "source_url":           rec["source_url"],
            "target_url":           rec["target_url"],
        })

    append_to_queue(to_queue, dry_run)
    append_to_source_history(to_history, dry_run)

    stats = {
        "total": len(records), "kept": len(to_queue),
        "skipped_score": skipped_score,
        "skipped_age": skipped_age,
        "skipped_history": skipped_history,
    }
    return stats, to_queue


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Import LinkedIn jobs into ds-radar queue")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, metavar="PATH",
                        help=f"LinkedIn CSV (default: {DEFAULT_CSV})")
    parser.add_argument("--min-score", type=float, default=0.6, metavar="FLOAT",
                        help="Minimum relevance_score (default: 0.6)")
    parser.add_argument("--max-age-days", type=int, default=45, metavar="INT",
                        help="Max job age in days (default: 45)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would happen without writing files")
    args = parser.parse_args()

    if args.dry_run:
        print("[DRY RUN] No files will be modified.")

    stats, to_queue = run_import(
        csv_path=args.csv,
        min_score=args.min_score,
        max_age_days=args.max_age_days,
        dry_run=args.dry_run,
    )
    total, queued = stats["total"], stats["kept"]
    print(
        f"[IMPORT_LINKEDIN] rows={total} kept={queued} "
        f"skipped_score={stats['skipped_score']} skipped_age={stats['skipped_age']} "
        f"skipped_history={stats['skipped_history']} queued={queued}"
    )

    if args.dry_run and to_queue:
        print("\nWould queue:")
        for url in to_queue[:5]:
            print(f"  {url}")
        if len(to_queue) > 5:
            print(f"  ... and {len(to_queue) - 5} more")


if __name__ == "__main__":
    main()
