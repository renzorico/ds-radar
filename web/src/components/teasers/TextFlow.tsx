"use client";

import { useEffect, useRef, useState } from "react";

const TOPICS = [
  { label: "SECURITY", x: 48, y: 28, dx: 1.2, dy: 0.6 },
  { label: "CLIMATE", x: 180, y: 20, dx: -0.8, dy: 1.0 },
  { label: "TRADE", x: 240, y: 55, dx: 0.5, dy: -0.9 },
  { label: "HUMAN RIGHTS", x: 30, y: 75, dx: 0.9, dy: 0.4 },
  { label: "SOVEREIGNTY", x: 140, y: 85, dx: -0.6, dy: -0.7 },
  { label: "NUCLEAR", x: 220, y: 110, dx: -1.1, dy: 0.5 },
  { label: "POVERTY", x: 60, y: 120, dx: 0.7, dy: -0.8 },
  { label: "TERRORISM", x: 170, y: 140, dx: 1.0, dy: 0.3 },
  { label: "DIPLOMACY", x: 100, y: 50, dx: -0.4, dy: 1.1 },
  { label: "SANCTIONS", x: 260, y: 80, dx: -0.9, dy: -0.6 },
  { label: "REFUGEES", x: 80, y: 155, dx: 0.6, dy: -0.5 },
  { label: "DEVELOPMENT", x: 190, y: 160, dx: -0.7, dy: 0.8 },
];

interface Pos {
  x: number;
  y: number;
}

export default function TextFlow({ className = "" }: { className?: string }) {
  const [positions, setPositions] = useState<Pos[]>(
    TOPICS.map((t) => ({ x: t.x, y: t.y }))
  );
  const hovered = useRef(false);
  const animRef = useRef<number>(0);
  const posRef = useRef<Pos[]>(TOPICS.map((t) => ({ x: t.x, y: t.y })));

  useEffect(() => {
    let frame = 0;
    const W = 300;
    const H = 180;

    function tick() {
      frame++;
      posRef.current = posRef.current.map((p, i) => {
        if (hovered.current) {
          // Converge toward center
          const cx = W / 2;
          const cy = H / 2;
          return {
            x: p.x + (cx - p.x) * 0.04,
            y: p.y + (cy - p.y) * 0.04,
          };
        } else {
          // Slow drift with bounce
          let nx = p.x + TOPICS[i].dx * 0.3;
          let ny = p.y + TOPICS[i].dy * 0.3;
          if (nx < 0 || nx > W - 60) TOPICS[i].dx *= -1;
          if (ny < 0 || ny > H - 12) TOPICS[i].dy *= -1;
          nx = Math.max(0, Math.min(W - 60, nx));
          ny = Math.max(0, Math.min(H - 12, ny));
          return { x: nx, y: ny };
        }
      });

      if (frame % 2 === 0) {
        setPositions([...posRef.current]);
      }

      animRef.current = requestAnimationFrame(tick);
    }

    animRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animRef.current);
  }, []);

  return (
    <svg
      viewBox="0 0 300 180"
      width="100%"
      height="100%"
      className={className}
      aria-label="UN Speeches topic visualization"
      onMouseEnter={() => { hovered.current = true; }}
      onMouseLeave={() => { hovered.current = false; }}
    >
      <defs>
        <style>{`
          .topic-label {
            font-family: 'Geist Mono', 'Courier New', monospace;
            font-size: 7.5px;
            fill: #8a8070;
            letter-spacing: 0.06em;
            transition: fill 0.3s;
          }
          .topic-label:hover {
            fill: #c49a52;
          }
        `}</style>
      </defs>

      {TOPICS.map((topic, i) => (
        <text
          key={topic.label}
          x={positions[i]?.x ?? topic.x}
          y={positions[i]?.y ?? topic.y}
          className="topic-label"
          opacity={0.6 + (i % 3) * 0.13}
        >
          {topic.label}
        </text>
      ))}
    </svg>
  );
}
