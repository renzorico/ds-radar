# Navigation — Living Data Museum

## Route structure

```
/                          → Homepage (Hero + ExhibitSection + Footer)
/projects/ds-radar         → ds-radar detail page
/projects/un-speeches      → UN Speeches detail page
/projects/no-botes-tu-voto → No botes tu voto detail page
/projects/london-bible     → The London Bible detail page
```

## Navigation component (`Navigation.tsx`)

Sticky, fixed to top. Two elements:
- **Left**: `Renzo Rico` wordmark — links to `/`
- **Right**: `PersonaToggle` pill + GitHub link (hidden on mobile)

Background: gradient from `rgba(8,8,8,0.95)` at top to transparent — avoids harsh edge while keeping nav readable over hero content.

No hamburger menu. On mobile, the GitHub link is hidden (`hidden md:block`). The PersonaToggle remains visible on all sizes.

## PersonaToggle (`PersonaToggle.tsx`)

A pill-shaped button group with two states:
- `RECRUITER` — shows metrics and business outcomes in card notes
- `ENGINEER` — shows technical stack and implementation details in card notes

State lives in `PersonaContext` (provided by `PersonaProvider` in `layout.tsx`). Updates propagate instantly to all `ProjectCard` components via `usePersona()` hook.

No persistence (localStorage not used). Resets to `recruiter` on page refresh.

## Project detail navigation

Each detail page has:
- Fixed top nav with `← Renzo Rico` back link and position indicator (`01 / 04`, etc.)
- Footer link: `← Back to all exhibits`

No prev/next between projects — return to homepage to browse. Keeps nav intent clear.

## Scroll behavior

Homepage uses native `scroll-behavior: smooth` (set in `globals.css`). The "View work" CTA in the Hero links to `#work` (the `ExhibitSection` section id).

No scroll-jacking. No sticky sidebars. The scroll indicator in the Hero is decorative only (animated down-arrow).

## Accessibility

- All interactive elements have `:focus-visible` outlines (1px amber, `outline-offset: 2px`)
- SVG teasers have `aria-label` attributes
- Navigation uses semantic `<nav>` elements
- Color contrast: text-secondary (`#8a8070`) on background (`#080808`) meets WCAG AA for large text
