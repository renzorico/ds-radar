"""
LinkedIn jobs search scraper for ds-radar.

Usage:
  python scripts/scrape_linkedin_search.py SEARCH_URL [--out PATH] [--max-jobs N] [--headless]

Opens a LinkedIn jobs search URL in a persistent Playwright browser profile,
scrapes visible job cards, and writes a CSV compatible with scripts/import_linkedin.py.

Notes:
- Discovery only. No apply behaviour.
- If LinkedIn requires login, log in manually in the opened browser, then press Enter here.
- If selectors fail or no cards are found, the script exits with a clear error instead of
  writing an empty CSV.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT.parent / "linkedin" / "visa_jobs_results.csv"
PROFILE_DIR = REPO_ROOT / ".playwright-linkedin-profile"
CSV_HEADER = [
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

CARD_SELECTORS = [
    "li.scaffold-layout__list-item",
    "li.jobs-search-results__list-item",
    "li[data-occludable-job-id]",
    "ul.jobs-search__results-list > li",
    "div.job-card-container",
]
RESULTS_CONTAINER_SELECTORS = [
    "ul.scaffold-layout__list-container",
    "div.scaffold-layout__list-container",
    "div.scaffold-layout__list",
    "div.jobs-search-results-list",
    "ul.jobs-search__results-list",
]
LOGIN_SELECTORS = [
    "input[name='session_key']",
    "a[href*='/login']",
    "button[data-litms-control-urn='login-submit']",
]
LOGGED_IN_SELECTORS = [
    "#global-nav",
    "nav.global-nav",
    "a[href='/feed/']",
]


def extract_search_title(search_url: str) -> str:
    parsed = urlparse(search_url)
    params = parse_qs(parsed.query)
    raw = params.get("keywords", ["linkedin search"])[0]
    return unquote(raw).replace("+", " ").strip() or "linkedin search"


def normalize_job_url(url: str) -> str:
    clean = url.strip().split("?")[0].split("#")[0]
    if clean.startswith("/"):
        return f"https://www.linkedin.com{clean}"
    return clean


def parse_posted_date(text: str) -> str:
    raw = " ".join(text.lower().split())
    raw = raw.replace("reposted", "").strip()
    today = date.today()

    if not raw:
        return ""
    if "today" in raw or "just now" in raw:
        return today.isoformat()
    if "yesterday" in raw:
        return (today - timedelta(days=1)).isoformat()

    match = re.search(r"(\d+)\s+(hour|day|week|month)s?\s+ago", raw)
    if not match:
        return ""

    value = int(match.group(1))
    unit = match.group(2)
    days = {
        "hour": 0,
        "day": value,
        "week": value * 7,
        "month": value * 30,
    }[unit]
    return (today - timedelta(days=days)).isoformat()


def wait_for_login_if_needed(page) -> None:
    for selector in LOGIN_SELECTORS:
        if page.locator(selector).count() > 0:
            print("[LINKEDIN] Login appears to be required.")
            print(f"[LINKEDIN] A persistent browser profile is stored at: {PROFILE_DIR}")
            input("[LINKEDIN] Log into LinkedIn in the opened browser, then press Enter to continue: ")
            page.wait_for_timeout(1500)
            return


def is_logged_in(page) -> bool:
    current_url = page.url.lower()
    if "linkedin.com/feed" in current_url or "linkedin.com/jobs" in current_url:
        return True
    for selector in LOGGED_IN_SELECTORS:
        try:
            if page.locator(selector).count() > 0:
                return True
        except Exception:
            continue
    return False


def debug_selector_counts(page) -> None:
    container_counts = []
    for selector in RESULTS_CONTAINER_SELECTORS:
        try:
            container_counts.append(f"{selector}={page.locator(selector).count()}")
        except Exception:
            container_counts.append(f"{selector}=ERR")
    card_counts = []
    for selector in CARD_SELECTORS:
        try:
            card_counts.append(f"{selector}={page.locator(selector).count()}")
        except Exception:
            card_counts.append(f"{selector}=ERR")
    print(f"[LINKEDIN][debug] containers: {', '.join(container_counts)}")
    print(f"[LINKEDIN][debug] cards: {', '.join(card_counts)}")


def sample_nearby_text(page, container=None) -> str:
    targets = []
    if container is not None:
        targets.extend(
            [
                container.locator("li").nth(0),
                container.locator("div").nth(0),
                container.locator("a").nth(0),
            ]
        )
    main = page.locator("main").first
    targets.extend([main.locator("h1").first, main.locator("h2").first, main.locator("li").nth(0)])

    samples: list[str] = []
    for locator in targets:
        try:
            if locator.count() == 0:
                continue
            text = " ".join((locator.inner_text() or "").split())
            if text:
                samples.append(text[:180])
        except Exception:
            continue
        if len(samples) >= 3:
            break
    return " | ".join(samples)


def is_jobs_results_page(page) -> bool:
    url = page.url.lower()
    if "/jobs/search" in url or "/jobs/collections" in url:
        return True
    if page.locator("main").get_by_text("Jobs you may be interested in", exact=False).count() > 0:
        return True
    return False


def find_results_container(page):
    for selector in RESULTS_CONTAINER_SELECTORS:
        locator = page.locator(selector).first
        if locator.count() > 0:
            return locator
    return None


def collect_cards(page, container=None):
    scope = container if container is not None else page
    for selector in CARD_SELECTORS:
        locator = scope.locator(selector)
        if locator.count() > 0:
            return locator
    return None


def wait_for_results_container(page):
    for selector in RESULTS_CONTAINER_SELECTORS:
        try:
            page.wait_for_selector(selector, timeout=6_000)
            locator = page.locator(selector).first
            if locator.count() > 0:
                print(f"[LINKEDIN][debug] results container selector matched: {selector}")
                return locator
        except PlaywrightTimeoutError:
            continue
    return None


def scroll_results(page, max_jobs: int) -> None:
    container = wait_for_results_container(page) or find_results_container(page)
    if container is None:
        debug_selector_counts(page)
        sample = sample_nearby_text(page)
        raise RuntimeError(
            "LinkedIn results container not found. "
            f"Current URL={page.url}. Nearby text: {sample or 'none'}"
        )

    stable_rounds = 0
    last_count = 0
    for _ in range(30):
        cards = collect_cards(page, container)
        count = cards.count() if cards is not None else 0
        if count >= max_jobs:
            break
        if count == last_count:
            stable_rounds += 1
        else:
            stable_rounds = 0
        if stable_rounds >= 3:
            break

        try:
            container.evaluate("(el) => { el.scrollTop = el.scrollHeight; }")
        except Exception:
            page.mouse.wheel(0, 2500)
        page.wait_for_timeout(1200)
        last_count = count


def text_or_empty(locator, selector: str) -> str:
    try:
        child = locator.locator(selector).first
        if child.count() == 0:
            return ""
        return " ".join((child.inner_text() or "").split())
    except Exception:
        return ""


def attr_or_empty(locator, selector: str, name: str) -> str:
    try:
        child = locator.locator(selector).first
        if child.count() == 0:
            return ""
        return (child.get_attribute(name) or "").strip()
    except Exception:
        return ""


def extract_job_rows(page, search_title: str, max_jobs: int) -> list[dict]:
    container = wait_for_results_container(page) or find_results_container(page)
    cards = collect_cards(page, container)
    if cards is None or cards.count() == 0:
        debug_selector_counts(page)
        sample = sample_nearby_text(page, container)
        raise RuntimeError(
            "LinkedIn jobs list appeared but 0 cards matched the current selectors. "
            f"Card selectors={CARD_SELECTORS}. Nearby text: {sample or 'none'}"
        )

    rows: list[dict] = []
    seen_urls: set[str] = set()

    for index in range(min(cards.count(), max_jobs)):
        card = cards.nth(index)
        title = text_or_empty(card, "a.job-card-container__link strong, a.job-card-list__title, strong")
        company = text_or_empty(card, ".artdeco-entity-lockup__subtitle, .job-card-container__company-name, .artdeco-entity-lockup__subtitle span")
        location = text_or_empty(card, ".job-card-container__metadata-item, .job-card-container__metadata-wrapper li, .artdeco-entity-lockup__caption")
        posted_text = text_or_empty(card, "time, .job-card-container__footer-item, .job-card-list__footer-wrapper")
        href = attr_or_empty(card, "a.job-card-container__link, a.job-card-list__title", "href")
        url = normalize_job_url(href)

        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        rows.append(
            {
                "search_title": search_title,
                "job_title": title,
                "relevance_score": "1.0",
                "company": company,
                "location": location,
                "posted": parse_posted_date(posted_text),
                "url": url,
                "licensed_sponsor": "",
                "sponsorship_signal": "unknown",
                "sponsorship_evidence": "",
                "hiring_contact_name": "",
                "hiring_contact_title": "",
            }
        )

    if not rows:
        raise RuntimeError("LinkedIn selectors matched the page, but no usable job rows were extracted.")
    return rows


def write_csv(rows: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_HEADER)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape LinkedIn job search results into import_linkedin.py CSV format")
    parser.add_argument("search_url", help="Full LinkedIn jobs search URL")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, metavar="PATH", help=f"Output CSV path (default: {DEFAULT_OUT})")
    parser.add_argument("--max-jobs", type=int, default=150, metavar="N", help="Maximum number of job cards to scrape (default: 150)")
    parser.add_argument("--headless", action="store_true", help="Run headless (default: visible browser)")
    args = parser.parse_args()

    search_title = extract_search_title(args.search_url)

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            headless=args.headless,
            viewport={"width": 1440, "height": 1200},
        )
        page = context.pages[0] if context.pages else context.new_page()

        try:
            print("[LINKEDIN] Opening LinkedIn login page...")
            page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=45_000)
            page.wait_for_timeout(2000)
            if not is_logged_in(page):
                print("[LINKEDIN] Please log in to LinkedIn in the opened browser, then press Enter to continue...")
                input()
                page.wait_for_timeout(1500)
                if not is_logged_in(page):
                    debug_selector_counts(page)
                    sample = sample_nearby_text(page)
                    raise RuntimeError(
                        "LinkedIn login was not detected after manual confirmation. "
                        f"Current URL={page.url}. Nearby text: {sample or 'none'}"
                    )
                print("[LINKEDIN] Login confirmed. Navigating to search results...")

            print(f"[LINKEDIN] Opening search: {args.search_url}")
            page.goto(args.search_url, wait_until="domcontentloaded", timeout=45_000)
            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except PlaywrightTimeoutError:
                page.wait_for_timeout(2500)

            if not is_jobs_results_page(page):
                debug_selector_counts(page)
                sample = sample_nearby_text(page)
                raise RuntimeError(
                    "Page does not look like a LinkedIn jobs search results page after navigation/login. "
                    f"Current URL={page.url}. Nearby text: {sample or 'none'}"
                )

            try:
                container = wait_for_results_container(page)
                if container is None:
                    debug_selector_counts(page)
                    sample = sample_nearby_text(page)
                    raise RuntimeError(
                        "LinkedIn results list did not load. "
                        f"Current URL={page.url}. Nearby text: {sample or 'none'}"
                    )
                cards = collect_cards(page, container)
                if cards is None or cards.count() == 0:
                    page.wait_for_timeout(2500)
            except PlaywrightTimeoutError as exc:
                debug_selector_counts(page)
                sample = sample_nearby_text(page)
                raise RuntimeError(
                    "LinkedIn job cards did not load. "
                    f"Current URL={page.url}. Nearby text: {sample or 'none'}"
                ) from exc

            scroll_results(page, args.max_jobs)
            rows = extract_job_rows(page, search_title, args.max_jobs)
            write_csv(rows, args.out)
        finally:
            context.close()

    print(f"[LINKEDIN] wrote {len(rows)} rows to {args.out}")
    print(f"[LINKEDIN] CSV header: {', '.join(CSV_HEADER)}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)
