import Navigation from "@/components/Navigation";
import Hero from "@/components/Hero";
import ExhibitSection from "@/components/ExhibitSection";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-[#080808]">
      <Navigation />
      <Hero />
      <ExhibitSection />
      <footer className="bg-[#080808] border-t border-[#1e1e1e] px-6 md:px-10 py-10">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div>
            <p className="font-['Geist_Mono',monospace] text-xs text-[#8a8070] tracking-wide">
              Renzo Rico
            </p>
            <p className="font-['Geist_Mono',monospace] text-[10px] text-[#3a3020] tracking-wide mt-1">
              London · Data Scientist · Available
            </p>
          </div>
          <div className="flex items-center gap-6">
            <a
              href="https://github.com/renzorico"
              target="_blank"
              rel="noopener noreferrer"
              className="font-['Geist_Mono',monospace] text-[10px] tracking-widest uppercase text-[#5a5040] hover:text-[#8a8070] transition-colors duration-200"
            >
              GitHub
            </a>
            <a
              href="https://linkedin.com/in/renzorico"
              target="_blank"
              rel="noopener noreferrer"
              className="font-['Geist_Mono',monospace] text-[10px] tracking-widest uppercase text-[#5a5040] hover:text-[#8a8070] transition-colors duration-200"
            >
              LinkedIn
            </a>
          </div>
        </div>
      </footer>
    </main>
  );
}
