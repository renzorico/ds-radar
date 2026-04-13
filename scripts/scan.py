"""
ds-radar scanner
Usage: python scan.py

Discovers job URLs from two sources:
  1. ATS boards defined in profile/target-companies.yaml
  2. LinkedIn CSV files dropped into csv-inbox/  (Detail URL column)

Deduplicates against scan-history.tsv + tracker.tsv, liveness-checks ATS URLs,
and writes new URLs to scan-queue.txt.
Processed CSVs are moved to csv-inbox/processed/ so they are never re-imported.
"""

import csv
import re
import shutil
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
TRACKER = REPO_ROOT / "tracker.tsv"
SCAN_QUEUE = REPO_ROOT / "scan-queue.txt"
ERRORS_LOG = REPO_ROOT / "evals" / "errors.log"
CSV_INBOX = REPO_ROOT / "csv-inbox"
CSV_PROCESSED = CSV_INBOX / "processed"

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
    """Return all URLs already in scan-history or tracker (both sources)."""
    seen: set[str] = set()
    for path in (SCAN_HISTORY, TRACKER):
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                if row.get("url"):
                    seen.add(row["url"].strip())
    return seen


# ── LinkedIn CSV inbox ────────────────────────────────────────────────────────

def ingest_csv_inbox(seen_urls: set[str]) -> list[str]:
    """Read all LinkedIn CSVs from csv-inbox/, return new URLs, archive processed files."""
    CSV_INBOX.mkdir(exist_ok=True)
    CSV_PROCESSED.mkdir(exist_ok=True)

    csv_files = sorted(CSV_INBOX.glob("*.csv"))
    if not csv_files:
        return []

    new_urls: list[str] = []
    for csv_path in csv_files:
        try:
            with csv_path.open(newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                if "Detail URL" not in (reader.fieldnames or []):
                    print(f"  [CSV] {csv_path.name}: no 'Detail URL' column — skipping")
                    continue
                urls = [row["Detail URL"].strip() for row in reader if row.get("Detail URL", "").strip()]
            fresh = [u for u in urls if u not in seen_urls]
            new_urls.extend(fresh)
            seen_urls.update(fresh)  # prevent cross-file duplication
            dest = CSV_PROCESSED / csv_path.name
            shutil.move(str(csv_path), str(dest))
            print(f"  [CSV] {csv_path.name}: {len(urls)} rows, {len(fresh)} new → archived")
        except Exception as exc:
            print(f"  [CSV] {csv_path.name}: error reading — {exc}")

    return new_urls


def log_error(company_name: str, url: str, error: str) -> None:
    ERRORS_LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with ERRORS_LOG.open("a") as f:
        f.write(f"[{ts}] SCAN ERROR — {company_name} ({url}): {error}\n")


def check_liveness(url: str) -> "str | None":
    """GET the URL; return None if live, or a short failure reason string.

    'Live' means: HTTP status < 400 and the first 600 bytes decode to at least
    300 characters (a minimal signal that a real page was served, not an error
    page or empty response).
    """
    import urllib.request as _ureq
    try:
        req = _ureq.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with _ureq.urlopen(req, timeout=6) as resp:
            if resp.status >= 400:
                return f"http status {resp.status}"
            chunk = resp.read(600).decode("utf-8", errors="ignore")
            if len(chunk) < 300:
                return "body too short"
            return None
    except Exception as exc:
        return f"request exception: {exc}"


# ── Greenhouse scraper ────────────────────────────────────────────────────────

def _infer_greenhouse_token(url: str) -> "str | None":
    """Extract the board token from a Greenhouse URL, e.g. 'monzo' from boards.greenhouse.io/monzo."""
    m = re.search(r"greenhouse\.io/([^/?#]+)", url)
    return m.group(1).rstrip("/") if m else None


def discover_jobs_greenhouse_api(company: dict) -> "list[str] | None":
    """Fetch job listings via the Greenhouse JSON API.

    Returns a list of job URLs on success, or None if the token is unavailable
    or the request fails.
    """
    import urllib.request as _ureq
    import json as _json

    token = company.get("greenhouse_token") or _infer_greenhouse_token(company.get("url", ""))
    if not token:
        return None

    api_url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
    try:
        req = _ureq.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
        with _ureq.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
        jobs = data.get("jobs", [])
        urls: list[str] = []
        seen: set[str] = set()
        for job in jobs:
            url = job.get("absolute_url") or ""
            if url and re.search(r"/jobs/\d+", url) and url not in seen:
                seen.add(url)
                urls.append(url)
        return urls
    except Exception:
        return None


def discover_jobs_greenhouse(company: dict) -> list[str]:
    """Scrape live job listings from a Greenhouse board.

    Tries the Greenhouse JSON API first; falls back to Playwright scraping.
    """
    name = company["name"]

    api_results = discover_jobs_greenhouse_api(company)
    if api_results:
        print(f"  [API] {name}: {len(api_results)} jobs via Greenhouse API")
        return api_results
    if api_results is not None:
        print(f"  [API] {name}: API returned empty — falling back to scraper")
    # else: None means token missing or request failed — go straight to scraper

    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    board_url = company["url"].rstrip("/")

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
    seen_urls = load_seen_urls()

    # ── Source 1: LinkedIn CSV inbox ─────────────────────────────────────────
    print()
    print("[SCAN] CSV inbox")
    csv_urls = ingest_csv_inbox(seen_urls)
    print(f"       {len(csv_urls)} new LinkedIn URLs from CSVs")

    # ── Source 2: ATS boards ──────────────────────────────────────────────────
    print()
    print("[SCAN] ATS boards")
    companies = load_companies()
    ats_urls: list[str] = []
    for company in companies:
        print(f"  {company['name']}...", end=" ", flush=True)
        discovered = discover_jobs(company)
        new = [u for u in discovered if u not in seen_urls]
        seen_urls.update(new)
        ats_urls.extend(new)
        print(f"→ {len(discovered)} found, {len(new)} new, {len(discovered)-len(new)} seen")
    print(f"       {len(ats_urls)} new ATS URLs")

    # ── Liveness check (ATS only; LinkedIn URLs are live by definition) ───────
    all_candidate_urls = csv_urls + ats_urls
    print(f"\n[SCAN] {len(all_candidate_urls)} total new URLs — liveness check on ATS ({len(ats_urls)})")

    live_urls: list[str] = list(csv_urls)  # LinkedIn URLs bypass liveness
    for url in ats_urls:
        if "mock" in url or "example.com" in url:
            live_urls.append(url)
            continue
        reason = check_liveness(url)
        if reason is None:
            live_urls.append(url)
        else:
            log_error("liveness", url, reason)

    print(f"[LIVENESS] {len(ats_urls) - (len(live_urls) - len(csv_urls))}/{len(ats_urls)} ATS URLs failed liveness")

    # ── Write scan-queue.txt (overwrite each run) ─────────────────────────────
    SCAN_QUEUE.write_text(
        "\n".join(live_urls) + ("\n" if live_urls else ""),
        encoding="utf-8",
    )

    sep = "─" * 45
    print(f"\n{sep}")
    print(f"  LinkedIn CSV:    {len(csv_urls)}")
    print(f"  ATS boards:      {len(ats_urls)}")
    print(f"  Queue total:     {len(live_urls)}")
    print(sep)
    if live_urls:
        print("  Next: python scripts/pipeline.py --parallel 3")
    print(f"{sep}\n")


if __name__ == "__main__":
    main()
