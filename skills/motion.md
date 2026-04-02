# SKILL: motion

## Purpose
Implement and tune animations for the Living Data Museum portfolio. Use when asked to add, adjust, or debug motion in components.

## Libraries in use

| Library | Role |
|---------|------|
| Framer Motion | Component entrance/exit animations, `whileHover`, persona transitions |
| CSS keyframes | SVG teaser animations (dashflow, nodepulse) |
| CSS transitions | Hover state color/opacity changes on dots, borders |
| `requestAnimationFrame` | TextFlow physics-style drift only |

## Animation inventory

### Page-level entrances (Hero.tsx)
- Eyebrow: `opacity 0→1`, `y: 8→0`, delay 0.1s
- H1: `opacity 0→1`, `y: 16→0`, delay 0.2s
- Subline (persona-aware): `opacity 0→1`, `y: 4→0`, 0.35s, key-remount on persona change
- CTA strip: `opacity 0→1`, delay 0.5s
- SignalFlow wrapper: `opacity 0→1`, `scale: 0.96→1`, delay 0.4s
- Scroll indicator: `opacity 0→1`, delay 1.0s; arrow: `y: 0→6→0` infinite 1.8s

### Card entrances (ExhibitSection + ProjectCard)
- Trigger: `useInView` with threshold 0.08, fires once
- Each card: `opacity 0→1`, `y: 30→0`, duration 0.55s, ease `[0.25, 0.1, 0.25, 1]`
- Stagger: `delay = index * 0.12` (0ms, 120ms, 240ms, 360ms)

### Persona note swap (ProjectCard)
- `motion.p` with `key={persona}` — React remounts on toggle
- `opacity 0→1`, duration 0.25s — fast, not distracting

### Project detail entrances (ProjectDetailClient)
- Header block: `opacity 0→1`, `y: 20→0`, 0.6s
- Teaser section: `opacity 0→1`, delay 0.2s
- Each content section: `opacity 0→1`, `y: 16→0`, delay 0.35 + i*0.1

## SVG teaser animation specs

### SignalFlow (CSS keyframes)
```css
@keyframes dashflow {
  from { stroke-dashoffset: 20; }
  to   { stroke-dashoffset: 0; }
}
@keyframes nodepulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50%       { opacity: 0.7; transform: scale(1.08); }
}
```
- Active node cycles via `setInterval(800ms)`
- Active edge: `animation: dashflow 0.35s linear infinite`
- Inactive edge: `animation: dashflow 0.6s linear infinite`
- Node pulse applies to active node only

### TextFlow (rAF physics)
- Each word drifts at its own `dx`/`dy` velocity (slow, 0.3 × multiplier per frame)
- Boundary bounce: negate velocity on edge hit
- Hover: converge toward `(W/2, H/2)` with `0.04` lerp factor
- State update throttled: every 2 frames (`frame % 2 === 0`)

### PolicyGrid (Framer Motion stagger)
- Each dot: `scale: 0→1`, `opacity: 0→1` on mount or hover
- Delay: `(rowIndex * COLS + colIndex) * 0.04`
- Hovered prop from parent card — animates from `{scale: 0.6, opacity: 0.5}` to `{scale: 1, opacity: 1}`

### UrbanDots (CSS transition + setInterval)
- Active cluster cycles every 1400ms via `setInterval`
- Dot fill/opacity change via `transition: fill 0.4s ease, opacity 0.4s ease`
- No Framer Motion needed — CSS handles the smooth transition

## Principles

1. **Entrance, not attention**: Animations reveal content, they don't perform. Default to 0.55s or less.
2. **Ease matters**: Use `[0.25, 0.1, 0.25, 1]` (slight deceleration) for spatial moves. `ease` for opacity.
3. **Stagger sparingly**: 4 cards × 120ms = 360ms total — acceptable. Don't stagger more than 6–8 items.
4. **Key remounting**: For persona-swap text, use `key={persona}` on `motion.p`. Simpler and more reliable than `AnimatePresence`.
5. **No layout animations**: Avoid `layout` prop and `AnimatePresence` for now — they add complexity for marginal gain.
6. **SVG stays CSS**: Keep teaser animations in CSS keyframes. Framer Motion adds bundle weight; CSS is zero-cost.
7. **RAF only when needed**: TextFlow needs physics-style per-frame updates. Everything else can use CSS or `setInterval`.
8. **Test at reduced motion**: Respect `prefers-reduced-motion` in future iteration by wrapping Framer Motion animations in a `useReducedMotion()` check.

## Debugging motion

If an animation doesn't run:
- Check `inView` state — `useInView` fires only once (observer disconnects after first intersection)
- Check `key` prop — persona toggle text needs `key={persona}` to remount
- Check SVG `transformOrigin` — must be set in `style` as `px` values, not `%`, for SVG elements
- Check `ssr: false` — teasers loaded with `next/dynamic` won't run on server, should not flash
