# ds-radar — Claude instructions
AI job search pipeline for DS/Analytics roles (London-focused, Renzo Rico).

## What this repo does
- Scan target ATS boards for DS/Analytics/ML roles
- Score offers on 10 dimensions (0–5 → A–F)
- Generate tailored CV + outreach
- Track pipeline in TSV files

## Files Claude should care about
- scripts/: scan.py, evaluate.py, pipeline.py, generate_pdf.py, oferta.py, contacto.py
- skills/: one SKILL.md per mode (scanner, evaluator, pipeline, pdf, tracker, apply)
- profile/: cv.md, profile.yaml, target-companies.yaml
- state files: scan-queue.txt, scan-history.tsv, tracker.tsv
- outputs: evals/, applications/

## Modes (one per session)
- /scanner   → use skills/scanner.md to discover & enqueue new roles
- /evaluator → use skills/evaluator.md to score ONE URL (10 dims, A–F)
- /pipeline  → use skills/pipeline.md to chain: queue → evaluate → pdf → tracker
- /pdf       → use skills/pdf.md to improve CV tailoring & PDF generation
- /tracker   → use skills/tracker.md to maintain tracker.tsv
- /apply     → use skills/apply.md to automate ATS forms
- /oferta    → scripts/oferta.py for deep 6-block brief of ONE offer
- /contacto  → scripts/contacto.py for 3 LinkedIn outreach variants

## Rules of engagement
- Before coding in a mode, skim its SKILL.md and existing script(s)
- Treat `evaluate_url()` + `parse_eval_file()` as the single scoring API
- Do NOT touch evals/ or applications/ unless I explicitly ask
- Preserve TSV schemas for scan-history.tsv and tracker.tsv
- Favour small, testable changes over big refactors
- Keep prompts and new skills compact; avoid repetition and boilerplate
- When context feels ~70% full, propose a /compact plan instead of repeating history
