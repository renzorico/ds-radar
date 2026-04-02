"use client";

import { usePersona } from "@/lib/hooks";
import SignalFlow from "./teasers/SignalFlow";
import { motion } from "framer-motion";

const SUBLINES: Record<string, string> = {
  recruiter: "DS/ML Engineer · London · Open to opportunities",
  engineer: "Python · LLMs · Agentic pipelines · Production systems",
};

export default function Hero() {
  const { persona } = usePersona();

  return (
    <section className="relative min-h-screen flex items-center overflow-hidden bg-[#080808]">
      {/* Subtle grid backdrop */}
      <div
        className="absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage:
            "linear-gradient(#f0ebe0 1px, transparent 1px), linear-gradient(90deg, #f0ebe0 1px, transparent 1px)",
          backgroundSize: "40px 40px",
        }}
      />

      {/* Content */}
      <div className="relative z-10 w-full max-w-7xl mx-auto px-6 md:px-10 pt-28 pb-20">
        <div className="flex flex-col md:flex-row md:items-center md:gap-16 lg:gap-24">
          {/* Left: text */}
          <div className="flex-1 max-w-xl">
            {/* Eyebrow label */}
            <motion.p
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.1 }}
              className="font-['Geist_Mono',monospace] text-[10px] tracking-[0.25em] uppercase text-[#c49a52] mb-6"
            >
              Living Data Museum — Portfolio
            </motion.p>

            {/* Main statement */}
            <motion.h1
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, delay: 0.2 }}
              className="text-4xl md:text-5xl lg:text-6xl font-['Geist_Sans',sans-serif] font-semibold text-[#f0ebe0] leading-[1.08] tracking-[-0.03em] mb-6"
            >
              I build systems
              <br />
              that make data
              <br />
              <span className="text-[#c49a52]">useful.</span>
            </motion.h1>

            {/* Persona-aware subline */}
            <motion.p
              key={persona}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35 }}
              className="font-['Geist_Mono',monospace] text-sm text-[#8a8070] tracking-wide mb-10"
            >
              {SUBLINES[persona]}
            </motion.p>

            {/* CTA strip */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.6, delay: 0.5 }}
              className="flex items-center gap-6"
            >
              <a
                href="#work"
                className="font-['Geist_Mono',monospace] text-xs tracking-[0.15em] uppercase text-[#c49a52] border border-[#c49a52]/30 rounded px-4 py-2 hover:border-[#c49a52] hover:bg-[#c49a52]/5 transition-all duration-200"
              >
                View work
              </a>
              <a
                href="https://linkedin.com/in/renzorico"
                target="_blank"
                rel="noopener noreferrer"
                className="font-['Geist_Mono',monospace] text-xs tracking-[0.15em] uppercase text-[#5a5040] hover:text-[#8a8070] transition-colors duration-200"
              >
                LinkedIn ↗
              </a>
            </motion.div>
          </div>

          {/* Right: SignalFlow */}
          <motion.div
            initial={{ opacity: 0, scale: 0.96 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.8, delay: 0.4 }}
            className="flex-1 mt-16 md:mt-0 flex items-center justify-center"
          >
            <div className="w-full max-w-[460px] aspect-[2.3/1] relative">
              {/* Dim border frame */}
              <div className="absolute inset-0 rounded-lg border border-[#1e1e1e] bg-[#0a0a0a]" />
              <div className="absolute inset-0 p-6 flex items-center justify-center">
                <SignalFlow hero className="w-full h-full" />
              </div>
              {/* Label */}
              <div className="absolute bottom-3 right-4 font-['Geist_Mono',monospace] text-[9px] tracking-widest uppercase text-[#3a3020]">
                ds-radar pipeline
              </div>
            </div>
          </motion.div>
        </div>

        {/* Scroll indicator */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6, delay: 1.0 }}
          className="absolute bottom-8 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2"
        >
          <span className="font-['Geist_Mono',monospace] text-[9px] tracking-[0.2em] uppercase text-[#3a3020]">
            scroll
          </span>
          <motion.div
            animate={{ y: [0, 6, 0] }}
            transition={{ repeat: Infinity, duration: 1.8, ease: "easeInOut" }}
            className="w-px h-6 bg-gradient-to-b from-[#3a3020] to-transparent"
          />
        </motion.div>
      </div>
    </section>
  );
}
