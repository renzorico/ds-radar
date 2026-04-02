import type { Metadata } from "next";
import { projects } from "@/data/projects";
import ProjectDetailClient from "@/components/ProjectDetailClient";

export const metadata: Metadata = {
  title: "ds-radar — Renzo Rico",
  description:
    "An agentic pipeline that hunts, evaluates, and applies to jobs. Built with Playwright, Claude API, and Python.",
};

export default function DsRadarPage() {
  const project = projects.find((p) => p.id === "ds-radar")!;
  return <ProjectDetailClient project={project} />;
}
