"""
Convert a raw LinkedIn scrape CSV into the compact ds-radar import format.

Usage:
  python scripts/import_linkedin_raw.py \
    --in ../linkedin/jobs_linkedin_scraped.csv \
    --out ../linkedin/visa_jobs_results.csv
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_IN = REPO_ROOT.parent / "linkedin" / "jobs_linkedin_scraped.csv"
DEFAULT_OUT = REPO_ROOT.parent / "linkedin" / "visa_jobs_results.csv"
OUTPUT_HEADER = [
    "search_title",
    "job_title",
    "relevance_score",
    "company",
    "location",
    "posted",
    "url",
    "licensed_sponsor",
    "sponsorship_signal",
    "sponsorship_evidence",
    "hiring_contact_name",
    "hiring_contact_title",
]


def clean(value: str) -> str:
    return str(value or "").strip()


def convert_rows(input_path: Path) -> tuple[list[dict], Counter, int]:
    rows_out: list[dict] = []
    skipped = Counter()
    total = 0

    with input_path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            total += 1
            title = clean(raw.get("Title"))
            company = clean(raw.get("Company Name"))
            url = clean(raw.get("Detail URL"))

            if not url:
                skipped["missing url"] += 1
                continue
            if not title:
                skipped["missing title"] += 1
                continue
            if not company:
                skipped["missing company"] += 1
                continue

            rows_out.append(
                {
                    "search_title": "linkedin_raw_scrape",
                    "job_title": title,
                    "relevance_score": 1.0,
                    "company": company,
                    "location": clean(raw.get("Location")),
                    "posted": clean(raw.get("Scraped At", "").strip()),
                    "url": url,
                    "licensed_sponsor": "",
                    "sponsorship_signal": "",
                    "sponsorship_evidence": "",
                    "hiring_contact_name": "",
                    "hiring_contact_title": "",
                }
            )

    return rows_out, skipped, total


def write_rows(output_path: Path, rows: list[dict]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_HEADER)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(total: int, written: int, skipped: Counter, dry_run: bool) -> None:
    print(
        f"[IMPORT_LINKEDIN_RAW] total_raw={total} "
        f"rows_written={written} rows_skipped={sum(skipped.values())} dry_run={dry_run}"
    )
    for reason, count in sorted(skipped.items()):
        print(f"  - {reason}: {count}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert raw LinkedIn scrape CSV to import_linkedin.py format")
    parser.add_argument("--in", dest="input_path", type=Path, default=DEFAULT_IN, metavar="PATH",
                        help=f"Raw LinkedIn scrape CSV (default: {DEFAULT_IN})")
    parser.add_argument("--out", dest="output_path", type=Path, default=DEFAULT_OUT, metavar="PATH",
                        help=f"Output CSV path (default: {DEFAULT_OUT})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be written without creating or overwriting the output file")
    args = parser.parse_args()

    if not args.input_path.exists():
        raise SystemExit(f"[ERROR] Input CSV not found: {args.input_path}")

    rows, skipped, total = convert_rows(args.input_path)
    if not args.dry_run:
        write_rows(args.output_path, rows)
    print_summary(total, len(rows), skipped, args.dry_run)


if __name__ == "__main__":
    main()
