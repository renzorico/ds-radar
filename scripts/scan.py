"""
ds-radar scanner
Usage: python scan.py

Discovers job URLs from two sources:
  1. LinkedIn CSV files dropped into csv-inbox/  (Detail URL column)
  2. ATS boards defined in profile/target-companies.yaml when explicitly enabled

Deduplicates against scan-history.tsv + tracker.tsv, liveness-checks ATS URLs,
and refreshes scan-queue.txt while preserving still-pending URLs.
Processed CSVs are moved to csv-inbox/processed/ so they are never re-imported.
"""

import argparse
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
SOURCE_HISTORY = REPO_ROOT / "source-history.tsv"
ERRORS_LOG = REPO_ROOT / "evals" / "errors.log"
CSV_INBOX = REPO_ROOT / "csv-inbox"
CSV_PROCESSED = CSV_INBOX / "processed"

GREENHOUSE_TIMEOUT_MS = 15_000
LINKEDIN_MAX_AGE_DAYS = 14
LINKEDIN_CLOSED_PHRASES = (
    "no longer accepting applications",
    "position has been filled",
)
SOURCE_HISTORY_HEADER = [
    "source", "discovered_at", "search_title", "job_title",
    "company", "location", "posted", "relevance_score",
    "licensed_sponsor", "sponsorship_signal", "sponsorship_evidence",
    "source_url", "target_url",
]


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


def load_queued_urls() -> list[str]:
    """Return current queue contents, deduplicated and order-preserving."""
    if not SCAN_QUEUE.exists():
        return []

    queued_urls: list[str] = []
    seen: set[str] = set()
    for raw_url in SCAN_QUEUE.read_text(encoding="utf-8").splitlines():
        url = raw_url.strip()
        if not url or url in seen:
            continue
        seen.add(url)
        queued_urls.append(url)
    return queued_urls


def load_source_history_urls() -> set[str]:
    if not SOURCE_HISTORY.exists():
        return set()
    with SOURCE_HISTORY.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return {
            row["target_url"].strip()
            for row in reader
            if row.get("target_url", "").strip()
        }


