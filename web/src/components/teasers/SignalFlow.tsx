"use client";

import { useEffect, useState } from "react";

const NODES = [
  { id: "scan", label: "SCAN", x: 20, y: 80 },
  { id: "filter", label: "FILTER", x: 110, y: 40 },
  { id: "evaluate", label: "EVAL", x: 110, y: 120 },
  { id: "grade", label: "GRADE", x: 210, y: 80 },
  { id: "cv", label: "CV", x: 300, y: 40 },
  { id: "apply", label: "APPLY", x: 300, y: 120 },
  { id: "track", label: "TRACK", x: 390, y: 80 },
];

const EDGES = [
  { from: "scan", to: "filter" },
  { from: "scan", to: "evaluate" },
  { from: "filter", to: "grade" },
  { from: "evaluate", to: "grade" },
  { from: "grade", to: "cv" },
  { from: "grade", to: "apply" },
  { from: "cv", to: "track" },
  { from: "apply", to: "track" },
];

const CYCLE = ["scan", "filter", "evaluate", "grade", "cv", "apply", "track"];

function getNode(id: string) {
  return NODES.find((n) => n.id === id)!;
}

interface SignalFlowProps {
  className?: string;
  /** If true, renders a slightly larger version for the hero section */
  hero?: boolean;
}

export default function SignalFlow({ className = "", hero = false }: SignalFlowProps) {
  const [activeIndex, setActiveIndex] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setActiveIndex((i) => (i + 1) % CYCLE.length);
    }, 800);
    return () => clearInterval(interval);
  }, []);

  const activeNode = CYCLE[activeIndex];
  const W = hero ? 460 : 420;
  const H = hero ? 180 : 160;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      height="100%"
      className={className}
      aria-label="ds-radar pipeline diagram"
    >
      <defs>
        <style>{`
          @keyframes dashflow {
            from { stroke-dashoffset: 20; }
            to   { stroke-dashoffset: 0; }
          }
          @keyframes nodepulse {
            0%   { opacity: 1; transform: scale(1); }
            50%  { opacity: 0.7; transform: scale(1.08); }
            100% { opacity: 1; transform: scale(1); }
          }
          .edge-line {
            stroke: #3a3020;
            stroke-width: 1.5;
            fill: none;
            stroke-dasharray: 5 3;
            animation: dashflow 0.6s linear infinite;
          }
          .edge-line-active {
            stroke: #c49a52;
            stroke-width: 1.5;
            fill: none;
            stroke-dasharray: 5 3;
            animation: dashflow 0.35s linear infinite;
          }
          .node-rect {
            fill: #111111;
            stroke: #2a2a2a;
            stroke-width: 1;
            rx: 4;
          }
          .node-rect-active {
            fill: #1a1200;
            stroke: #c49a52;
            stroke-width: 1.5;
            rx: 4;
            animation: nodepulse 0.8s ease-in-out infinite;
          }
          .node-label {
            font-family: 'Geist Mono', 'Courier New', monospace;
            font-size: 8px;
            fill: #8a8070;
            text-anchor: middle;
            dominant-baseline: middle;
            letter-spacing: 0.05em;
          }
          .node-label-active {
            font-family: 'Geist Mono', 'Courier New', monospace;
            font-size: 8px;
            fill: #c49a52;
            text-anchor: middle;
            dominant-baseline: middle;
            letter-spacing: 0.05em;
          }
        `}</style>
      </defs>

      {/* Edges */}
      {EDGES.map((edge) => {
        const from = getNode(edge.from);
        const to = getNode(edge.to);
        const isActive =
          edge.from === activeNode || edge.to === activeNode;
        return (
          <line
            key={`${edge.from}-${edge.to}`}
            x1={from.x + 28}
            y1={from.y + 10}
            x2={to.x}
            y2={to.y + 10}
            className={isActive ? "edge-line-active" : "edge-line"}
          />
        );
      })}

      {/* Nodes */}
      {NODES.map((node) => {
        const isActive = node.id === activeNode;
        const w = 52;
        const h = 22;
        return (
          <g key={node.id} style={{ transformOrigin: `${node.x + w / 2}px ${node.y + h / 2}px` }}>
            <rect
              x={node.x}
              y={node.y}
              width={w}
              height={h}
              rx={4}
              className={isActive ? "node-rect-active" : "node-rect"}
            />
            <text
              x={node.x + w / 2}
              y={node.y + h / 2}
              className={isActive ? "node-label-active" : "node-label"}
            >
              {node.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
