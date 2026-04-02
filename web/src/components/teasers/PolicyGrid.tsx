"use client";

import { useState } from "react";
import { motion } from "framer-motion";

// 5 parties × 6 policy dimensions
// Colors: amber = strong align, blue-ish = partial, grey = neutral, rose = misalign
const PARTIES = ["PP", "PSOE", "VOX", "SUMAR", "PNV"];
const POLICIES = ["Economy", "Climate", "Housing", "Immigration", "Rights", "EU"];

// Alignment matrix: 0 = misalign (rose), 1 = neutral (grey), 2 = partial (dim amber), 3 = strong (amber)
const MATRIX: number[][] = [
  [2, 3, 0, 1, 2, 3],  // PP
  [2, 2, 2, 2, 3, 3],  // PSOE
  [3, 0, 1, 0, 0, 1],  // VOX
  [1, 3, 3, 3, 3, 2],  // SUMAR
  [2, 2, 2, 2, 2, 3],  // PNV
];

const DOT_COLOR: Record<number, string> = {
  0: "#4a1a1a",   // misalign — deep rose-grey
  1: "#2a2a2a",   // neutral — grey
  2: "#4a3010",   // partial — dim amber
  3: "#c49a52",   // strong — accent amber
};

const DOT_STROKE: Record<number, string> = {
  0: "#6a2a2a",
  1: "#3a3a3a",
  2: "#7a5e2a",
  3: "#d4aa62",
};

export default function PolicyGrid({
  className = "",
  hovered = false,
}: {
  className?: string;
  hovered?: boolean;
}) {
  const COLS = PARTIES.length;
  const ROWS = POLICIES.length;
  const DOT_R = 8;
  const GAP = 22;
  const LABEL_W = 58;
  const PAD = 12;
  const W = LABEL_W + PAD + COLS * GAP;
  const H = PAD + ROWS * GAP + 20;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      height="100%"
      className={className}
      aria-label="Policy alignment grid"
    >
      <defs>
        <style>{`
          .grid-label {
            font-family: 'Geist Mono', 'Courier New', monospace;
            font-size: 6.5px;
            fill: #8a8070;
            letter-spacing: 0.04em;
          }
          .col-label {
            font-family: 'Geist Mono', 'Courier New', monospace;
            font-size: 6px;
            fill: #5a5040;
            letter-spacing: 0.04em;
            text-anchor: middle;
          }
        `}</style>
      </defs>

      {/* Column headers (parties) */}
      {PARTIES.map((party, ci) => (
        <text
          key={party}
          x={LABEL_W + PAD + ci * GAP + DOT_R}
          y={PAD + 4}
          className="col-label"
        >
          {party}
        </text>
      ))}

      {/* Rows */}
      {POLICIES.map((policy, ri) => (
        <g key={policy}>
          {/* Row label */}
          <text
            x={0}
            y={PAD + 22 + ri * GAP + 3}
            className="grid-label"
            dominantBaseline="middle"
          >
            {policy}
          </text>

          {/* Dots */}
          {PARTIES.map((_, ci) => {
            const val = MATRIX[ci][ri];
            const cx = LABEL_W + PAD + ci * GAP + DOT_R;
            const cy = PAD + 22 + ri * GAP;
            const delay = (ri * COLS + ci) * 0.04;

            return (
              <motion.circle
                key={`${ri}-${ci}`}
                cx={cx}
                cy={cy}
                r={DOT_R - 2}
                fill={DOT_COLOR[val]}
                stroke={DOT_STROKE[val]}
                strokeWidth={0.8}
                initial={{ scale: 0, opacity: 0 }}
                animate={
                  hovered
                    ? { scale: 1, opacity: 1 }
                    : { scale: 0.6, opacity: 0.5 }
                }
                transition={{ delay, duration: 0.3, ease: "easeOut" }}
                style={{ transformOrigin: `${cx}px ${cy}px` }}
              />
            );
          })}
        </g>
      ))}
    </svg>
  );
}