def append_source_history_rows(rows: list[dict]) -> None:
    if not rows:
        return
    write_header = not SOURCE_HISTORY.exists() or SOURCE_HISTORY.stat().st_size == 0
    with SOURCE_HISTORY.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SOURCE_HISTORY_HEADER, delimiter="\t")
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def parse_linkedin_created_at(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def is_closed_linkedin_row(row: dict) -> bool:
    haystacks = [
        row.get("Title", ""),
        row.get("Description", ""),
        row.get("Primary Description", ""),
        row.get("Insight", ""),
    ]
    combined = "\n".join(str(part or "") for part in haystacks).lower()
    return any(phrase in combined for phrase in LINKEDIN_CLOSED_PHRASES)


# ── LinkedIn CSV inbox ────────────────────────────────────────────────────────

def ingest_csv_inbox(seen_urls: set[str]) -> list[str]:
    """Read all LinkedIn CSVs from csv-inbox/, return new URLs, archive processed files."""
    CSV_INBOX.mkdir(exist_ok=True)
    CSV_PROCESSED.mkdir(exist_ok=True)

    csv_files = sorted(CSV_INBOX.glob("*.csv"))
    if not csv_files:
        return []

    new_urls: list[str] = []
    source_history_urls = load_source_history_urls()
    for csv_path in csv_files:
        try:
            with csv_path.open(newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                if "Detail URL" not in (reader.fieldnames or []):
                    print(f"  [CSV] {csv_path.name}: no 'Detail URL' column — skipping")
                    continue
                rows = list(reader)
            urls = [row["Detail URL"].strip() for row in rows if row.get("Detail URL", "").strip()]
            cutoff = datetime.now().date().toordinal() - LINKEDIN_MAX_AGE_DAYS
            eligible_urls: list[str] = []
            skipped_old = 0
            skipped_closed = 0
            for row in rows:
                url = row.get("Detail URL", "").strip()
                if not url:
                    continue
                if is_closed_linkedin_row(row):
                    skipped_closed += 1
                    continue
                created_at = parse_linkedin_created_at(row.get("Created At", ""))
                if created_at and created_at.date().toordinal() < cutoff:
                    skipped_old += 1
                    continue
                eligible_urls.append(url)
            fresh = [u for u in eligible_urls if u not in seen_urls]
            new_urls.extend(fresh)
            seen_urls.update(fresh)  # prevent cross-file duplication
            discovered_at = datetime.now().date().isoformat()
            source_rows: list[dict] = []
            for row in rows:
                url = row.get("Detail URL", "").strip()
                if not url or url in source_history_urls:
                    continue
                source_rows.append({
                    "source": "linkedin_csv_inbox",
                    "discovered_at": discovered_at,
                    "search_title": "linkedin_csv_inbox",
                    "job_title": row.get("Title", "").strip(),
                    "company": row.get("Company Name", "").strip(),
                    "location": row.get("Location", "").strip(),
                    "posted": row.get("Created At", "").strip(),
                    "relevance_score": "",
                    "licensed_sponsor": "",
                    "sponsorship_signal": "",
                    "sponsorship_evidence": "",
                    "source_url": url,
                    "target_url": url,
                })
                source_history_urls.add(url)
            append_source_history_rows(source_rows)
            dest = CSV_PROCESSED / csv_path.name
            shutil.move(str(csv_path), str(dest))
            print(
                f"  [CSV] {csv_path.name}: {len(urls)} rows, "
                f"{skipped_old} old, {skipped_closed} closed, {len(fresh)} new → archived"
            )
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
    parser = argparse.ArgumentParser(description="Scan CSV inbox and optionally ATS boards")
    parser.add_argument(
        "--with-ats",
        action="store_true",
        help="Also discover roles from ATS boards in profile/target-companies.yaml",
    )
    args = parser.parse_args()

    seen_urls = load_seen_urls()
    queued_urls = [url for url in load_queued_urls() if url not in seen_urls]
    dedupe_urls = seen_urls | set(queued_urls)

    # ── Source 1: LinkedIn CSV inbox ─────────────────────────────────────────
    print()
    print("[SCAN] CSV inbox")
    csv_urls = ingest_csv_inbox(dedupe_urls)
    print(f"       {len(csv_urls)} new LinkedIn URLs from CSVs")

    ats_urls: list[str] = []
    if args.with_ats:
        print()
        print("[SCAN] ATS boards")
        companies = load_companies()
        for company in companies:
            print(f"  {company['name']}...", end=" ", flush=True)
            discovered = discover_jobs(company)
            new = [u for u in discovered if u not in dedupe_urls]
            dedupe_urls.update(new)
            ats_urls.extend(new)
            print(f"→ {len(discovered)} found, {len(new)} new, {len(discovered)-len(new)} seen")
        print(f"       {len(ats_urls)} new ATS URLs")
    else:
        print()
        print("[SCAN] ATS boards skipped (use --with-ats to enable)")

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

    queue_urls = queued_urls + live_urls

    # ── Write scan-queue.txt (preserve pending + append fresh) ────────────────
    SCAN_QUEUE.write_text(
        "\n".join(queue_urls) + ("\n" if queue_urls else ""),
        encoding="utf-8",
    )

    sep = "─" * 45
    print(f"\n{sep}")
    print(f"  LinkedIn CSV:    {len(csv_urls)}")
    print(f"  ATS boards:      {len(ats_urls)}")
    print(f"  Queue carried:   {len(queued_urls)}")
    print(f"  Queue new:       {len(live_urls)}")
    print(f"  Queue total:     {len(queue_urls)}")
    print(sep)
    if queue_urls:
        print("  Next: python scripts/pipeline.py --parallel 3")
    print(f"{sep}\n")


if __name__ == "__main__":
    main()
