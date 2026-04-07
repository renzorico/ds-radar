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

    print(f"\n[SCAN] Total: {len(all_new_urls)} new URLs before liveness check")

    live_urls: list[str] = []
    for url in all_new_urls:
        if "mock" in url or "example.com" in url:
            live_urls.append(url)
            continue
        reason = check_liveness(url)
        if reason is None:
            live_urls.append(url)
        else:
            log_error("liveness", url, reason)

    print(f"[LIVENESS] {len(live_urls)}/{len(all_new_urls)} URLs passed")

    # Write scan-queue.txt (overwrite each run)
    SCAN_QUEUE.write_text(
        "\n".join(live_urls) + ("\n" if live_urls else ""),
        encoding="utf-8",
    )

    if live_urls:
        print()
        print("Run: python evaluate.py <url>  OR  python pipeline.py to process all")
    print()


if __name__ == "__main__":
    main()
