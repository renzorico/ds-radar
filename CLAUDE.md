# ds-radar
AI job search pipeline for DS/Analytics roles.

## Modes
- skills/scanner.md — discover job offers from target URLs
- skills/evaluator.md — score a single offer (10 dimensions, A–F grade)
- skills/pipeline.md — orchestrate: evaluate → pdf → track
- skills/pdf.md — generate ATS-optimised CV tailored per offer
- skills/tracker.md — append/update row in tracker.tsv
- skills/apply.md — Playwright form-filler for ATS portals
- scripts/oferta.py — deep 6-block strategic brief for one offer
- scripts/contacto.py — generate 3 LinkedIn outreach message variants

## Rules
- Always read the relevant skills/ file before starting any task
- Never read evals/ or applications/ unless explicitly asked
- One mode per session — do not touch unrelated files
- Run /compact when context reaches ~70% capacity
