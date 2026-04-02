# SKILL: ui-builder

## Purpose
Build and iterate on the Living Data Museum portfolio site (`web/`). Use when asked to add pages, modify components, change design tokens, or add new project exhibits.

## Stack
- Next.js 15 App Router, React 19, TypeScript
- Tailwind CSS 3 (custom design tokens in `tailwind.config.ts`)
- Framer Motion (component animations only — no scroll libs)
- Geist Sans + Geist Mono (via `geist` npm package, set in `layout.tsx`)
- Pure SVG + CSS for data visualizations (no canvas, no D3, no chart libs)

## Key files

| File | Purpose |
|------|---------|
| `web/src/app/layout.tsx` | Root layout, fonts, metadata, PersonaProvider |
| `web/src/app/page.tsx` | Homepage composition |
| `web/src/app/globals.css` | CSS custom properties + Tailwind base |
| `web/src/data/projects.ts` | All project content — single source of truth |
| `web/src/lib/hooks.ts` | `useInView`, `PersonaContext`, `usePersona` |
| `web/src/components/PersonaProvider.tsx` | Context provider (client, wraps app) |
| `web/src/components/Navigation.tsx` | Sticky top nav |
| `web/src/components/Hero.tsx` | Full-screen opening section |
| `web/src/components/ExhibitSection.tsx` | Project grid with scroll reveal |
| `web/src/components/ProjectCard.tsx` | Individual exhibit card |
| `web/src/components/ProjectDetailClient.tsx` | Shared detail page layout |
| `web/src/components/teasers/SignalFlow.tsx` | ds-radar pipeline DAG |
| `web/src/components/teasers/TextFlow.tsx` | UN Speeches topic drift |
| `web/src/components/teasers/PolicyGrid.tsx` | No botes tu voto alignment matrix |
| `web/src/components/teasers/UrbanDots.tsx` | London Bible dot map |

## Design tokens (always use these, never invent new colors)

```
background:     #080808
surface:        #111111
border:         #1e1e1e
text-primary:   #f0ebe0
text-secondary: #8a8070
accent:         #c49a52
accent-dim:     #7a5e2a
```

## Rules

1. Read `docs/design-system.md` before touching any styling.
2. All colors must come from the token set above — no ad-hoc hex values.
3. New project data goes in `web/src/data/projects.ts` — never inline in components.
4. New teasers go in `web/src/components/teasers/` — must be self-contained SVG or canvas components with no external deps.
5. Do not add chart libraries (D3, Recharts, Nivo, etc.) — keep teasers pure SVG/CSS.
6. Do not add CSS-in-JS libraries — Tailwind + inline styles only.
7. Animations must remain subtle. If it draws attention to itself, dial it back.
8. Always lazy-load teasers with `next/dynamic` + `{ ssr: false }` in cards and detail pages.
9. `PersonaContext` is the only global state. Do not add Redux, Zustand, or any state manager.
10. Project detail pages use `ProjectDetailClient` — do not duplicate layout logic.

## Adding a new project

1. Add entry to `web/src/data/projects.ts` with all required fields including `detail`.
2. Create teaser component in `web/src/components/teasers/`.
3. Add the teaser type to `TeaserType` union in `projects.ts`.
4. Add the case to `Teaser()` in `ProjectCard.tsx` and `LargeTeaser()` in `ProjectDetailClient.tsx`.
5. Create `web/src/app/projects/<slug>/page.tsx` using the same pattern as existing pages.

## Dev commands

```bash
cd web
npm install
npm run dev        # http://localhost:3000
npm run build      # production build check
```
