# ds-radar

`ds-radar` is an automated job scanning, evaluation, and tracking pipeline. It ingests job feeds, evaluates listings, records decisions in tabular state, and keeps the generated eval markdowns linked back to the tracker.

High-level flow: ingest CSV feeds -> evaluate listings -> update tracker state -> record eval history.

## Single Source Of Truth

The live system is built around a small set of canonical files and directories:

- `tracker.tsv` - master job/application table and the main operational state.
- `scan-history.tsv` - append-style log of evaluation runs and eval link history.
- `evals/` - canonical store for eval markdown files.
- `csv-inbox/processed/` - provenance store for already ingested CSV feeds.
- `source-history.tsv` - source-level history, when present and used by the current pipeline.

Key invariants:

- Every non-empty `eval_path` in `tracker.tsv` points into `evals/`.
- Every non-empty `eval_path` in `scan-history.tsv` points into `evals/`.
- `pdf_path` in `tracker.tsv` is currently empty for all rows; generated CV PDFs are treated as ephemeral cache, not canonical history.
- No live data or code reads from `archive/` or `backups/`.

Notes:

- `archive/` contains historical snapshots only. It must never be used as a live data source for repairs, migrations, or canonical state reconstruction.
- `cv/` is a cache of generated CV PDFs. If an `applications/` directory is used in another snapshot or branch, treat it the same way: cache only, safe to regenerate from canonical tracker and eval state.

## Repository Structure

- `tracker.tsv` - main job/application table (SSOT).
- `scan-history.tsv` - evaluation run history (SSOT).
- `source-history.tsv` - source ingestion history when the current pipeline uses it.
- `evals/` - canonical eval markdowns (SSOT).
- `csv-inbox/` - CSV intake area for new job feed exports.
- `csv-inbox/processed/` - consumed CSV feeds kept for provenance (SSOT for ingestion history).
- `scripts/` - pipeline and maintenance scripts, including scan, eval, repair, verify, PDF generation, and dashboard helpers.
- `profile/` - configuration and prompt/persona assets used by the scanning and evaluation workflows.
- `archive/` - historical snapshots such as `archive/2026-04-24/`; never read as live state.
- `cv/` - optional cache of generated CV PDFs; safe to recreate.
- `CLAUDE.md` - repo-local AI assistant notes and working instructions.
- `artifacts-index.jsonl` - artifact metadata index used by parts of the pipeline.
- `scan-queue.txt` - queue/input helper for scan runs when used.

## How The Pipeline Works

1. Place new job feeds in `csv-inbox/incoming/` if you use a staging subdirectory, or directly in `csv-inbox/` in the current repo layout.
2. Run the scan/eval pipeline from `scripts/`, typically via the main orchestration entrypoint such as `scripts/pipeline.py`, or the narrower helpers like `scripts/scan.py` and `scripts/evaluate.py`.
3. The pipeline updates `tracker.tsv` with statuses, grades, notes, and `eval_path` links into `evals/`.
4. Every eval run is recorded in `scan-history.tsv`.
5. An optional CV generation step can write PDFs into `cv/` or `applications/`, but those files are cache outputs rather than canonical state.

## Data Integrity & Repair

- `scripts/repair_state.py` only consults live canonical locations: `tracker.tsv`, `scan-history.tsv`, `evals/`, live PDF cache paths, and the current repo state.
- `scripts/repair_state.py` explicitly ignores archival prefixes: `archive/`, `backups/`, `backup_20260407/`, `evals_backup/`, and `applications_backup/`.
- `scripts/repair_state.py` never migrates data from archived snapshots back into live TSVs or canonical directories.
- `scripts/verify_pipeline.py` validates live data consistency and may suggest archiving or deleting orphaned files manually when it finds leftovers outside the canonical graph.
- No script should ever read from `archive/` to repair, extend, or reconstruct live state.
- All repairs must be derived from the canonical TSVs plus `evals/`, with PDF caches treated as optional secondary artifacts.

## Contributing / Development Notes

- Treat `tracker.tsv`, `scan-history.tsv`, and `evals/` as the only canonical history.
- Treat `csv-inbox/processed/` as provenance for consumed feeds, not a place to rebuild canonical tracker state from scratch.
- Treat `archive/` as read-only historical context.
- Treat `cv/` or `applications/` as cache directories that can be cleared or regenerated.
- New code must not reintroduce logic that reads historical backups to repair or mutate live state.
