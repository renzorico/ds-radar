"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import Link from "next/link";
import { useRouter } from "next/navigation";

// ── SVG layout (viewBox 900 × 540) ───────────────────────────────────────────
const VW = 900;
const VH = 540;
const ML = 82;  // left margin  (room for Y-axis labels)
const MR = 44;  // right margin
const MT = 44;  // top margin
const MB = 78;  // bottom margin (room for X-axis labels)
const PW = VW - ML - MR; // plot width  = 774
const PH = VH - MT - MB; // plot height = 418

/** Map normalised [0,1] coords to SVG pixels. yNorm=1 → top of plot. */
function toSvg(xN: number, yN: number) {
  return {
    x: ML + xN * PW,
    y: VH - MB - yN * PH,
  };
}

// ── Project data ──────────────────────────────────────────────────────────────
const DOTS = [
  {
    id: "ds-radar",
    title: "ds-radar",
    href: "/projects/ds-radar",
    xN: 0.12,
    yN: 0.88,
    scope: "individual",
    agency: "high",
    tags: ["python", "llm", "agentic"],
    summary: "An agentic pipeline that hunts, evaluates, and applies to jobs.",
  },
  {
    id: "no-botes-tu-voto",
    title: "No botes tu voto",
    href: "/projects/no-botes-tu-voto",
    xN: 0.40,
    yN: 0.78,
    scope: "civic",
    agency: "high",
    tags: ["nlp", "civic-tech", "python"],
    summary: "Policy alignment tool that served 12K voters in the 2023 Spanish election.",
  },
  {
    id: "london-bible",
    title: "The London Bible",
    href: "/projects/london-bible",
    xN: 0.70,
    yN: 0.30,
    scope: "city-wide",
    agency: "low",
    tags: ["geospatial", "open-data", "pandas"],
    summary: "A data-driven guide to London's 33 boroughs.",
  },
  {
    id: "un-speeches",
    title: "UN Speeches",
    href: "/projects/un-speeches",
    xN: 0.90,
    yN: 0.17,
    scope: "global",
    agency: "low",
    tags: ["nlp", "bertopic", "python"],
    summary: "Topic modeling 70 years of UN General Assembly debate.",
  },
] as const;

type Dot = (typeof DOTS)[number];

// ── Floating italic annotations ───────────────────────────────────────────────
const ANNOTATIONS = [
  { xN: 0.18, yN: 0.60, lines: ["automation as", "a research output"], anchor: "start" as const },
  { xN: 0.56, yN: 0.91, lines: ["where analysis", "becomes action"], anchor: "middle" as const },
  { xN: 0.83, yN: 0.49, lines: ["understanding", "at scale"], anchor: "end" as const },
];

const GRID_TICKS = [0.2, 0.4, 0.6, 0.8];

