"use client";

import { useEffect, useRef, useState } from "react";

const COLS = 22;
const ROWS = 13;
const DOT = 5;
const GAP = 2;
const STEP = DOT + GAP;
const W = COLS * STEP + GAP;
const H = ROWS * STEP + GAP;

const CLUSTERS = [
  { name: "Central", cols: [8, 9, 10, 11], rows: [4, 5, 6, 7] },
  { name: "East", cols: [14, 15, 16, 17], rows: [3, 4, 5, 6, 7] },
  { name: "South", cols: [7, 8, 9, 10, 11, 12], rows: [8, 9, 10] },
  { name: "North", cols: [6, 7, 8, 9, 10], rows: [1, 2, 3] },
  { name: "West", cols: [2, 3, 4, 5], rows: [4, 5, 6, 7, 8] },
];

function isInCluster(col: number, row: number, clusterIdx: number) {
  const c = CLUSTERS[clusterIdx];
  return c.cols.includes(col) && c.rows.includes(row);
}

export default function UrbanDots({ className = "" }: { className?: string }) {
  const [activeCluster, setActiveCluster] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    timerRef.current = setInterval(() => {
      setActiveCluster((i) => (i + 1) % CLUSTERS.length);
    }, 1400);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  const dots: { col: number; row: number; active: boolean }[] = [];
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      dots.push({ col: c, row: r, active: isInCluster(c, r, activeCluster) });
    }
  }

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      height="100%"
      className={className}
      aria-label="London borough dot map"
    >
      <defs>
        <style>{`
          .dot-base {
            transition: fill 0.4s ease, opacity 0.4s ease;
          }
        `}</style>
      </defs>

      {dots.map(({ col, row, active }) => (
        <rect
          key={`${col}-${row}`}
          x={col * STEP + GAP}
          y={row * STEP + GAP}
          width={DOT}
          height={DOT}
          rx={1}
          className="dot-base"
          fill={active ? "#c49a52" : "#1e1e1e"}
          opacity={active ? 0.9 : 0.5}
        />
      ))}

      <text
        x={W / 2}
        y={H - 2}
        textAnchor="middle"
        dominantBaseline="auto"
        style={{
          fontFamily: "'Geist Mono', 'Courier New', monospace",
          fontSize: "7px",
          fill: "#c49a52",
          letterSpacing: "0.08em",
          opacity: 0.7,
        }}
      >
        {CLUSTERS[activeCluster].name.toUpperCase()} LONDON
      </text>
    </svg>
  );
}
