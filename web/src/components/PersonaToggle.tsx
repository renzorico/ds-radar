"use client";

import { usePersona } from "@/lib/hooks";
import clsx from "clsx";

export default function PersonaToggle() {
  const { persona, setPersona } = usePersona();

  return (
    <div
      className="flex items-center gap-0 rounded-full border border-[#1e1e1e] bg-[#0c0c0c] p-0.5"
      role="group"
      aria-label="View mode"
    >
      <button
        onClick={() => setPersona("recruiter")}
        className={clsx(
          "rounded-full px-3 py-1 text-[10px] tracking-widest uppercase transition-all duration-200",
          "font-['Geist_Mono',monospace]",
          persona === "recruiter"
            ? "bg-[#c49a52] text-[#080808] font-semibold"
            : "text-[#5a5040] hover:text-[#8a8070]"
        )}
      >
        Recruiter
      </button>
      <button
        onClick={() => setPersona("engineer")}
        className={clsx(
          "rounded-full px-3 py-1 text-[10px] tracking-widest uppercase transition-all duration-200",
          "font-['Geist_Mono',monospace]",
          persona === "engineer"
            ? "bg-[#c49a52] text-[#080808] font-semibold"
            : "text-[#5a5040] hover:text-[#8a8070]"
        )}
      >
        Engineer
      </button>
    </div>
  );
}
