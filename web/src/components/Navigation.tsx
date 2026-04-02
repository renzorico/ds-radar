"use client";

import Link from "next/link";
import PersonaToggle from "./PersonaToggle";

export default function Navigation() {
  return (
    <nav
      className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 py-4 md:px-10"
      style={{
        background:
          "linear-gradient(to bottom, rgba(8,8,8,0.95) 0%, rgba(8,8,8,0) 100%)",
        backdropFilter: "blur(0px)",
      }}
    >
      {/* Logo / wordmark */}
      <Link
        href="/"
        className="font-['Geist_Mono',monospace] text-xs tracking-[0.2em] uppercase text-[#8a8070] hover:text-[#c49a52] transition-colors duration-200"
      >
        Renzo Rico
      </Link>

      {/* Right side */}
      <div className="flex items-center gap-4">
        <PersonaToggle />
        <a
          href="https://github.com/renzorico"
          target="_blank"
          rel="noopener noreferrer"
          className="hidden md:block font-['Geist_Mono',monospace] text-[10px] tracking-widest uppercase text-[#5a5040] hover:text-[#8a8070] transition-colors duration-200"
        >
          GitHub ↗
        </a>
      </div>
    </nav>
  );
}
