# ds-radar

`ds-radar` is a focused job evaluation and CV generation pipeline. It evaluates listings, writes scored markdown reports, and generates tailored CV artifacts from those reports.

High-level flow: evaluate listing -> write `evals/*.md` -> generate tailored CV markdown/PDF in `applications/`.

## Single Source Of Truth

The live system is built around a small set of canonical files and directories:

- `scan-history.tsv` - append-style log of evaluation runs and eval link history.
- `evals/` - canonical store for eval markdown files.
- `source-history.tsv` - source-level history, when present and used by the current pipeline.
- `profile/profile.yaml` - verified candidate facts used by scoring and CV tailoring.
- `applications/` - generated CV markdown/PDF outputs.

Key invariants:

- Every non-empty `eval_path` in `scan-history.tsv` points into `evals/`.
- No live data or code reads from `archive/` or `backups/`.

Notes:

- `archive/` contains historical snapshots only. It must never be used as a live data source for repairs, migrations, or canonical state reconstruction.
- `cv/` is a cache of generated CV PDFs. If an `applications/` directory is used in another snapshot or branch, treat it the same way: cache only, safe to regenerate from canonical tracker and eval state.

## Repository Structure

- `scan-history.tsv` - evaluation run history (SSOT).
- `source-history.tsv` - source ingestion history when the current pipeline uses it.
- `evals/` - canonical eval markdowns (SSOT).
- `applications/` - generated CV markdown/PDF outputs.
- `scripts/` - active pipeline scripts and direct dependencies.
- `profile/` - verified candidate facts and targeting configuration.
- `archive/` - historical snapshots such as `archive/2026-04-24/`; never read as live state.
- `CLAUDE.md` - repo-local AI assistant notes and working instructions.
- `artifacts-index.jsonl` - artifact metadata index used by parts of the pipeline.

## How The Pipeline Works

1. Run `python scripts/evaluate.py <job_url>` to score a job and write an eval report under `evals/`.
2. Run `python scripts/generate_pdf.py <eval_path>` to rewrite the CV for that eval and render outputs under `applications/`.
3. Both scripts accept `--model <model_name>`. If omitted, they use `MODEL_OVERRIDE` from `.env`, then fall back to `claude-haiku-4-5-20251001`.
4. Every evaluation run is recorded in `scan-history.tsv`.

## Data Integrity & Repair

- No script should ever read from `archive/` to repair, extend, or reconstruct live state.
- All tailoring facts must come from `profile/profile.yaml` plus the canonical eval markdown.
- Generated PDFs are cache outputs; the markdown eval and CV files remain the durable artifacts.

## Contributing / Development Notes

- Treat `scan-history.tsv` and `evals/` as the canonical evaluation history.
- Treat `archive/` as read-only historical context.
- Treat `applications/` as generated output that can be regenerated from `evals/`.
- New code must not reintroduce logic that reads historical backups to repair or mutate live state.

## Setup

1. Create `.env` from `.env.example`.
2. Set `ANTHROPIC_API_KEY` for the default Haiku pipeline.
3. Optionally set `MODEL_OVERRIDE` or pass `--model` per run.
