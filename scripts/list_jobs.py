"""
ds-radar job dashboard
Usage: python scripts/list_jobs.py [options]

Reads tracker.tsv and enriches each row with eval metadata,
source info from source-history.tsv, and file presence checks.

Options:
  --limit N               Max rows to show (default: 30)
  --sort date|grade|company|score
  --filter-grade B+       Show grades >= B
  --filter-source linkedin|ats
  --filter-sponsorship pass|fail
"""

from __future__ import annotations

import argparse

from job_data import grade_passes, load_job_records


def main() -> None:
    parser = argparse.ArgumentParser(description="ds-radar job dashboard")
    parser.add_argument("--limit", type=int, default=30, metavar="N")
    parser.add_argument(
        "--sort",
        default="date",
        choices=["date", "grade", "company", "score"],
    )
    parser.add_argument("--filter-grade", default=None, metavar="GRADE", help="e.g. A  B+  C-")
    parser.add_argument("--filter-source", default=None, choices=["linkedin", "ats"])
    parser.add_argument("--filter-sponsorship", default=None, choices=["pass", "fail"])
    args = parser.parse_args()

    records = load_job_records(sort_by=args.sort)
    out = [record for record in records if grade_passes(record.grade, args.filter_grade)]

    if args.filter_source:
        out = [record for record in out if record.source == args.filter_source]
    if args.filter_sponsorship:
        target = args.filter_sponsorship.upper()
        if target == "FAIL":
            out = [record for record in out if record.spons == "FAIL"]
        else:
            out = [record for record in out if record.spons != "FAIL"]

    page = out[: args.limit]
    if not page:
        print("No matching jobs.")
        return

    company_width = 22
    role_width = 34
    header = (
        f"{'DATE':<10}  {'GR':2}  {'SRC':<8}  {'JD':<4}  {'SPONS':<5}  "
        f"{'CV':3}  {'OFE':3}  {'CON':3}  {'COMPANY':<{company_width}}  ROLE"
    )
    separator = "─" * len(header)
    print(header)
    print(separator)
    for record in page:
        print(
            f"{record.date:<10}  {record.grade:2}  {record.source:<8}  "
            f"{record.jd_src:<4}  {record.spons:<5}  "
            f"{record.cv:3}  {record.ofe:3}  {record.con:3}  "
            f"{record.company[:company_width]:<{company_width}}  {record.role[:role_width]}"
        )

    print(separator)
    print(f"  {len(page)} of {len(out)} matching  ({len(records)} total in tracker)")


if __name__ == "__main__":
    main()
