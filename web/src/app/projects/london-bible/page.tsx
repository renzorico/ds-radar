import type { Metadata } from "next";
import { projects } from "@/data/projects";
import ProjectDetailClient from "@/components/ProjectDetailClient";

export const metadata: Metadata = {
  title: "The London Bible — Renzo Rico",
  description:
    "A data-driven guide to London's 33 boroughs. 15+ open datasets aggregated into one tool.",
};

export default function LondonBiblePage() {
  const project = projects.find((p) => p.id === "london-bible")!;
  return <ProjectDetailClient project={project} />;
}
