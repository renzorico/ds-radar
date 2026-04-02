"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import dynamic from "next/dynamic";
import type { Project } from "@/data/projects";

const SignalFlow = dynamic(() => import("./teasers/SignalFlow"), { ssr: false });
const TextFlow = dynamic(() => import("./teasers/TextFlow"), { ssr: false });
const PolicyGrid = dynamic(() => import("./teasers/PolicyGrid"), { ssr: false });
const UrbanDots = dynamic(() => import("./teasers/UrbanDots"), { ssr: false });

function LargeTeaser({ type }: { type: Project["teaser"] }) {
  switch (type) {
    case "SignalFlow":
      return <SignalFlow hero className="w-full h-full" />;
    case "TextFlow":
      return <TextFlow className="w-full h-full" />;
    case "PolicyGrid":
      return <PolicyGrid className="w-full h-full" hovered />;
    case "UrbanDots":
      return <UrbanDots className="w-full h-full" />;
  }
}

interface Props {
  project: Project;
}

export default function ProjectDetailClient({ project }: Props) {
  return (
    <main className="min-h-screen bg-[#080808] text-[#f0ebe0]">
      {/* Nav bar */}
      <nav className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 py-4 md:px-10 border-b border-[#1e1e1e] bg-[#080808]/95 backdrop-blur-sm">
        <Link
          href="/"
          className="font-['Geist_Mono',monospace] text-xs tracking-[0.2em] uppercase text-[#8a8070] hover:text-[#c49a52] transition-colors duration-200 flex items-center gap-2"
        >
          <span className="text-[#3a3020]">←</span> The Field
        </Link>
        <span className="font-['Geist_Mono',monospace] text-[10px] tracking-[0.2em] uppercase text-[#3a3020]">
          {project.index} / 04
        </span>
      </nav>

      {/* Hero */}
      <section className="pt-28 pb-16 px-6 md:px-10 max-w-5xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
        >
          <p className="font-['Geist_Mono',monospace] text-[10px] tracking-[0.25em] uppercase text-[#c49a52] mb-4">
            {project.index} — Exhibit
          </p>
          <h1 className="font-['Geist_Sans',sans-serif] text-3xl md:text-5xl font-semibold text-[#f0ebe0] tracking-[-0.03em] mb-4 leading-tight">
            {project.title}
          </h1>
          <p className="font-['Geist_Sans',sans-serif] text-lg text-[#8a8070] leading-relaxed max-w-2xl">
            {project.tagline}
          </p>
        </motion.div>
      </section>

      {/* Large teaser */}
      <motion.section
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.7, delay: 0.2 }}
        className="px-6 md:px-10 max-w-5xl mx-auto mb-16"
      >
        <div className="w-full h-56 md:h-72 bg-[#0a0a0a] border border-[#1e1e1e] rounded-lg overflow-hidden flex items-center justify-center p-8">
          <LargeTeaser type={project.teaser} />
        </div>
      </motion.section>

      {/* Metadata strip */}
      <section className="px-6 md:px-10 max-w-5xl mx-auto mb-16">
        <div className="flex flex-wrap gap-6 pb-8 border-b border-[#1e1e1e]">
          <div>
            <p className="font-['Geist_Mono',monospace] text-[9px] tracking-[0.2em] uppercase text-[#3a3020] mb-1">
              Year
            </p>
            <p className="font-['Geist_Mono',monospace] text-sm text-[#8a8070]">
              {project.detail.year}
            </p>
          </div>
          <div>
            <p className="font-['Geist_Mono',monospace] text-[9px] tracking-[0.2em] uppercase text-[#3a3020] mb-1">
              Role
            </p>
            <p className="font-['Geist_Mono',monospace] text-sm text-[#8a8070]">
              {project.detail.role}
            </p>
          </div>
          <div>
            <p className="font-['Geist_Mono',monospace] text-[9px] tracking-[0.2em] uppercase text-[#3a3020] mb-1">
              Stack
            </p>
            <div className="flex flex-wrap gap-1.5 mt-1">
              {project.tags.map((tag) => (
                <span
                  key={tag}
                  className="font-['Geist_Mono',monospace] text-[9px] tracking-wider uppercase px-2 py-0.5 rounded border border-[#1e1e1e] text-[#4a4030] bg-[#0a0a0a]"
                >
                  {tag}
                </span>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Content sections */}
      <section className="px-6 md:px-10 max-w-3xl mx-auto pb-32 space-y-12">
        {[
          { label: "The problem", body: project.detail.problem },
          { label: "The approach", body: project.detail.approach },
          { label: "The result", body: project.detail.result },
        ].map(({ label, body }, i) => (
          <motion.div
            key={label}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.35 + i * 0.1 }}
          >
            <h2 className="font-['Geist_Mono',monospace] text-[10px] tracking-[0.25em] uppercase text-[#c49a52] mb-4">
              {label}
            </h2>
            <p className="font-['Geist_Sans',sans-serif] text-base text-[#8a8070] leading-[1.75]">
              {body}
            </p>
          </motion.div>
        ))}
      </section>

      {/* Footer nav */}
      <div className="border-t border-[#1e1e1e] px-6 md:px-10 py-8">
        <div className="max-w-5xl mx-auto">
          <Link
            href="/"
            className="font-['Geist_Mono',monospace] text-xs tracking-[0.15em] uppercase text-[#5a5040] hover:text-[#c49a52] transition-colors duration-200"
          >
            ← The Field
          </Link>
        </div>
      </div>
    </main>
  );
}
