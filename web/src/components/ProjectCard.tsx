"use client";

import { useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { usePersona } from "@/lib/hooks";
import type { Project } from "@/data/projects";
import dynamic from "next/dynamic";

// Lazy-load teasers to avoid SSR issues with animations
const SignalFlow = dynamic(() => import("./teasers/SignalFlow"), { ssr: false });
const TextFlow = dynamic(() => import("./teasers/TextFlow"), { ssr: false });
const PolicyGrid = dynamic(() => import("./teasers/PolicyGrid"), { ssr: false });
const UrbanDots = dynamic(() => import("./teasers/UrbanDots"), { ssr: false });

function Teaser({
  type,
  hovered,
}: {
  type: Project["teaser"];
  hovered: boolean;
}) {
  switch (type) {
    case "SignalFlow":
      return <SignalFlow className="w-full h-full" />;
    case "TextFlow":
      return <TextFlow className="w-full h-full" />;
    case "PolicyGrid":
      return <PolicyGrid className="w-full h-full" hovered={hovered} />;
    case "UrbanDots":
      return <UrbanDots className="w-full h-full" />;
  }
}

interface ProjectCardProps {
  project: Project;
  delay?: number;
  inView: boolean;
}

export default function ProjectCard({
  project,
  delay = 0,
  inView,
}: ProjectCardProps) {
  const { persona } = usePersona();
  const [hovered, setHovered] = useState(false);

  const note =
    persona === "recruiter" ? project.recruiterNote : project.engineerNote;

  return (
    <motion.div
      initial={{ opacity: 0, y: 30 }}
      animate={inView ? { opacity: 1, y: 0 } : { opacity: 0, y: 30 }}
      transition={{ duration: 0.55, delay, ease: [0.25, 0.1, 0.25, 1] }}
    >
      <Link
        href={project.href}
        className="group block"
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      >
        <div
          className="rounded-lg border border-[#1e1e1e] bg-[#111111] overflow-hidden transition-all duration-300"
          style={{
            borderColor: hovered ? "#2e2e2e" : "#1e1e1e",
            boxShadow: hovered
              ? "0 0 0 1px #1e1e1e, 0 8px 40px rgba(0,0,0,0.6)"
              : "none",
          }}
        >
          {/* Visual teaser */}
          <div className="relative w-full h-44 bg-[#0a0a0a] border-b border-[#1e1e1e] overflow-hidden flex items-center justify-center p-4">
            <div className="w-full h-full">
              <Teaser type={project.teaser} hovered={hovered} />
            </div>
            {/* Subtle vignette */}
            <div className="absolute inset-0 pointer-events-none bg-gradient-to-t from-[#111111]/60 to-transparent" />
          </div>

          {/* Content */}
          <div className="p-6">
            {/* Index + title */}
            <div className="flex items-baseline gap-3 mb-3">
              <span className="font-['Geist_Mono',monospace] text-[10px] text-[#3a3020] tracking-widest">
                {project.index}
              </span>
              <h3 className="font-['Geist_Mono',monospace] text-base font-medium text-[#f0ebe0] tracking-tight">
                {project.title}
              </h3>
            </div>

            {/* Divider */}
            <div className="h-px w-full bg-[#1e1e1e] mb-3" />

            {/* Tagline */}
            <p className="font-['Geist_Sans',sans-serif] text-sm text-[#8a8070] leading-relaxed mb-4">
              {project.tagline}
            </p>

            {/* Persona note */}
            <motion.p
              key={persona}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.25 }}
              className="font-['Geist_Mono',monospace] text-[10px] text-[#5a5040] tracking-wide mb-5 leading-relaxed"
            >
              {note}
            </motion.p>

            {/* Tags + arrow */}
            <div className="flex items-center justify-between gap-2">
              <div className="flex flex-wrap gap-1.5">
                {project.tags.map((tag) => (
                  <span
                    key={tag}
                    className="font-['Geist_Mono',monospace] text-[9px] tracking-wider uppercase px-2 py-0.5 rounded border border-[#1e1e1e] text-[#4a4030] bg-[#0a0a0a]"
                  >
                    {tag}
                  </span>
                ))}
              </div>
              <span
                className="font-['Geist_Mono',monospace] text-[10px] text-[#c49a52] tracking-wider whitespace-nowrap transition-transform duration-200"
                style={{
                  transform: hovered ? "translateX(4px)" : "translateX(0)",
                }}
              >
                View →
              </span>
            </div>
          </div>
        </div>
      </Link>
    </motion.div>
  );
}
