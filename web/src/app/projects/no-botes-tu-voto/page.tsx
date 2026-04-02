import type { Metadata } from "next";
import { projects } from "@/data/projects";
import ProjectDetailClient from "@/components/ProjectDetailClient";

export const metadata: Metadata = {
  title: "No botes tu voto — Renzo Rico",
  description:
    "A policy alignment tool for the 2023 Spanish elections. 12K users, zero ad spend.",
};

export default function NoBotesTuVotoPage() {
  const project = projects.find((p) => p.id === "no-botes-tu-voto")!;
  return <ProjectDetailClient project={project} />;
}
