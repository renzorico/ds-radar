"""
ds-radar scanner
Usage: python scan.py

Reads target companies from profile/target-companies.yaml, discovers live job
listings (Greenhouse: real Playwright scraping; others: mock), deduplicates
against scan-history.tsv, and writes new URLs to scan-queue.txt.
Does NOT modify scan-history.tsv — that is evaluate.py's responsibility.
"""

import csv
import re
import sys
from datetime import datetime
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
ERRORS_LOG = REPO_ROOT / "evals" / "errors.log"

GREENHOUSE_TIMEOUT_MS = 15_000


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


def log_error(company_name: str, url: str, error: str) -> None:
    ERRORS_LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with ERRORS_LOG.open("a") as f:
        f.write(f"[{ts}] SCAN ERROR — {company_name} ({url}): {error}\n")


# ── Greenhouse scraper ────────────────────────────────────────────────────────

def discover_jobs_greenhouse(company: dict) -> list[str]:
    """Scrape live job listings from a Greenhouse board using Playwright."""
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    board_url = company["url"].rstrip("/")
    name = company["name"]

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(board_url, timeout=GREENHOUSE_TIMEOUT_MS)
            page.wait_for_selector('a[href*="/jobs/"]', timeout=GREENHOUSE_TIMEOUT_MS)
            hrefs = [
                a.get_attribute("href")
                for a in page.query_selector_all('a[href*="/jobs/"]')
            ]
            browser.close()
    except PWTimeout:
        msg = f"Timed out after {GREENHOUSE_TIMEOUT_MS // 1000}s"
        log_error(name, board_url, msg)
        print(f"  [WARN] {name}: {msg} — skipping")
        return []
    except Exception as e:
        log_error(name, board_url, str(e))
        print(f"  [WARN] {name}: {e} — skipping")
        return []

    seen: set[str] = set()
    results: list[str] = []
    for href in hrefs:
        if not href or not re.search(r"/jobs/\d+", href):
            continue
        full = href if href.startswith("http") else f"https://boards.greenhouse.io{href}"
        if full not in seen:
            seen.add(full)
            results.append(full)
    return results


# ── Mock fallback (non-Greenhouse ATS) ───────────────────────────────────────

def discover_jobs_mock(company: dict) -> list[str]:
    base = company["url"].rstrip("/")
    name = company["name"].lower().replace(" ", "-")
    return [
        f"{base}/jobs/{name}-data-scientist-001",
        f"{base}/jobs/{name}-senior-analytics-engineer-002",
        f"{base}/jobs/{name}-ml-engineer-003",
    ]


# ── Router ────────────────────────────────────────────────────────────────────

def discover_jobs(company: dict) -> list[str]:
    url = company.get("url", "")
    if "greenhouse.io" in url:
        return discover_jobs_greenhouse(company)
    return discover_jobs_mock(company)


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    companies = load_companies()
    seen_urls = load_seen_urls()

    all_new_urls: list[str] = []
    rows: list[tuple[str, int, int, int]] = []  # (name, found, new, seen)

    print()
    for company in companies:
        print(f"[SCAN] Scanning {company['name']}...", end=" ", flush=True)
        discovered = discover_jobs(company)
        new_urls = [u for u in discovered if u not in seen_urls]
        already_seen = len(discovered) - len(new_urls)
        all_new_urls.extend(new_urls)
        rows.append((company["name"], len(discovered), len(new_urls), already_seen))
        print(f"→ {len(discovered)} found, {len(new_urls)} new, {already_seen} already seen")

    print(f"\n[SCAN] Total: {len(all_new_urls)} new URLs queued")

    # Write scan-queue.txt (overwrite each run)
    SCAN_QUEUE.write_text(
        "\n".join(all_new_urls) + ("\n" if all_new_urls else ""),
        encoding="utf-8",
    )

    if all_new_urls:
        print()
        print("Run: python evaluate.py <url>  OR  python pipeline.py to process all")
    print()


if __name__ == "__main__":
    main()
