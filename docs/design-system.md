# Design System — Living Data Museum

Dark, editorial, premium. Each exhibit has its own interactive signature. No hero photo. No skill bars. No contact form.

## Color tokens

| Token         | Value     | Use                                      |
|---------------|-----------|------------------------------------------|
| `background`  | `#080808` | Page background                          |
| `surface`     | `#111111` | Cards, panels, nav backgrounds           |
| `border`      | `#1e1e1e` | All borders, dividers                    |
| `text-primary`| `#f0ebe0` | Headings, body copy                      |
| `text-secondary`| `#8a8070`| Secondary text, descriptions             |
| `accent`      | `#c49a52` | Active states, highlights, CTAs          |
| `accent-dim`  | `#7a5e2a` | Subdued accent, inactive nodes           |

## Typography

| Role          | Font              | Notes                              |
|---------------|-------------------|------------------------------------|
| Headings      | `Geist Mono`      | Labels, titles, metadata, tags     |
| Body          | `Geist Sans`      | Prose text, descriptions, taglines |
| Scale         | Tight editorial   | `tracking-tight` / `tracking-[-0.03em]` on display sizes |

Font variables are set in `layout.tsx` via `geist/font/sans` and `geist/font/mono`, exposed as CSS variables `--font-geist-sans` and `--font-geist-mono`.

## Spacing

- Consistent 6/10 px horizontal padding at mobile/desktop (`px-6 md:px-10`)
- Section padding: `py-24`
- Card internal padding: `p-6`
- Section header margin below: `mb-14`

## Component patterns

### Cards
- Background: `surface` (`#111111`)
- Border: `border` (`#1e1e1e`), transitions to `#2e2e2e` on hover
- Box shadow on hover: `0 8px 40px rgba(0,0,0,0.6)`
- Teaser visual: `h-44`, `bg-[#0a0a0a]`, bottom gradient vignette
- Border radius: `rounded-lg` (8px)

### Tags
- Font: Geist Mono, 9px, tracking-wider, uppercase
- Background: `#0a0a0a`, border `#1e1e1e`
- Color: `#4a4030`

### Persona toggle
- Pill shape, border `#1e1e1e`, background `#0c0c0c`
- Active: `bg-[#c49a52] text-[#080808]`
- Inactive: `text-[#5a5040]`

## Animation principles

- All entrance animations: `opacity 0→1`, `y: 30→0`, `duration ~0.55s`, `ease [0.25, 0.1, 0.25, 1]`
- Stagger between cards: 120ms
- Persona toggle text swap: `opacity 0→1`, `duration 0.25s` (key-based remount)
- SVG teasers: CSS keyframe animations only — no JS RAF unless required for physics (TextFlow)
- No GSAP. No scroll libraries. Framer Motion for component-level animations only.
- Keep animations subtle — they signal craft, not showmanship.

## SVG teaser conventions

Each teaser is a self-contained SVG component, no external assets.

| Component    | Technique                        | Interaction          |
|--------------|----------------------------------|----------------------|
| SignalFlow   | CSS `stroke-dashoffset` + keyframes | Auto-cycles active node |
| TextFlow     | `requestAnimationFrame` drift     | Hover converges to center |
| PolicyGrid   | Framer Motion `scale` stagger     | Hover triggers reveal |
| UrbanDots    | CSS `transition` + `setInterval` | Auto-cycles borough clusters |

All teasers use `viewBox` with `width/height="100%"` for responsive scaling.
