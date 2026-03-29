# TODO: replace mock_discover_jobs() with real Playwright scraping
"""
ds-radar scanner — MOCK MODE
Usage: python scan.py

Reads target companies from profile/target-companies.yaml, generates mock job
URLs, deduplicates against scan-history.tsv, and writes new URLs to scan-queue.txt.
Does NOT modify scan-history.tsv — that is evaluate.py's responsibility.
"""

import csv
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Error: PyYAML not installed. Run: pip install pyyaml")
    sys.exit(1)

# ── Paths ────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET_COMPANIES = REPO_ROOT / "profile" / "target-companies.yaml"
SCAN_HISTORY = REPO_ROOT / "scan-history.tsv"
SCAN_QUEUE = REPO_ROOT / "scan-queue.txt"


# ── Helpers ──────────────────────────────────────────────────────────────────

def load_companies() -> list[dict]:
    if not TARGET_COMPANIES.exists():
        print(f"Error: {TARGET_COMPANIES} not found.")
        sys.exit(1)
    with TARGET_COMPANIES.open() as f:
        data = yaml.safe_load(f)
    companies = data.get("companies", [])
    if not companies:
        print("Error: No companies defined in target-companies.yaml.")
        sys.exit(1)
    return companies


def load_seen_urls() -> set[str]:
    if not SCAN_HISTORY.exists():
        return set()
    with SCAN_HISTORY.open(newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        return {row["url"].strip() for row in reader if row.get("url")}


# ── Mock discovery ────────────────────────────────────────────────────────────

def mock_discover_jobs(company: dict) -> list[str]:
    base = company["url"].rstrip("/")
    name = company["name"].lower().replace(" ", "-")
    return [
        f"{base}/jobs/{name}-data-scientist-001",
        f"{base}/jobs/{name}-senior-analytics-engineer-002",
        f"{base}/jobs/{name}-ml-engineer-003",
    ]


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    companies = load_companies()
    seen_urls = load_seen_urls()

    all_new_urls: list[str] = []
    rows: list[tuple[str, int, int, int]] = []  # (name, found, new, seen)

    for company in companies:
        discovered = mock_discover_jobs(company)
        new_urls = [u for u in discovered if u not in seen_urls]
        already_seen = len(discovered) - len(new_urls)

        all_new_urls.extend(new_urls)
        rows.append((company["name"], len(discovered), len(new_urls), already_seen))

    # Print summary table
    print()
    name_width = max(len(r[0]) for r in rows) + 2
    for name, found, new, seen in rows:
        print(
            f"[SCAN] {name:<{name_width}}"
            f"→ {found} found, {new} new, {seen} already seen"
        )

    print(f"\n[SCAN] Total: {len(all_new_urls)} new URLs queued")

    # Write scan-queue.txt (overwrite each run)
    SCAN_QUEUE.write_text("\n".join(all_new_urls) + ("\n" if all_new_urls else ""), encoding="utf-8")

    # Next step hint
    if all_new_urls:
        print()
        print("Run: python evaluate.py <url>  OR  python pipeline.py to process all")
    print()


if __name__ == "__main__":
    main()
