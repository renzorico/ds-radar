"use client";

import { useInView } from "@/lib/hooks";
import { projects } from "@/data/projects";
import ProjectCard from "./ProjectCard";

export default function ExhibitSection() {
  const { ref, inView } = useInView({ threshold: 0.08 });

  return (
    <section id="work" className="bg-[#080808] py-24 px-6 md:px-10">
      <div className="max-w-7xl mx-auto">
        {/* Section header */}
        <div className="mb-14" ref={ref}>
          <p className="font-['Geist_Mono',monospace] text-[10px] tracking-[0.25em] uppercase text-[#c49a52] mb-3">
            Selected work
          </p>
          <h2 className="font-['Geist_Sans',sans-serif] text-2xl md:text-3xl font-semibold text-[#f0ebe0] tracking-[-0.02em]">
            Four exhibits. Four problems worth solving.
          </h2>
        </div>

        {/* Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-2 xl:grid-cols-4 gap-5">
          {projects.map((project, i) => (
            <ProjectCard
              key={project.id}
              project={project}
              delay={i * 0.12}
              inView={inView}
            />
          ))}
        </div>
      </div>
    </section>
  );
}
