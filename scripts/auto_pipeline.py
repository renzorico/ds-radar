"""
ds-radar auto pipeline — weekly pass
Usage: python scripts/auto_pipeline.py [options]
       python scripts/auto_pipeline.py --batch-file urls.txt [options]

Steps:
  1. Import from LinkedIn CSV   (unless --skip-linkedin)
  2. ATS scan via scan.py logic
  3. Evaluate new URLs          (up to --limit-evals)
  4. Run oferta + contacto for grade >= min_grade AND jd_source=REAL
  5. Print compact run summary

Batch mode:
  - Processes URLs from a file with resumable local state.
  - Retries failed items up to --max-retries.
  - Never auto-applies.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from evaluate import evaluate_url, read_scan_history, REPO_ROOT
from generate_pdf import generate_pdf
from pipeline import load_tracked_urls, append_tracker_row, APPLY_GRADES
from scan import load_companies, discover_jobs

SCAN_QUEUE   = REPO_ROOT / "scan-queue.txt"
SCRIPTS_DIR  = Path(__file__).resolve().parent

GRADE_ORDER  = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4}


def grade_meets(grade: str, min_grade: str) -> bool:
    return GRADE_ORDER.get(grade, 99) <= GRADE_ORDER.get(min_grade, 99)


def _jd_source_from_eval(eval_path) -> str:
    try:
        text = Path(eval_path).read_text(encoding="utf-8")
        m = re.search(r"\[JD_SOURCE: (REAL|MOCK)\]", text)
        return m.group(1) if m else "MOCK"
    except Exception:
        return "MOCK"


def utc_timestamp() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_batch_urls(path: Path) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        url = raw.strip()
        if not url or url.startswith("#") or url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls


def load_batch_state(path: Path) -> dict:
    if not path.exists():
        return {"items": [], "updated_at": ""}
    return json.loads(path.read_text(encoding="utf-8"))


def save_batch_state(path: Path, state: dict) -> None:
    state["updated_at"] = utc_timestamp()
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def upsert_batch_items(state: dict, urls: list[str], max_retries: int) -> dict:
    items = state.setdefault("items", [])
    items_by_url = {item["url"]: item for item in items}
    for item in items:
        if item.get("status") == "running":
            item["status"] = "pending"
            item["last_error"] = "Reset from running on resume."
            item["updated_at"] = utc_timestamp()
    for url in urls:
        if url in items_by_url:
            continue
        item = {
            "url": url,
            "status": "pending",
            "attempt_count": 0,
            "last_error": "",
            "updated_at": utc_timestamp(),
            "eval_path": "",
            "pdf_path": "",
            "company": "",
            "title": "",
            "grade": "",
            "jd_source": "",
        }
        items.append(item)
        items_by_url[url] = item
    state["max_retries"] = max_retries
    return state


def batch_counts(state: dict) -> dict[str, int]:
    counts = {"pending": 0, "running": 0, "succeeded": 0, "failed": 0, "skipped": 0}
    for item in state.get("items", []):
        status = item.get("status", "pending")
        counts[status] = counts.get(status, 0) + 1
    return counts


def summarize_batch(state: dict, path: Path) -> None:
    counts = batch_counts(state)
    print(
        f"[BATCH] state={path} "
        f"pending={counts['pending']} running={counts['running']} "
        f"succeeded={counts['succeeded']} failed={counts['failed']} skipped={counts['skipped']}"
    )


def process_single_url(args, url: str, tracked_urls: set[str]) -> tuple[dict, int]:
    today = date.today().isoformat()
    if args.dry_run:
        print(f"[DRY] would evaluate: {url[:80]}")
        return {
            "url": url,
            "skipped": False,
            "grade": "?",
            "jd_source": "MOCK",
            "_dry": True,
            "pdf_path": "",
        }, 0

    result = evaluate_url(url)
    grade = result.get("grade", "?")
    jd_src = _jd_source_from_eval(result.get("eval_path", ""))
    result["jd_source"] = jd_src

    if result["skipped"]:
        print(f"[AUTO] eval url={url[:70]} already_evaluated=true")
        result["pdf_path"] = ""
        return result, 0

    if result.get("sponsorship", {}).get("status") == "negative":
        print(f"[AUTO] sponsorship_gate=FAIL url={url[:70]} — skipping downstream")
        append_tracker_row({
            "date": today, "company": result.get("company", "?"),
            "role": result.get("title", ""), "url": url,
            "grade": "F", "score": str(result.get("overall_score", 0.0)),
            "status": "sponsorship_fail", "pdf_path": "",
            "notes": result.get("sponsorship", {}).get("reason", ""),
        })
        tracked_urls.add(url)
        result["pdf_path"] = ""
        return result, 0

    score = result.get("overall_score", 0.0)
    pdf_path = ""
    cvs_written = 0

    if grade_meets(grade, args.min_grade):
        ep = result.get("eval_path")
        if ep:
            try:
                pdf_path = generate_pdf(ep)
                cvs_written += 1
            except Exception as exc:
                print(f"[WARN] generate_pdf: {exc}")

    if url not in tracked_urls:
        status = "cv_ready" if pdf_path else "evaluated"
        append_tracker_row({
            "date": today, "company": result.get("company", "?"),
            "role": result.get("title", ""), "url": url,
            "grade": grade, "score": str(score),
            "status": status, "pdf_path": pdf_path, "notes": jd_src,
        })
        tracked_urls.add(url)

    result["pdf_path"] = pdf_path
    cv_flag = "yes" if pdf_path else "no"
    print(f"[AUTO] eval url={url[:70]} grade={grade} jd_source={jd_src} cv={cv_flag}")
    return result, cvs_written


# ── Phase 1: LinkedIn ─────────────────────────────────────────────────────────

def phase_linkedin(args) -> tuple[int, list[str]]:
    print("[AUTO] phase=linkedin_import")
    if args.skip_linkedin:
        print("[AUTO] skipped (--skip-linkedin)")
        return 0, []

    try:
        from import_linkedin import run_import, DEFAULT_CSV
    except ImportError as e:
        print(f"[AUTO] import_linkedin unavailable: {e} — skipping")
        return 0, []

    if not DEFAULT_CSV.exists():
        print(f"[AUTO] LinkedIn CSV not found at {DEFAULT_CSV} — skipping")
        return 0, []

    try:
        stats, urls = run_import(dry_run=args.dry_run)
    except SystemExit:
        print("[AUTO] LinkedIn import failed — skipping")
        return 0, []

    print(f"[AUTO] linkedin rows={stats['total']} kept={stats['kept']} "
          f"skipped_score={stats['skipped_score']} skipped_age={stats['skipped_age']}")
    return stats["kept"], urls


# ── Phase 2: ATS scan ─────────────────────────────────────────────────────────

def phase_scan(args, seen_urls: set[str]) -> tuple[int, list[str]]:
    print("[AUTO] phase=ats_scan")
    try:
        companies = load_companies()
    except SystemExit:
        print("[AUTO] No target companies — scan skipped")
        return 0, []

    new_urls: list[str] = []
    for company in companies:
        print(f"[AUTO] scanning {company['name']}...", end=" ", flush=True)
        discovered = discover_jobs(company)
        fresh = [u for u in discovered if u not in seen_urls]
        new_urls.extend(fresh)
        print(f"→ {len(fresh)} new")

    print(f"[AUTO] ats_scan total_new={len(new_urls)}")
    return len(new_urls), new_urls


# ── Phase 3: Evaluate + CV ────────────────────────────────────────────────────

def phase_evaluate(
    args, urls: list[str], tracked_urls: set[str]
) -> tuple[list[dict], int]:
    capped = urls[:args.limit_evals] if args.limit_evals else urls
    print(f"[AUTO] phase=evaluate urls={len(capped)}"
          + (f" (capped from {len(urls)})" if len(capped) < len(urls) else ""))

    today = date.today().isoformat()
    results: list[dict] = []
    cvs_written = 0

    for url in capped:
        result, written = process_single_url(args, url, tracked_urls)
        cvs_written += written
        results.append(result)

    return results, cvs_written


# ── Phase 4: Oferta + Contacto ────────────────────────────────────────────────

def phase_oferta_contacto(args, results: list[dict]) -> tuple[int, int, float]:
    print("[AUTO] phase=oferta_contacto")
    briefs = outreach = 0
    total_cost = 0.0

    for r in results:
        if r.get("skipped") or r.get("_dry"):
            continue
        grade   = r.get("grade", "?")
        jd_src  = r.get("jd_source", "MOCK")
        url     = r["url"]

        if not grade_meets(grade, args.min_grade) or jd_src != "REAL":
            reason = f"grade={grade}" if not grade_meets(grade, args.min_grade) else "jd_source=MOCK"
            print(f"[AUTO] oferta/contacto skip url={url[:60]} {reason}")
            continue

        if args.dry_run:
            print(f"[DRY] would run oferta + contacto for {url[:60]}")
            continue

        for script, label in [("oferta.py", "oferta"), ("contacto.py", "contacto")]:
            proc = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / script), url],
                capture_output=True, text=True,
            )
            for line in proc.stdout.splitlines():
                m = re.search(r"\~\$([0-9.]+)", line)
                if m:
                    total_cost += float(m.group(1))
            if proc.returncode == 0:
                briefs   += (label == "oferta")
                outreach += (label == "contacto")
            else:
                print(f"[WARN] {script} exit={proc.returncode} url={url[:60]}")

    return briefs, outreach, total_cost


def run_batch_mode(args, tracked_urls: set[str]) -> None:
    batch_file = Path(args.batch_file)
    if not batch_file.exists():
        print(f"[BATCH] batch file not found: {batch_file}")
        sys.exit(1)

    state_path = Path(args.batch_state) if args.batch_state else batch_file.with_suffix(".state.json")
    urls = load_batch_urls(batch_file)
    state = upsert_batch_items(load_batch_state(state_path), urls, args.max_retries)
    save_batch_state(state_path, state)
    summarize_batch(state, state_path)

    if args.dry_run:
        pending_urls = [
            item["url"] for item in state["items"]
            if item["status"] in {"pending", "failed", "running"}
            and item.get("attempt_count", 0) < args.max_retries
        ]
        capped = pending_urls[:args.limit_evals] if args.limit_evals else pending_urls
        for url in capped:
            print(f"[DRY] batch would process: {url}")
        print(f"[BATCH] dry-run eligible={len(capped)} state={state_path}")
        return

    processed = 0
    briefs = 0
    outreach = 0
    brief_cost = 0.0

    for item in state["items"]:
        status = item.get("status", "pending")
        attempts = item.get("attempt_count", 0)
        if status in {"succeeded", "skipped"}:
            continue
        if status == "failed" and attempts >= args.max_retries:
            continue
        if args.limit_evals and processed >= args.limit_evals:
            break

        item["status"] = "running"
        item["attempt_count"] = attempts + 1
        item["last_error"] = ""
        item["updated_at"] = utc_timestamp()
        save_batch_state(state_path, state)

        try:
            result, written = process_single_url(args, item["url"], tracked_urls)
            item["company"] = result.get("company", "")
            item["title"] = result.get("title", "")
            item["grade"] = result.get("grade", "")
            item["jd_source"] = result.get("jd_source", "")
            eval_path = result.get("eval_path")
            item["eval_path"] = str(eval_path) if eval_path else ""
            item["pdf_path"] = result.get("pdf_path", "")

            if result.get("skipped"):
                item["status"] = "skipped"
            else:
                item["status"] = "succeeded"
                brief_add, outreach_add, cost_add = phase_oferta_contacto(args, [result])
                briefs += brief_add
                outreach += outreach_add
                brief_cost += cost_add
            item["last_error"] = ""
        except Exception as exc:
            item["status"] = "failed"
            item["last_error"] = repr(exc)
            print(f"[BATCH] failed url={item['url'][:80]} error={exc}")
        item["updated_at"] = utc_timestamp()
        save_batch_state(state_path, state)
        processed += 1

    summarize_batch(state, state_path)
    print(
        f"[BATCH] done processed={processed} "
        f"oferta={briefs} contacto={outreach} cost_estimate=~${brief_cost:.4f} "
        f"state={state_path}"
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="ds-radar weekly auto pipeline")
    parser.add_argument("--skip-linkedin", action="store_true",
                        help="Skip LinkedIn CSV import")
    parser.add_argument("--min-grade", default="B", choices=list("ABCDF"),
                        help="Minimum grade for CV/oferta/contacto (default: B)")
    parser.add_argument("--limit-evals", type=int, default=None, metavar="N",
                        help="Max URLs to evaluate this run")
    parser.add_argument("--dry-run", action="store_true",
                        help="No writes — log what would happen")
    parser.add_argument("--batch-file", default=None,
                        help="Process URLs from this file using resumable batch state")
    parser.add_argument("--batch-state", default=None,
                        help="Path to batch state JSON (default: <batch-file>.state.json)")
    parser.add_argument("--max-retries", type=int, default=2, metavar="N",
                        help="Retry failed batch items up to N times (default: 2)")
    args = parser.parse_args()

    if args.dry_run:
        print("[AUTO] DRY RUN — no files will be written\n")

    # Shared state
    seen_urls    = {r["url"] for r in read_scan_history() if r.get("url")}
    tracked_urls = load_tracked_urls()

    if args.batch_file:
        run_batch_mode(args, tracked_urls)
        return

    # ── Phase 1 ──
    linkedin_kept, linkedin_urls = phase_linkedin(args)

    # ── Phase 2 ──
    ats_count, ats_urls = phase_scan(args, seen_urls)

    # Merge new ATS URLs into queue (LinkedIn already wrote its share via run_import)
    if ats_urls and not args.dry_run:
        with SCAN_QUEUE.open("a", encoding="utf-8") as f:
            for u in ats_urls:
                f.write(u + "\n")

    # Build the evaluation list: existing queue + dry-run notional set
    if SCAN_QUEUE.exists():
        queue_urls = [u.strip() for u in
                      SCAN_QUEUE.read_text(encoding="utf-8").splitlines() if u.strip()]
    else:
        queue_urls = []

    if args.dry_run:
        queue_urls = list(dict.fromkeys(queue_urls + linkedin_urls + ats_urls))

    # ── Phase 3 ──
    eval_results, cvs = phase_evaluate(args, queue_urls, tracked_urls)

    # Clear queue after processing
    if not args.dry_run and queue_urls:
        SCAN_QUEUE.write_text("", encoding="utf-8")

    # ── Phase 4 ──
    briefs, outreach, brief_cost = phase_oferta_contacto(args, eval_results)

    # ── Summary ──
    real = [r for r in eval_results if not r.get("skipped") and not r.get("_dry")]
    bplus = sum(1 for r in real if grade_meets(r.get("grade", "F"), args.min_grade))

    print()
    print(
        f"[AUTO] done "
        f"imported_linkedin={linkedin_kept} "
        f"scanned_ats={ats_count} "
        f"evaluated={len(real)} "
        f"Bplus={bplus} "
        f"cv={cvs} "
        f"oferta={briefs} "
        f"contacto={outreach} "
        f"cost_estimate=~${brief_cost:.4f} "
        f"dry_run={args.dry_run}"
    )


if __name__ == "__main__":
    main()
