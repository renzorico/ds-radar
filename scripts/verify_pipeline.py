"""
Conservative pipeline integrity checker for ds-radar.

Usage:
  python scripts/verify_pipeline.py
  python scripts/verify_pipeline.py --json

This script is read-only by default. It verifies tracker/artifact consistency
using the current repo conventions and prints either a human-readable report or
machine-readable JSON.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from job_data import (
    APPLICATIONS,
    EVALS_DIR,
    REPO_ROOT,
    TRACKER,
    JobRecord,
    _artifact_matches_row,
    _company_date_key,
    load_job_records,
    load_tsv,
    short_role_slug,
    slugify,
    url_job_slug,
)

VALID_STATUSES = {"", "evaluated", "cv_ready", "applied", "skipped", "sponsorship_fail"}
def _row_signature(row: dict) -> str:
    return f"{row.get('date', '').strip()} | {row.get('company', '').strip()} | {row.get('role', '').strip()}"


def _record_signature(record: JobRecord) -> str:
    return f"{record.date} | {record.company} | {record.role}"


def _candidate_artifacts_for_row(
    row: dict,
    rows_by_company_date: dict[tuple[str, str], list[dict]],
    directory: Path,
    prefix: str,
) -> list[Path]:
    company = row.get("company", "").strip()
    role = row.get("role", "").strip()
    company_slug = slugify(company)
    role_slug = short_role_slug(role)
    job_slug = url_job_slug(row.get("url", ""))
    related_rows = rows_by_company_date.get(_company_date_key(row), [])

    if not company_slug:
        return []

    pattern = f"{prefix}_{company_slug}_*.md"
    if prefix == "cv":
        patterns = [f"{prefix}_{company_slug}_*.pdf", f"{prefix}_{company_slug}_*.md"]
    else:
        patterns = [pattern]

    candidates: list[Path] = []
    for artifact_pattern in patterns:
        for candidate in sorted(directory.glob(artifact_pattern), reverse=True):
            if len(related_rows) == 1:
                candidates.append(candidate)
                continue
            if _artifact_matches_row(candidate, company_slug, role_slug, job_slug):
                candidates.append(candidate)

    seen: set[Path] = set()
    unique_candidates: list[Path] = []
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            unique_candidates.append(candidate)
    return unique_candidates


def _matching_rows_for_artifact(
    artifact: Path,
    tracker_rows: list[dict],
    rows_by_company_date: dict[tuple[str, str], list[dict]],
) -> tuple[str | None, list[dict]]:
    matches: list[dict] = []
    stem = artifact.stem.lower()
    if artifact.parent == APPLICATIONS and stem.startswith("cv_"):
        artifact_type = "cv"
    elif artifact.parent == APPLICATIONS and stem.startswith("outreach_"):
        artifact_type = "outreach"
    elif artifact.parent == EVALS_DIR and stem.startswith("deep_"):
        artifact_type = "deep"
    elif artifact.parent == EVALS_DIR:
        artifact_type = "eval"
    else:
        return None, matches

    for row in tracker_rows:
        company_slug = slugify(row.get("company", "").strip())
        role_slug = short_role_slug(row.get("role", "").strip())
        job_slug = url_job_slug(row.get("url", ""))
        related_rows = rows_by_company_date.get(_company_date_key(row), [])

        if company_slug and company_slug not in stem:
            continue

        if artifact_type == "eval":
            name = artifact.name
            if name.startswith(f"{company_slug}_"):
                matches.append(row)
            continue

        if len(related_rows) == 1 or _artifact_matches_row(artifact, company_slug, role_slug, job_slug):
            matches.append(row)

    return artifact_type, matches


def _artifact_inventory() -> list[Path]:
    artifacts: list[Path] = []
    artifacts.extend(sorted(APPLICATIONS.glob("cv_*.pdf")))
    artifacts.extend(sorted(APPLICATIONS.glob("cv_*.md")))
    artifacts.extend(sorted(APPLICATIONS.glob("outreach_*.md")))
    artifacts.extend(sorted(EVALS_DIR.glob("deep_*.md")))
    artifacts.extend(
        sorted(
            path
            for path in EVALS_DIR.glob("*.md")
            if not path.name.startswith("deep_") and path.name != "errors.log"
        )
    )
    return artifacts


def run_verification() -> dict:
    tracker_rows = load_tsv(TRACKER)
    records = load_job_records(sort_by="date")
    rows_by_company_date: dict[tuple[str, str], list[dict]] = defaultdict(list)
    record_by_url = {record.url: record for record in records}

    for row in tracker_rows:
        rows_by_company_date[_company_date_key(row)].append(row)

    findings: dict[str, list[dict]] = {
        "duplicate_tracker_rows": [],
        "invalid_statuses": [],
        "missing_artifacts": [],
        "orphaned_artifacts": [],
        "readiness_inconsistencies": [],
        "ambiguous_artifacts": [],
    }

    rows_by_url: dict[str, list[dict]] = defaultdict(list)
    for row in tracker_rows:
        rows_by_url[row.get("url", "").strip()].append(row)
    for url, rows in rows_by_url.items():
        if url and len(rows) > 1:
            findings["duplicate_tracker_rows"].append(
                {
                    "url": url,
                    "count": len(rows),
                    "rows": [_row_signature(row) for row in rows],
                }
            )

    for row in tracker_rows:
        status = row.get("status", "").strip()
        if status not in VALID_STATUSES:
            findings["invalid_statuses"].append(
                {
                    "row": _row_signature(row),
                    "url": row.get("url", "").strip(),
                    "status": status,
                }
            )

        url = row.get("url", "").strip()
        record = record_by_url.get(url)
        if record is None:
            findings["missing_artifacts"].append(
                {
                    "row": _row_signature(row),
                    "url": url,
                    "artifact": "eval",
                    "reason": "Tracker row could not be enriched into a job record.",
                }
            )
            continue

        if status in {"evaluated", "cv_ready", "applied"} and not record.eval_path:
            findings["missing_artifacts"].append(
                {
                    "row": _record_signature(record),
                    "url": record.url,
                    "artifact": "eval",
                    "reason": f"Status={status} but no eval markdown was resolved.",
                }
            )

        if status in {"cv_ready", "applied"} and not record.cv_path:
            findings["missing_artifacts"].append(
                {
                    "row": _record_signature(record),
                    "url": record.url,
                    "artifact": "cv",
                    "reason": f"Status={status} but no CV artifact was resolved.",
                }
            )

        tracker_pdf_path = row.get("pdf_path", "").strip()
        if tracker_pdf_path and not (REPO_ROOT / tracker_pdf_path).exists():
            findings["missing_artifacts"].append(
                {
                    "row": _record_signature(record),
                    "url": record.url,
                    "artifact": "tracker_pdf_path",
                    "reason": f"tracker.tsv points to missing file: {tracker_pdf_path}",
                }
            )

        if tracker_pdf_path and record.cv_path and tracker_pdf_path != record.cv_path:
            findings["readiness_inconsistencies"].append(
                {
                    "row": _record_signature(record),
                    "url": record.url,
                    "reason": f"tracker pdf_path={tracker_pdf_path} but resolved CV is {record.cv_path}",
                }
            )

        if record.ready_to_apply and record.status in {"skipped", "sponsorship_fail"}:
            findings["readiness_inconsistencies"].append(
                {
                    "row": _record_signature(record),
                    "url": record.url,
                    "reason": f"ready_to_apply=yes while status={record.status}",
                }
            )

        if record.ready_to_apply and record.spons == "FAIL":
            findings["readiness_inconsistencies"].append(
                {
                    "row": _record_signature(record),
                    "url": record.url,
                    "reason": "ready_to_apply=yes while sponsorship gate failed",
                }
            )

        for label, directory, prefix in (
            ("cv", APPLICATIONS, "cv"),
            ("outreach", APPLICATIONS, "outreach"),
            ("oferta", EVALS_DIR, "deep"),
        ):
            candidates = _candidate_artifacts_for_row(row, rows_by_company_date, directory, prefix)
            if len(candidates) > 1:
                findings["ambiguous_artifacts"].append(
                    {
                        "row": _record_signature(record),
                        "url": record.url,
                        "artifact": label,
                        "candidates": [str(path.relative_to(REPO_ROOT)) for path in candidates],
                    }
                )

    for artifact in _artifact_inventory():
        artifact_type, matches = _matching_rows_for_artifact(artifact, tracker_rows, rows_by_company_date)
        rel_path = str(artifact.relative_to(REPO_ROOT))
        if not matches:
            findings["orphaned_artifacts"].append({"artifact": rel_path})
        elif artifact_type in {"cv", "outreach", "deep"} and len(matches) > 1:
            findings["ambiguous_artifacts"].append(
                {
                    "artifact": rel_path,
                    "matched_rows": [_row_signature(row) for row in matches],
                }
            )

    summary = {
        "tracker_rows": len(tracker_rows),
        "job_records": len(records),
        "artifacts_scanned": len(_artifact_inventory()),
    }
    for key, items in findings.items():
        summary[key] = len(items)

    next_actions: list[str] = []
    if findings["duplicate_tracker_rows"]:
        next_actions.append("Deduplicate tracker rows by URL before trusting readiness or status counts.")
    if findings["invalid_statuses"]:
        next_actions.append("Normalize invalid tracker statuses to the current dashboard/apply status set.")
    if findings["missing_artifacts"]:
        next_actions.append("Rebuild or relink missing eval/CV artifacts for rows with progressed statuses.")
    if findings["orphaned_artifacts"]:
        next_actions.append("Review orphaned files and either link them to tracker rows or archive/delete them manually.")
    if findings["ambiguous_artifacts"]:
        next_actions.append("Tighten artifact filenames or tracker links where one file can match multiple rows.")
    if findings["readiness_inconsistencies"]:
        next_actions.append("Inspect readiness mismatches before using the dashboard's ready-to-apply filter as truth.")
    if not next_actions:
        next_actions.append("No integrity issues detected by this conservative verifier.")

    return {
        "summary": summary,
        "findings": findings,
        "next_actions": next_actions,
    }


def _print_group(title: str, items: list[dict], limit: int = 20) -> None:
    print(f"\n{title} ({len(items)})")
    print("-" * (len(title) + len(str(len(items))) + 3))
    if not items:
        print("  none")
        return
    for item in items[:limit]:
        print(f"  - {json.dumps(item, ensure_ascii=False)}")
    if len(items) > limit:
        print(f"  ... {len(items) - limit} more")


def print_human_report(report: dict) -> None:
    summary = report["summary"]
    print("ds-radar pipeline integrity report")
    print("=" * 33)
    print(f"Tracker rows:      {summary['tracker_rows']}")
    print(f"Job records:       {summary['job_records']}")
    print(f"Artifacts scanned: {summary['artifacts_scanned']}")

    for key in (
        "duplicate_tracker_rows",
        "invalid_statuses",
        "missing_artifacts",
        "orphaned_artifacts",
        "readiness_inconsistencies",
        "ambiguous_artifacts",
    ):
        print(f"{key}: {summary[key]}")

    _print_group("Duplicate Tracker Rows", report["findings"]["duplicate_tracker_rows"])
    _print_group("Invalid Statuses", report["findings"]["invalid_statuses"])
    _print_group("Missing Artifacts", report["findings"]["missing_artifacts"])
    _print_group("Orphaned Artifacts", report["findings"]["orphaned_artifacts"])
    _print_group("Readiness Inconsistencies", report["findings"]["readiness_inconsistencies"])
    _print_group("Ambiguous Artifacts", report["findings"]["ambiguous_artifacts"])

    print("\nSuggested next actions")
    print("----------------------")
    for action in report["next_actions"]:
        print(f"  - {action}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify tracker/artifact integrity for ds-radar.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    report = run_verification()
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return
    print_human_report(report)


if __name__ == "__main__":
    main()