// ── Tooltip ───────────────────────────────────────────────────────────────────
function FieldTooltip({
  dot,
  containerRef,
}: {
  dot: Dot | null;
  containerRef: React.RefObject<HTMLDivElement | null>;
}) {
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);

  useEffect(() => {
    if (!dot || !containerRef.current) {
      setPos(null);
      return;
    }
    const cw = containerRef.current.offsetWidth;
    const ch = containerRef.current.offsetHeight;
    // SVG fills container exactly (matching aspect ratio), so scale is uniform
    const scale = cw / VW;

    const { x, y } = toSvg(dot.xN, dot.yN);
    const dotPxX = x * scale;
    const dotPxY = y * scale;

    // Flip horizontally if dot is in right ~60% of field
    const flipX = dot.xN > 0.56;
    // Flip vertically if dot is in upper ~60% of field (show tooltip below)
    const flipY = dot.yN > 0.60;

    setPos({
      left: flipX ? dotPxX - 216 : dotPxX + 22,
      top: flipY ? dotPxY + 18 : dotPxY - 158,
    });
  }, [dot, containerRef]);

  return (
    <AnimatePresence>
      {dot && pos && (
        <motion.div
          key={dot.id}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 6 }}
          transition={{ duration: 0.14, ease: "easeOut" }}
          className="absolute z-20 w-52 pointer-events-none select-none"
          style={{ left: pos.left, top: pos.top }}
          aria-hidden="true"
        >
          <div className="bg-[#111111] border border-[#252525] p-4">
            <p className="font-['Geist_Mono',monospace] text-[10px] tracking-[0.2em] uppercase text-[#c49a52] mb-1.5">
              {dot.title}
            </p>
            <p className="font-['Geist_Sans',sans-serif] text-[11px] text-[#8a8070] leading-relaxed mb-3">
              {dot.summary}
            </p>
            <div className="flex flex-wrap gap-1 mb-3">
              {dot.tags.map((tag) => (
                <span
                  key={tag}
                  className="font-['Geist_Mono',monospace] text-[8px] uppercase tracking-wider px-1.5 py-0.5 border border-[#1e1e1e] text-[#4a4030] bg-[#0a0a0a]"
                >
                  {tag}
                </span>
              ))}
            </div>
            <p className="font-['Geist_Mono',monospace] text-[8px] tracking-[0.15em] uppercase text-[#c49a52]/50">
              View project ↗
            </p>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function TheField() {
  const router = useRouter();
  const prefersReducedMotion = useReducedMotion();
  const containerRef = useRef<HTMLDivElement>(null);

  const [hovered, setHovered] = useState<Dot | null>(null);
  const [pulseIdx, setPulseIdx] = useState<number | null>(null);

  // ── Idle pulse cycle (starts 4 s after last interaction) ─────────────────
  const idleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pulseCycleRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPulse = useCallback(() => {
    if (pulseCycleRef.current) {
      clearInterval(pulseCycleRef.current);
      pulseCycleRef.current = null;
    }
    setPulseIdx(null);
  }, []);

  const scheduleIdlePulse = useCallback(() => {
    if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
    stopPulse();
    if (prefersReducedMotion) return;
    idleTimerRef.current = setTimeout(() => {
      let i = 0;
      pulseCycleRef.current = setInterval(() => {
        setPulseIdx(i % DOTS.length);
        i++;
      }, 900);
    }, 4000);
  }, [stopPulse, prefersReducedMotion]);

  useEffect(() => {
    scheduleIdlePulse();
    return () => {
      if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
      stopPulse();
    };
  }, [scheduleIdlePulse, stopPulse]);

  const handleInteraction = useCallback(() => {
    stopPulse();
    scheduleIdlePulse();
  }, [stopPulse, scheduleIdlePulse]);

  // ── SVG entrance animation config ─────────────────────────────────────────
  const fade = (delay: number) =>
    prefersReducedMotion
      ? {}
      : { initial: { opacity: 0 }, animate: { opacity: 1 }, transition: { duration: 0.5, delay } };

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-[#080808] text-[#f0ebe0] flex flex-col">

      {/* ── Navigation ──────────────────────────────────────────────────── */}
      <nav className="fixed top-0 left-0 right-0 z-50 flex items-start justify-between px-6 md:px-10 pt-6">
        <div>
          <p className="font-['Geist_Mono',monospace] text-[10px] tracking-[0.2em] uppercase text-[#b0a898]">
            Renzo Rico — Data Scientist, London
          </p>
          <p className="font-['Geist_Mono',monospace] text-[9px] tracking-[0.1em] text-[#3a3020] mt-1 italic">
            Fig. 1 — Four projects mapped by scope and agency
          </p>
        </div>
        <div className="flex items-center gap-5 pt-0.5">
          <Link
            href="/about"
            className="font-['Geist_Mono',monospace] text-[9px] tracking-[0.2em] uppercase text-[#4a4030] hover:text-[#8a8070] transition-colors duration-200"
          >
            About
          </Link>
          <a
            href="https://github.com/renzorico"
            target="_blank"
            rel="noopener noreferrer"
            className="font-['Geist_Mono',monospace] text-[9px] tracking-[0.2em] uppercase text-[#4a4030] hover:text-[#8a8070] transition-colors duration-200"
          >
            GitHub ↗
          </a>
        </div>
      </nav>

      {/* ── Scatter plot — desktop ───────────────────────────────────────── */}
      <div className="hidden sm:flex flex-1 items-center justify-center px-6 md:px-10 pt-20 pb-6">
        <div
          ref={containerRef}
          className="relative w-full max-w-5xl"
          style={{ aspectRatio: `${VW} / ${VH}` }}
          onMouseMove={handleInteraction}
          onPointerMove={handleInteraction}
        >
          {/* SVG canvas */}
          <svg
            viewBox={`0 0 ${VW} ${VH}`}
            className="absolute inset-0 w-full h-full"
            aria-label="Scatter plot: four projects positioned by scope (x) and agency (y)"
          >
            <defs>
              <marker
                id="tf-arrowhead"
                markerWidth="7"
                markerHeight="5"
                refX="7"
                refY="2.5"
                orient="auto"
              >
                <polygon points="0 0, 7 2.5, 0 5" fill="#2a2a2a" />
              </marker>

              <style>{`
                @keyframes tf-pulse {
                  0%   { r: 5.5; opacity: 0.5; }
                  40%  { r: 9;   opacity: 0.9; }
                  100% { r: 14;  opacity: 0;   }
                }
                .tf-pulse-ring {
                  fill: none;
                  stroke: #c49a52;
                  stroke-width: 1;
                  animation: tf-pulse 1.1s ease-out forwards;
                  transform-box: fill-box;
                  transform-origin: center;
                }
              `}</style>
            </defs>

            {/* Graph-paper grid */}
            <motion.g {...fade(0.1)}>
              {GRID_TICKS.map((t) => {
                const gx = toSvg(t, 0).x;
                const gy = toSvg(0, t).y;
                return (
                  <g key={t}>
                    <line x1={gx} y1={MT} x2={gx} y2={VH - MB} stroke="#131313" strokeWidth="1" />
                    <line x1={ML} y1={gy} x2={VW - MR} y2={gy} stroke="#131313" strokeWidth="1" />
                  </g>
                );
              })}
            </motion.g>

            {/* Axes */}
            <motion.g {...fade(0.25)}>
              {/* X axis */}
              <line
                x1={ML} y1={VH - MB}
                x2={VW - MR + 6} y2={VH - MB}
                stroke="#282828" strokeWidth="1.5"
                markerEnd="url(#tf-arrowhead)"
              />
              {/* Y axis */}
              <line
                x1={ML} y1={VH - MB}
                x2={ML} y2={MT - 6}
                stroke="#282828" strokeWidth="1.5"
                markerEnd="url(#tf-arrowhead)"
              />
            </motion.g>

            {/* Axis labels */}
            <motion.g
              fontFamily="'Geist Mono', 'Courier New', monospace"
              fontSize="8"
              letterSpacing="0.15em"
              {...fade(0.55)}
            >
              {/* X endpoints */}
              <text x={ML} y={VH - MB + 20} fill="#2e2818" textAnchor="start" style={{ textTransform: "uppercase" }}>
                individual
              </text>
              <text x={VW - MR} y={VH - MB + 20} fill="#2e2818" textAnchor="end" style={{ textTransform: "uppercase" }}>
                societal
              </text>
              {/* X title */}
              <text x={ML + PW / 2} y={VH - 12} fill="#221e16" textAnchor="middle" letterSpacing="0.3em" style={{ textTransform: "uppercase" }}>
                scope
              </text>

              {/* Y endpoints */}
              <text x={ML - 10} y={VH - MB + 2} fill="#2e2818" textAnchor="end" style={{ textTransform: "uppercase" }}>
                describing
              </text>
              <text x={ML - 10} y={MT + 6} fill="#2e2818" textAnchor="end" style={{ textTransform: "uppercase" }}>
                changing
              </text>
              {/* Y title (rotated) */}
              <text
                x={16}
                y={MT + PH / 2}
                fill="#221e16"
                textAnchor="middle"
                letterSpacing="0.3em"
                style={{ textTransform: "uppercase" }}
                transform={`rotate(-90, 16, ${MT + PH / 2})`}
              >
                agency
              </text>
            </motion.g>

            {/* Floating field annotations */}
            {ANNOTATIONS.map((ann, i) => {
              const p = toSvg(ann.xN, ann.yN);
              return (
                <motion.g key={i} {...fade(1.0 + i * 0.12)}>
                  {ann.lines.map((line, li) => (
                    <text
                      key={li}
                      x={p.x}
                      y={p.y + li * 13}
                      fill="#1e1a12"
                      fontSize="8.5"
                      fontFamily="'Geist Mono', 'Courier New', monospace"
                      fontStyle="italic"
                      textAnchor={ann.anchor}
                      letterSpacing="0.04em"
                    >
                      {line}
                    </text>
                  ))}
                </motion.g>
              );
            })}

            {/* Dots */}
            {DOTS.map((dot, i) => {
              const { x, y } = toSvg(dot.xN, dot.yN);
              const isHovered = hovered?.id === dot.id;
              const isPulsing = !prefersReducedMotion && pulseIdx !== null && DOTS[pulseIdx]?.id === dot.id;

              return (
                <motion.g
                  key={dot.id}
                  {...(prefersReducedMotion
                    ? {}
                    : {
                        initial: { opacity: 0 },
                        animate: { opacity: 1 },
                        transition: { duration: 0.35, delay: 0.6 + i * 0.14 },
                      })}
                  onMouseEnter={() => {
                    handleInteraction();
                    setHovered(dot);
                  }}
                  onMouseLeave={() => setHovered(null)}
                  onClick={() => router.push(dot.href)}
                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") router.push(dot.href); }}
                  tabIndex={0}
                  role="button"
                  aria-label={`${dot.title}: ${dot.summary}`}
                  style={{ cursor: "pointer", outline: "none" }}
                >
                  {/* Idle pulse ring (animated, rerenders on pulseIdx change) */}
                  {isPulsing && (
                    <circle
                      key={`pulse-${dot.id}-${pulseIdx}`}
                      cx={x}
                      cy={y}
                      r={5.5}
                      className="tf-pulse-ring"
                    />
                  )}

                  {/* Hover ring */}
                  <circle
                    cx={x}
                    cy={y}
                    r={12}
                    fill="none"
                    stroke="#c49a52"
                    strokeWidth="1"
                    style={{
                      opacity: isHovered ? 0.35 : 0,
                      transition: "opacity 0.15s ease",
                    }}
                  />

                  {/* Main dot */}
                  <circle
                    cx={x}
                    cy={y}
                    r={isHovered ? 7 : 5.5}
                    fill={isHovered ? "#c49a52" : "#6b5022"}
                    style={{ transition: "r 0.15s ease, fill 0.15s ease" }}
                  />
                </motion.g>
              );
            })}
          </svg>

          {/* HTML tooltip overlay */}
          <FieldTooltip dot={hovered} containerRef={containerRef} />
        </div>
      </div>

      {/* ── Mobile fallback — coordinate-tagged card list ────────────────── */}
      <div className="sm:hidden flex flex-col px-5 pt-24 pb-16 gap-3">
        <p className="font-['Geist_Mono',monospace] text-[8px] tracking-[0.3em] uppercase text-[#2e2818] mb-1">
          4 projects
        </p>
        {DOTS.map((dot, i) => (
          <motion.div
            key={dot.id}
            initial={prefersReducedMotion ? {} : { opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, delay: i * 0.1 }}
          >
            <Link href={dot.href}>
              <div className="border border-[#1e1e1e] bg-[#0a0a0a] p-5 hover:border-[#c49a52]/30 transition-colors duration-200">
                <p className="font-['Geist_Mono',monospace] text-[10px] tracking-[0.2em] uppercase text-[#c49a52] mb-1.5">
                  {dot.title}
                </p>
                <p className="font-['Geist_Sans',sans-serif] text-sm text-[#8a8070] leading-relaxed mb-3">
                  {dot.summary}
                </p>
                <div className="flex gap-4 font-['Geist_Mono',monospace] text-[8px] uppercase tracking-wider text-[#3a3020]">
                  <span>scope: {dot.scope}</span>
                  <span>agency: {dot.agency}</span>
                </div>
              </div>
            </Link>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
